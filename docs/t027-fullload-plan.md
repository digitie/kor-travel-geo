# T-027: Docker 기반 실 데이터 전체 적재 검증 계획

## 상태

- 상태: 2026-05-29 최종 클린 재적재 완료. 새 Docker compose project와 빈 `pgdata` 경로에서 전체 적재, optional direct 출입구/SPPN, daily delta, MV swap, C1~C10, smoke, data-quality export, DB size snapshot까지 확인했다.
- 대상 PR: T-027 최종 클린 적재 보강 PR
- 실행 대상 데이터: `F:\dev\python-kraddr-geo\data\juso` (`/mnt/f/dev/python-kraddr-geo/data/juso`)
- 원칙: Docker PostGIS에 새 볼륨을 만들고, 로컬 개발 DB나 기존 운영성 데이터는 건드리지 않는다.

## 목적

`data/juso` 아래 실제 행안부 주소 데이터를 Docker PostGIS에 전량 적재해 다음을 확인한다.

1. 텍스트 정본 3종(도로명주소 한글, 위치정보요약DB, 내비게이션용DB)이 전국 단위로 적재되는지 확인한다.
2. 도로명주소 전자지도 SHP 보조 레이어 9종이 전국 시도별로 적재되는지 확인한다.
3. `tl_locsum_entrc`와 `tl_navi_entrc`의 `bd_mgt_sn` 후처리 링크가 전국 데이터에서 충분히 해소되는지 확인한다.
4. `mv_geocode_target`을 full-load 이후 swap 전략으로 재생성할 수 있는지 확인한다.
5. C1~C10 정합성 검증과 geocode/reverse/search/zipcode smoke test를 통과하는지 확인한다.
6. 아직 로더가 없는 `data/juso` 하위 자료는 "누락"이 아니라 "미지원 입력"으로 명시해 후속 태스크로 분리한다. T-039 이후 `도로명주소 출입구 정보`는 선택 지원으로 이동했으므로 기본 full-load와 별도 검증을 구분한다.

## 현재 데이터 인벤토리

2026-05-24 기준 로컬 경로를 읽어 확인한 결과, `data/juso` 전체 용량은 약 28GB다. 2026-05-29 최종 클린 재적재에서는 NTFS 원본을 WSL ext4 작업 사본 `/home/digitie/kraddr-geo-data`로 복사한 뒤 Docker PostGIS(`localhost:15434`)에 새 compose project/pgdata를 만들어 처음부터 적재했다.

| 경로 | 크기/형태 | 현재 로더 지원 | 이번 T-027 처리 |
|------|-----------|----------------|-----------------|
| `202603_도로명주소 한글_전체분/` | `rnaddrkor_*.txt` 17개 + `jibun_rnaddrkor_*.txt` 17개 | 지원 | `rnaddrkor_*.txt`는 `tl_juso_text`, `jibun_*`은 T-038 이후 `tl_juso_parcel_link` 1:N 테이블로 적재 |
| `202603_도로명주소 한글_전체분.zip` | 원본 ZIP | 간접 지원 | 압축 해제본을 적재 대상으로 사용 |
| `full/202603_도로명주소 한글_전체분.zip` | 중복 원본 ZIP | 간접 지원 | 중복 보관으로 기록. 기본 적재 대상 아님 |
| `202604_위치정보요약DB_전체분.zip` | `entrc_*.txt` ZIP member | 지원 | `tl_locsum_entrc` 적재 |
| `202604_내비게이션용DB_전체분/` | `match_build_*.txt`, `match_rs_entrc.txt`, `match_jibun_*.txt` | 부분 지원 | `match_build_*`, `match_rs_entrc.txt` 적재. `match_jibun_*`은 현재 로더 미지원 |
| `202604_내비게이션용DB_전체분.7z` | 원본 압축 | 간접 지원 | 압축 해제본을 적재 대상으로 사용 |
| `도로명주소 전자지도/` | 시도별 SHP directory 17개 | 지원 | SHP 9개 보조 레이어 적재 |
| `daily/*.zip` | 일변동 ZIP 20260401~20260506 | 지원 | `DAILY_JUSO_ZIP`이 지정되면 `TH_SGCO_RNADR_MST.TXT`를 `tl_juso_text`에, `TH_SGCO_RNADR_LNBR.TXT`를 `tl_juso_parcel_link`에 증분 적용한다. 2026-05-29 최종 재적재에서는 `20260401_dailyjusukrdata.zip`을 적용했다 |
| `건물군 내 상세주소 동 도형/` | 시도별 ZIP | 분석 지원 | T-041 이후 `scripts/compare_extra_shape_layers.py`로 전자지도 건물과 비교 가능. serving loader는 보류 |
| `구역의 도형/` | 별도 도형 묶음 | 선택 지원 | T-041 이후 중복 5개 레이어와 추가 2개 레이어를 비교 가능. T-042 이후 `TL_SPPN_MAKAREA`는 `tl_sppn_makarea` optional source로 적재 가능하며, source set plan에서는 `sppn_makarea_load` child로 연결됨 |
| `도로명주소 건물 도형/` | 별도 건물 도형 묶음 | 분석 지원 | T-040 이후 `scripts/compare_building_shape_bundle.py`로 전자지도와 natural key overlap 비교 가능. serving loader는 보류 |
| `도로명주소 출입구 정보/` | 별도 출입구 정보 | 선택 지원 | T-039 이후 `RNENTDATA_2605_*.txt`를 `tl_roadaddr_entrc`에 적재 가능. 기본 full-load child에는 자동 포함하지 않음 |

## 중요한 실행 전 보정

초안은 단일 `YYYYMM=202604`를 모든 자료에 적용했지만, 현재 로컬 데이터는 자료별 기준월이 다르다.

| 자료 | 실제 기준월 | 환경변수 |
|------|-------------|----------|
| 도로명주소 한글 전체분 | `202603` | `JUSO_YYYYMM=202603` |
| 위치정보요약DB 전체분 | `202604` | `LOCSUM_YYYYMM=202604` |
| 내비게이션용DB 전체분 | `202604` | `NAVI_YYYYMM=202604` |
| 도로명주소 출입구 정보 | `202605` | `ROADADDR_ENTRANCE_YYYYMM=202605` |
| `TL_SPPN_MAKAREA` 구역의 도형 | `202605` | `SPPN_MAKAREA_YYYYMM=202605` |

정합성 C10은 기준월 불일치를 감지한다. T-027 최종 클린 적재 보강 이후 C10은 `load_manifest`만 보지 않고 각 테이블 row-level `source_yyyymm`을 우선 집계한다. 현재 로컬 조합은 `202603`, `202604`, `202605` 3종 기준월이 섞이므로 C10은 `WARN`, `distinct_months=3`으로 남는다. ADR-029/T-045 이후에는 이 조합을 `source_set.yyyymm_by_kind`로 명시하고, 혼합 기준월임을 운영자가 확인한 경우 `mixed_yyyymm_acknowledged=true`로 남긴다. 확인 기록이 없는 혼합 기준월은 batch/swap gate에서 실수 가능성이 있으므로 막고, 확인된 혼합 기준월은 C10 `INFO` 또는 `WARN`과 note로 남긴다. "동월 전체분" 검증이 필요하면 도로명주소 한글 전체분도 `202604` 또는 direct 출입구와 같은 `202605` 자료로 맞춰 받아 재실행해야 한다.

T-039 direct 출입구는 선택 적재로만 실행하고 기본 full-load batch 6종에는 넣지 않는다. 2026-05-27 검증에서 `tl_roadaddr_entrc=202605`를 `tl_juso_text=202603` 세트에 serving 1순위로 섞으면 C4/C6/C7 오류가 크게 증가했다. 따라서 현재 MV/정합성 serving CTE는 `tl_locsum_entrc`를 먼저 쓰고, direct 출입구는 `source_yyyymm`이 `tl_juso_text.source_yyyymm`와 같은 기준월일 때만 fallback 후보로 사용한다.

ADR-030/T-046 구현 이후 운영 전환용 최종 클린 적재가 성공하면 `serving-ready` 백업 생성을 권장한다. 이 백업은 `pg_dump -Fd --jobs` directory dump를 `tar.zst` artifact로 묶은 형태여야 하며, 복원 검증은 먼저 대구광역시 부분 DB에서 완료한 뒤 전국 DB에는 보존용 백업 생성만 수행한다. 2026-05-29 T-027 PR 범위는 "빈 DB 재적재와 정상성 확인"까지로 한정했고, 전국 DB 백업 생성은 운영 보존 절차로 별도 실행한다.

## 실행 금지선

다음 조건이 충족되기 전에는 전체 적재를 실행하지 않는다.

- PR #13 계획 문서와 스크립트 리뷰 완료
- Docker 컨테이너가 새 볼륨을 사용한다는 점 확인
- `docker compose down -v`가 기존 운영 DB 볼륨을 삭제하지 않는다는 점 확인
- `PLAN_ONLY=1 bash scripts/fullload_test.sh`로 경로 preflight만 먼저 확인
- 전체 적재 로그를 남길 경로 확정: `artifacts/fullload/YYYYMMDD_HHMMSS/`
- 실패 시 중단 기준과 재개 기준 합의

## Docker 환경

`docker-compose.yml`은 PostGIS 16 계열 컨테이너 하나를 띄운다.

| 항목 | 값 |
|------|----|
| 서비스 | `db` |
| 이미지 | `postgis/postgis:16-3.5` |
| DB | `kraddr_geo` |
| 사용자/비밀번호 | `addr` / `addr` |
| 외부 포트 | `localhost:${KRADDR_GEO_DB_PORT:-5432}` |
| 기본 DSN | `postgresql+psycopg://addr:addr@localhost:${KRADDR_GEO_DB_PORT:-5432}/kraddr_geo` |
| 볼륨 | compose project 전용 `pgdata` |

운영성 데이터와 섞이지 않게 별도 project name을 권장한다.
로컬의 다른 PostgreSQL이 5432 포트를 이미 쓰는 경우에는 `KRADDR_GEO_DB_PORT=15432`처럼 별도 포트를 지정한다. `scripts/fullload_test.sh`는 `KRADDR_GEO_PG_DSN`이 없을 때 `KRADDR_GEO_DB_PORT`를 반영해 DSN을 만든다.

```bash
KRADDR_GEO_DB_PORT=15432 docker compose -p kraddr-geo-t027 up -d db
docker compose -p kraddr-geo-t027 ps
```

삭제할 때는 반드시 대상 project name과 volume을 확인한다.

```bash
docker compose -p kraddr-geo-t027 down
# 적재 결과를 폐기할 때만:
docker compose -p kraddr-geo-t027 down -v
```

## 실행 순서

### Phase -1: 계획 전용 preflight

실제 DB 명령 없이 경로와 환경변수만 확인한다.

```bash
export DATA_DIR=/mnt/f/dev/python-kraddr-geo/data
export JUSO_YYYYMM=202603
export LOCSUM_YYYYMM=202604
export NAVI_YYYYMM=202604
export DAILY_JUSO_ZIP=/mnt/f/dev/python-kraddr-geo/data/juso/daily/20260401_dailyjusukrdata.zip
PLAN_ONLY=1 bash scripts/fullload_test.sh
```

기대 결과:

- `202603_도로명주소 한글_전체분`
- `202604_위치정보요약DB_전체분.zip`
- `202604_내비게이션용DB_전체분`
- `DAILY_JUSO_ZIP`을 지정한 경우 해당 daily ZIP

세 경로와 지정한 daily ZIP이 모두 존재해야 한다. `DAILY_JUSO_ZIP`을 비워 두면 daily delta phase는 skip된다.

### Phase 0: 환경 준비

```bash
cd /mnt/f/dev/python-kraddr-geo
docker compose -p kraddr-geo-t027 up -d db
docker compose -p kraddr-geo-t027 ps

python -m venv .venv
source .venv/bin/activate
sudo apt-get install -y gdal-bin libgdal-dev
pip install "gdal==$(gdal-config --version)"
pip install -e ".[api,loaders,dev]"
```

확인 항목:

```bash
gdal-config --version
python - <<'PY'
from osgeo import gdal
print(gdal.VersionInfo("--version"))
PY
python -c "import kraddr.geo; print(kraddr.geo.__version__)"
```

### Phase 1: DDL 적용

`kraddr-geo init-db` 명령을 사용한다. `SCHEMA_SQL` → `INDEX_SQL` → `MV_SQL`을 순서대로 적용하므로 빈 MV와 unique index까지 준비된다. 이미 존재하는 인덱스/MV는 경고만 출력하고 계속 진행한다.

PR #14 이후 기존 DB를 이어서 쓰는 경우에는 Alembic `0002_t027_shp_schema_fixups`가 필수다. 이 migration은 `tl_spbd_buld_polygon` natural key 컬럼, `tl_sprd_manage.geom`, `tl_sprd_rw.geom` 타입 변경을 기존 DB에 반영한다. `tl_spbd_buld_polygon.bjd_cd`/`rncode_full` generated column은 drop 후 재생성되므로 해당 테이블에 이미 대량 row가 있으면 rewrite 시간이 발생한다. PR #14 이전 스키마로 `tl_sprd_rw`에 도로 폴리라인(`MULTILINESTRING`) 데이터가 들어 있으면 `MULTIPOLYGON` cast가 실패하므로, migration은 non-polygon row를 감지하면 `tl_sprd_rw`를 `TRUNCATE`하고 타입을 변경한다. 이미 PR #14 이전 스키마로 SHP를 적재했다면 migration 후 SHP full reset을 다시 실행한다.

```bash
export KRADDR_GEO_DB_PORT=15432
export KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:${KRADDR_GEO_DB_PORT}/kraddr_geo
kraddr-geo init-db
```

Alembic을 직접 쓰는 환경:

```bash
alembic upgrade head
```

확인 SQL:

```sql
SELECT extname, nspname
  FROM pg_extension e
  JOIN pg_namespace n ON n.oid = e.extnamespace
 WHERE extname IN ('postgis', 'pg_trgm', 'unaccent');

SELECT matviewname
  FROM pg_matviews
 WHERE matviewname = 'mv_geocode_target';

SELECT
  count(*) FILTER (WHERE li_cd = '')      AS empty_li,
  count(*) FILTER (WHERE rn_cd = '')      AS empty_rn,
  count(*) FILTER (WHERE rds_sig_cd = '') AS empty_rds_sig
FROM tl_spbd_buld_polygon;
```

### Phase 2: 텍스트 정본 3종 적재

```bash
export DATA_DIR=/mnt/f/dev/python-kraddr-geo/data
export JUSO_YYYYMM=202603
export LOCSUM_YYYYMM=202604
export NAVI_YYYYMM=202604
export ROADADDR_ENTRANCE_YYYYMM=202605
export DAILY_JUSO_ZIP=/mnt/f/dev/python-kraddr-geo/data/juso/daily/20260401_dailyjusukrdata.zip
export BATCH_SIZE=10000
export KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000

bash scripts/fullload_test.sh 2>&1 | tee artifacts/fullload_$(date +%Y%m%d_%H%M%S).log
```

`KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000`은 30분이다. 운영 API 기본값 5초는 일반 조회를 보호하기 위한 값이므로, 전국 풀로드의 링크 해소·shadow MV 생성처럼 대량 scan/sort가 필요한 유지보수 작업에는 별도 timeout을 사용한다. `scripts/fullload_test.sh`는 이 값이 없으면 30분을 기본값으로 export한다.

스크립트 내부에서 실행되는 핵심 명령:

```bash
kraddr-geo load juso   "$DATA_DIR/juso/${JUSO_YYYYMM}_도로명주소 한글_전체분" --yyyymm "$JUSO_YYYYMM"
kraddr-geo load locsum "$DATA_DIR/juso/${LOCSUM_YYYYMM}_위치정보요약DB_전체분.zip" --yyyymm "$LOCSUM_YYYYMM"
kraddr-geo load navi   "$DATA_DIR/juso/${NAVI_YYYYMM}_내비게이션용DB_전체분" --yyyymm "$NAVI_YYYYMM"
```

T-039 direct 출입구는 선택 적재다. 같은 기준월 자료로 동월 검증을 구성했거나 기준월 혼합을 의도적으로 기록하려는 경우에만 다음 명령을 추가한다.

```bash
kraddr-geo load roadaddr-entrances \
  "$DATA_DIR/juso/도로명주소 출입구 정보" \
  --yyyymm "$ROADADDR_ENTRANCE_YYYYMM"
kraddr-geo refresh mv --swap
```

### Phase 3c: 일변동 ZIP 증분 적용

`DAILY_JUSO_ZIP`이 지정되면 full snapshot 뒤에 같은 ZIP을 두 로더에 적용한다. `DAILY_YYYYMM`을 지정하지 않으면 ZIP 내부 이동일자에서 기준월을 추론한다.

```bash
kraddr-geo load daily-juso "$DAILY_JUSO_ZIP"
kraddr-geo load daily-parcel-links "$DAILY_JUSO_ZIP"
```

2026-05-29 최종 재적재에서는 `20260401_dailyjusukrdata.zip`을 사용했다. `daily-juso`는 422건 처리, 242건 upsert, 180건 delete, `daily-parcel-links`는 204건 처리, 74건 upsert, 82건 delete로 완료됐다.

중간 row count 기준:

| 테이블 | 기대 |
|--------|------|
| `tl_juso_text` | 17개 `rnaddrkor_*.txt` 합계. 서울 단일 52만+보다 충분히 큼 |
| `tl_locsum_entrc` | 좌표가 있는 `entrc_*.txt` 행만 적재 |
| `tl_roadaddr_entrc` | 선택 적재 시 좌표가 있는 `RNENTDATA_*.txt` 행만 적재 |
| `tl_navi_buld_centroid` | 17개 `match_build_*.txt` 합계 |
| `tl_navi_entrc` | `match_rs_entrc.txt` 행 |

### Phase 3: SHP 보조 레이어 적재

현재 SHP 로더는 `도로명주소 전자지도/<시도>/<SIG>/` 아래에서 다음 9개 레이어만 적재한다.

`load shp-all --mode full`은 첫 시도 실행 전에 9개 대상 테이블을 `TRUNCATE`한다. TRUNCATE 직전 로더는 대상 테이블별 approximate row count snapshot을 출력한다. 중간 실패나 host crash가 나면 9개 SHP 테이블이 비어 있거나 일부 시도만 들어간 상태일 수 있으므로 같은 명령을 다시 full로 실행해 전체를 재적재한다.

| SHP layer | target table |
|-----------|--------------|
| `TL_SCCO_CTPRVN` | `tl_scco_ctprvn` |
| `TL_SCCO_SIG` | `tl_scco_sig` |
| `TL_SCCO_EMD` | `tl_scco_emd` |
| `TL_SCCO_LI` | `tl_scco_li` |
| `TL_KODIS_BAS` | `tl_kodis_bas` |
| `TL_SPRD_MANAGE` | `tl_sprd_manage` |
| `TL_SPRD_INTRVL` | `tl_sprd_intrvl` |
| `TL_SPRD_RW` | `tl_sprd_rw` |
| `TL_SPBD_BULD` | `tl_spbd_buld_polygon` |

`TL_SPRD_INTRVL`은 T-034부터 DBF 직접 scan + `psycopg COPY` 경로를 사용한다. `TL_SPBD_BULD`는 T-037부터 GDAL projection staging table을 거쳐 운영 테이블에 `INSERT ... SELECT`한다. 세종 단일 `TL_SPBD_BULD`는 기존 append 38.36초에서 18.59초로 줄었지만, 경기도 단일 `TL_SPBD_BULD` 1,649,975행은 여전히 40분 17.15초가 걸렸다. 따라서 최종 클린 로드에서는 SHP phase를 별도 timer로 반드시 기록한다.

`TL_SPBD_EQB`, `TL_SPBD_ENTRC`는 discovery 대상에는 있지만 현재 `POLYGON_LAYER_NAMES`에서 제외되어 있다. 이번 검증에서는 "발견되지만 미적재"로 기록하고, 별도 활용 필요성이 있으면 후속 태스크로 분리한다.

### Phase 4: 후처리 링크와 MV 갱신

별도 `load juso/locsum/navi/shp-all` 명령을 순서대로 실행한 경우에는 `bd_mgt_sn` 후처리를 반드시 별도로 수행해야 한다. PR #13 스크립트는 `resolve_text_geometry_links()`를 직접 호출한 뒤 full-load에 더 적합한 `kraddr-geo refresh mv --swap`을 사용한다. 복구 과정에서 기존 `mv_geocode_target`이 없어진 경우에도 `refresh mv --swap`은 `mv_geocode_target_next`를 바로 운영 이름으로 승격할 수 있어야 한다.

확인 SQL:

```sql
SELECT
  count(*) AS total,
  count(*) FILTER (WHERE bd_mgt_sn IS NOT NULL) AS resolved,
  round(100.0 * count(*) FILTER (WHERE bd_mgt_sn IS NOT NULL) / nullif(count(*), 0), 2) AS resolved_pct
FROM tl_locsum_entrc;

SELECT
  count(*) AS total,
  count(*) FILTER (WHERE bd_mgt_sn IS NOT NULL) AS resolved,
  round(100.0 * count(*) FILTER (WHERE bd_mgt_sn IS NOT NULL) / nullif(count(*), 0), 2) AS resolved_pct
FROM tl_navi_entrc;
```

### Phase 5: 정합성 검증

```bash
kraddr-geo validate consistency --scope full
```

판정:

| 케이스 | 기대 |
|--------|------|
| C1~C3 | 전국 단위에서 WARN은 가능. ERROR면 sample 확인 |
| C4~C8 | SHP 적재 누락, 좌표계 오인, 도형 누락을 우선 의심 |
| C9 | PNU 형식 오류 0건이어야 함 |
| C10 | ADR-029 source set 확인이 있으면 INFO/WARN 가능. 확인 없는 혼합 기준월은 ERROR. 동월 자료 확보 후 재검증 필요 |

### Phase 6: smoke test

스크립트는 DTO 구조에 맞춰 다음을 확인한다.

- `GeocodeResponse.result.point`
- `ReverseResponse.result`
- `SearchResponse.result`
- `ZipcodeResponse.result`

실패 시 smoke test 주소가 실제 적재 월 데이터에 존재하는지 먼저 확인한다.

### Phase 7: 쿼리 성능 baseline (ADR-031, T-047)

T-027 클린 full-load가 성공하면 같은 DB를 지우기 전에 T-047 query benchmark baseline을 실행한다. smoke test는 "동작 여부"만 확인하므로 운영 준비 판단에는 부족하다. T-047은 도로명 exact, 지번 exact, fuzzy geocode, 통합 search, reverse nearest/radius, zipcode, no-result 경로를 다수 반복 측정해 p50/p95/p99와 slow plan을 남긴다.

원칙:

- 외부 API fallback은 끄고 로컬 DB query 성능을 먼저 측정한다.
- `pg_stat_statements`와 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, SETTINGS)`를 함께 저장한다.
- p95/p99 목표를 초과하면 index/query rewrite뿐 아니라 보조 view/materialized view 후보도 실험한다.
- benchmark artifact는 `artifacts/perf/<run_id>/`에 두고 git에는 커밋하지 않는다.
- 최종 PR에는 baseline과 튜닝 전후 핵심 표만 문서로 옮긴다.

## 예상 시간

| Phase | 내용 | 예상 |
|-------|------|------|
| -1 | `PLAN_ONLY=1` preflight | 즉시 |
| 0 | Docker/Python 준비 | 5~20분 |
| 1 | DDL | 5~30초 |
| 2 | 텍스트 3종 COPY | 20~60분 |
| 2a | 선택 direct 출입구 COPY | 수분~20분, 기준월 혼합 검증 시에만 |
| 3 | SHP 9 레이어 전국 적재 | 1~4시간. T-034/T-037 개선 후에도 경기도급 `TL_SPBD_BULD` geometry COPY가 길 수 있음 |
| 3b | 선택 SPPN makarea 적재 | 수십 초~수분 |
| 3c | 선택 daily delta 적용 | 수초~수분 |
| 4 | 링크 해소 + MV swap | 10~30분 |
| 5 | C1~C10 | 3~20분 |
| 6 | smoke test | 수초 |
| 7 | query benchmark baseline | corpus 크기와 동시성에 따라 수분~1시간 이상 |

총 예상은 1~3시간이다. NTFS → WSL I/O, Docker Desktop disk backend, Windows Defender 실시간 검사 여부에 따라 크게 달라질 수 있다.

## 중단·재개 정책

| 실패 위치 | 재개 방법 |
|-----------|-----------|
| DDL 전 | 컨테이너/볼륨 삭제 후 재시작 |
| 텍스트 적재 중 | 같은 명령 재실행 가능. 로더는 `ON CONFLICT` upsert 경로를 사용하지만 시간은 다시 든다 |
| SHP 적재 중 | `load shp-all --mode full` 재실행. full mode는 첫 시도 전에 9개 SHP 테이블을 TRUNCATE하고 이후 시도는 append한다 |
| 후처리 중 | `resolve_text_geometry_links()`와 `refresh mv --swap` 재실행 |
| 정합성 실패 | report JSON sample을 저장하고 해당 case SQL부터 분석 |
| smoke 실패 | MV row count, sample 주소 존재 여부, geocode SQL EXPLAIN 순으로 확인 |

부분 적재 결과를 버리고 새로 시작할 때만 `docker compose -p kraddr-geo-t027 down -v`를 사용한다.

## 결과 산출물

실행 후 다음 파일을 남긴다.

```
artifacts/fullload/<run_id>/
├── inventory.txt
├── docker-info.txt
├── fullload.log
├── row-counts.tsv
├── consistency-report.json
├── smoke-test.json
├── perf-baseline-summary.md
└── notes.md
```

`artifacts/`는 git에 커밋하지 않는다. PR에는 요약과 주요 오류 sample만 문서/코멘트로 남긴다.

## 2026-05-29 최종 클린 재적재 관찰 결과

실행 로그는 로컬 산출물 `artifacts/fullload/20260529_1643_final/` 아래에 있다. 이 경로는 git ignore 대상이며, PR에는 핵심 표와 재현 명령만 옮긴다.

### 실행 환경

| 항목 | 값 |
|------|----|
| 작업 디렉터리 | `/home/digitie/dev/geo-codex` |
| 데이터 작업 사본 | `/home/digitie/kraddr-geo-data` |
| daily ZIP | `/mnt/f/dev/python-kraddr-geo/data/juso/daily/20260401_dailyjusukrdata.zip` |
| Docker compose project | `kraddr-geo-t027-final` |
| PostgreSQL | Docker PostGIS `16-3.5`, `localhost:15434`, DB `kraddr_geo` |
| 전용 pgdata | `/home/digitie/kraddr-geo-data/pgdata-final-20260529` |
| OS/WSL | Ubuntu 24.04 on WSL2 |
| CPU/RAM | AMD Ryzen 7 7840HS, 16 vCPU, RAM 약 29GiB |
| Docker/GDAL/Python | Docker 29.5.2, GDAL 3.8.4, Python 3.12.3 |
| 시작 디스크 | ext4 `/dev/sdd` 약 1007GiB 중 737GiB 여유 |

기존 `kraddr-geo-t027-db-1`(`localhost:15432`)은 건드리지 않고, 새 project와 port `15434`를 사용했다. `load shp-all --mode full`의 TRUNCATE 직전 row count가 9개 SHP 테이블 모두 0이어서 빈 DB에서 시작했음을 확인했다.

### 실행 명령

```bash
KRADDR_GEO_DB_PORT=15434 \
KRADDR_PGDATA=/home/digitie/kraddr-geo-data/pgdata-final-20260529 \
KRADDR_JUSO_DATA=/home/digitie/kraddr-geo-data/juso \
docker compose -p kraddr-geo-t027-final up -d db

env \
  DATA_DIR=/home/digitie/kraddr-geo-data \
  DAILY_JUSO_ZIP=/mnt/f/dev/python-kraddr-geo/data/juso/daily/20260401_dailyjusukrdata.zip \
  PYTHON=/home/digitie/.cache/python-kraddr-geo-venv/bin/python \
  KRADDR_GEO_BIN=/home/digitie/.cache/python-kraddr-geo-venv/bin/kraddr-geo \
  KRADDR_GEO_DB_PORT=15434 \
  KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kraddr_geo \
  KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000 \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  /usr/bin/time -v -o artifacts/fullload/20260529_1643_final/time.txt \
  bash scripts/fullload_test.sh \
  2>&1 | tee artifacts/fullload/20260529_1643_final/full-load.log
```

### 전체 phase 시간

| Phase | 결과 | 시간 |
|-------|------|-----:|
| DDL/init-db | schema/index/MV 생성 | 3초 |
| `juso_hangul` | `tl_juso_text` 6,416,637행 | 289초 |
| `parcel_links` | `tl_juso_parcel_link` 1,769,370행 | 68초 |
| `locsum` | `tl_locsum_entrc` 6,405,094행 | 181초 |
| `navi` | `tl_navi_buld_centroid` 10,687,317행, `tl_navi_entrc` 12,830행 | 361초 |
| 텍스트 로더 합계 | juso/parcel/locsum/navi | 899초 |
| SHP 17개 시도 × 9개 레이어 | 153 레이어 | 1,578초 |
| `roadaddr_entrance` | `tl_roadaddr_entrc` 6,404,697행 | 225초 |
| `sppn_makarea` | `tl_sppn_makarea` 24,204행 | 30초 |
| daily delta | MST + LNBR 적용 | 3초 |
| geometry link resolution | text geometry link 해소 | 142초 |
| MV swap refresh | `mv_geocode_target`, `mv_geocode_text_search` 재생성 | 437초 |
| C1~C10 | full consistency report | 약 633초 |
| smoke | geocode/reverse/search/zipcode | 1초 내외 |
| 전체 | script total | 3,963초 |
| `/usr/bin/time` | wall clock / max RSS | 1:06:02 / 283,304KB |

SHP와 SPPN 적재 중 GDAL이 일부 polygon winding order를 자동 보정했다. 모두 warning으로 처리됐고 적재는 계속 진행됐다. 이 warning은 원천 SHP 품질 기록으로 남기되, 현재 로더 실패로 보지 않는다.

### daily delta 적용 결과

`DAILY_JUSO_ZIP`은 임의 mock이 아니라 실제 `20260401_dailyjusukrdata.zip`을 사용했다. 이 ZIP은 최종 snapshot에 증분 적용 가능 여부를 검증하기 위한 단일 daily sample이다.

| 로더 | 처리 | upsert | delete | skip/no-data | 마지막 이동일자 |
|------|-----:|-------:|-------:|--------------|----------------|
| `daily-juso` | 422 | 242 | 180 | `lnbr_skipped=204`, `no_data_sources=0` | `20260402` |
| `daily-parcel-links` | 204 | 74 | 82 | `no_data_sources=0` | `20260402` |

적용 후 `tl_juso_text`는 6,416,642행으로 full snapshot 대비 순증 5행이다. `tl_juso_parcel_link`는 full snapshot 1,769,370행에서 1,769,314행으로 조정됐다.

### 최종 row count

| 테이블 | 건수 |
|--------|-----:|
| `tl_juso_text` | 6,416,642 |
| `tl_juso_parcel_link` | 1,769,314 |
| `tl_locsum_entrc` | 6,405,091 |
| `tl_roadaddr_entrc` | 6,404,697 |
| `tl_navi_buld_centroid` | 10,687,317 |
| `tl_navi_entrc` | 12,830 |
| `tl_sppn_makarea` | 24,204 |
| `mv_geocode_target` | 6,416,642 |
| `mv_geocode_text_search` | 6,416,642 |
| `tl_scco_ctprvn` | 17 |
| `tl_scco_sig` | 255 |
| `tl_scco_emd` | 5,067 |
| `tl_scco_li` | 15,161 |
| `tl_kodis_bas` | 34,516 |
| `tl_sprd_manage` | 875,221 |
| `tl_sprd_intrvl` | 16,993,167 |
| `tl_sprd_rw` | 1,482,679 |
| `tl_spbd_buld_polygon` | 10,687,732 |
| `postal_pobox` | 0 |
| `postal_bulk_delivery` | 0 |

`postal_pobox`와 `postal_bulk_delivery`는 입력 파일이 없어 skip했다.

### DB size와 주요 relation size

`db-summary.json` 기준 전체 DB 크기는 36,804,891,107 bytes(약 34.28GiB)다.

| relation | rows | total | heap | index |
|----------|-----:|------:|-----:|------:|
| `mv_geocode_target` | 6,416,642 | 5.13GB | 1.98GB | 3.15GB |
| `mv_geocode_text_search` | 6,416,642 | 2.54GB | 895MB | 1.65GB |
| `tl_spbd_buld_polygon` | 10,687,732 | 5.40GB | 3.65GB | 1.76GB |
| `tl_navi_buld_centroid` | 10,687,317 | 4.85GB | 2.97GB | 1.88GB |
| `tl_juso_text` | 6,416,642 | 4.35GB | 1.87GB | 2.48GB |
| `tl_locsum_entrc` | 6,405,091 | 4.03GB | 2.36GB | 1.67GB |
| `tl_roadaddr_entrc` | 6,404,697 | 3.34GB | 1.79GB | 1.55GB |
| `tl_sprd_intrvl` | 16,993,167 | 3.10GB | 1.88GB | 1.22GB |

최신 active serving release는 `faa1f42b-f5b9-4ef0-af0b-1a422d938ed3`, snapshot은 `59179cee-d17e-4763-8ccc-c7b63bf8e83c`, `mv_hash=ac8614153b1e3a26ef7e29ff9928066d`다.

### C1~C10 결과

`consistency_163e89acfb4a41e0a8c19599c2faa678` 리포트는 2026-05-29 08:40:41Z에 시작해 08:51:14Z에 끝났다. `severity_max=ERROR`는 기존 실제 원천 품질 이슈인 C2/C4/C6/C7 때문이다. daily delta를 적용했기 때문에 C10에는 `tl_juso_text`의 202603 full snapshot row와 202604 daily upsert row가 함께 evidence로 남는다.

| 케이스 | 심각도 | 건수 | 핵심 metric |
|--------|--------|-----:|-------------|
| C1 | WARN | 32,353 | 텍스트에만 있는 natural-key |
| C2 | ERROR | 34,454 | `missing_text=33,873`, `missing_resolve_key=581` |
| C3 | WARN | 3,510,220 | 대표 출입구 미해소 |
| C4 | ERROR | 3,415 | `over_500m=16`, `p95=3.82m`, `p99=15.50m` |
| C5 | WARN | 202 | `over_10m=202` |
| C6 | ERROR | 803 | `outside_polygon=803` |
| C7 | ERROR | 6,817 | `outside_polygon=6,817` |
| C8 | WARN | 24,479 | 같은 도로명 LineString 100m 밖 |
| C9 | OK | 0 | PNU 형식 오류 없음 |
| C10 | WARN | 8 | `distinct_months=3`, row-level evidence 사용 |

C10 sample은 다음 row-level evidence를 포함한다.

| 테이블 | 기준월 | row count |
|--------|--------|----------:|
| `tl_juso_text` | 202603 | 6,416,400 |
| `tl_juso_text` | 202604 | 242 |
| `tl_locsum_entrc` | 202604 | 6,405,091 |
| `tl_navi_buld_centroid` | 202604 | 10,687,317 |
| `tl_navi_entrc` | 202604 | 12,830 |
| `tl_spbd_buld_polygon` | 202604 | 10,687,732 |
| `tl_roadaddr_entrc` | 202605 | 6,404,697 |
| `tl_sppn_makarea` | 202605 | 24,204 |

### smoke 결과

| 항목 | 결과 |
|------|------|
| geocode | `서울특별시 종로구 자하문로 94` → `OK`, point `(126.97040554796257, 37.58441543603026)` |
| reverse | 위 point 기준 `OK`, 10건 |
| search | `자하문로` → `OK`, total 368, 첫 결과 `서울특별시 종로구 자하문로 94` |
| zipcode | 같은 주소 → `OK`, 첫 우편번호 `03047` |

### data-quality CSV export

`kraddr-geo validate data-quality-samples --cases C2,C4,C6,C7 --limit 20`을 `KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000`로 실행해 CSV 8개를 생성했다. 첫 실행은 기본 statement timeout에서 C4 temp table 생성 중 `QueryCanceled`로 실패했으므로, 전국 data-quality export도 full consistency와 같은 유지보수 timeout으로 실행해야 한다.

| 파일 | 크기 | 용도 |
|------|-----:|------|
| `c2_samples.csv` | 74,946 bytes | C2 reason별 sample |
| `c2_missing_key_summary.csv` | 141 bytes | SHP natural-key 결측 요약 |
| `c4_distance_samples.csv` | 45,352 bytes | C4 거리 상위 sample, 출입구/polygon 좌표와 delta 포함 |
| `c4_distance_buckets.csv` | 153 bytes | C4 거리 bucket 분포 |
| `c6_samples.csv` | 22,191 bytes | C6 sample |
| `c6_region_summary.csv` | 3,068 bytes | C6 우편번호 region summary |
| `c7_samples.csv` | 22,560 bytes | C7 sample |
| `c7_region_summary.csv` | 3,904 bytes | C7 법정동 region summary |

C4 bucket:

| bucket | rows | min_m | avg_m | max_m |
|--------|-----:|------:|------:|------:|
| `0-50` | 2,887,877 | 0.00 | 0.64 | 49.99 |
| `50-100` | 2,847 | 50.00 | 66.95 | 99.96 |
| `100-500` | 552 | 100.10 | 141.92 | 477.08 |
| `500+` | 16 | 513.38 | 78,914.93 | 182,401.19 |

C2 natural-key 결측 요약은 `rows=581`, `missing_rds_sig_cd=581`이고 다른 key 필드 결측은 0건이다. SHP `source_file`은 PR #17 이후 경로가 채워져 이번 최종 DB에서는 `null_source_file=0`이다. C6 상위 region은 `54002=49`, `48700=23`, `54004=15`, `48239=11`, `52570=11`이고, C7 상위 region은 `48121103=216`, `28260101=167`, `41273104=165`, `41273106=97`, `26470102=85`다.

## 2026-05-27 이전 클린 적재 관찰 결과

실행 로그는 로컬 산출물 `artifacts/fullload/20260527_135155/` 아래에 있다. 이 경로는 git ignore 대상이며, PR에는 핵심 표와 재현 명령만 옮긴다.

### 실행 환경

| 항목 | 값 |
|------|----|
| 작업 디렉터리 | `/home/digitie/dev/python-kraddr-geo` |
| 데이터 작업 사본 | `/home/digitie/kraddr-geo-data` |
| 원본 데이터 | `/mnt/f/dev/python-kraddr-geo/data/juso` |
| PostgreSQL | Docker PostGIS, `localhost:15432`, DB `kraddr_geo` |
| OS/WSL | Ubuntu 24.04 on WSL2 |
| CPU/RAM | AMD Ryzen 7 7840HS, 16 vCPU, RAM 약 29GiB |
| Docker/GDAL/Python | Docker 29.5.2, GDAL 3.8.4, Python 3.12.3 |
| 디스크 | ext4 `/dev/sdd` 약 1007GiB 중 시작 시 782GiB 여유 |

### 전체 phase 시간

| Phase | 결과 | 시간 |
|-------|------|-----:|
| DDL/init-db | schema/index/MV 생성 | 3초 |
| `juso_hangul` | `tl_juso_text` 6,416,637행 | 245초 |
| `parcel_links` | `tl_juso_parcel_link` 1,769,370행 | 68초 |
| `locsum` | `tl_locsum_entrc` 6,405,091행 | 169초 |
| `navi` | `tl_navi_buld_centroid` 10,687,317행, `tl_navi_entrc` 12,830행 | 343초 |
| SHP 17개 시도 × 9개 레이어 | 153 레이어 | 1,525초 |
| `roadaddr_entrance` | `tl_roadaddr_entrc` 6,404,697행 | 216초 |
| `sppn_makarea` | `tl_sppn_makarea` 24,204행 | 33초 |
| geometry link resolution | text geometry link 해소 | 140초 |
| MV swap refresh | `mv_geocode_target` 재생성 | 159초 |
| 최초 C1~C10 | direct 우선 정책 상태 | 약 1,011초 |
| smoke | geocode/reverse/search/zipcode | 1초 내외 |
| 전체 | script total | 3,934초 |

SHP와 SPPN 적재 중 GDAL이 일부 polygon winding order를 자동 보정했다. 모두 warning으로 처리됐고 적재는 계속 진행됐다. 이 warning은 원천 SHP 품질 기록으로 남기되, 현재 로더 실패로 보지 않는다.

### 최종 row count

| 테이블 | 건수 |
|--------|-----:|
| `tl_juso_text` | 6,416,637 |
| `tl_juso_parcel_link` | 1,769,370 |
| `tl_locsum_entrc` | 6,405,091 |
| `tl_roadaddr_entrc` | 6,404,697 |
| `tl_navi_buld_centroid` | 10,687,317 |
| `tl_navi_entrc` | 12,830 |
| `tl_sppn_makarea` | 24,204 |
| `mv_geocode_target` | 6,416,637 |
| `tl_scco_ctprvn` | 17 |
| `tl_scco_sig` | 255 |
| `tl_scco_emd` | 5,067 |
| `tl_kodis_bas` | 34,516 |
| `tl_spbd_buld_polygon` | 10,687,732 |
| `postal_pobox` | 0 |
| `postal_bulk_delivery` | 0 |

`postal_pobox`와 `postal_bulk_delivery`는 입력 파일이 없어 skip했다. T-046 백업/복원 검증은 대구광역시 부분 DB에서 완료했지만, 이번 전국 DB의 serving-ready 백업 생성은 후속 운영 절차로 남긴다.

### direct 출입구 우선순위 보정

최초 full-load 스크립트는 T-039 당시 설계대로 `tl_roadaddr_entrc`를 `tl_locsum_entrc`보다 먼저 사용했다. 하지만 현재 로컬 원천은 direct 출입구가 `202605`, 텍스트 정본이 `202603`, SHP/locsum/navi가 `202604`라 같은 시점의 데이터가 아니다. 이 상태에서 direct 출입구를 serving 좌표로 우선 사용하면 C4/C6/C7이 크게 늘었다.

| 조건 | C4 `over_50m` | C4 `over_500m` | C6 | C7 |
|------|--------------:|---------------:|---:|---:|
| direct `roadaddr` 우선 | 12,225 | 91 | 3,593 | 9,827 |
| `locsum`만 임시 비교 | 3,415 | 16 | 803 | 6,817 |
| same-month gate 적용 후 | 3,415 | 16 | 803 | 6,817 |

반영한 정책:

- `mv_geocode_target`은 `tl_locsum_entrc` 대표 출입구를 먼저 사용한다.
- `tl_roadaddr_entrc`는 `source_yyyymm`이 `tl_juso_text.source_yyyymm`와 같은 기준월일 때만 fallback 후보로 쓴다.
- 기준월이 다른 direct 출입구는 적재와 분석에는 사용하지만 기본 serving 좌표와 C3/C4/C6/C7/C8 serving CTE에는 반영하지 않는다.
- API 호환성을 위해 direct 출입구가 사용되는 경우에도 `pt_source='entrance'`는 유지한다.

same-month gate 적용 후 `mv_geocode_target.pt_source` 분포:

| `pt_source` | 건수 |
|-------------|-----:|
| `centroid` | 3,496,182 |
| `entrance` | 2,906,372 |
| `NULL` | 14,083 |

### 보강 후 C1~C10 결과

보강 후 전체 C1~C10 재검증은 611.71초, 최대 RSS 82,424KB로 완료됐다. `severity_max=ERROR`는 기존 실제 원천 품질 이슈인 C2/C4/C6/C7 때문이다. C10은 기존 `OK`가 아니라 row-level 기준월 집계 기준 `WARN`으로 바로잡았다.

| 케이스 | 심각도 | 건수 | 핵심 metric |
|--------|--------|-----:|-------------|
| C1 | WARN | 32,531 | 텍스트에만 있는 natural-key |
| C2 | ERROR | 34,699 | `missing_text=34,118`, `missing_resolve_key=581` |
| C3 | WARN | 3,510,265 | 기준월 다른 direct 출입구를 serving 후보에서 제외했으므로 locsum 결측이 그대로 드러남 |
| C4 | ERROR | 3,415 | `over_500m=16`, `p95=3.82m`, `p99=15.50m` |
| C5 | WARN | 202 | `over_10m=202` |
| C6 | ERROR | 803 | `outside_polygon=803` |
| C7 | ERROR | 6,817 | `outside_polygon=6,817` |
| C8 | WARN | 24,471 | 같은 도로명 LineString 100m 밖 |
| C9 | OK | 0 | PNU 형식 오류 없음 |
| C10 | WARN | 7 | `distinct_months=3`, row-level evidence 사용 |

C10 sample은 다음 7개 row-level evidence를 포함한다.

| 테이블 | 기준월 | row count |
|--------|--------|----------:|
| `tl_juso_text` | 202603 | 6,416,637 |
| `tl_locsum_entrc` | 202604 | 6,405,091 |
| `tl_navi_buld_centroid` | 202604 | 10,687,317 |
| `tl_navi_entrc` | 202604 | 12,830 |
| `tl_spbd_buld_polygon` | 202604 | 10,687,732 |
| `tl_roadaddr_entrc` | 202605 | 6,404,697 |
| `tl_sppn_makarea` | 202605 | 24,204 |

### smoke 결과

보강 후 MV를 다시 swap refresh하고 smoke를 재실행했다.

| 항목 | 결과 |
|------|------|
| geocode | `서울특별시 종로구 자하문로 94` → `OK`, point `(126.97040554796257, 37.58441543603026)` |
| reverse | 위 point 기준 `OK`, 10건 |
| search | `자하문로` → `OK`, total 1,701, 첫 결과 `서울특별시 종로구 자하문로 94` |
| zipcode | 같은 주소 → `OK`, 첫 우편번호 `03047` |

### data-quality CSV export

`kraddr-geo validate data-quality-samples --cases C2,C4,C6,C7 --limit 20`을 실행해 CSV 8개를 생성했다. 경과는 86.18초, 최대 RSS는 82,292KB다.

| 파일 | 용도 |
|------|------|
| `c2_samples.csv` | C2 reason별 sample |
| `c2_missing_key_summary.csv` | SHP natural-key 결측 요약 |
| `c4_distance_samples.csv` | C4 거리 상위 sample, 출입구/polygon 좌표와 delta 포함 |
| `c4_distance_buckets.csv` | C4 거리 bucket 분포 |
| `c6_samples.csv`, `c6_region_summary.csv` | C6 sample과 우편번호 region summary |
| `c7_samples.csv`, `c7_region_summary.csv` | C7 sample과 법정동 region summary |

C4 bucket:

| bucket | rows | min_m | avg_m | max_m |
|--------|-----:|------:|------:|------:|
| `0-50` | 2,887,827 | 0.00 | 0.64 | 49.99 |
| `50-100` | 2,847 | 50.00 | 66.95 | 99.96 |
| `100-500` | 552 | 100.10 | 141.92 | 477.08 |
| `500+` | 16 | 513.38 | 78,914.93 | 182,401.19 |

C4 `500+` 상위 sample은 기존 분석과 같은 패턴이다. 예를 들어 부산 sample은 출입구 `(131.02008388, 35.09199694)`, polygon `(129.02021257, 35.09195243)`로 경도만 약 `+1.99987131`도 차이난다. 따라서 180km급 이상치는 로더 좌표계 변환 실패라기보다 일부 원천 row의 경도 방향 약 2도 이동 패턴으로 계속 분류한다.

상위 region:

| 케이스 | 상위 region |
|--------|-------------|
| C6 | `54002=49`, `48700=23`, `54004=15`, `48239=11`, `52570=11` |
| C7 | `48121103=216`, `28260101=167`, `41273104=165`, `41273106=97`, `26470102=85` |

C2 natural-key 결측 요약은 `rows=581`, `missing_rds_sig_cd=581`이고 다른 key 필드 결측은 0건이다. SHP `source_file`은 PR #17 이후 경로가 채워져 이번 최종 DB에서는 `null_source_file=0`이다.

### Playwright 검증 위치

이번 T-027 보강은 백엔드 적재/MV/정합성 로직 변경이며 UI 동작 변경은 없다. 사용자의 최신 지시에 따라 앞으로 Playwright가 필요한 UI 검증은 WSL이 아니라 Windows Node/브라우저 환경에서 수행한다. 문서나 PR에는 Windows에서 실행한 명령, 브라우저, screenshot 경로를 함께 남긴다.

## PR #14 실제 실행 관찰 결과

2026-05-24~2026-05-25에 `codex/t027-fullload-execution` 브랜치에서 실제 전국 적재를 수행했다. 상세 로그는 로컬 산출물 `artifacts/fullload/20260524_173115/execution-log.md`에 있으며, 해당 경로는 git ignore 대상이다.

### 실행 환경

| 항목 | 값 |
|------|----|
| 작업 디렉터리 | `/home/digitie/dev/python-kraddr-geo` |
| 데이터 작업 사본 | `/home/digitie/kraddr-geo-data` |
| Docker compose project | `kraddr-geo-t027` |
| PostgreSQL container | `kraddr-geo-t027-db-1` |
| PostgreSQL port | `15432` |
| WSL | Ubuntu 24.04, WSL2 |
| CPU/RAM | AMD Ryzen 7 7840HS 16 vCPU, RAM 약 29GiB |
| Docker/GDAL/Python | Docker 29.5.2, GDAL 3.8.4, Python 3.12.3 |

### SHP 재적재 결과

- 대상: `도로명주소 전자지도` 17개 시도 × 9개 레이어 = 153 레이어
- 경과: 3시간 10분 4초
- 결과: 성공, exit status 0
- 최대 RSS: 187,100KB
- 종료 직후 DB 크기: 24GB
- 종료 직후 디스크 여유: ext4 약 796GB, C: 약 682GB, F: 약 264GB

정확한 row count:

| 테이블 | 건수 |
|--------|------:|
| `tl_scco_ctprvn` | 17 |
| `tl_scco_sig` | 255 |
| `tl_scco_emd` | 5,067 |
| `tl_scco_li` | 15,161 |
| `tl_kodis_bas` | 34,516 |
| `tl_sprd_manage` | 875,221 |
| `tl_sprd_rw` | 1,482,679 |
| `tl_sprd_intrvl` | 16,993,167 |
| `tl_spbd_buld_polygon` | 10,687,732 |

새 natural-key 컬럼 검증:

- `tl_spbd_buld_polygon.bjd_cd`, 건물구분, 본번, 부번, geometry는 전 건 채워졌다.
- `rds_sig_cd`/`rncode_full`은 581건이 NULL이었다. 원천 SHP에 도로명 시군구 코드가 비어 있는 건물로 확인되며, natural-key 기반 정합성 해석에서 별도 고려가 필요하다.
- `tl_sprd_manage.geom`은 875,221건 전부 채워졌다.
- `source_file`은 PR #17 이전 GDAL append 경로에서 전 건 NULL이었다. PR #17부터 SHP loader가 `source_file=<시도>/<시군구코드>/<레이어>.shp`와 `source_yyyymm`을 projection에 넣으므로, 원천 파일 역추적이 필요한 DB는 SHP 보조 레이어를 재적재해야 한다.

### consistency 결과

SHP 9개 테이블 `ANALYZE` 후 `kraddr-geo validate consistency --scope full`을 실행했다.

처음 실행에서는 C4/C5가 같은 natural key의 중복 polygon 후보를 모두 조인해 다대다 거리 이상치를 대량 생성했다. 이후 C4/C5를 가장 가까운 polygon 1개만 평가하도록 보강한 뒤 재실행했다.

최종 결과:

| 케이스 | 심각도 | 건수 | 참고 |
|--------|--------|-----:|------|
| C1 | WARN | 32,531 | 텍스트에만 있는 natural-key 건 |
| C2 | ERROR | 34,699 | SHP polygon에만 있는 natural-key 건 |
| C3 | WARN | 3,510,265 | 위치정보요약DB 직접 출입구 미해소. T-039 direct 출입구를 선택 적재하면 이 수치는 별도 재측정 필요 |
| C4 | ERROR | 3,415 | 50m 초과, 이 중 500m 초과 16건 |
| C5 | WARN | 202 | 내비 centroid와 SHP centroid 10m 초과 |
| C6 | ERROR | 803 | 우편번호 기초구역 polygon 외부 |
| C7 | ERROR | 6,817 | 행정구역 polygon 외부 |
| C8 | WARN | 24,471 | 같은 도로명 LineString 100m 밖 |
| C9 | OK | 0 | PNU 형식 오류 없음 |
| C10 | OK | 0 | 적재 기준월 리포트 기준 불일치 없음 |

해석:

- C1/C2는 25자리 SHP `BD_MGT_SN`과 26자리 정본 `bd_mgt_sn`을 직접 비교하던 전수 불일치 문제에서 natural-key 비교로 줄었다.
- C4/C5는 nearest polygon 보강 후 현실적인 규모로 줄었다. C4의 500m 초과 16건은 실제 원천 좌표 또는 잔여 매칭 이상치로 별도 분석 대상이다.
- C6/C7은 재적재 전후 같은 건수로 남아 있어, 적재 실패보다는 원천 좌표와 polygon 경계 간 데이터 품질 항목으로 분류한다. 현재 SQL은 polygon 경계 위 점을 false positive로 보지 않도록 `ST_Contains` 대신 `ST_Covers`를 사용한다.
- C8은 `tl_sprd_manage.geom` 기반으로 전환한 뒤 전체 WARN이 아니라 0.84% 수준으로 줄었다.

추가 리뷰 반영 후 선택 재검증:

- 2026-05-25에 기존 T-027 Docker DB(`localhost:15432`)에서 C2/C4/C6/C7만 다시 실행했다. 경과는 3분 53.82초, 최대 RSS는 80,076KB였다.
- C2는 총 34,699건으로 유지됐고, 새 metric 기준 `missing_text=34,118`, `missing_resolve_key=581`로 분리됐다. `missing_resolve_key`는 SHP polygon row 자체의 `rncode_full` 또는 `bjd_cd` 등 natural key가 비어 있어 텍스트와 직접 비교할 수 없는 건이다.
- C4는 총 3,415건으로 유지됐고, `over_500m=16`이 `error_count`로 명시됐다.
- C6/C7은 `ST_Covers` 전환 후에도 각각 803건, 6,817건으로 유지됐다. 이 데이터셋에서는 polygon 경계 위 point 오탐보다 실제 polygon 외부 좌표 또는 원천 경계 불일치일 가능성이 높다.

## PR #13에서 보강한 계획상 수정점

- 단일 `YYYYMM` 대신 `JUSO_YYYYMM`, `LOCSUM_YYYYMM`, `NAVI_YYYYMM`을 분리한다.
- ADR-029/T-045 이후 새 실행 경로는 `source_set.yyyymm_by_kind`를 사용하고, 기준월이 섞이면 CLI/UI 확인 기록을 남긴다.
- `PLAN_ONLY=1` preflight 모드를 추가해 실제 DB 명령 없이 경로 검증만 수행할 수 있게 한다.
- `python -m kraddr.geo.cli ...` 대신 설치된 console script `kraddr-geo ...`를 사용한다.
- DDL은 inline SQL 대신 `alembic upgrade head`를 사용한다.
- 별도 적재 명령 뒤 누락될 수 있는 `resolve_text_geometry_links()`를 명시적으로 수행한다.
- full-load MV 갱신은 `--swap` 전략을 기본으로 한다.
- smoke test는 실제 DTO 구조(`result.point`, `result` tuple)에 맞춘다.

## 후속 태스크 후보

| 후보 | 이유 |
|------|------|
| T-028 일변동 ZIP 로더 | 완료. `TH_SGCO_RNADR_MST.TXT`는 `tl_juso_text`에 적용하고 `LNBR`은 manifest에 기록 |
| T-029 `jibun_rnaddrkor_*` 활용 여부 결정 | 완료. `tl_juso_text.pnu`에 덮어쓰지 않고 후속 `tl_juso_parcel_link` 1:N 테이블로 분리 |
| T-038 `tl_juso_parcel_link` 구현 | 완료. `jibun_rnaddrkor_*` full snapshot과 daily `LNBR` delta를 `tl_juso_parcel_link`에 적재 |
| T-030 별도 도형/출입구 자료 검토 | 완료. 기본 full-load에는 즉시 섞지 않고 T-039~T-041로 분리 |
| T-039 `도로명주소 출입구 정보` direct entrance loader | 완료. `tl_roadaddr_entrc` 선택 적재, same-month일 때만 MV fallback 후보, 기본 full-load 자동 포함 제외 |
| T-040 `도로명주소 건물 도형` bundle 비교 | 완료. 전자지도 `TL_SPBD_BULD`와 단순 중복이 아니므로 별도 분석 후보로 유지 |
| T-041 상세주소 동/구역 추가 레이어 검토 | 완료. 상세주소 동 도형은 전자지도 건물 부분집합, 구역 중복 5개 레이어는 전자지도와 key 기준 완전 중복으로 확인 |
| T-037 SHP geometry 포함 대형 레이어 튜닝 | 완료. `TL_SPBD_BULD` projection staging 경로를 도입하고 세종/경기도 실제 파일 기준 시간을 기록 |
| T-042 `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 | 완료. `tl_sppn_makarea` 별도 테이블, loader, reverse/geocode enrichment를 구현했고 세종 실제 ZIP 146행 적재를 검증했다. T-027 최종 클린 로드에서 optional source 포함 여부와 전국 적재 시간을 기록 |
| T-047 전국 적재 후 쿼리 성능 벤치마크 | 완료. T-027 클린 DB 기준 여러 SQL/REST benchmark, tuning, `mv_geocode_text_search` helper까지 T-047/T-057/T-061에서 기록했다 |
