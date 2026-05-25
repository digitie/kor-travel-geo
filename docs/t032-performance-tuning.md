# T-032 성능 튜닝 기록

본 문서는 PR #18 merge 이후 진행한 T-032 성능 튜닝의 구현 범위, 축소 검증 결과, 남은 후속 작업을 기록한다. 2026-05-25 사용자 지시에 따라 이번 PR의 반복 검증은 **세종특별자치시 + 경상남도 데이터 1회**로 제한한다. 전국 full test, 여러 번의 trial-and-error 반복, MV refresh/swap 전체 벤치마크는 후속 PR에서 별도로 수행한다.

## 범위

이번 PR에서 다루는 병목은 다음 세 가지다.

| 항목 | 기존 문제 | 변경 |
|------|-----------|------|
| C4 data-quality export | `c4_distance_samples.csv`와 `c4_distance_buckets.csv`가 같은 nearest polygon 거리 계산을 각각 수행 | `_kraddr_dq_c4_distances` 임시 테이블을 한 번 만들고 두 CSV가 재사용 |
| C6/C7 data-quality export | sample CSV와 region summary CSV가 같은 `ST_Covers` mismatch scan을 각각 수행 | `_kraddr_dq_c6_violations`, `_kraddr_dq_c7_violations` 임시 테이블을 한 번 만들고 재사용 |
| 다중 시도 SHP 적재 | `load shp-all`/`load all-sidos --shp-root`가 시도별 적재 후 통계 갱신을 반복할 수 있음 | 마지막 시도 적재 뒤에만 `ANALYZE` 1회 수행 |

부가로 다음 안정화도 포함한다.

- C4/C6/C7 정합성 SQL에 `MATERIALIZED` CTE를 명시해 PostgreSQL planner가 고비용 CTE를 샘플/통계 경로에서 중복 평가하지 않게 한다.
- `idx_juso_text_resolve` 인덱스를 추가해 `resolve_text_geometry_links()`와 C1/C2/C4/C5 natural key 조인의 기준 컬럼을 맞춘다.
- `resolve_text_geometry_links()`는 대량 후처리 단계이므로 transaction-local `statement_timeout` 기본값을 30분으로 둔다. 일반 조회 경로의 5초 timeout 정책은 유지한다.

## 검증 환경

| 항목 | 값 |
|------|----|
| 실행일 | 2026-05-25 |
| OS | WSL2 Linux `6.6.87.2-microsoft-standard-WSL2` |
| CPU | 16 logical cores |
| 메모리 | 29GiB total, 실행 전 available 약 27GiB |
| ext4 여유 공간 | `/dev/sdd` 1007G 중 791G available |
| NTFS 데이터 공간 | `/mnt/f` 932G 중 267G available |
| Docker DB | `kraddr-geo-t027-db-1`, `postgis/postgis:16-3.5`, host port `15432` |
| PostgreSQL | 16.9 + PostGIS image |
| DB 설정 | `shared_buffers=512MB`, `work_mem=64MB`, `maintenance_work_mem=256MB`, `random_page_cost=1.1` |
| 테스트 DB | `kraddr_geo_t032` |
| 데이터 경로 | `/mnt/f/dev/python-kraddr-geo/data/juso` |

## 입력 데이터

전체 전국 데이터 대신 다음 두 시도만 사용했다.

| 자료 | 경로 |
|------|------|
| 도로명주소 한글 | `202603_도로명주소 한글_전체분/rnaddrkor_sejong.txt`, `rnaddrkor_gyeongnam.txt` |
| 위치정보요약DB | `202604_위치정보요약DB_전체분.zip`에서 `entrc_sejong.txt`, `entrc_gyeongnam.txt`만 추출 |
| 내비게이션용DB | `202604_내비게이션용DB_전체분/match_build_sejong.txt`, `match_build_gyeongnam.txt`, `match_rs_entrc.txt` |
| 전자지도 SHP | `도로명주소 전자지도/세종특별자치시`, `도로명주소 전자지도/경상남도` |

## 실행 명령

```bash
PGPASSWORD=addr createdb -h localhost -p 15432 -U addr kraddr_geo_t032

KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t032 \
  .venv/bin/kraddr-geo init-db

/usr/bin/time -v env \
  KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t032 \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/kraddr-geo load all-sidos \
    --juso artifacts/t032-two-sido/input/juso \
    --locsum artifacts/t032-two-sido/input/locsum \
    --navi artifacts/t032-two-sido/input/navi \
    --shp-root artifacts/t032-two-sido/input/shp \
    --yyyymm 202604 \
    --no-refresh \
    --allow-consistency-error
```

첫 실행은 SHP 적재까지 완료한 뒤 `resolve_text_geometry_links()`에서 기본 5초 statement timeout에 걸려 실패했다. 이는 이번 PR에서 후처리 전용 transaction-local timeout을 추가하는 직접 근거가 됐다.

```text
Elapsed wall clock: 2:01:13
Maximum resident set size: 163,672 KB
Exit status: 1
실패 지점: UPDATE tl_locsum_entrc ... FROM tl_juso_text ...
오류: canceling statement due to statement timeout
```

패치 후 같은 DB에서 후처리 단계만 재실행했다.

```bash
/usr/bin/time -v env \
  KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t032 \
  KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000 \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/python - <<'PY'
import asyncio
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.loaders.postload import resolve_text_geometry_links

async def main() -> None:
    async with AsyncAddressClient() as client:
        assert client.engine is not None
        await resolve_text_geometry_links(client.engine)

asyncio.run(main())
print("postload links resolved")
PY
```

```text
Elapsed wall clock: 0:28.53
Maximum resident set size: 77,156 KB
Exit status: 0
```

## 적재 결과

```text
tl_juso_text          685,521
tl_locsum_entrc       683,823
tl_navi_buld_centroid 1,324,697
tl_navi_entrc          12,830
tl_scco_ctprvn              2
tl_scco_sig                23
tl_scco_emd               579
tl_scco_li              1,949
tl_kodis_bas            2,493
tl_sprd_manage         92,928
tl_sprd_intrvl      1,960,217
tl_sprd_rw            160,660
tl_spbd_buld_polygon 1,324,177
```

SHP 적재 중 `TL_SPRD_RW.shp`, `TL_SPBD_BULD.shp`에서 winding order 자동 보정 경고가 나왔다. GDAL이 자동 보정했고 적재는 계속 진행됐다. 성능 관점에서는 두 시도 축소 검증에서도 `TL_SPRD_INTRVL`과 `TL_SPBD_BULD` append 시간이 전체 실행을 지배했다. 특히 GDAL 로그와 `pg_stat_activity`에서는 `PG_USE_COPY=YES` 설정에도 일부 구간이 INSERT 형태로 관측되어, 후속 PR에서 GDAL PostgreSQL COPY 강제 여부와 `TL_SPRD_INTRVL` 전용 텍스트/COPY 로더 가능성을 다시 검토한다.

## T-032 쿼리 검증

변경된 data-quality export 경로를 같은 DB에서 1회 실행했다.

```bash
/usr/bin/time -v env \
  KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t032 \
  KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000 \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/kraddr-geo validate data-quality-samples \
    --cases C4,C6,C7 \
    --limit 5 \
    --output-dir artifacts/t032-two-sido/data-quality
```

```text
Elapsed wall clock: 0:11.25
Maximum resident set size: 79,884 KB
Exit status: 0
생성 파일: C4 2개, C6 2개, C7 2개
```

C4 bucket 결과는 다음과 같았다.

| bucket | rows | min_m | avg_m | max_m |
|--------|------|-------|-------|-------|
| 0-50 | 196,940 | 0.0 | 0.72 | 49.88 |
| 50-100 | 188 | 50.12 | 68.21 | 99.17 |
| 100-500 | 23 | 100.56 | 142.61 | 277.27 |
| 500+ | 2 | 538.16 | 647.87 | 757.58 |

정합성 C4/C6/C7도 같은 DB에서 1회 실행했다.

```bash
/usr/bin/time -v env \
  KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t032 \
  KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000 \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/kraddr-geo validate consistency \
    --cases C4,C6,C7 \
    --scope t032-two-sido
```

```text
Elapsed wall clock: 0:14.88
Maximum resident set size: 80,204 KB
Exit status: 0
severity_max: ERROR
```

| case | count | 주요 metric |
|------|-------|-------------|
| C4 | 213 | `over_500m=2`, `p95_m=4.01`, `p99_m=14.91` |
| C6 | 77 | `outside_polygon=77`, `missing_polygon=0` |
| C7 | 851 | `outside_polygon=851`, `missing_polygon=0` |

`severity_max=ERROR`는 데이터 품질 게이트의 기대 동작이다. 이번 PR은 정합성 오류를 보정하지 않고, 동일 오류를 더 적은 중복 스캔으로 산출하는 성능/운영 안정화에 초점을 둔다.

## 단위/정적 검증

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/pytest \
  tests/unit/test_data_quality_exports.py \
  tests/unit/test_consistency_sql.py \
  tests/unit/test_shp_loader_gdal.py \
  tests/unit/test_cli_contract.py \
  tests/unit/test_infra_engine_pnu_sql.py \
  tests/unit/test_alembic_migrations.py \
  tests/unit/test_postload_mv.py \
  -q
```

결과: `38 passed in 1.04s`.

추가로 전체 테스트와 정적 검사를 실행했다.

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/pytest -q
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/ruff check .
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/mypy src/kraddr/geo
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/lint-imports
git diff --check
```

결과:

- `pytest -q` → 101 passed, 7 skipped in 3.30s
- `ruff check .` → 통과
- `mypy src/kraddr/geo` → Success: no issues found in 69 source files
- `lint-imports` → Layered architecture KEPT
- `git diff --check` → 통과

## 후속

- 전국 full-load 전체 실행은 이번 PR에서 수행하지 않았다.
- MV refresh/swap 벤치마크도 이번 PR에서 수행하지 않았다.
- `TL_SPRD_INTRVL`과 `TL_SPBD_BULD`의 GDAL append 병목은 후속 PR에서 별도 측정한다.
- C2 export는 이번 T-032 최적화 범위에서 제외했다. C2는 공간 조인보다 natural key 존재성 검사가 중심이라 C4/C6/C7 대비 우선순위가 낮다.
