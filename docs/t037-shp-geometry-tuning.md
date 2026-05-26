# T-037 SHP geometry 포함 대형 레이어 적재 튜닝

본 문서는 T-033/T-034에서 남겨 둔 `TL_SPBD_BULD` 적재 병목을 실제 `data/juso` SHP와 Docker PostGIS로 검증한 기록이다. 목표는 전체 전국 재적재를 반복하기 전에, geometry를 포함한 대형 SHP 레이어에서 GDAL append 경로를 어디까지 줄일 수 있는지 확인하고, T-027 최종 클린 로드가 비교할 수 있는 기준선을 남기는 것이다.

## 배경

T-034는 geometry가 필요 없는 `TL_SPRD_INTRVL`을 직접 DBF scan + `psycopg COPY`로 바꿔 큰 개선을 만들었다. 하지만 `TL_SPBD_BULD`는 건물 polygon geometry를 실제 운영 테이블에 넣어야 한다. 따라서 `TL_SPRD_INTRVL`처럼 DBF만 읽는 방식으로 단순 치환할 수 없다.

기존 `TL_SPBD_BULD` 경로는 다음 형태였다.

1. `gdal.VectorTranslate()`를 대상 운영 테이블 `tl_spbd_buld_polygon`에 바로 append한다.
2. `SQLStatement`로 필요한 key 컬럼만 projection한다.
3. `PG_USE_COPY=YES`를 설정하지만, 실제 관찰에서는 대형 geometry append 구간이 여전히 오래 걸렸다.

T-037에서는 운영 테이블에 직접 append하지 않고 임시 staging table을 만든 뒤, PostgreSQL 내부 `INSERT ... SELECT`로 운영 테이블에 옮기는 방식을 검증했다.

## 결정

`TL_SPBD_BULD`만 staging table 경로로 분기한다.

- GDAL은 `public._kraddr_stage_spbd_buld_polygon` 임시성 테이블을 `accessMode="overwrite"`로 만든다.
- staging 생성에도 기존 `plan.sql_statement`를 사용해 필요한 컬럼만 projection한다.
- GDAL 설정은 기존과 같이 `PG_USE_COPY=YES`, `SHAPE_ENCODING=CP949`를 유지한다.
- staging table에는 spatial index를 만들지 않는다.
- 운영 테이블에는 SQLAlchemy sync connection으로 `INSERT ... SELECT`한다.
- insert transaction에서는 `SET LOCAL search_path = public, x_extension`를 명시한다. PostGIS extension이 `x_extension`에 있으므로 `geometry(MultiPolygon, 5179)` cast가 이 search path를 필요로 한다.
- `bd_mgt_sn`과 key 문자열은 `BTRIM(...::text)` 후 빈 문자열을 `NULL`로 정규화한다.
- `buld_mnnm`, `buld_slno`는 빈 문자열을 `NULL`로 정규화한 뒤 `integer`로 cast한다.
- geometry는 `ST_Multi(geom)::geometry(MultiPolygon, 5179)`로 운영 테이블 타입에 맞춘다.
- staging table은 시작 전과 종료 `finally`에서 모두 `DROP TABLE IF EXISTS`로 정리한다.

## 구현 범위

| 파일 | 내용 |
|------|------|
| `src/kraddr/geo/loaders/shp/polygons_loader.py` | `TL_SPBD_BULD` 전용 staging COPY 경로 추가, stage drop finally 보장, projection staging 적용 |
| `tests/unit/test_shp_loader_gdal.py` | `TL_SPBD_BULD`가 generic append가 아니라 staging 경로를 타는지, `PG_USE_COPY`/projection/search_path/geometry cast 계약을 source-level로 고정 |

DB 스키마 변경은 없다. 외부 호출 표면(`load_shp_polygons`, CLI `load shp`, `load shp-all`, admin job)은 그대로다.

## 실행 환경

| 항목 | 값 |
|------|----|
| 실행일 | 2026-05-26 |
| 작업 브랜치 | `codex/t037-shp-geometry-tuning` |
| 기준 commit | `05ab818` 위 작업 |
| OS | WSL2 Linux `6.6.87.2-microsoft-standard-WSL2` |
| CPU | AMD Ryzen 7 7840HS, 8 cores / 16 threads |
| 메모리 | 29GiB total, 실행 전 available 약 27GiB |
| ext4 여유 공간 | `/dev/sdd` 1007G 중 759G available |
| NTFS 데이터 공간 | `/mnt/f` 932G 중 267G available |
| Docker DB | `kraddr-geo-t027-db-1`, `postgis/postgis:16-3.5`, host port `15432` |
| PostgreSQL | 16.9 |
| GDAL | 3.8.4 |
| 실제 데이터 | `/mnt/f/dev/python-kraddr-geo/data/juso/도로명주소 전자지도` |

## 측정 명령

세종/경기도 단일 `TL_SPBD_BULD` 측정은 같은 전용 DB `kraddr_geo_t037`에서 수행했다.

```bash
DB=kraddr_geo_t037
PGPASSWORD=addr dropdb -h localhost -p 15432 -U addr --if-exists "$DB"
PGPASSWORD=addr createdb -h localhost -p 15432 -U addr "$DB"
KRADDR_GEO_PG_DSN="postgresql+psycopg://addr:addr@localhost:15432/$DB" \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/kraddr-geo init-db
```

단일 레이어 측정은 내부 load plan에서 `TL_SPBD_BULD`만 골라 수행했다.

```bash
/usr/bin/time -v env \
  KRADDR_GEO_PG_DSN="postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t037" \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/python - <<'PY'
import asyncio
from pathlib import Path

from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.loaders.shp.polygons_loader import build_shp_load_plan, _load_plans_sync

path = Path("/mnt/f/dev/python-kraddr-geo/data/juso/도로명주소 전자지도/세종특별자치시")
plans = tuple(
    plan for plan in build_shp_load_plan(path, source_yyyymm="202604")
    if plan.source_layer == "TL_SPBD_BULD"
)
engine = make_async_engine()
try:
    print(_load_plans_sync(engine.url.render_as_string(hide_password=False), plans, "full", True, None, None))
finally:
    asyncio.run(engine.dispose())
PY
```

세종 public CLI 검증은 별도 DB `kraddr_geo_t037_cli`에서 수행했다.

```bash
KRADDR_GEO_PG_DSN="postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t037_cli" \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/kraddr-geo load shp \
  "/mnt/f/dev/python-kraddr-geo/data/juso/도로명주소 전자지도/세종특별자치시" \
  --mode full --yyyymm 202604
```

## 실험 과정과 결과

### 세종특별자치시 단일 `TL_SPBD_BULD`

| 경로 | 행 수 | wall clock | 최대 RSS | 결과 |
|------|------:|-----------:|---------:|------|
| 기존 운영 append 경로 | 55,819 | 38.36초 | 124,032KB | 성공 |
| raw staging, 전체 DBF 속성 복사 | 55,819 | 18.96초 | 124,592KB | 성공 |
| projection staging, 필요한 컬럼만 복사 | 55,819 | 18.59초 | 124,032KB | 성공 |

세종 기준으로 staging table 경로는 기존 append 대비 약 2.06배 빨랐다. raw staging과 projection staging의 차이는 작았지만, projection staging은 대형 시도에서 의미가 크므로 최종 구현으로 채택했다.

### 경기도 단일 `TL_SPBD_BULD`

경기도 `TL_SPBD_BULD.dbf` header record count는 1,649,975행이다.

| 경로 | 행 수 | wall clock | 최대 RSS | 결과 |
|------|------:|-----------:|---------:|------|
| raw staging, 전체 DBF 속성 복사 | 617,214 feature 부근에서 중단 | 22분 58.46초 | 137,584KB | `pg_terminate_backend()`로 중단 |
| projection staging, 필요한 컬럼만 복사 | 1,649,975 | 40분 17.15초 | 137,468KB | 성공 |

raw staging 실험은 staging table에 원본 DBF의 모든 속성 컬럼을 COPY하는 경로였다. `pg_stat_activity`에서는 `COPY "_kraddr_stage_spbd_buld_polygon" (...) FROM STDIN` 상태로, PostgreSQL은 `ClientRead`에서 GDAL 입력을 기다리고 있었다. 22분 58.46초 경과 시점에도 끝나지 않아 테스트 DB의 backend를 `pg_terminate_backend()`로 끊었고, 이 중단 덕분에 projection staging 필요성이 분명해졌다.

projection staging은 같은 실제 경기도 파일을 끝까지 적재했다. 종료 후 검증 결과:

```sql
SELECT count(*) AS tl_spbd_buld_polygon_rows,
       count(source_file) AS source_file_rows,
       count(source_yyyymm) AS source_yyyymm_rows
FROM tl_spbd_buld_polygon;
```

| 항목 | 값 |
|------|---:|
| `tl_spbd_buld_polygon_rows` | 1,649,975 |
| `source_file_rows` | 1,649,975 |
| `source_yyyymm_rows` | 1,649,975 |
| `source_file` | `경기도/41000/TL_SPBD_BULD.shp` |
| 종료 후 staging table | 없음 |

경기도는 성공했지만 여전히 40분대다. 즉 T-037 구현은 작은/중간 시도에서 기존 append 대비 시간을 줄이고, projection 없는 staging 실수를 피하지만, 대형 geometry SHP의 주 병목은 GDAL이 SHP geometry를 읽어 PostgreSQL COPY stream으로 넘기는 단계에 남아 있다.

### 세종특별자치시 public CLI 9개 레이어

`kraddr-geo load shp ... --mode full --yyyymm 202604`로 전체 9개 SHP 보조 레이어를 적재했다.

| 항목 | 값 |
|------|---:|
| loaded layers | 9 |
| wall clock | 1분 19.54초 |
| 최대 RSS | 128,416KB |
| `tl_spbd_buld_polygon` | 55,819행 |
| `tl_sprd_intrvl` | 100,009행 |
| `tl_sprd_rw` | 7,429행 |
| 종료 후 staging table | 없음 |

기존 GDAL 레이어에서는 `Layer creation options ignored since an existing layer is being appended to` 경고가 반복되고, `TL_SPRD_RW.shp`에서는 winding order 자동 보정 경고가 나왔다. 두 경고는 T-033/T-034에서도 관찰된 기존 동작이며, 이번 적재는 정상 완료됐다.

## 해석

이번 변경은 `TL_SPBD_BULD`에서 "운영 테이블 직접 append"를 "projection staging + 운영 테이블 insert-select"로 바꾼다. 이 전략은 다음 효과가 있다.

- 운영 테이블의 타입/constraint/index와 GDAL append 경로를 직접 결합하지 않는다.
- staging 생성 시 `accessMode="overwrite"`를 사용할 수 있어 GDAL PostgreSQL driver가 COPY 경로를 더 잘 탄다.
- projection을 staging에 적용해 불필요한 DBF 속성 컬럼 전송을 막는다.
- 운영 테이블 insert-select 구간에서 trimming, NULL normalization, geometry type cast를 명시적으로 관리한다.
- 실패/취소 시 staging table을 남기지 않는다.

다만 대형 geometry 파일에서는 여전히 GDAL SHP decode + COPY stream 자체가 길다. 경기도 1,649,975 polygon은 단일 레이어만 40분 17초가 걸렸다. 전국 전체 시간은 T-027 최종 클린 로드에서 다시 확인해야 하며, 경기도급 대형 시도의 추가 개선은 별도 PR 후보로 남긴다.

## 운영상 주의

- staging table 이름은 고정이다. 현재 `load_jobs`와 full-load batch는 직렬 실행을 전제로 하므로 같은 DB에서 두 개의 `TL_SPBD_BULD` 적재를 동시에 실행하지 않는다.
- `mode="full"`은 대상 운영 테이블을 먼저 truncate한다. staging/insert 중 실패하면 해당 레이어 운영 테이블이 비어 있을 수 있다. 전국 full-load에서는 ADR-017 batch gate와 MV swap이 최종 노출을 막아야 한다.
- staging table은 `finally`에서 drop되지만, 프로세스가 강제 종료되면 다음 실행 시작 시 다시 drop한다.
- `pg_stat_progress_copy`의 `tuples_processed`는 이번 경기도 실행에서 누적형으로 안정적으로 보이지 않았다. 진행률 판단은 최종 row count와 `/usr/bin/time` 값을 기준으로 한다.

## 검증

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py -q
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kraddr/geo/loaders/shp/polygons_loader.py tests/unit/test_shp_loader_gdal.py
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy src/kraddr/geo/loaders/shp/polygons_loader.py
```

실제 Docker PostGIS 검증:

- `kraddr_geo_t037`: 세종 단일 `TL_SPBD_BULD` projection staging 55,819행, 18.59초.
- `kraddr_geo_t037`: 경기도 단일 `TL_SPBD_BULD` projection staging 1,649,975행, 40분 17.15초.
- `kraddr_geo_t037_cli`: 세종 SHP 9개 레이어 public CLI 적재 성공, 1분 19.54초.

## 후속 작업

- T-027 최종 클린 로드에서 전국 SHP 전체 시간이 실제로 얼마나 줄었는지 확인한다.
- 경기도급 대형 polygon 레이어가 계속 전체 시간을 지배하면, 다음 후보는 시도별 SHP를 더 작은 시군구 단위로 나눠 병렬 staging 후 serial merge하는 방식, 또는 GDAL/OGR Arrow·COPY 경로를 별도 실험하는 것이다. 이 결정은 별도 ADR/PR에서 다룬다.
