# T-042 `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 적재/조회

T-042는 T-041/ADR-027에서 문서화한 `TL_SPPN_MAKAREA`를 실제 운영 스키마와 loader, geocode/reverse 보조 조회 경로에 연결한 작업이다. 이 레이어는 "지점번호표기 의무지역"의 polygon이며, 개별 국가지점번호판이나 시설물 point 목록이 아니다. 따라서 도로명/지번 주소의 정본 materialized view인 `mv_geocode_target`에 섞지 않고, 별도 테이블 `tl_sppn_makarea`와 `x_extension.sppn_makarea` 응답 확장으로 노출한다.

## 범위

이번 구현에 포함한 범위는 다음과 같다.

| 구분 | 반영 내용 |
|------|-----------|
| 스키마 | `tl_sppn_makarea` DDL, GiST 공간 인덱스, `sig_cd` btree 인덱스, Alembic `0007_t042_sppn_makarea` |
| loader | `TL_SPPN_MAKAREA.shp` 또는 `구역의 도형` ZIP/디렉터리 탐지, GDAL Python binding 기반 staging 적재, `MultiPolygon 5179` 정규화, `SIG_CD + MAKAREA_ID` upsert |
| CLI/API job | `ktgctl load sppn-makarea`, API queue kind `sppn_makarea_load`, source set optional child 연결 |
| core | 국가지점번호 문자열 parser, EPSG:5179 좌표 → 국가지점번호 formatter, geocode/reverse extension 조립 |
| infra repo | `GeocodeRepository.lookup_sppn_area()`, `ReverseRepository.sppn_areas()` raw SQL |
| DTO | `SppnMakareaContext`, `GeocodeExtension.national_point_number`, `GeocodeExtension.sppn_makarea`, `ReverseExtension.sppn_makarea` |
| 테스트 | parser/formatter, core fake repo, SQL 계약, loader 탐지/정규화, CLI/API/source set/DDL/migration 계약, 실제 Docker 적재 optional integration |

이번 구현에 포함하지 않은 범위는 다음과 같다.

- `MAKAREA_NM`만으로 좌표를 반환하는 구역명 검색. 이는 주소 geocode가 아니라 polygon 검색 또는 관리 UI overlay 검색에 가깝다.
- `mv_geocode_target` union. 주소 1행 계약과 `bd_mgt_sn` 중심 lookup을 깨지 않기 위해 제외한다.
- 디버그 UI polygon overlay. T-044의 `maplibre-vworld-js` 0.1.0 문서-only 재확인 결과를 바탕으로, 별도 UI 구현 PR에서 `PolygonArea` 또는 동등한 지도 primitive로 구현한다.
- 전국 `구역의 도형` 전체 적재. 이번 실제 검증은 세종특별자치시 파일로 수행했고, T-027 최종 클린 로드에서 전국 적재 포함 여부와 시간을 다시 기록한다.

## 원천 데이터와 key

세종 실제 파일:

```text
/mnt/f/dev/geodata/juso/구역의 도형/구역의도형_전체분_세종특별자치시.zip
```

ZIP 내부 layer:

```text
36110/TL_SPPN_MAKAREA.shp
36110/TL_SPPN_MAKAREA.shx
36110/TL_SPPN_MAKAREA.dbf
```

세종 파일에서 확인한 주요 필드는 다음과 같다.

| 원천 필드 | 운영 컬럼 | 설명 |
|-----------|-----------|------|
| `SIG_CD` | `sig_cd` | 시군구 코드. 세종은 `36110` |
| `MAKAREA_ID` | `makarea_id` | 시군구 내 표기 의무지역 ID. `sig_cd + makarea_id`가 primary key |
| `NTFC_YN` | `ntfc_yn` | 고시 여부 |
| `MAKAREA_NM` | `makarea_nm` | 표기 의무지역명. 표시명이며 unique key로 사용하지 않음 |
| `NTFC_DE` | `ntfc_de` | 고시일 |
| `MVM_RES_CD` | `mvm_res_cd` | 이동/변동 사유 코드 |
| `MVMN_RESN` | `mvmn_resn` | 변동 사유 |
| `OPERT_DE` | `opert_de` | 작업일 |
| `MAKAREA_AR` | `makarea_ar` | 원천 면적 값 |
| `MVMN_DESC` | `mvmn_desc` | 변동 설명 |
| geometry | `geom` | 운영에서는 `geometry(MultiPolygon, 5179)`로 통일 |

실측 결과 세종 `TL_SPPN_MAKAREA`는 146행이고, `SIG_CD + MAKAREA_ID` distinct key도 146개다. T-041에서 확인한 경상남도 파일은 3,486행이며 역시 같은 key가 distinct였다.

## 국가지점번호 parser/formatter 규칙

국가지점번호 문자열은 두 개의 한글 100km 격자 문자와 4자리 동서 좌표, 4자리 남북 좌표로 처리한다.

예:

```text
다사 6925 4045
```

이번 parser는 다음 형태를 허용한다.

- `다사 6925 4045`
- `다사69254045`
- `다사-6925-4045`

주소 문장 내부에 우연히 포함된 패턴이 일반 주소 geocode를 가로채지 않도록 전체 문자열이 국가지점번호 형식과 일치할 때만 parser가 성공한다. 예를 들어 `세종시 다사 6925 4045 부근`은 국가지점번호 geocode로 처리하지 않는다.

좌표 계산 규칙은 EPSG:5179 기준 100km 한글 격자와 10m 숫자 격자를 사용한다.

```text
GRID_LETTERS = 가나다라마바사아자차카타파하
X_ORIGIN_5179 = 700000
Y_ORIGIN_5179 = 1300000
GRID_SIZE_M = 100000
CELL_SIZE_M = 10
```

`다사 6925 4045`는 다음 EPSG:5179 10m cell 중심으로 계산된다.

```text
x = 969255
y = 1940455
```

formatter는 EPSG:5179 점이 속한 10m cell을 같은 규칙으로 문자열화한다. 실제 적재 검증에서는 polygon 내부 `ST_PointOnSurface()` 좌표를 formatter로 국가지점번호 문자열로 바꾼 뒤, 다시 geocode parser와 polygon 포함 검증을 통과하는지 확인했다.

참고한 공개 설명:

- 행정안전부 국가지점번호 설명자료: `https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000009&nttId=66987`
- 국가지점번호 좌표 예시 정리: `https://progworks.tistory.com/44`

## 스키마

운영 테이블은 다음 계약을 갖는다.

```sql
CREATE TABLE IF NOT EXISTS tl_sppn_makarea (
  sig_cd          TEXT NOT NULL,
  makarea_id      TEXT NOT NULL,
  ntfc_yn         TEXT,
  makarea_nm      TEXT,
  ntfc_de         TEXT,
  mvm_res_cd      TEXT,
  mvmn_resn       TEXT,
  opert_de        TEXT,
  makarea_ar      NUMERIC(12,3),
  mvmn_desc       TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT NOT NULL,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, makarea_id),
  CHECK (char_length(sig_cd) = 5),
  CHECK (btrim(makarea_id) <> '')
);

CREATE INDEX IF NOT EXISTS idx_sppn_makarea_geom
  ON tl_sppn_makarea
  USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_sppn_makarea_sig
  ON tl_sppn_makarea (sig_cd);
```

`geom`은 원천이 `Polygon`이어도 운영에서는 `MultiPolygon`으로 통일한다. loader는 staging insert-select에서 다음 정규화를 수행한다.

```sql
ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Force2D(geom)), 3))
  ::geometry(MultiPolygon, 5179)
```

## Loader

`load_sppn_makarea()`는 다음 입력을 허용한다.

| 입력 | 동작 |
|------|------|
| `구역의도형_전체분_세종특별자치시.zip` | ZIP 내부에서 정확히 하나의 `TL_SPPN_MAKAREA.shp`를 찾는다 |
| `구역의 도형/` 디렉터리 | 디렉터리 바로 아래 ZIP들을 정렬해 차례로 처리한다 |
| 추출된 디렉터리 | 하위 `TL_SPPN_MAKAREA.shp`들을 정렬해 처리한다 |
| `TL_SPPN_MAKAREA.shp` 단일 파일 | `.shp`, `.shx`, `.dbf` sidecar 존재를 확인한 뒤 처리한다 |

지원 mode는 `full`, `append`, `delta`다. 현재 `append`와 `delta`는 같은 upsert 의미를 갖고, `full`은 대상 테이블을 먼저 `TRUNCATE`한다. source set full-load plan에서는 optional `sppn_makarea`가 선택되면 child payload에 `mode="full"`을 넣는다.

GDAL 설정:

```text
PG_USE_COPY=YES
SHAPE_ENCODING=CP949
srcSRS=EPSG:5179
dstSRS=EPSG:5179
geometryType=PROMOTE_TO_MULTI
```

loader는 `_staging_sppn_makarea`라는 고정 staging table을 사용하므로, 같은 DB에서 동시에 두 개의 `TL_SPPN_MAKAREA` 적재가 실행되면 서로 stage를 지울 수 있다. 이를 막기 위해 `pg_try_advisory_lock(hashtext('kortravelgeo.loaders.sppn_makarea_loader.stage'))`를 적재 전체 구간에 걸고, lock을 얻지 못하면 fail-fast한다. API batch queue는 기본적으로 직렬이지만, CLI를 직접 여러 개 실행하는 운영자 실수를 방어하기 위한 장치다.

적재가 끝나면 `load_manifest.table_name='tl_sppn_makarea'`를 갱신한다. `row_count`, `source_yyyymm`, `source_set.kind='sppn_makarea'`, `source_files`를 남겨 C10 기준월 정합성과 최종 full-load 실행 로그에서 optional source를 함께 추적할 수 있게 한다.

실제 적재 중 발견해 수정한 문제:

- 최초 초안은 문자 컬럼 정규화에 `REPLACE(col, chr(0), '')`를 사용했다.
- PostgreSQL은 `chr(0)` 자체를 text로 만들 수 없으므로 `ProgramLimitExceeded: null character not permitted`가 발생했다.
- PostgreSQL text 컬럼까지 도달한 값은 이미 NUL 문자를 포함할 수 없으므로, 정규화는 `NULLIF(BTRIM(col::text), '')`로 단순화했다.
- GDAL 3.8 계열은 `gdal.UseExceptions()`를 명시하지 않으면 GDAL 4.0 전환 경고를 낸다. loader 진입 시 `gdal.UseExceptions()`를 호출하도록 고정했다.

## Query

reverse 보조 조회는 입력 좌표를 한 번만 EPSG:5179로 변환한다. polygon 컬럼에는 변환 함수를 씌우지 않아 GiST index 스캔을 유도한다.

```sql
WITH target_pt AS (
  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179) AS geom
)
SELECT m.sig_cd,
       m.makarea_id,
       m.makarea_nm,
       m.ntfc_yn,
       m.ntfc_de,
       m.mvm_res_cd,
       m.source_file,
       m.source_yyyymm,
       ST_Area(m.geom) AS area_m2,
       ST_X(ST_Transform(p.geom, 4326)) AS lon,
       ST_Y(ST_Transform(p.geom, 4326)) AS lat
  FROM tl_sppn_makarea m, target_pt p
 WHERE ST_Covers(m.geom, p.geom)
 ORDER BY ST_Area(m.geom) ASC, m.sig_cd, m.makarea_id
 LIMIT :limit;
```

geocode 경로는 국가지점번호 parser가 EPSG:5179 cell 중심을 계산한 뒤 같은 `ST_Covers(m.geom, p.geom)` 조건으로 표기 의무지역에 속하는지 검증한다. 검증에 성공하면 `GeocodeResponse.result.point`는 WGS84로 변환한 점을 담고, `x_extension`은 다음 정보를 포함한다.

```json
{
  "source": "local",
  "confidence": 0.72,
  "national_point_number": "다바 7363 4856",
  "sppn_makarea": {
    "sig_cd": "36110",
    "makarea_id": "29",
    "makarea_nm": "금이산",
    "ntfc_yn": "Y",
    "ntfc_de": "20231212",
    "mvm_res_cd": "11",
    "source_file": "구역의도형_전체분_세종특별자치시.zip:36110/TL_SPPN_MAKAREA.shp",
    "source_yyyymm": "202605",
    "area_m2": 14146845.532463465
  }
}
```

reverse geocode는 도로명/지번 후보가 없어도 `sppn_makarea`가 있으면 `status="OK"`로 반환한다. 이때 `result`는 비어 있을 수 있고, 표기 의무지역 문맥은 `x_extension.sppn_makarea` 배열에 담긴다.

## 실제 Docker 검증

검증 환경:

| 항목 | 값 |
|------|----|
| OS | WSL2 Linux `6.6.87.2-microsoft-standard-WSL2` |
| CPU | AMD Ryzen 7 7840HS, 8 cores / 16 threads |
| Memory | 29GiB total, 검증 시 available 27GiB |
| ext4 작업 디스크 | `/dev/sdd`, 1007G total, 759G available |
| NTFS 데이터 디스크 | `/mnt/f`, 932G total, 267G available |
| Docker | Docker 29.5.2 |
| PostgreSQL/PostGIS image | `postgis/postgis:16-3.5` |
| PostgreSQL server | 16.9 |
| PostgreSQL config | `shared_buffers=512MB`, `work_mem=64MB`, `maintenance_work_mem=256MB` |
| 테스트 DB | `kor_travel_geo_t042_sppn` |
| 원천 ZIP 크기 | 2.3MiB |

실행 순서:

1. `kor_travel_geo_t042_sppn` DB를 새로 만들었다.
2. `SCHEMA_SQL`과 `INDEX_SQL`을 적용했다.
3. `ktgctl load sppn-makarea`로 세종 `구역의 도형` ZIP을 적재했다.
4. `MV_SQL`로 빈 `mv_geocode_target`을 만들어 reverse core smoke가 주소 후보 없음 상태에서도 실패하지 않는지 확인했다.
5. `tl_sppn_makarea`에서 `ST_PointOnSurface(geom)` 샘플을 뽑아 국가지점번호 formatter → geocode → reverse 보조 조회 순서로 검증했다.

적재 명령:

```bash
KTG_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kor_travel_geo_t042_sppn \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/ktgctl load sppn-makarea \
  "/mnt/f/dev/geodata/juso/구역의 도형/구역의도형_전체분_세종특별자치시.zip" \
  --yyyymm 202605
```

결과:

```text
loaded tl_sppn_makarea rows: 146
elapsed_s=1.35 max_rss_kb=130920
```

검증 SQL 결과:

```text
rows=146
distinct_keys=146
min(source_yyyymm)=202605
max(source_yyyymm)=202605
all_valid=true
all_multipolygon=true
```

샘플 조회 결과:

| 항목 | 값 |
|------|----|
| `sig_cd` | `36110` |
| `makarea_id` | `29` |
| `makarea_nm` | `금이산` |
| point-on-surface EPSG:5179 | `x=973637.0155769116`, `y=1848566.03015` |
| point-on-surface EPSG:4326 | `lon=127.20511239227915`, `lat=36.63461765453511` |
| formatter 결과 | `다바 7363 4856` |
| geocode 결과 | `OK`, `x_extension.sppn_makarea.makarea_nm="금이산"` |
| reverse 보조 조회 | 1건, `makarea_id="29"` |

optional integration test:

```bash
KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kor_travel_geo_t042_sppn \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/python -m pytest \
  tests/integration/test_optional_real_postgres_load.py::test_real_postgres_can_load_sppn_makarea_and_lookup_when_dsn_is_set \
  -q
```

결과:

```text
1 passed in 1.32s
```

## 테스트 케이스

추가한 주요 테스트는 다음과 같다.

| 테스트 | 검증 내용 |
|--------|-----------|
| `tests/unit/test_sppn_core.py` | parser example, embedded address rejection, formatter round-trip, geocode/reverse core extension |
| `tests/unit/test_sppn_makarea_loader.py` | ZIP/디렉터리/source discovery, missing layer 오류, staging insert-select 계약, `chr(0)` 사용 금지 |
| `tests/unit/test_infra_repo_sql.py` | `ST_Covers`, polygon 컬럼 raw 사용, point 변환 위치, geocode/reverse SQL 계약 |
| `tests/unit/test_cli_contract.py` | `load sppn-makarea --help`, CLI mode/source_yyyymm 계약 |
| `tests/unit/test_source_set_plan.py` | optional `sppn_makarea` 탐지와 `sppn_makarea_load` child payload |
| `tests/unit/test_api_app_contract.py` | API queue handler 등록 |
| `tests/unit/test_alembic_migrations.py` | `0007_t042_sppn_makarea` migration 계약 |
| `tests/unit/test_infra_engine_pnu_sql.py` | `SCHEMA_SQL`/`INDEX_SQL`에 table/index 반영 |
| `tests/integration/test_optional_real_postgres_load.py` | 실제 세종 ZIP → Docker PostGIS 적재 → geocode/reverse lookup |

## 운영 메모

- `sppn_makarea`는 optional source다. `source_set` discovery에 잡히면 full-load batch child로 등록할 수 있지만, 원천 기준월이 다른 경우 ADR-029/T-045의 혼합 기준월 확인 UX를 그대로 따른다.
- `source_file`은 `ZIP명:내부/SHP명` 형태로 저장한다. 전국 적재 시 지역별 ZIP 출처 추적과 C10 기준월 리포트에 사용할 수 있다.
- reverse geocode에서 도로명/지번 후보와 `sppn_makarea`가 동시에 나올 수 있다. vworld 호환 주소 후보는 `result`에 유지하고, 표기 의무지역은 보조 문맥으로만 둔다.
- `confidence=0.72`는 "국가지점번호 문자열 자체는 좌표를 직접 지정하지만, `TL_SPPN_MAKAREA`는 표지판 point 목록이 아니라 의무지역 polygon"이라는 한계를 반영한 보수값이다. 추후 실제 시설물 point 원천을 확보하면 별도 source와 confidence 정책을 둔다.
- T-047 성능 벤치마크에는 국가지점번호 geocode/reverse query를 Q11로 포함한다. 전국 polygon 수가 크지 않더라도 `ST_Covers` 공간 조인의 p95/p99를 확인하고, 필요하면 read-only accelerator view를 검토한다.

## 후속

- T-027 최종 클린 로드에서 전국 `구역의 도형` source set을 포함할지 결정하고, 포함한다면 row count와 적재 시간을 전체 로그에 남긴다.
- T-047에서 Q11 국가지점번호 geocode/reverse latency, plan, buffer 사용량을 측정한다.
- 별도 UI 구현 PR에서 `maplibre-vworld-js` 0.1.0의 `PolygonArea` 또는 동등한 지도 primitive를 활용해 `TL_SPPN_MAKAREA` polygon overlay와 reverse result overlay를 추가한다.
