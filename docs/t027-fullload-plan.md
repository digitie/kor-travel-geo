# T-027: Docker 기반 실 데이터 전체 적재 검증 계획

## 상태

- 상태: 계획 보강 중. 실제 전체 적재 실행은 아직 하지 않는다.
- 대상 PR: PR #13 (`claude/t027-docker-fullload-plan`)
- 실행 대상 데이터: `F:\dev\python-kraddr-geo\data\juso` (`/mnt/f/dev/python-kraddr-geo/data/juso`)
- 원칙: Docker PostGIS에 새 볼륨을 만들고, 로컬 개발 DB나 기존 운영성 데이터는 건드리지 않는다.

## 목적

`data/juso` 아래 실제 행안부 주소 데이터를 Docker PostGIS에 전량 적재해 다음을 확인한다.

1. 텍스트 정본 3종(도로명주소 한글, 위치정보요약DB, 내비게이션용DB)이 전국 단위로 적재되는지 확인한다.
2. 도로명주소 전자지도 SHP 보조 레이어 9종이 전국 시도별로 적재되는지 확인한다.
3. `tl_locsum_entrc`와 `tl_navi_entrc`의 `bd_mgt_sn` 후처리 링크가 전국 데이터에서 충분히 해소되는지 확인한다.
4. `mv_geocode_target`을 full-load 이후 swap 전략으로 재생성할 수 있는지 확인한다.
5. C1~C10 정합성 검증과 geocode/reverse/search/zipcode smoke test를 통과하는지 확인한다.
6. 아직 로더가 없는 `data/juso` 하위 자료는 "누락"이 아니라 "미지원 입력"으로 명시해 후속 태스크로 분리한다.

## 현재 데이터 인벤토리

2026-05-24 기준 로컬 경로를 읽어 확인한 결과, `data/juso` 전체 용량은 약 28GB다. 실제 적재 실행은 하지 않았고 파일/디렉터리 존재만 확인했다.

| 경로 | 크기/형태 | 현재 로더 지원 | 이번 T-027 처리 |
|------|-----------|----------------|-----------------|
| `202603_도로명주소 한글_전체분/` | `rnaddrkor_*.txt` 17개 + `jibun_rnaddrkor_*.txt` 17개 | 부분 지원 | `rnaddrkor_*.txt`만 `tl_juso_text`로 적재. `jibun_*`은 ADR-022에 따라 후속 `tl_juso_parcel_link` 1:N 테이블로 분리 |
| `202603_도로명주소 한글_전체분.zip` | 원본 ZIP | 간접 지원 | 압축 해제본을 적재 대상으로 사용 |
| `full/202603_도로명주소 한글_전체분.zip` | 중복 원본 ZIP | 간접 지원 | 중복 보관으로 기록. 기본 적재 대상 아님 |
| `202604_위치정보요약DB_전체분.zip` | `entrc_*.txt` ZIP member | 지원 | `tl_locsum_entrc` 적재 |
| `202604_내비게이션용DB_전체분/` | `match_build_*.txt`, `match_rs_entrc.txt`, `match_jibun_*.txt` | 부분 지원 | `match_build_*`, `match_rs_entrc.txt` 적재. `match_jibun_*`은 현재 로더 미지원 |
| `202604_내비게이션용DB_전체분.7z` | 원본 압축 | 간접 지원 | 압축 해제본을 적재 대상으로 사용 |
| `도로명주소 전자지도/` | 시도별 SHP directory 17개 | 지원 | SHP 9개 보조 레이어 적재 |
| `daily/*.zip` | 일변동 ZIP 20260401~20260506 | 부분 지원 | T-028 이후 `TH_SGCO_RNADR_MST.TXT`는 `tl_juso_text` 증분 적용 가능. `TH_SGCO_RNADR_LNBR.TXT`는 ADR-022에 따라 후속 `tl_juso_parcel_link` delta source로 사용 |
| `건물군 내 상세주소 동 도형/` | 시도별 ZIP | 미지원 | 상세주소 동 도형 로더 후속 후보 |
| `구역의 도형/` | 별도 도형 묶음 | 미지원 | 파일 구조 조사 후 후속 |
| `도로명주소 건물 도형/` | 별도 건물 도형 묶음 | 미지원 또는 전자지도와 중복 가능 | 전자지도 `TL_SPBD_BULD`와 중복 여부 확인 후 후속 |
| `도로명주소 출입구 정보/` | 별도 출입구 정보 | 미지원 또는 locsum/navi와 중복 가능 | 위치정보요약DB와 중복 여부 확인 후 후속 |

## 중요한 실행 전 보정

초안은 단일 `YYYYMM=202604`를 모든 자료에 적용했지만, 현재 로컬 데이터는 자료별 기준월이 다르다.

| 자료 | 실제 기준월 | 환경변수 |
|------|-------------|----------|
| 도로명주소 한글 전체분 | `202603` | `JUSO_YYYYMM=202603` |
| 위치정보요약DB 전체분 | `202604` | `LOCSUM_YYYYMM=202604` |
| 내비게이션용DB 전체분 | `202604` | `NAVI_YYYYMM=202604` |

정합성 C10은 기준월 불일치를 감지하므로, 이번 검증에서는 C10 WARN/ERROR가 나올 수 있다. 이 결과는 로더 버그라기보다 서로 다른 배포월 조합에서 생기는 기대 가능한 신호로 해석한다. "동월 전체분" 검증이 필요하면 도로명주소 한글 전체분도 `202604` 자료로 맞춰 받아 재실행해야 한다.

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
PLAN_ONLY=1 bash scripts/fullload_test.sh
```

기대 결과:

- `202603_도로명주소 한글_전체분`
- `202604_위치정보요약DB_전체분.zip`
- `202604_내비게이션용DB_전체분`

세 경로가 모두 존재해야 한다.

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

중간 row count 기준:

| 테이블 | 기대 |
|--------|------|
| `tl_juso_text` | 17개 `rnaddrkor_*.txt` 합계. 서울 단일 52만+보다 충분히 큼 |
| `tl_locsum_entrc` | 좌표가 있는 `entrc_*.txt` 행만 적재 |
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
| C10 | 이번 혼합 기준월에서는 WARN/ERROR 가능. 동월 자료 확보 후 재검증 필요 |

### Phase 6: smoke test

스크립트는 DTO 구조에 맞춰 다음을 확인한다.

- `GeocodeResponse.result.point`
- `ReverseResponse.result`
- `SearchResponse.result`
- `ZipcodeResponse.result`

실패 시 smoke test 주소가 실제 적재 월 데이터에 존재하는지 먼저 확인한다.

## 예상 시간

| Phase | 내용 | 예상 |
|-------|------|------|
| -1 | `PLAN_ONLY=1` preflight | 즉시 |
| 0 | Docker/Python 준비 | 5~20분 |
| 1 | DDL | 5~30초 |
| 2 | 텍스트 3종 COPY | 20~60분 |
| 3 | SHP 9 레이어 전국 적재 | 20~60분 |
| 4 | 링크 해소 + MV swap | 10~30분 |
| 5 | C1~C10 | 3~20분 |
| 6 | smoke test | 수초 |

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
└── notes.md
```

`artifacts/`는 git에 커밋하지 않는다. PR에는 요약과 주요 오류 sample만 문서/코멘트로 남긴다.

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
| C3 | WARN | 3,510,265 | 위치정보요약DB 직접 출입구 미해소 |
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
| T-038 `tl_juso_parcel_link` 구현 | `jibun_rnaddrkor_*` full snapshot과 daily `LNBR` delta를 적재할 DDL/loader 필요 |
| T-030 상세주소 동 도형 로더 | `건물군 내 상세주소 동 도형` 자료를 별도 테이블로 쓸지 결정 필요 |
| T-031 출입구 정보 별도 로더 | `도로명주소 출입구 정보`와 위치정보요약DB/내비 진입점 중복 관계 확인 필요 |
| T-032 full-load 벤치마크 리포트 | 실제 실행 후 COPY 속도, MV swap 시간, C1~C10 결과, smoke 결과 정리 |
