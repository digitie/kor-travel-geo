# T-034 SHP append 병목 튜닝

본 문서는 T-033 전국 full-load에서 확인한 SHP 적재 병목 중 `TL_SPRD_INTRVL` 레이어를 먼저 개선한 기록이다. 목표는 전체 full-load를 다시 반복하지 않고도 병목 경로를 분리 측정해, 후속 T-035/T-027이 비교할 수 있는 재현 가능한 기준선을 남기는 것이다.

## 배경

T-033 전국 full-load는 성공했지만 전체 4시간 8분 2초 중 SHP 17개 시도 × 9개 레이어 적재가 약 3시간 37분 32초를 차지했다. 특히 `TL_SPRD_INTRVL`은 geometry가 없는 DBF 속성 보조 테이블인데도 GDAL `VectorTranslate` 경로에서 다음 형태의 행 단위 insert로 관측됐다.

```sql
INSERT INTO "tl_sprd_intrvl" (...) VALUES (...)
```

`PG_USE_COPY=YES`를 GDAL config option으로 주고 있었지만, `TL_SPRD_INTRVL`처럼 `geometryType="NONE"`인 SQL projection 레이어에는 기대한 COPY 경로가 적용되지 않는 것으로 보인다. T-033 관찰 기준 경기도 `TL_SPRD_INTRVL` 단일 레이어는 약 24분 이상 걸렸고, 전국 `tl_sprd_intrvl` 최종 행 수는 16,993,167행이었다.

## 결정

`TL_SPRD_INTRVL`만 GDAL을 우회한다. 나머지 도형 레이어는 기존 GDAL 경로를 유지한다.

- `TL_SPRD_INTRVL.dbf`를 직접 읽는다.
- 필요한 원천 컬럼만 추출한다.
  - `SIG_CD` → `sig_cd`
  - `RDS_MAN_NO` → `rds_man_no`
  - `BSI_INT_SN` → `bsi_int_sn`
  - `ODD_BSI_MN` → `start_bsi_no`
  - `EVE_BSI_MN` → `end_bsi_no`
- `source_file`, `source_yyyymm` 추적 컬럼은 기존 SHP projection과 같은 값을 넣는다.
- PostgreSQL에는 `psycopg` sync connection의 `COPY ... FROM STDIN`으로 적재한다.
- 전체 `load_shp_polygons()` 인터페이스와 진행률 callback 계약은 유지한다.

이 변경은 도형 처리, 좌표계 변환, winding order 보정에는 관여하지 않는다. T-034 당시에는 `TL_SPBD_BULD`, `TL_SPRD_RW`, 행정경계 polygon 레이어가 계속 GDAL `VectorTranslate` 직접 append 경로를 담당했다. 이후 T-037에서 `TL_SPBD_BULD`만 projection staging table 경로로 분기했다.

## 구현 범위

변경 파일:

| 파일 | 내용 |
|------|------|
| `src/kraddr/geo/loaders/shp/polygons_loader.py` | `TL_SPRD_INTRVL` 전용 DBF parser + `COPY` 적재 경로 추가, row dataclass 기반 COPY projection, CP949/truncated record 오류 문맥 보강 |
| `tests/unit/test_shp_loader_gdal.py` | synthetic DBF 기반 projection 테스트, 직접 COPY 경로 라우팅, deleted record skip, decode/truncated 오류 테스트 추가 |

DB 스키마 변경은 없다. `tl_sprd_intrvl`의 기존 컬럼과 PK `(sig_cd, rds_man_no, bsi_int_sn)`를 그대로 사용한다.

T-036 후속 리뷰 반영으로 COPY 컬럼과 row tuple shape는 `RoadIntervalRow` dataclass와 `ROAD_INTERVAL_COPY_COLUMNS` 상수에서 함께 관리한다. 스키마 컬럼을 바꿀 때 SQL column list와 `copy.write_row()` tuple 순서가 흩어지지 않도록 하기 위한 방어다. DBF decode 실패는 `LoaderError`에 파일 경로, record 번호, 필드명, byte slice를 포함하고, record truncation도 expected/actual byte 수, header `record_count`, file size를 함께 출력한다.

## 실행 환경

| 항목 | 값 |
|------|----|
| 실행일 | 2026-05-26 |
| 작업 브랜치 | `codex/t034-shp-append-tuning` |
| OS | WSL2 Linux `6.6.87.2-microsoft-standard-WSL2` |
| CPU | AMD Ryzen 7 7840HS, 16 logical cores |
| 메모리 | 29GiB total, 실행 시 available 약 27GiB |
| ext4 여유 공간 | `/dev/sdd` 1007G 중 758G available |
| NTFS 데이터 공간 | `/mnt/f` 932G 중 267G available |
| Docker DB | `kraddr-geo-t027-db-1`, `postgis/postgis:16-3.5`, host port `15432` |
| 실제 데이터 | `/home/digitie/kraddr-geo-data/juso/도로명주소 전자지도` |

## 실제 DBF 구조 확인

세종특별자치시와 경기도의 `TL_SPRD_INTRVL.dbf` header를 확인했다.

| 지역 | record count | header length | record length | 필드 |
|------|-------------:|--------------:|--------------:|------|
| 세종특별자치시 | 100,009 | 289 | 62 | `BSI_INT_SN`, `EVE_BSI_MN`, `EVE_BSI_SL`, `ODD_BSI_MN`, `ODD_BSI_SL`, `OPERT_DE`, `RDS_MAN_NO`, `SIG_CD` |
| 경기도 | 2,677,715 | 289 | 62 | 동일 |

로드 대상 컬럼은 기존 SQL projection이 쓰던 5개 필드뿐이다. `EVE_BSI_SL`, `ODD_BSI_SL`, `OPERT_DE`는 현재 운영 테이블에 컬럼이 없어 적재하지 않는다.

## 측정 명령

튜닝 전 세종 단일 레이어 기준선은 코드 변경 전 `main` 경로에서 같은 방식으로 측정했다.

```bash
DB=kraddr_geo_t034_before
PGPASSWORD=addr dropdb -h localhost -p 15432 -U addr --if-exists "$DB"
PGPASSWORD=addr createdb -h localhost -p 15432 -U addr "$DB"
KRADDR_GEO_PG_DSN="postgresql+psycopg://addr:addr@localhost:15432/$DB" \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/kraddr-geo init-db

/usr/bin/time -v env \
  KRADDR_GEO_PG_DSN="postgresql+psycopg://addr:addr@localhost:15432/$DB" \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/python - <<'PY'
from pathlib import Path
from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.loaders.shp.polygons_loader import build_shp_load_plan, _load_plans_sync

path = Path("/home/digitie/kraddr-geo-data/juso/도로명주소 전자지도/세종특별자치시")
plans = tuple(p for p in build_shp_load_plan(path, source_yyyymm="202604") if p.source_layer == "TL_SPRD_INTRVL")
engine = make_async_engine()
try:
    print(_load_plans_sync(engine.url.render_as_string(hide_password=False), plans, "full", True, None, None))
finally:
    import asyncio
    asyncio.run(engine.dispose())
PY
```

튜닝 후 세종과 경기도 단일 레이어도 같은 내부 호출로 측정했다. 세종 9개 레이어 전체 검증은 public CLI를 사용했다.

```bash
KRADDR_GEO_PG_DSN="postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t034_sejong" \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/kraddr-geo load shp \
  "/home/digitie/kraddr-geo-data/juso/도로명주소 전자지도/세종특별자치시" \
  --mode full --yyyymm 202604
```

## 결과

### 단일 `TL_SPRD_INTRVL` 레이어

| 대상 | 행 수 | 변경 전 | 변경 후 | 개선 |
|------|------:|--------:|--------:|-----:|
| 세종특별자치시 `TL_SPRD_INTRVL` | 100,009 | 36.12초 | 1.59초 | 약 22.7배 빠름 |
| 경기도 `TL_SPRD_INTRVL` | 2,677,715 | T-033 관찰상 약 24분 이상 | 15.88초 | 대형 시도에서 수십 배 이상 개선 예상 |

세종 변경 전 측정의 `/usr/bin/time -v` 핵심값:

| 항목 | 값 |
|------|----|
| wall clock | 0:36.12 |
| 최대 RSS | 124,404KB |
| voluntary context switches | 100,337 |
| file system inputs | 77,416 |
| exit status | 0 |

세종 변경 후 측정의 핵심값:

| 항목 | 값 |
|------|----|
| wall clock | 0:01.59 |
| 최대 RSS | 114,080KB |
| voluntary context switches | 50 |
| file system inputs | 0 |
| exit status | 0 |

경기도 변경 후 측정의 핵심값:

| 항목 | 값 |
|------|----|
| wall clock | 0:15.88 |
| 최대 RSS | 168,464KB |
| 적재 행 수 | 2,677,715 |
| `source_file` | `경기도/41000/TL_SPRD_INTRVL.shp` |
| `source_yyyymm` | `202604` |
| exit status | 0 |

### 세종특별자치시 SHP 9개 레이어 전체

`kraddr-geo load shp ... --mode full --yyyymm 202604` 실행 결과:

| 항목 | 값 |
|------|----|
| wall clock | 0:31.69 |
| 최대 RSS | 128,808KB |
| loaded layers | 9 |
| `tl_sprd_intrvl` | 100,009행 |
| `tl_spbd_buld_polygon` | 55,819행 |
| `tl_sprd_rw` | 7,429행 |
| DB 크기 | 80MB |

기존 일지의 세종 9개 레이어 전체 기준선은 59.09초였다. 이번 변경 후 31.69초로 줄었고, 남은 시간은 대부분 GDAL이 계속 담당하는 도형 레이어에서 발생한다.

## 해석

`TL_SPRD_INTRVL`은 SHP geometry가 필요 없는 순수 DBF 속성 보조 테이블이다. GDAL PostgreSQL driver를 거치면 `geometryType="NONE"`인 append에서도 COPY가 강제되지 않아 행 단위 insert에 가까운 비용이 발생했다. 직접 DBF scan + `COPY`로 바꾸면 다음 효과가 있다.

- PostgreSQL round trip이 행 단위 insert에서 streaming COPY로 줄어든다.
- GDAL SQL projection과 PostgreSQL layer append 경로를 거치지 않는다.
- source metadata는 기존과 동일하게 유지된다.
- `load_shp_polygons()`의 외부 호출자는 변경을 인식할 필요가 없다.

전국 전체 시간 절감 추정은 보수적으로 봐야 한다. T-033에서 SHP 전체는 약 3시간 37분 32초였고, `TL_SPRD_INTRVL` 외에도 `TL_SPBD_BULD`가 큰 비중을 차지한다. 다만 `TL_SPRD_INTRVL` 전국 16,993,167행이 모두 새 경로를 타면, 기존 GDAL append 병목 중 상당 부분은 제거된다.

## 남은 한계

- `TL_SPBD_BULD`는 T-037에서 projection staging table 경로로 보강했다. 세종 단일 레이어는 기존 append 38.36초에서 18.59초로 줄었지만, 경기도 1,649,975행 단일 레이어는 여전히 40분 17.15초가 걸렸다. 대형 geometry SHP decode/COPY stream 비용은 후속 튜닝 후보로 남는다.
- 이번 PR은 전체 전국 full-load를 다시 돌리지 않았다. 전국 재적재는 T-027 최종 클린 로드에서 DB 삭제 후 처음부터 검증한다.
- DBF parser는 현재 `TL_SPRD_INTRVL`의 실제 필드와 CP949/ASCII 숫자 필드에 맞춰 최소 구현했다. 다른 DBF 레이어로 일반화하지 않는다.
- 동일 시도 `TL_SPRD_INTRVL`을 append 모드로 중복 재실행하면 기존 GDAL append와 마찬가지로 PK 충돌이 날 수 있다. full-load의 첫 시도는 truncate, 이후 시도는 시도별 key가 달라 충돌하지 않는 운영 경로를 기준으로 한다.
- deleted record(`record[:1] == b"*"`)는 copy 대상에서 제외한다. parser 내부 `record_no`는 deleted record를 포함한 DBF header record index이고, progress의 `processed`/`copied`는 실제 copy row 기준이다. progress denominator는 header `record_count`라 deleted record가 많으면 마지막 1.0 callback 전까지 약간 낮게 보일 수 있다.

## 검증

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_shp_loader_gdal.py -q
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check src/kraddr/geo/loaders/shp/polygons_loader.py tests/unit/test_shp_loader_gdal.py
```

추가로 실제 Docker PostGIS에서 다음을 확인했다.

- `kraddr_geo_t034_before`: 세종 `TL_SPRD_INTRVL` 기존 경로 100,009행, 36.12초.
- `kraddr_geo_t034_after`: 세종 `TL_SPRD_INTRVL` 새 경로 100,009행, 1.59초.
- `kraddr_geo_t034_after`: 경기도 `TL_SPRD_INTRVL` 새 경로 2,677,715행, 15.88초.
- `kraddr_geo_t034_sejong`: 세종 9개 SHP 레이어 전체 적재 성공, 31.69초.

## 후속 작업

- T-035: MV refresh/swap benchmark를 별도 PR에서 진행한다.
- T-036: `maplibre-vworld-js` upstream main과 UI dependency SHA를 동기화한다.
- T-037: 완료. `TL_SPBD_BULD`는 GDAL projection staging + 운영 테이블 insert-select 경로로 바꿨다. 도형 레이어는 geometry 변환과 winding 보정이 얽혀 있어 `TL_SPRD_INTRVL`처럼 단순 DBF COPY로 옮기지 않는다.
- T-027: 남은 튜닝과 증분 로더 작업을 모두 머지한 뒤 DB를 삭제하고 실제 전체 데이터를 처음부터 다시 적재한다.
