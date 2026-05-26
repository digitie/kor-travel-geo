# 백엔드 패키지 사양서 — `python-kraddr-geo` (`kraddr.geo`)

본 문서는 첨부 사양서(2026-05-22 작성)를 master 브랜치 문서 체계로 옮긴 정리본이다. 구현 시 본 문서를 1차 reference로 본다. GitHub 저장소 이름은 `python-kraddr-geo`, Python import는 `kraddr.geo`, CLI는 `kraddr-geo`, 환경변수 prefix는 `KRADDR_GEO_`다.

## 1. 개요

`python-kraddr-geo`(이하 본 패키지)는 한 코어(`core/`) 위에 두 인터페이스를 노출한다.

- **Python 라이브러리 API**: `AsyncAddressClient` — asyncio 컨텍스트 매니저
- **REST API**: FastAPI 라우터가 라이브러리 API를 호출하는 얇은 wrapper. vworld 호환 응답.

두 인터페이스는 같은 코어 함수(`core.geocoder.geocode`, `core.reverse_geocoder.reverse_geocode` 등)를 호출하므로 동작이 갈리지 않는다. 코어는 DB 어댑터(Repository Protocol)를 받아 작동하므로 단위 테스트 시 in-memory Fake 어댑터로 교체 가능하다.

### 핵심 원칙

- **All async** — 동기 라이브러리 API는 만들지 않는다(ADR-002).
- **Pydantic v2 DTO** — 입력/출력은 모두 pydantic 모델. `ConfigDict(frozen=True)`로 불변. 직렬화는 `model_dump(mode='json')`. mypy strict.
- **응답 = vworld 호환** — 자체 확장은 `x_extension` 필드로만(ADR-003).
- **Repository 패턴** — core는 Protocol에만 의존, infra가 SQLAlchemy/GeoAlchemy 구현 제공(ADR-004).
- **로더 분리** — `loaders/`는 일반 쿼리 경로와 완전 분리.
- **CLI 분리** — `cli/`는 라이브러리에 의존하지 않는다.

## 2. 패키지 구조

```
python-kraddr-geo/
├── pyproject.toml
├── README.md
├── SKILL.md
├── CHANGELOG.md
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── data-model.md
│   ├── tasks.md
│   ├── resume.md
│   └── journal.md
├── src/kraddr/geo/
│   ├── __init__.py
│   ├── version.py
│   ├── settings.py
│   ├── exceptions.py
│   ├── client.py
│   ├── dto/
│   │   ├── common.py
│   │   ├── address.py
│   │   ├── geocode.py
│   │   ├── reverse.py
│   │   ├── search.py
│   │   ├── zipcode.py
│   │   ├── pobox.py
│   │   ├── admin.py
│   │   └── errors.py
│   ├── core/
│   │   ├── protocols.py
│   │   ├── normalize.py
│   │   ├── geocoder.py
│   │   ├── reverse_geocoder.py
│   │   ├── searcher.py
│   │   ├── zipcoder.py
│   │   ├── poboxer.py
│   │   └── responses.py
│   ├── infra/
│   │   ├── engine.py
│   │   ├── models.py
│   │   ├── geocode_repo.py
│   │   ├── reverse_repo.py
│   │   ├── search_repo.py
│   │   ├── zip_repo.py
│   │   ├── pobox_repo.py
│   │   └── admin_repo.py
│   ├── loaders/
│   │   ├── manifest.py
│   │   ├── sido_loader.py
│   │   ├── delta_loader.py
│   │   ├── pobox_loader.py
│   │   ├── bulk_loader.py
│   │   ├── postload.py
│   │   └── swap.py
│   ├── api/
│   │   ├── app.py
│   │   ├── deps.py
│   │   ├── responses.py
│   │   ├── middlewares.py
│   │   ├── _jobs.py
│   │   └── routers/
│   │       ├── geocode.py
│   │       ├── reverse.py
│   │       ├── search.py
│   │       ├── zipcode.py
│   │       ├── pobox.py
│   │       ├── admin.py
│   │       └── healthz.py
│   └── cli/
│       ├── main.py
│       ├── load.py
│       ├── refresh.py
│       ├── validate.py
│       └── healthz.py
├── alembic/
├── sql/
│   ├── ddl/
│   ├── indexes.sql
│   ├── mv.sql
│   └── postload.sql
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── scripts/
    └── export_openapi.py
```

공개 심볼은 `__init__.py`에서 명시:

```python
from .version import __version__
from .client import AsyncAddressClient
from . import dto, exceptions

__all__ = ["AsyncAddressClient", "dto", "exceptions", "__version__"]
```

## 3. 환경과 설정

### 3.1 `pyproject.toml` (핵심)

```toml
[project]
name = "python-kraddr-geo"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2.9,<3",
  "pydantic-settings>=2.5",
  "sqlalchemy[asyncio]>=2.0.35",
  "geoalchemy2>=0.15",
  "psycopg[binary,pool]>=3.2",
  "anyio>=4.5",
  "typer>=0.12",
  "httpx>=0.27",
  "tenacity>=9.0",
  "rapidfuzz>=3.10",
  "structlog>=24.4",
  "orjson>=3.10",
]
[project.optional-dependencies]
api     = ["fastapi>=0.115", "uvicorn[standard]>=0.32", "prometheus-client>=0.21"]
loaders = ["gdal>=3.8", "geopandas>=1.0", "shapely>=2.0", "fiona>=1.10", "pyogrio>=0.10"]
dev     = ["pytest>=8.3", "pytest-asyncio>=0.24", "pytest-postgresql>=6.1",
           "testcontainers[postgres]>=4.8", "ruff>=0.7", "mypy>=1.13",
           "import-linter>=2.0", "hypothesis>=6.115"]

[project.scripts]
kraddr-geo = "kraddr.geo.cli.main:app"

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[tool.ruff]
line-length = 100
target-version = "py312"
[tool.ruff.lint]
select = ["E","F","W","I","N","UP","B","A","C4","SIM","TCH","RUF","ASYNC"]

[tool.importlinter]
root_package = "kraddr.geo"
[[tool.importlinter.contracts]]
name = "Layered architecture"
type = "layers"
layers = ["kraddr.geo.api", "kraddr.geo.cli", "kraddr.geo.client",
          "kraddr.geo.loaders", "kraddr.geo.infra",
          "kraddr.geo.core", "kraddr.geo.dto"]
ignore_imports = ["kraddr.geo.api.routers.admin -> kraddr.geo.loaders"]
```

### 3.2 `Settings` (pydantic-settings)

`KRADDR_GEO_` prefix. 외부 API 키는 `SecretStr`. 전체 필드는 첨부 사양 §3.2 참조. 핵심:

| 카테고리 | 키 | 비고 |
|----------|----|------|
| DB | `pg_dsn`, `pg_pool_size`, `pg_max_overflow`, `pg_statement_timeout_ms`, `pg_pool_recycle_s` | `postgresql+psycopg://...` |
| API | `api_title`, `api_cors_origins`, `api_default_radius_m`, `api_max_search_size`, `api_max_upload_bytes`, `api_explain_timeout_ms` | 업로드 기본 상한 2GiB, EXPLAIN 기본 timeout 3초 |
| 외부 | `juso_api_key`, `juso_search_url`, `juso_coord_url`, `juso_coord_api_key`, `vworld_api_key`, `vworld_url`, `epost_api_key`, `epost_download_url` | 모두 `SecretStr` 또는 URL |
| 캐시 | `cache_enabled`, `cache_ttl_days` | `geo_cache` 테이블 사용 |
| 로깅 | `log_level`, `log_format` | `json` 권장 |
| 로더 | `loader_data_dir`, `loader_batch_size`, `loader_temp_schema` | |

`get_settings()`는 lazy 싱글톤. 테스트에서는 `reset_settings()`로 싱글톤을 비우고, 명시 주입이 필요할 때만 `set_settings(settings)`를 사용한다.

### 3.3 예외

`KraddrGeoError` (base) 아래 사용자 입력 오류(`InvalidInputError`, `InvalidAddressError`, `InvalidCoordinateError`, `RateLimitError`), 결과 부재(`NotFoundError`), 인프라 오류(`DatabaseError`, `ExternalApiError`, `LoaderError`, `ConfigError`).

각 예외는 `code: str`(E0xxx)과 `http_status: int`를 가진다. `api/responses.py`가 핸들러 등록.

## 4. DTO — pydantic v2

### 공통

- `Status = Literal["OK","NOT_FOUND","ERROR"]`
- `Point(x: float, y: float)` — frozen
- `CRS` — `EPSG:XXXX` 정규화(소문자/하이픈 허용)
- `ServiceMeta(name, operation, version="2.0", time: str | None)`
- `ZipSource(Enum)` — `building_bsi_zon_no` / `bulk_delivery` / `kodis_bas_within` / `kodis_bas_centroid` / `pobox`
- `ResultSource = Literal["local","api_juso","api_vworld","cache"]`
- `AddressType = Literal["road","parcel"]`
- `Page(page>=1, size 1..100)`

### `AddressStructure` (vworld 호환)

`level0`(="대한민국"), `level1`(시도), `level2`(시군구), `level3`(미사용), `level4L`(법정동), `level4LC`(법정동코드10), `level4A`(행정동), `level4AC`(행정동코드10), `level5`(도로명), `detail`(본번-부번).

### Geocode

- `GeocodeInput`: `address`, `type`, `crs`, `refine`, `simple`, `fallback ∈ {"off","local_only","api"}`
- `GeocodeResult(crs, point)`
- `GeocodeExtension`: `source`, `confidence (0..1)`, `bd_mgt_sn`, `rncode_full`, `bjd_cd`, `zip_no`, `zip_source`, `buld_nm`
- `GeocodeResponse(service, status, input, refined?, result?, x_extension?)`

### Reverse / Search / Zipcode / Pobox

- `ReverseInput`: `point`, `crs`, `type ∈ {"both","road","parcel"}`, `zipcode: bool`, `radius_m (1..2000)`. `model_validator`로 한국 좌표 범위(`123<x<132, 32<y<39`) 검증.
- `SearchInput(Page)`: `query`, `type ∈ {"address","place","district","road"}`, `category`, `crs`, `bbox?`.
- `ZipcodeInput`: `address | point | bd_mgt_sn` 중 하나 필수(`model_validator(mode="after")`), `include_bulk`.
- `PoboxInput(Page)`: `query`, `si_nm`, `sgg_nm`, `kind ∈ {"PO","PG","ALL"}`.

### Admin/디버깅

`TableStat`, `NormalizeRequest/Response`, `ExplainRequest/Response`, `LoadJobStatus`, `CacheMetrics`. 자세한 정의는 첨부 §4.6.

## 5. 라이브러리 API

```python
from kraddr.geo import AsyncAddressClient

async with AsyncAddressClient() as client:    # .env에서 DSN 자동 로드
    r = await client.geocode("서울특별시 강남구 테헤란로 152")
    if r.status == "OK":
        print(r.result.point)            # Point(x=127.028..., y=37.500...)
        print(r.refined.text)            # '서울특별시 강남구 테헤란로 152'
        print(r.x_extension.bd_mgt_sn)   # '11680101...'
```

`AsyncAddressClient`의 메서드: `geocode`, `reverse_geocode`, `search`, `zipcode`, `pobox`, `geocode_many(addresses, concurrency=8)`. 편의 헬퍼 `open_client()`도 제공.

배치 호출은 내부 `asyncio.Semaphore(concurrency)`로 동시성 제한.

동기 호출이 필요하면 호출자가 `asyncio.run`으로 한 줄 래퍼를 둔다.

## 6. 코어 비즈니스 로직

### Repository Protocol

`core/protocols.py`에 `GeocodeRepo`, `ReverseRepo`, `SearchRepo`, `ZipRepo`, `PoboxRepo`를 Protocol로 정의. core는 이들에만 의존. `@runtime_checkable` 마크.

### 주소 정규화 (`core/normalize.py`)

- 입력: raw 문자열. 출력: `AddrParts(frozen dataclass)`.
- 처리: NFC 정규화, 괄호 노트 분리, 공백 정규화, 시도 별칭 정규화(`서울→서울특별시` 등), 시군구 매칭, 도로명/지번 분기 (`ROAD_RE`/`JIBUN_RE`).
- 산물: `si`, `sgg`, `sgg_nrm`, `emd`, `li`, `road`, `road_nrm`, `mnnm`, `slno`, `mt`(산 여부), `under`(지하), `detail`, `bracket_note`, `is_road`.

### `core/geocoder.py` 흐름

1. `parse_address` → `AddrParts`. `sgg_nrm` 없으면 `InvalidAddressError`.
2. `type=="road"`: 도로명/본번 검증 → `repo.lookup_by_road(...)`. 실패 시 `fallback != "off"`면 `repo.fuzzy_roads(...)`로 5개 후보 재시도 (`confidence = sim`).
3. `type=="parcel"`: 동/번지 검증 → `repo.lookup_by_jibun(...)`.
4. 결과 없으면 `GeocodeResponse(status="NOT_FOUND")`.
5. `RefinedAddress(text, structure)` 빌드. `GeocodeExtension(source="local", confidence, bd_mgt_sn, rncode_full, bjd_cd, zip_no, zip_source, buld_nm)`.

`fallback="api"`는 core가 직접 HTTP를 호출하지 않는다. `AsyncAddressClient.geocode()`가 로컬 core 결과가 `NOT_FOUND`일 때만 `infra/external_api.py::ExternalGeocodeClient`를 호출한다. 호출 순서는 vworld 주소 좌표 API → juso 검색 + 좌표 API다. 외부 응답도 동일한 `GeocodeResponse` DTO로 변환하며, 자체 출처는 `x_extension.source = "api_vworld" | "api_juso"`에만 넣는다.

`reverse_geocoder`, `searcher`, `zipcoder`, `poboxer`도 같은 패턴.

## 7. DB 어댑터

### 엔진 (`infra/engine.py`)

```python
# Settings.pg_dsn은 이미 normalize_pg_dsn validator로 'postgresql+psycopg://' 형식이
# 보장된다. engine factory에서 중복 보정하지 않는다.
engine = create_async_engine(
    settings.pg_dsn,
    pool_size=settings.pg_pool_size,
    max_overflow=settings.pg_max_overflow,
    pool_pre_ping=True,
    pool_recycle=settings.pg_pool_recycle_s,
    poolclass=AsyncAdaptedQueuePool,
    connect_args={"options": f"-c statement_timeout={settings.pg_statement_timeout_ms}"},
    json_serializer=lambda o: orjson.dumps(o).decode(),
    json_deserializer=orjson.loads,
)
```

DSN 정규화는 `Settings.normalize_pg_dsn` 단일 책임이다. 어떤 경로로 들어와도 (`.env`, env var, 직접 인자) settings가 한 번 보정하고, 다른 모듈은 그 결과를 신뢰한다.

### Repository 구현 (`infra/*_repo.py`)

raw SQL 상수(`_LOOKUP_ROAD`, `_LOOKUP_JIBUN`, `_FUZZY_ROADS` 등)를 `text(...)`로 정의하고 `engine.connect()`로 실행. `pg_trgm.similarity_threshold` 변경은 `SET LOCAL`(트랜잭션 단위).

자세한 SQL은 첨부 §7.3 참조 (`mv_geocode_target`을 단일 lookup 대상으로).

## 8. REST API

### 앱 팩토리

```python
app = FastAPI(
    title="kraddr-geo", version="0.1.0",
    default_response_class=ORJSONResponse, lifespan=lifespan,
    docs_url="/v1/docs", openapi_url="/v1/openapi.json",
)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(LoggingMiddleware)
register_exception_handlers(app)
app.include_router(healthz.router)
app.include_router(geocode.router, prefix="/v1")
# ... reverse, search, zipcode, pobox
app.include_router(admin.router, prefix="/v1/admin")
```

`lifespan`에서 `AsyncAddressClient`를 `__aenter__` 후 `app.state.client`에 보관. shutdown 시 `__aexit__`.

### 라우터 — geocode

```python
@router.get("/address/geocode", response_model=GeocodeResponse, response_model_exclude_none=True)
async def geocode(
    address: str = Query(..., min_length=1, max_length=200),
    type:    Literal["road","parcel"] = "road",
    crs:     str = "EPSG:4326",
    refine:  bool = True,
    simple:  bool = False,
    fallback: Literal["off","local_only","api"] = "local_only",
    client:  AsyncAddressClient = Depends(get_client),
) -> GeocodeResponse:
    return await client.geocode(address, type=type, crs=crs,
                                refine=refine, simple=simple, fallback=fallback)
```

reverse / search / zipcode / pobox 라우터도 같은 패턴 — 검증은 DTO가 자동, 코어 호출은 한 줄.

### Admin 라우터

내부망 전용(ADR-013). `AsyncAddressClient.engine`을 그대로 사용 — 디버거 EXPLAIN과 운영 쿼리가 같은 환경에서 평가됨을 보장.

주요 엔드포인트:

- `POST /v1/admin/normalize` — 주소 정규화 디버거
- `GET  /v1/admin/tables` — `pg_class` 기반 통계
- `POST /v1/admin/explain` — `SELECT`/`WITH`만 허용, `EXPLAIN(FORMAT JSON [, ANALYZE, BUFFERS])`, `api_explain_timeout_ms`를 `SET LOCAL`로 적용
- `POST /v1/admin/maintenance/refresh-mv` — `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target`
- `POST /v1/admin/maintenance/analyze?table=...` — 테이블명 화이트리스트 검증(`isalnum`)
- `POST /v1/admin/upload/sido-zip?filename=...&sido=...` — 시도 ZIP raw body 스트리밍 업로드(SHA256 해시 반환). `filename`과 `sido`는 path token으로 정규화하고 `loader_data_dir/uploads` 밖으로 resolve되면 거절한다. `api_max_upload_bytes` 초과 시 partial file을 삭제하고 실패한다.
- `POST /v1/admin/loads` — 업로드된 시도 또는 full-load batch payload를 작업 큐에 직렬 등록
- `GET  /v1/admin/jobs`, `GET /v1/admin/jobs/{id}`, `POST /v1/admin/jobs/{id}/cancel`
- `GET  /v1/admin/cache/metrics` — `geo_cache` 통계

### 에러 핸들러

`KraddrGeoError`, `NotFoundError`를 `ORJSONResponse`로 변환. 응답 본문은 `{"response": {"status": "...", "errorCode": "Exxxx", "errorMessage": "...", "hint": "..."}}` 구조.

## 9. 파일 로더

ADR-012에 따라 두 경로로 분리한다.

```
loaders/
├── text/                    ← 텍스트 정본 1차 (ADR-012, GDAL 무의존)
│   ├── juso_hangul_loader.py    # tl_juso_text (도로명주소 한글_전체분)
│   ├── daily_juso_loader.py     # tl_juso_text 일변동 ZIP (MST만 적용, LNBR은 기록)
│   ├── locsum_loader.py         # tl_locsum_entrc (위치정보요약DB)
│   ├── roadaddr_entrance_loader.py # tl_roadaddr_entrc (도로명주소 출입구 정보)
│   └── navi_loader.py           # tl_navi_buld_centroid, tl_navi_entrc (내비게이션용DB)
├── shp/                     ← polygon/폴리라인 (ADR-005, GDAL 필요)
│   ├── polygons_loader.py       # tl_scco_*, tl_kodis_bas, tl_spbd_buld_polygon, tl_sprd_rw
│   └── delta_loader.py          # SHP polygon 변동분 (MVM_RES_CD)
├── pobox_loader.py / bulk_loader.py     # epost 우편번호 (ADR-009)
├── manifest.py
├── postload.py / swap.py / consistency.py
```

### 매니페스트 (`loaders/manifest.py`)

`LoadManifest`는 파일/DB 양쪽에 미러링. 핵심: `last_full_load_at`, `last_delta_at`, `last_mvmn_de`(YYYYMMDD), `source_checksum`(sha256), `source_yyyymm`, `source_set`(기본 텍스트 3종 + 보조 링크/선택 direct 출입구 + SHP 적재월 묶음).

### 텍스트 로더 (`loaders/text/`, ADR-012)

원칙:

- **stdlib `csv`** + **`psycopg.copy()`** 로 적재. GDAL 무의존.
- 인코딩: BOM이 있으면 `utf-8-sig`, 그 외에는 CP949를 기본값으로 둔다. 실제 `data/juso`의 2026-03/2026-04 자료는 `file` 명령에서 ISO-8859처럼 보이지만 내용은 CP949 한글 바이트다. 임의 sample을 잘라 `cp949` strict decode로 판정하면 멀티바이트 문자가 sample 경계에서 잘려 오탐될 수 있으므로, 로더는 BOM 우선 + CP949 기본 전략을 쓴다.
- 한 시도 단위로 staging 테이블에 COPY → master로 UPSERT. 파라미터 한도(SKILL.md §4-12) 회피.
- 진행률 보고: 파일 크기 기준 byte offset 또는 처리 줄 수 기준. `Job.progress` (0~1)에 throttle 갱신.

#### `juso_hangul_loader.py` (T-013a)

`data/juso/202603_도로명주소 한글_전체분/*.txt`의 시도별 파일을 적재한다. 현재 구현은 `rnaddrkor_*.txt`만 `tl_juso_text`에 적재한다. `jibun_rnaddrkor_*.txt`는 대표 지번이 아니라 건물↔지번 1:N 보조 관계이므로 `tl_juso_text.pnu`에 덮어쓰지 않는다. 보조 관계는 `parcel_link_loader.py`가 `tl_juso_parcel_link`에 별도 적재한다(ADR-022, T-038).

#### `daily_juso_loader.py` (T-028)

`data/juso/daily/*.zip`의 일변동 ZIP을 적용한다. ZIP member 중 `AlterD.JUSUKR.*.TH_SGCO_RNADR_MST.TXT`만 `tl_juso_text`에 반영한다. `MST`는 기존 도로명주소 한글 정본과 같은 컬럼 구조에 `MVM_RES_CD`가 추가된 형태라 `parse_juso_row()`와 PNU generated column을 그대로 재사용한다.

처리 규칙:

- `MVM_RES_CD`는 `Settings.mvm_res_code_actions`를 사용한다. 기본값은 `31/33=insert`, `34/35/36=update`, `63/64=delete`다.
- `insert`와 `update`는 모두 UPSERT로 처리한다. daily ZIP 재실행과 full-load 기준월 불일치에 안전해야 하기 때문이다.
- `delete`는 `bd_mgt_sn` 기준으로 `tl_juso_text`에서 삭제한다.
- 알 수 없는 `MVM_RES_CD`는 silent skip하지 않고 `LoaderError`로 중단한다.
- 한 batch 안에 같은 `bd_mgt_sn`이 여러 번 나오면 `mvmn_de DESC`, `source_file DESC`, `staging_seq DESC` 기준 최신 1건만 반영한다.
- member 내용이 `No Data`이면 컬럼 수 오류로 보지 않고 skip하며 `skipped_no_data_sources`에 기록한다.

`AlterD.JUSUKR.*.TH_SGCO_RNADR_LNBR.TXT`는 `daily_juso_loader.py`가 직접 반영하지 않는다. 이 member는 건물↔지번 보조 관계를 담으므로 T-038의 `parcel_link_loader.py`가 `tl_juso_parcel_link`에 daily delta로 적용한다. 즉 같은 daily ZIP을 MST 반영용 `daily_juso_delta`와 LNBR 반영용 `juso_parcel_link_delta`로 나누어 실행한다. 상세 결정은 ADR-021, ADR-022, `docs/t028-daily-juso-delta.md`, `docs/t029-jibun-rnaddrkor-decision.md`, `docs/t038-parcel-link-loader.md`를 본다.

#### `parcel_link_loader.py` (T-038)

`jibun_rnaddrkor_*.txt` full snapshot과 daily `TH_SGCO_RNADR_LNBR.TXT` delta를 `tl_juso_parcel_link`에 적재한다.

- full snapshot: `kraddr-geo load parcel-links <도로명주소 한글 전체분 경로> --yyyymm 202603`
- daily delta: `kraddr-geo load daily-parcel-links <daily ZIP 또는 디렉터리>`
- API 작업 kind: `juso_parcel_link_load`, `juso_parcel_link_delta`
- full-load batch 기본 child 순서: `juso_text_load` 다음에 `juso_parcel_link_load`

이 테이블은 serving MV를 즉시 다중화하지 않는다. 후속 지번 검색 확장 또는 UI 상세 패널이 필요할 때 `tl_juso_parcel_link.pnu -> bd_mgt_sn -> mv_geocode_target` 순서로 연결한다.

#### `roadaddr_entrance_loader.py` (T-039)

`data/juso/도로명주소 출입구 정보/*.zip`의 `RNENTDATA_2605_*.txt`를 `tl_roadaddr_entrc`에 적재한다. 위치정보요약DB `entrc_*.txt`와 달리 `bd_mgt_sn`을 직접 제공하므로 `resolve_text_geometry_links()` 후해소가 필요 없다.

실제 전국 17개 ZIP을 읽어 구조를 검증했다.

- 총 source row: 6,418,169행
- 모든 row: 19컬럼
- `ent_source_cd`: `RM` 단일값
- `ent_detail_cd`: `01` 단일값
- 세종특별자치시: source 27,868행, 유효 좌표 27,779행, `bd_mgt_sn` 중복 0건, `ent_man_no` 공백 9건
- 경상남도: source 657,845행, `bd_mgt_sn` 중복 0건, `ent_man_no` 공백 100건

이 검증 때문에 테이블 PK는 `bd_mgt_sn` 단독으로 둔다. `ent_man_no`는 일부 원천에서 비어 있으므로 nullable 원본 보존 필드로 둔다. 로더는 directory, 단일 ZIP, 단일 TXT를 모두 입력으로 받을 수 있고, directory 입력에서는 이미 풀린 `RNENTDATA_*.txt`와 ZIP 내부 member를 함께 탐색한다.

```bash
kraddr-geo load roadaddr-entrances "./data/juso/도로명주소 출입구 정보" --yyyymm 202605
```

API job kind는 `roadaddr_entrance_load`다. payload는 다른 경로 기반 loader와 같은 형식이다.

```json
{
  "kind": "roadaddr_entrance_load",
  "payload": {
    "path": "/data/juso/도로명주소 출입구 정보",
    "source_yyyymm": "202605",
    "replace": true
  }
}
```

`tl_roadaddr_entrc`가 채워지면 `mv_geocode_target` 대표 좌표는 `tl_roadaddr_entrc` → `tl_locsum_entrc` → `tl_navi_buld_centroid` 순서로 선택한다. API 응답 호환성을 위해 `pt_source`는 direct 출입구와 위치정보요약DB 출입구 모두 `entrance`로 유지한다. direct 여부를 더 자세히 분석해야 하는 경우에는 `tl_roadaddr_entrc.source_file`, `source_yyyymm`, 정합성 sample의 `source_kind='roadaddr'`를 본다.

적재 결과를 기존 DB의 serving MV에 반영할 때는 `kraddr-geo refresh mv --swap`을 권장한다. T-039 이전에 만들어진 MV에 단순 `REFRESH CONCURRENTLY`만 수행하면 옛 MV 정의가 그대로 새로고침되어 direct 출입구 우선순위가 적용되지 않는다.

주의: 현재 로컬 direct 출입구 원천은 `202605`, 도로명주소 한글/위치정보요약DB/내비 기본 검증 원천은 `202603~202604`다. 이 자료를 기본 `full_load_batch`에 자동 포함하면 C10 기준월 불일치가 곧바로 운영 gate에 섞일 수 있다. 그래서 T-039에서는 handler와 명시적 child 검증만 추가하고, 기본 `BATCH_SOURCE_KINDS` 6종에는 포함하지 않는다. 같은 기준월의 전체분이 확보되었거나 운영자가 의도적으로 direct 출입구를 섞어 검증하려는 경우에는 `children` 또는 `child_jobs`로 명시 등록한다.

#### 별도 도형 묶음 (T-030 후속)

`건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`은 현재 full-load source child에 포함하지 않는다. T-030/T-041 실제 파일 검토 결과, 이 자료들은 기준월과 레이어 의미가 다르므로 기본 serving path에 즉시 섞지 않고 후속 분석 대상으로 분리했다.

- T-040: 완료. `도로명주소 건물 도형` address polygon/entrance/connection bundle은 `scripts/compare_building_shape_bundle.py`로 전자지도와 비교할 수 있지만, serving loader는 보류한다.
- T-041: 완료. 상세주소 동 도형은 `scripts/compare_extra_shape_layers.py`로 전자지도 건물과 비교할 수 있고, `구역의 도형`은 중복 5개 레이어와 추가 2개 레이어를 구분해 비교할 수 있다. 상세주소 동과 `TL_SCCO_GEMD`는 기본 full-load/MV에는 섞지 않는다.
- ADR-027: `TL_SPPN_MAKAREA`는 지점번호표기 의무지역 polygon이므로 단순 overlay 후보에서 국가지점번호 보조 geocode/reverse 데이터 후보로 승격한다. 구현 시에도 `mv_geocode_target`에는 union하지 않고 `tl_sppn_makarea` 별도 테이블과 `x_extension` 확장으로 연결한다.

상세 근거는 ADR-023과 `docs/t030-extra-shape-sources.md`를 본다.

#### 국가지점번호 표기 의무지역 (`TL_SPPN_MAKAREA`, 구현 전)

`TL_SPPN_MAKAREA`는 건물이 없어 도로명주소가 부여되지 않는 산악·해안·도서·하천 주변 등에서 국가지점번호를 표기해야 하는 의무지역 polygon이다. 이름은 `SPPN`(Spot Point Position Number) + `MAKAREA`(Marking Area)로 해석한다.

후속 구현의 원칙:

- `tl_sppn_makarea` 별도 테이블로 적재한다.
- primary key는 실제 세종/경남 파일에서 distinct로 확인한 `SIG_CD + MAKAREA_ID`를 사용한다.
- `MAKAREA_NM`은 표시명으로만 보존하고 unique key로 쓰지 않는다.
- reverse geocode는 도로명/지번 후보가 없거나 낮은 confidence일 때 `ST_Covers(tl_sppn_makarea.geom, target_pt_5179)`로 보조 후보를 찾는다.
- geocode는 국가지점번호 문자열 parser/generator가 좌표를 계산한 뒤, 해당 좌표가 표기 의무지역에 속하는지 검증하고 `x_extension.sppn_makarea`에 구역 문맥을 붙인다.
- 이 레이어는 개별 국가지점번호판 point 목록이 아니므로, `MAKAREA_NM`만으로 정밀 좌표를 만들지 않는다. 구역명 검색이 필요하면 centroid/bbox 기반 낮은 confidence `search` 기능으로 분리한다.

실제 파일 검증 결과(서울 첫 행 기준):

| index | 의미 | 예 |
|-------|------|----|
| 0 | `bd_mgt_sn` | `11110101310001200009400000` |
| 1 | `bjd_cd` | `1111010100` |
| 2~5 | 시도/시군구/읍면동/리 | `서울특별시`, `종로구`, `청운동`, 빈 값 |
| 6~8 | 산여부/지번 본번/부번 | `0`, `144`, `3` |
| 9~10 | `rncode_full`, 도로명 | `111103100012`, `자하문로` |
| 11~13 | 지하 여부/건물 본번/부번 | `0`, `94`, `0` |
| 14~16 | 행정동코드/행정동명/우편번호 | `1111051500`, `청운효자동`, `03047` |
| 22 | 건물명 | 비어 있거나 `평안빌` |

`tl_juso_text.pnu`는 DB generated column이지만, 로더 단위 테스트에서도 같은 규칙(`mntn_yn 0→1`, `1→2`, 필수 지번 필드 결측 시 `NULL`)을 검증한다.

```python
"""도로명주소 한글_전체분 로더.

행안부 배포 파일 포맷:
  - 인코딩: CP949 (또는 UTF-8 BOM, 시기에 따라)
  - 구분자: '|'
  - 헤더: 없음
  - 컬럼 인덱스: 행안부 'rnaddrkor 파일레이아웃' PDF 기준
"""
from __future__ import annotations
import csv, io
from pathlib import Path
from collections.abc import Iterator
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import text
import psycopg                          # COPY 사용
import structlog

log = structlog.get_logger()

# 실제 rnaddrkor_*.txt 검증 기준(2026-03):
# 0 bd_mgt_sn, 1 bjd_cd, 2 시도, 3 시군구, 4 읍면동, 5 리,
# 6 mntn_yn, 7 lnbr_mnnm, 8 lnbr_slno, 9 rncode_full, 10 rn,
# 11 buld_se_cd, 12 buld_mnnm, 13 buld_slno, 14 adm_cd, 15 adm_kor_nm,
# 16 zip_no, 22 buld_nm.
COLUMNS = {
    "bd_mgt_sn": 0,
    "bjd_cd": 1,
    "ctp_kor_nm": 2,
    "sig_kor_nm": 3,
    "emd_kor_nm": 4,
    "li_kor_nm": 5,
    "mntn_yn": 6,
    "lnbr_mnnm": 7,
    "lnbr_slno": 8,
    "rncode_full": 9,
    "rn": 10,
    "buld_se_cd": 11,
    "buld_mnnm": 12,
    "buld_slno": 13,
    "adm_cd": 14,
    "adm_kor_nm": 15,
    "zip_no": 16,
    "buld_nm": 22,
}

def detect_encoding(path: Path, sample_bytes: int = 65_536) -> str:
    with path.open("rb") as f:
        raw = f.read(sample_bytes)
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return "cp949"


def iter_rows(path: Path, encoding: str) -> Iterator[dict[str, str | None]]:
    """한 줄 = 한 dict. 빈 문자열은 None으로 정규화."""
    with path.open("rb") as raw:
        text_stream = io.TextIOWrapper(raw, encoding=encoding, errors="replace", newline="")
        reader = csv.reader(text_stream, delimiter="|", quoting=csv.QUOTE_NONE)
        for line_no, row in enumerate(reader, start=1):
            if len(row) < 23:
                log.warning("juso.row.too_short", line=line_no, cols=len(row), path=str(path))
                continue
            yield {
                col: (row[index].strip() or None)
                for col, index in COLUMNS.items()
            }


async def load_juso_hangul(
    engine: AsyncEngine,
    *,
    file_path: Path,
    source_yyyymm: str,
    on_progress: ProgressCallback | None = None,
    cancel_event: asyncio.Event | None = None,
) -> int:
    """한 시도 파일을 staging COPY → master UPSERT. 반환: 적재 행 수."""
    enc = detect_encoding(file_path)
    file_size = file_path.stat().st_size
    bytes_done = 0

    # psycopg async 직접 사용 (SQLAlchemy 우회: COPY가 더 빠르고 파라미터 한도 무관)
    pg_dsn = _alchemy_to_libpq(engine.url)
    async with await psycopg.AsyncConnection.connect(pg_dsn) as conn:
        async with conn.cursor() as cur:
            await cur.execute("CREATE TEMP TABLE _juso_staging (LIKE tl_juso_text INCLUDING ALL)")
            async with cur.copy(
                "COPY _juso_staging "
                "(sig_cd, rn_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm, "
                " rn, buld_se_cd, buld_mnnm, buld_slno, adm_cd, adm_kor_nm, "
                " bjd_cd, lnbr_mnnm, lnbr_slno, mntn_yn, zip_no, bd_mgt_sn, buld_nm, "
                " sig_cd, source_file, source_yyyymm) "
                "FROM STDIN"
            ) as copy:
                for r in iter_rows(file_path, enc):
                    if cancel_event and cancel_event.is_set():
                        raise asyncio.CancelledError("juso_hangul_loader cancelled")
                    sig_cd = (r["rncode_full"] or "")[:5]
                    rn_cd = (r["rncode_full"] or "")[5:]
                    await copy.write_row([
                        sig_cd, rn_cd, r["ctp_kor_nm"], r["sig_kor_nm"], r["emd_kor_nm"],
                        r["li_kor_nm"], r["rn"], r["buld_se_cd"],
                        int(r["buld_mnnm"]) if r["buld_mnnm"] else None,
                        int(r["buld_slno"]) if r["buld_slno"] else None,
                        r["adm_cd"], r["adm_kor_nm"], r["bjd_cd"],
                        int(r["lnbr_mnnm"]) if r["lnbr_mnnm"] else None,
                        int(r["lnbr_slno"]) if r["lnbr_slno"] else None,
                        r["mntn_yn"], r["zip_no"], r["bd_mgt_sn"], r["buld_nm"],
                        file_path.name, source_yyyymm,
                    ])
                    # progress: 줄당 byte 추정. 정확도는 ±5%.
                    bytes_done += sum(len((v or "").encode(enc)) for v in r.values()) + 20
                    if on_progress and bytes_done % (1 << 20) == 0:  # 1MB throttle
                        on_progress(min(bytes_done / file_size, 1.0))

            await cur.execute("""
                INSERT INTO tl_juso_text AS t (...)
                SELECT ... FROM _juso_staging
                ON CONFLICT (bd_mgt_sn) DO UPDATE SET
                  sig_cd = EXCLUDED.sig_cd,
                  rn_cd = EXCLUDED.rn_cd, ...
                  loaded_at = now();
            """)
            inserted = cur.rowcount
        await conn.commit()
    return inserted
```

`COPY ... FROM STDIN`은 파라미터 바인딩이 아닌 스트림이라 SQLAlchemy 65k 한도(SKILL.md §4-12) 무관. 시도 한 파일이 수십 MB라도 한 connection에서 처리.

#### `locsum_loader.py` (T-013b)

`data/juso/202604_위치정보요약DB_전체분.zip` — 출입구 좌표(EPSG:5179). 실제 자료는 ZIP 내부 `entrc_*.txt`로 배포되며, 작업 디렉터리에 반드시 풀 필요 없이 ZIP member를 직접 스트리밍할 수 있다.

중요 구현 차이: 실제 `entrc_*.txt`는 `bd_mgt_sn`을 직접 제공하지 않는다. 따라서 `tl_locsum_entrc`는 다음 원본 키를 먼저 보관한다.

| 컬럼 (예) | 의미 | DB 매핑 |
|-----------|------|---------|
| 0 | 시군구 코드 | `sig_cd` |
| 1 | 출입구 관리번호 | `ent_man_no` |
| 2 | 법정동코드 | `bjd_cd` |
| 6 | 도로명코드 12자리 | `sig_cd + rn_cd` |
| 8~10 | 지하 여부/건물 본번/부번 | `buld_se_cd`, `buld_mnnm`, `buld_slno` |
| 12 | 우편번호 | `zip_no` |
| 14 | 출입구구분코드 | `ent_se_cd` |
| 16~17 | X/Y 좌표 | `geometry(Point, 5179)` |

좌표 적재는 COPY에서 EWKT(`SRID=5179;POINT(x y)`)로 넣는다. X/Y가 모두 비어 있는 행이 실제 파일에 존재하므로, `geom NOT NULL` 테이블에는 좌표가 있는 행만 적재한다. 적재 후 `loaders/postload.py::resolve_text_geometry_links()`가 `tl_juso_text`와 `rncode_full + buld_se_cd + buld_mnnm + buld_slno + bjd_cd (+ zip_no)`로 조인해 `bd_mgt_sn`을 채운다. `ent_se_cd` 값 분포와 `bd_mgt_sn` 해소 실패율은 정합성 리포트에서 추적한다.

#### `navi_loader.py` (T-013c)

`data/juso/202604_내비게이션용DB_전체분/*.txt` — 건물 centroid + 내비/차량/부속 출입구.

현재 구현 범위:

- `match_build_*.txt` → `tl_navi_buld_centroid`: 원본 `bd_mgt_sn`은 들어 있지만 실제 2026년 파일 기준 25자리이고, 도로명주소 한글 정본의 `bd_mgt_sn`은 26자리라 직접 조인 키로 쓰지 않는다. centroid fallback은 `rncode_full`, 건물구분, 본번/부번, 법정동 읍면동 8자리(`left(bjd_cd, 8)`)로 대표 centroid를 고른다. 내비 파일의 법정동코드는 리 코드가 `00`인 경우가 많으므로 정본의 10자리 법정동과 완전 일치시키면 centroid fallback이 거의 붙지 않는다. 실제 서울 첫 행 기준 `23~24`가 centroid X/Y, `25~26`이 대표 출입구에 가까운 보조 X/Y다. MV fallback은 `23~24` centroid를 쓴다.
- `match_rs_entrc.txt` → `tl_navi_entrc`: 원본에는 `bd_mgt_sn`이 없고 `sig_cd`, entry no, `rncode_full`, 건물번호, 법정동코드, 진입점 코드, X/Y만 있다. `kind`는 `01→navi`, `02→vehicle`, `03→parcel`, 그 외 `aux`로 보관한다.
- `match_jibun_*.txt`는 현재 MV/역지오코딩 1차 경로에는 사용하지 않는다. 지번 centroid 보강이 필요해지면 T-016 후속으로 별도 repo 경로에 붙인다.

```python
KIND_MAP = {
    "navi":    "내비게이션 진입점",
    "vehicle": "차량 진입점",
    "parcel":  "부속 건물",
    "aux":     "기타",
}
```

내비게이션용DB는 여러 파일로 구성(건물·부속·도로). 본 로더는 두 마스터에 분리 적재:
- `tl_navi_buld_centroid` ← 건물 파일의 centroid 좌표
- `tl_navi_entrc` ← 진입점 파일들에 `kind` 매핑

### SHP polygon 로더 (`loaders/shp/`, ADR-005 한정)

도형 데이터만 SHP에서 가져온다. 속성은 텍스트 정본을 신뢰하므로 SHP의 DBF는 JOIN 키(`bd_mgt_sn`, `sig_cd`, `rds_man_no` 등)만 사용한다.

원칙은 ADR-005를 유지:

- `osgeo.gdal.VectorTranslate` in-process
- GDAL 3.8 Python binding에서는 `VectorTranslateOptions(openOptions=...)`가 허용되지 않으므로 `gdal.config_options({"SHAPE_ENCODING": "CP949"})`로 CP949를 지정한다.
- `PG_USE_COPY=YES` (`gdal.config_options` 컨텍스트 매니저)
- 진행률 callback + 협조적 취소

단, `TL_SPRD_INTRVL`은 예외다. 이 레이어는 실제 파일 기준 geometry가 필요 없는 DBF 속성 보조 테이블이고, T-033 전국 full-load에서 GDAL append가 `PG_USE_COPY=YES` 설정에도 행 단위 insert 병목을 만들었다. T-034부터는 `TL_SPRD_INTRVL.dbf`를 직접 읽어 `SIG_CD`, `RDS_MAN_NO`, `BSI_INT_SN`, `ODD_BSI_MN`, `EVE_BSI_MN`만 추출한 뒤 `psycopg COPY`로 `tl_sprd_intrvl`에 적재한다. 외부 호출 표면(`load_shp_polygons`, CLI `load shp`, `load shp-all`)은 그대로이며, source 추적 컬럼도 다른 SHP 레이어와 같은 `source_file=<시도>/<시군구코드>/TL_SPRD_INTRVL.shp`, `source_yyyymm=<옵션값>`을 유지한다.

`TL_SPBD_BULD`도 T-037부터 예외 경로를 탄다. 이 레이어는 건물 polygon geometry를 보존해야 하므로 DBF 직접 COPY로 대체하지 않는다. 대신 GDAL이 `public._kraddr_stage_spbd_buld_polygon` staging table을 `accessMode="overwrite"`로 만들고, 기존 `SQLStatement` projection을 적용해 필요한 key 컬럼과 geometry만 COPY한다. 이후 PostgreSQL 내부 `INSERT ... SELECT`로 `tl_spbd_buld_polygon`에 옮기며, 이때 `ST_Multi(geom)::geometry(MultiPolygon, 5179)`, 문자열 trim/NULL 정규화, 건물번호 integer cast를 명시한다. PostGIS extension이 `x_extension`에 있으므로 insert transaction에서는 `SET LOCAL search_path = public, x_extension`를 설정한다. staging table은 시작 전과 종료 `finally`에서 모두 drop한다.

대상은 polygon/도로 보조 9종이다. 문서 초기판의 "polygon 7종" 표현은 `tl_sprd_manage`, `tl_sprd_intrvl`처럼 도형이 없거나 속성 보조 성격인 도로 테이블을 빠뜨린 축약이었다. 구현상 load plan은 다음 9개를 명시한다: `TL_SCCO_CTPRVN`, `TL_SCCO_SIG`, `TL_SCCO_EMD`, `TL_SCCO_LI`, `TL_KODIS_BAS`, `TL_SPRD_MANAGE`, `TL_SPRD_INTRVL`, `TL_SPRD_RW`, `TL_SPBD_BULD`.

2026년 실제 전자지도 파일 기준으로 `TL_SPRD_RW`는 `LineString`이 아니라 `Polygon` 레이어다. 따라서 운영 테이블 `tl_sprd_rw.geom`은 `MULTIPOLYGON 5179`로 둔다. 도로명 인접성 검증(C8)은 `rds_man_no`가 있는 `TL_SPRD_MANAGE`의 도로명 중심선/관리 선형 geometry와 출입구 point 사이의 `ST_DWithin`으로 해석한다.

`SQLStatement`에는 JOIN 키와 필요한 속성 컬럼만 alias한다. OGR SQL 결과 레이어는 geometry를 별도 필드로 쓰지 않아도 원본 geometry를 유지하므로 `GEOMETRY AS geom` 같은 가짜 문자열 필드를 만들지 않는다. geometry 컬럼명은 대상 PostgreSQL 테이블의 `geom`과 `GEOMETRY_NAME=geom` 설정으로 맞춘다.

PR #17부터 SHP 로더는 모든 9개 보조 레이어 projection에 다음 추적 컬럼도 함께 넣는다.

```sql
, '<시도>/<시군구코드>/<레이어>.shp' AS source_file,
  '<YYYYMM 또는 NULL>' AS source_yyyymm
```

예를 들어 서울 `TL_SPBD_BULD.shp`를 `--yyyymm=202604`로 적재하면 `source_file='Seoul/11000/TL_SPBD_BULD.shp'`, `source_yyyymm='202604'`가 된다. 기존 T-027 실제 DB처럼 PR #17 이전에 적재된 SHP row는 이 값이 NULL일 수 있으므로, C2/C4 원천 파일 역추적이 필요하면 SHP 보조 레이어를 재적재해야 한다.

#### `tl_spbd_buld_polygon` 분리 전략

SHP `TL_SPBD_BULD`는 건물 polygon + 속성을 함께 가진다. 속성(도로명/지번/우편번호/건물명)의 정본은 여전히 `tl_juso_text`지만, 실제 SHP `BD_MGT_SN`은 25자리이고 텍스트 정본 `bd_mgt_sn`은 26자리라 직접 조인 키로 사용할 수 없다. 따라서 polygon 테이블에는 검증과 공간 조인을 위한 최소 natural key(`RDS_SIG_CD`, `RN_CD`, `BULD_SE_CD`, `BULD_MNNM`, `BULD_SLNO`, `SIG_CD`, `EMD_CD`, `LI_CD`)를 함께 적재한다.

```python
stage_opts = gdal.VectorTranslateOptions(
    format="PostgreSQL",
    layerName="_kraddr_stage_spbd_buld_polygon",
    SQLStatement=(
        "SELECT BD_MGT_SN AS bd_mgt_sn, SIG_CD AS sig_cd, EMD_CD AS emd_cd, "
        "LI_CD AS li_cd, RDS_SIG_CD AS rds_sig_cd, RN_CD AS rn_cd, "
        "BULD_SE_CD AS buld_se_cd, BULD_MNNM AS buld_mnnm, "
        "BULD_SLNO AS buld_slno, "
        "'Seoul/11000/TL_SPBD_BULD.shp' AS source_file, "
        "'202604' AS source_yyyymm FROM TL_SPBD_BULD"
    ),
    layerCreationOptions=[
        "GEOMETRY_NAME=geom",
        "SPATIAL_INDEX=NONE",
    ],
    srcSRS="EPSG:5179", dstSRS="EPSG:5179",
    accessMode="overwrite",
    geometryType="PROMOTE_TO_MULTI",
)
```

운영 테이블 insert는 staging 완료 뒤 DB 내부에서 수행한다.

```sql
SET LOCAL search_path = public, x_extension;

INSERT INTO tl_spbd_buld_polygon (
  bd_mgt_sn, sig_cd, emd_cd, li_cd, rds_sig_cd, rn_cd,
  buld_se_cd, buld_mnnm, buld_slno, geom, source_file, source_yyyymm
)
SELECT
  NULLIF(BTRIM(bd_mgt_sn::text), ''),
  NULLIF(BTRIM(sig_cd::text), ''),
  NULLIF(BTRIM(emd_cd::text), ''),
  NULLIF(BTRIM(li_cd::text), ''),
  NULLIF(BTRIM(rds_sig_cd::text), ''),
  NULLIF(BTRIM(rn_cd::text), ''),
  NULLIF(BTRIM(buld_se_cd::text), ''),
  NULLIF(BTRIM(buld_mnnm::text), '')::integer,
  NULLIF(BTRIM(buld_slno::text), '')::integer,
  ST_Multi(geom)::geometry(MultiPolygon, 5179),
  :source_file,
  :source_yyyymm
FROM _kraddr_stage_spbd_buld_polygon
WHERE NULLIF(BTRIM(bd_mgt_sn::text), '') IS NOT NULL
  AND geom IS NOT NULL;
```

postload에서 `CREATE INDEX ON tl_spbd_buld_polygon USING GIST (geom)`.

### 시도 로더 (`loaders/sido_loader.py`)

원칙:

- `ogr2ogr` subprocess 제거. `osgeo.gdal.VectorTranslate` in-process (ADR-005).
- CP949 디코딩: GDAL 3.8 호환을 위해 `gdal.config_options({"SHAPE_ENCODING": "CP949"})` 사용.
- 진행률 callback: `gdal.VectorTranslate(callback=...)`로 0~1.0 보고 → 작업 큐에 반영.
- 협조적 취소: callback에서 `cancel_event` 확인, 0 반환 시 GDAL 즉시 중단.
- ZIP 입력 직접 처리: `_extract_zip`(zip slip 방어), `_find_shp_dir`.
- 비동기 통합: `asyncio.to_thread`로 GDAL 동기 API를 워커 스레드에서 실행.
- `PG_USE_COPY=YES`는 `gdal.config_options` 컨텍스트 매니저로 한정 적용(GDAL 3.5+, ADR-005). `gdal.SetConfigOption` 전역 호출 금지.

레이어 적재 순서 (FK 의존):

```
TL_SCCO_CTPRVN, TL_SCCO_SIG, TL_SCCO_EMD, TL_SCCO_LI,
TL_KODIS_BAS,
TL_SPRD_MANAGE, TL_SPRD_INTRVL, TL_SPRD_RW,
TL_SPBD_EQB, TL_SPBD_BULD, TL_SPBD_ENTRC
```

### 증분 적재 (`loaders/delta_loader.py`)

`MVM_RES_CD` 분기로 staging → master 머지. `INSERT ... ON CONFLICT DO UPDATE` (신규/수정), `DELETE ... USING staging` (삭제). `mvm_res_cd` 컬럼이 없는 마스터는 전량 UPSERT. PK 매핑은 `PK_MAP` 상수.

머지 후 staging은 `TRUNCATE`(drop은 하지 않음).

### 후처리 (`loaders/postload.py`)

`VACUUM (ANALYZE)` → `SET LOCAL maintenance_work_mem='1500MB'` → `REFRESH MATERIALIZED VIEW mv_geocode_target` → `ANALYZE mv_geocode_target` → (옵션) `CLUSTER ... USING idx_buld_road_match`.

T-035 이후 MV 갱신 성능 비교는 `scripts/benchmark_mv_refresh.py`로 재현한다. 실제 전국 DB `kraddr_geo_t033` 기준 `CONCURRENTLY`는 1분 49.64초, shadow swap은 2분 16.28초였고, shadow swap의 rename/index rename 구간은 약 0.016초였다. `shadow_swap_mv()`는 rename transaction과 `ANALYZE` transaction을 분리해 swap lock window에 통계 갱신 시간을 포함하지 않는다. 상세 수치와 phase별 index build 시간은 `docs/t035-mv-refresh-benchmark.md`를 본다.

### 무중단 스왑 (`loaders/swap.py`)

```python
async def atomic_schema_swap(engine, staging="staging_new", live="public"):
    async with engine.begin() as conn:
        await conn.execute(text(f"ALTER SCHEMA {live}    RENAME TO __swap_old"))
        await conn.execute(text(f"ALTER SCHEMA {staging} RENAME TO {live}"))
        await conn.execute(text(f"ALTER SCHEMA __swap_old RENAME TO {staging}"))
```

스왑 후 search_path/권한/MV 재설정이 필요할 수 있음.

### 작업 큐 (`api/_jobs.py`)

설계:

- 단일 백엔드 인스턴스 가정 (ADR-006).
- `asyncio.Semaphore(1)`로 in-process 직렬 처리 + **`load_jobs` 테이블로 상태 영속화**(ADR-011).
- `Job` dataclass(in-memory): `job_id`, `kind`, `payload`, `state ∈ {queued, running, done, failed, cancelled}`, `progress (0..1)`, `current_stage`, `started_at`, `ended_at`, `error`, `log_tail (deque maxlen=200)`, `cancel_event (asyncio.Event)`.
- 핸들러 등록: `queue.register(kind, handler)`. 핸들러 시그니처는 `(payload, cancel_event, progress_cb)`이며, `progress_cb(progress?, stage?, message?)`를 호출하면 `load_jobs.progress`, `current_stage`, `heartbeat_at`, `log_tail`이 함께 갱신된다. 기본 앱은 `juso_text_load`, `daily_juso_delta`, `juso_parcel_link_load`, `juso_parcel_link_delta`, `roadaddr_entrance_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`, `bulk_load`, `consistency_check`, `mv_refresh` 핸들러를 등록한다. 이 중 `roadaddr_entrance_load`는 선택 child라 기본 `full_load_batch` 6종에는 들어가지 않는다.

#### `load_jobs` 영속 테이블 (ADR-011)

`load_manifest`는 "성공한 적재의 watermark"로 유지하고, 작업 실행 상태는 별도 테이블로 분리한다.

```sql
CREATE TABLE load_jobs (
  job_id         TEXT PRIMARY KEY,
  kind           TEXT NOT NULL,
  payload        JSONB NOT NULL,
  state          TEXT NOT NULL CHECK (state IN ('queued','running','done','failed','cancelled')),
  load_batch_id  TEXT,                  -- ADR-017: batch root/child 묶음
  parent_job_id  TEXT,                  -- ADR-017: child가 속한 full_load_batch root
  progress       NUMERIC(5,4) NOT NULL DEFAULT 0.0 CHECK (progress >= 0 AND progress <= 1),
  current_stage  TEXT,
  source_yyyymm  TEXT,
  source_set     JSONB,
  source_checksum TEXT,
  error_message  TEXT,
  log_tail       JSONB NOT NULL DEFAULT '[]'::jsonb,
  payload_summary JSONB,
  started_at     TIMESTAMPTZ,
  finished_at    TIMESTAMPTZ,
  heartbeat_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_load_jobs_state ON load_jobs (state) WHERE state IN ('queued','running');
CREATE INDEX idx_load_jobs_batch ON load_jobs (load_batch_id, created_at) WHERE load_batch_id IS NOT NULL;
CREATE INDEX idx_load_jobs_parent ON load_jobs (parent_job_id) WHERE parent_job_id IS NOT NULL;
```

`JobQueue._run`은 상태 전이 시점(`queued → running → done|failed|cancelled`)마다 `load_jobs`에 UPDATE를 보낸다. 진행률·current_stage는 1~5초 단위 throttle로 갱신해 부하 회피.

ADR-017에 따라 `full_load_batch`는 실행 핸들러가 없는 root job으로 남고, 실제 실행은 child job이 담당한다. source child 6종이 모두 `done`이 되면 큐가 `consistency_check`를 자동 등록한다. 정합성 리포트가 `ERROR`가 아니고 `source_set.load_batch_id`가 확인되면 `mv_refresh`를 `strategy='swap'`으로 등록한다. child 실패 또는 취소가 발생하면 root는 `failed`, 아직 대기 중인 같은 batch child는 `cancelled`가 된다.

`full_load_batch` payload는 enqueue 직전에 `infra.batch.batch_children()`에서 검증한다. 기본 경로는 `payload.payloads` 객체에 source child 6종을 모두 넣어야 하며, 각 child payload는 실제 로더가 요구하는 `path` 또는 `source_path`를 포함해야 한다. 이 검증은 REST `/v1/admin/loads`와 라이브러리 `AsyncAddressClient.submit_load("full_load_batch", ...)`가 같은 helper를 공유하므로 두 표면에서 동일하게 적용된다.

```json
{
  "payloads": {
    "juso_text_load": {
      "path": "/data/juso/202604_도로명주소 한글_전체분",
      "source_yyyymm": "202604"
    },
    "juso_parcel_link_load": {
      "path": "/data/juso/202604_도로명주소 한글_전체분",
      "source_yyyymm": "202604"
    },
    "locsum_load": {
      "path": "/data/juso/202604_위치정보요약DB_전체분.zip",
      "source_yyyymm": "202604"
    },
    "navi_load": {
      "path": "/data/juso/202604_내비게이션용DB_전체분",
      "source_yyyymm": "202604"
    },
    "shp_polygons_load": {
      "path": "/data/juso/도로명주소 전자지도",
      "mode": "full"
    },
    "pobox_load": {
      "path": "/data/epost/zipcode_full.zip"
    }
  }
}
```

`source_set` 같은 운영 메타데이터를 root payload에 추가로 보관할 수는 있지만, 자동으로 등록되는 `consistency_check` child에는 큐가 `load_batch_id`를 별도 주입한다. 따라서 batch swap gate가 의존하는 최소 식별자는 `load_consistency_reports.source_set.load_batch_id`다.

고급 사용자는 `children` 또는 `child_jobs` 배열로 기본 6종을 대체할 수 있다. 이때 각 entry는 `{"kind": "...", "payload": {...}}` 형식이어야 하며, `juso_text_load`, `juso_parcel_link_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`, `bulk_load`처럼 경로 기반 로더인 kind는 동일하게 `path`/`source_path`가 필요하다. 잘못된 entry를 조용히 버리지 않고 `InvalidInputError(E0100, HTTP 400)`로 거절한다. 잘못 만든 batch root와 빈 child가 `load_jobs`에 남아 이후 drain에서 실패하는 상황을 막기 위한 정책이다.

#### lifespan 복구 (`api/app.py`)

```python
@asynccontextmanager
async def lifespan(app):
    # ... settings/engine 초기화 ...
    async with engine.begin() as conn:
        # 1) 잔존 RUNNING은 무조건 FAILED (재시작으로 끊긴 작업)
        await conn.execute(text("""
            UPDATE load_jobs
               SET state = 'failed',
                   error_message = COALESCE(error_message, '') || ' [recovered: process restart]',
                   finished_at = now()
             WHERE state = 'running'
        """))
        # 2) QUEUED는 payload가 DB에 남아 있으므로 drain 재개 대상
        has_queued = await conn.scalar(text(
            "SELECT EXISTS (SELECT 1 FROM load_jobs WHERE state = 'queued')"
        ))
    if has_queued:
        # 구현에서는 내부 drain task를 한 번 깨워 queued 작업을 다시 픽업한다.
        queue.spawn_drain_task()
    yield
    # shutdown: 진행 중 작업 cancel
```

#### 다중 워커 환경 보강

`uvicorn --workers N` (N>1)을 사용하면 in-process Semaphore가 워커마다 갈라진다. 사양의 기본은 `--workers 1`이지만, 워커가 늘어나는 운영 환경에 대비해 **DB 수준의 실행 직렬성**을 함께 둔다.

```python
# 워커가 작업을 실행하기 직전, DB advisory lock 한 자리만 점유 가능
async with engine.begin() as conn:
    locked = await conn.scalar(text(
        "SELECT pg_try_advisory_lock(:slot)"
    ), {"slot": ADVISORY_SLOT_LOAD_QUEUE})
    if not locked:
        return  # 다른 워커가 실행 중. 큐 픽업은 다음 폴링 사이클.
    try:
        # state='queued' 한 건 픽업
        row = await conn.execute(text("""
            SELECT job_id, kind, payload
              FROM load_jobs
             WHERE state = 'queued'
             ORDER BY created_at
             FOR UPDATE SKIP LOCKED
             LIMIT 1
        """))
        # ... handler 실행 ...
    finally:
        await conn.execute(text(
            "SELECT pg_advisory_unlock(:slot)"
        ), {"slot": ADVISORY_SLOT_LOAD_QUEUE})
```

`pg_try_advisory_lock` + `FOR UPDATE SKIP LOCKED`의 이중 가드로 동일 작업이 두 워커에서 동시에 실행되는 케이스를 막는다. 단일 워커 환경에서는 advisory lock이 즉시 점유되어 비용은 거의 없다.

### 업로드 + 일괄 처리

프론트엔드 워크플로는 2단계:

1. **업로드**: 시도별 ZIP을 `POST /v1/admin/upload/sido-zip?filename=...&sido=...`로 보낸다. 요청 body는 multipart가 아니라 raw binary stream이다. 이 방식은 `python-multipart` 의존을 추가하지 않고 FastAPI `Request.stream()`으로 바로 디스크에 쓰기 위함이다. 업로드된 경로/사이즈/sha256을 반환한다. 업로드는 `api_max_upload_bytes`(기본 2GiB)를 넘을 수 없고, `sido`/`filename` 정규화 후에도 `loader_data_dir/uploads` 밖으로 나가는 경로는 거절한다.
2. **처리**: 모든 업로드 완료 후 `POST /v1/admin/loads`에 `kind="full_load_batch"` payload를 등록한다. 큐가 직렬 처리한다. 진행률은 `/v1/admin/loads` 또는 compatibility alias `/v1/admin/jobs`로 폴링한다.

업로드 디렉토리는 `settings.loader_data_dir/uploads/`. `upload_id = "{timestamp}_{sido_name}"`로 충돌 방지. 30일 이상 된 ZIP은 cron이 정리.

### 9.8 적재 진행도/상태 — 라이브러리·API 표면 (ADR-016)

라이브러리 사용자(앱)가 적재 cron이나 1회 트리거의 상태를 직접 폴링할 수 있도록 일급 함수와 REST를 제공한다.

#### 라이브러리 (`AsyncAddressClient`)

```python
class AsyncAddressClient:
    async def load_status(self, job_id: str) -> LoadJobStatus:
        """단일 작업 상태/진행률/current_stage/log_tail (최근 N라인)."""

    async def list_load_jobs(
        self,
        *,
        kind: str | None = None,            # 'juso_text_load' / 'locsum_load' / ...
        state: str | None = None,           # 'queued' / 'running' / 'done' / 'failed' / 'cancelled'
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[LoadJobStatus]:
        """필터 조회. 운영 대시보드 용도."""

    async def submit_load(
        self,
        kind: str,
        payload: dict[str, Any],
    ) -> LoadJobStatus:
        """관리자 라이브러리에서 직접 적재 트리거. 큐 등록 후 즉시 반환."""

    async def cancel_load(self, job_id: str) -> LoadJobStatus:
        """협조적 취소 — cancel_event set 후 다음 폴링에서 반영."""
```

DTO는 `dto/admin.LoadJobStatus`(이미 PR #5에서 추가됨). 본 함수들은 `client.engine`을 통해 `load_jobs` 테이블을 직접 조회하며 `JobQueue.status()`를 사용하지 않는다(in-memory 휘발 위험 회피, ADR-011).

#### REST API (`/v1/admin/loads/*`)

```
POST   /v1/admin/loads               body: { kind, payload }      → LoadJobStatus
GET    /v1/admin/loads               query: kind?, state?, limit, since? → list[LoadJobStatus]
GET    /v1/admin/loads/{job_id}      → LoadJobStatus
POST   /v1/admin/loads/{job_id}/cancel → LoadJobStatus
WS     /v1/admin/loads/{job_id}/stream → ndjson log lines (structlog)  -- 선택, 별도 후속 PR
```

기존 `/v1/admin/jobs` (사양 §8.5)는 deprecate하고 `/v1/admin/loads`가 표준 경로. `kraddr-geo-ui /admin/load` 페이지(`docs/frontend-package.md` §A6.3)는 본 REST를 그대로 사용.

#### `LoadJobStatus` DTO 확장

기존 `dto/admin.LoadJobStatus`에 ADR-011/ADR-016 반영 필드를 추가:

```python
class LoadJobStatus(FrozenModel):
    job_id:        str
    kind:          Literal[
        "juso_text_load", "daily_juso_delta",
        "juso_parcel_link_load", "juso_parcel_link_delta",
        "roadaddr_entrance_load",
        "locsum_load", "navi_load",
        "shp_polygons_load", "shp_polygons_delta",
        "pobox_load", "bulk_load",
        "mv_refresh", "consistency_check",
    ]
    state:         Literal["queued","running","done","failed","cancelled"]
    progress:      float = Field(default=0.0, ge=0.0, le=1.0)
    current_stage: str | None = None
    source_yyyymm: str | None = None
    source_set:    dict[str, str] | None = None   # {juso, locsum, roadaddr_entrance?, navi, shp}
    started_at:    datetime | None = None
    finished_at:   datetime | None = None
    heartbeat_at:  datetime | None = None
    error_message: str | None = None
    log_tail:      tuple[str, ...] = Field(default_factory=tuple)  # 최근 200줄
    payload_summary: dict[str, Any] | None = None  # 민감 정보 제거된 요약
```

`log_tail`은 `Job.log_tail`(deque maxlen=200)을 그대로 직렬화 — 진행 중 작업도 마지막 N줄을 즉시 확인 가능.

### 9.9 정합성 검증 — 라이브러리·API 표면 (ADR-016)

ADR-012의 텍스트 ↔ SHP 정합성 케이스(C1~C10, `docs/data-model.md` "정합성 검증")를 라이브러리 사용자와 디버그 UI가 직접 트리거·조회할 수 있다.

#### 라이브러리

```python
class AsyncAddressClient:
    async def run_consistency_check(
        self,
        *,
        scope: Literal["full", "sido", "recent"] = "full",
        sido: str | None = None,        # scope='sido'일 때 시도명
        recent_days: int = 7,           # scope='recent'일 때
        cases: tuple[str, ...] | None = None,  # 기본은 모든 C1~C10
    ) -> LoadJobStatus:
        """정합성 검증 작업을 큐에 등록. kind='consistency_check'. 즉시 반환.
        결과는 finish 후 consistency_report(report_id)로 조회."""

    async def consistency_report(self, report_id: str) -> ConsistencyReport:
        """단일 리포트의 cases JSON, severity_max, source_set 등."""

    async def list_consistency_reports(
        self,
        *,
        limit: int = 20,
        severity_at_least: Literal["INFO","WARN","ERROR"] | None = None,
    ) -> list[ConsistencyReportSummary]:
        """시계열 회귀 추적 — 최근 N건 리포트 요약."""
```

#### REST

```
POST /v1/admin/consistency/run
       body: { scope, sido?, recent_days?, cases? }
       → LoadJobStatus (kind='consistency_check')

GET  /v1/admin/consistency
       query: limit, severity_at_least
       → list[ConsistencyReportSummary]

GET  /v1/admin/consistency/{report_id}
       → ConsistencyReport (cases JSON 전체 + 샘플 outliers)
```

#### `ConsistencyReport` DTO

```python
class ConsistencyCase(FrozenModel):
    code:       Literal["C1","C2","C3","C4","C5","C6","C7","C8","C9","C10"]
    name:       str                       # 사람이 읽는 케이스명
    severity:   Literal["OK","INFO","WARN","ERROR"]
    count:      int                       # 위반 건수
    ratio:      float | None = None       # 위반 비율 (전체 대비)
    threshold:  str | None = None         # "5% 초과 시 WARN" 등 임계값 표기
    metric:     dict[str, float] | None = None   # 케이스별 측정값 (예: p50/p95/p99)
    sample:     tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    note:       str | None = None

class ConsistencyReport(FrozenModel):
    report_id:    str
    scope:        str
    severity_max: Literal["OK","INFO","WARN","ERROR"]
    source_set:   dict[str, str]          # {juso_yyyymm, locsum_yyyymm, roadaddr_entrance_yyyymm?, navi_yyyymm, shp_yyyymm}
    started_at:   datetime
    finished_at:  datetime | None = None
    cases:        tuple[ConsistencyCase, ...]
    generated_by: Literal["cli","api","cron"]
```

#### 검증 함수 (`loaders/consistency.py`)

각 케이스 C1~C10은 단일 SQL로 표현하고 결과를 `ConsistencyCase`로 환원한다. 표는 `docs/data-model.md` "정합성 케이스 분류" 참조.

```python
# loaders/consistency.py — 케이스 한 건의 시그니처
async def run_case(
    engine: AsyncEngine,
    code: str,
) -> ConsistencyCase: ...

# 전체 실행
async def run_all_cases(
    engine: AsyncEngine,
    *,
    scope: str = "full",
    cases: tuple[str, ...] = ("C1","C2","C3","C4","C5","C6","C7","C8","C9","C10"),
    source_set: dict[str, str] | None = None,  # batch DAG에서는 {"load_batch_id": "..."}
    on_progress: ProgressReporter | None = None,
) -> ConsistencyReport:
    """각 케이스의 count/ratio/threshold/metric/sample을 채우고 리포트를 DB에 저장."""
```

#### 디버그 UI 노출

`kraddr-geo-ui /admin/consistency` 페이지(신규)는 `GET /v1/admin/consistency`로 리스트 + 클릭 시 `GET /v1/admin/consistency/{report_id}`로 상세를 받아 케이스별 severity·count·sample을 카드로 표시한다. `POST /v1/admin/consistency/run`은 우측 상단 "정합성 재검증" 버튼에서 트리거. 화면 사양은 `docs/frontend-package.md`에 후속 PR로 추가.

### 9.10 적재 진행도 로그·리포트 정책

- **JSON 라인 로그**: `structlog`. 키는 `event`, `job_id`, `kind`, `stage`, `progress`, `rows`, `bytes`, `severity`. 작업 시작/단계 전환/완료/실패 4 시점은 필수, 나머지 진행 갱신은 5초~1MB throttle.
- **`load_jobs.log_tail` JSONB**: 최근 200줄을 DB에 직접 보관한다. 작업 시작, 단계 전환, 완료, 실패, handler의 `progress_cb(..., message=...)` 호출 시 tail을 갱신한다. 프로세스 재시작 후에도 마지막 로그 단서가 남아야 하므로 메모리 전용 deque에 의존하지 않는다.
- **`load_consistency_reports.cases`**: JSONB로 전체 케이스 결과를 한 행에 보관. 시계열 회귀는 `started_at` 인덱스로 조회.
- **알람 정책**(ADR-011 후속, 운영 단계): `severity_max IN ('ERROR')`인 리포트가 생성되면 Prometheus alert (T-025).

## 10. CLI

데이터 경로는 NTFS의 프로젝트 디렉토리 `data/`를 가리킨다. WSL에서 작업할 때는 ext4 작업 디렉토리에 `ln -s /mnt/<drive>/projects/python-kraddr-geo/data data`로 심볼릭 링크를 두거나 절대경로(`/mnt/<drive>/projects/python-kraddr-geo/data/...`)로 참조한다.

CLI는 운영자가 WSL shell에서 직접 실행하는 **동기 관리 명령**이다. API의 `/v1/admin/loads`는 `load_jobs` 큐와 batch DAG를 통해 백그라운드 실행을 담당한다. 두 경로 모두 같은 loader/core/repository 코드를 쓰지만, CLI는 장기 실행 프로세스가 끊기면 shell exit code로 실패를 전달하고, API 큐는 `load_jobs` 상태로 실패를 남긴다.

```bash
# === 텍스트 정본 적재 (ADR-012, GDAL 무의존) ===
kraddr-geo load juso  ./data/juso/202603_도로명주소\ 한글_전체분 --yyyymm 202603
kraddr-geo load locsum ./data/juso/202604_위치정보요약DB_전체분 --yyyymm 202604
kraddr-geo load navi   ./data/juso/202604_내비게이션용DB_전체분 --yyyymm 202604
kraddr-geo load daily-juso ./data/juso/daily/20260401_dailyjusukrdata.zip
kraddr-geo load roadaddr-entrances "./data/juso/도로명주소 출입구 정보" --yyyymm 202605

# === 전국 단위 직접 풀로드 ===
kraddr-geo load all-sidos \
  --juso ./data/juso/202603_도로명주소\ 한글_전체분 \
  --locsum ./data/juso/202604_위치정보요약DB_전체분.zip \
  --navi ./data/juso/202604_내비게이션용DB_전체분 \
  --shp-root ./data/juso/도로명주소\ 전자지도 \
  --yyyymm 202604 \
  --swap

# === SHP polygon 적재 (ADR-005, GDAL 필요) ===
kraddr-geo load shp ./data/juso/도로명주소\ 전자지도/강원특별자치도 --mode full --yyyymm 202604
kraddr-geo load shp-all ./data/juso/도로명주소\ 전자지도 --mode full --yyyymm 202604

# 변동분 (SHP polygon만)
kraddr-geo load shp ./data/juso/delta/202605/seoul --mode delta

# 변동분 (도로명주소 한글 일변동 ZIP)
kraddr-geo load daily-juso ./data/juso/daily

# === 보조 우편번호 (ADR-009, 분기 1회) ===
kraddr-geo load pobox ./data/postal/202605/JUSO_사서함.txt
kraddr-geo load bulk  ./data/postal/202605/도로명주소_zipcode.txt
# 또는 epost OpenAPI 자동 다운로드
kraddr-geo load epost --kind=full

# === 후처리 ===
kraddr-geo refresh mv                        # CONCURRENTLY (평시)
kraddr-geo refresh mv --swap                 # shadow MV swap (분기 풀로드 후)

# === 정합성 검증 (ADR-012, ADR-016) ===
kraddr-geo validate consistency               # 모든 케이스 C1~C10
kraddr-geo validate consistency --scope=full
kraddr-geo validate consistency --cases=C4,C7 # 특정 케이스만 JSON 출력

# === T-031 데이터 품질 후속 sample export ===
kraddr-geo validate data-quality-samples \
  --cases C2,C4,C6,C7 \
  --limit 200 \
  --output-dir artifacts/fullload/data-quality

# === 작업 큐 상태 조회 (ADR-011, ADR-016) ===
kraddr-geo jobs list                          # 최근 작업 목록
kraddr-geo jobs status <job_id>               # 단일 작업 상태/진행률/log_tail
kraddr-geo jobs cancel <job_id>

# === 무결성 + 헬스 ===
kraddr-geo validate all                       # 행 수·FK·MV·확장 설치 점검
kraddr-geo healthz
```

## 11. 테스트

| 계층 | 위치 | 전제 | 도구 |
|------|------|------|------|
| unit | `tests/unit/` | DB 없음 (Fake repo) | pytest, pytest-asyncio, hypothesis |
| integration | `tests/integration/` | 실제 PostgreSQL+PostGIS (testcontainers) | testcontainers-python, GeoPandas |
| e2e | `tests/e2e/` | FastAPI TestClient + integration DB | httpx.AsyncClient |

`tests/conftest.py`는 `PostgresContainer("postgis/postgis:16-3.4-alpine")` 세션 픽스처로 DDL을 적용한 DSN을 제공.

## 12. 패키징·CI

### pre-commit

- ruff check
- mypy (strict)
- import-linter (local)

### CI (`.github/workflows/ci.yml`)

```yaml
services:
  pg:
    image: postgis/postgis:16-3.4
    env: { POSTGRES_PASSWORD: t, POSTGRES_DB: kraddr_geo }
    options: >-
      --health-cmd pg_isready --health-interval 10s
      --health-timeout 5s --health-retries 5
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: { python-version: '3.12' }
  - run: pip install -e ".[api,loaders,dev]"
  - run: ruff check .
  - run: mypy src/kraddr/geo
  - run: lint-imports
  - run: pytest -q --maxfail=1
```

### OpenAPI export

`scripts/export_openapi.py`가 `create_app().openapi()`를 `openapi.json`에 저장한다.

```bash
python scripts/export_openapi.py --output openapi.json
python scripts/export_openapi.py --check --output openapi.json
```

`.github/workflows/openapi.yml`은 PR마다 패키지를 `.[api]` extra로 설치한 뒤 `--check`를 실행한다. API DTO/라우터가 바뀌었는데 `openapi.json`이 갱신되지 않으면 CI가 실패한다. 프론트엔드는 본 파일을 받아 `gen:types`.

## 13. 부록

### 도메인 어휘

`SKILL.md` §6의 표 참조 — BJD_CD, RNCODE_FULL, BD_MGT_SN, BSI_ZON_NO, BAS_ID, MV, MVM_RES_CD, MVMN_DE.

### 외부 REST API 키

발급 절차·정책은 `docs/external-apis.md` 참조.

### 운영 (uvicorn systemd)

```ini
[Service]
Type=simple
User=addr
WorkingDirectory=/opt/addr/app
Environment=KRADDR_GEO_LOG_FORMAT=json
EnvironmentFile=/etc/kraddr-geo/env
ExecStart=/opt/addr/app/.venv/bin/uvicorn kraddr.geo.api.app:app \
          --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers
Restart=always
RestartSec=3
LimitNOFILE=65535
```

### 외부 API 호출 정책

- **재시도**: `tenacity`로 5xx/timeout만 3회 지수 backoff. 4xx는 즉시 실패.
- **회로차단**: 같은 외부 서비스에 1분 내 5회 연속 실패하면 60초 폴백 호출 차단.
- **쿼터 보호**: 일 한도 80% 도달 시 Prometheus 알람. 90% 초과 시 자동으로 인터벌 늘리거나 폴백 비활성화.
- **로그**: 호출 1건당 한 줄 structlog(서비스명·응답 시간·상태·응답 크기). 키는 절대 로그에 남기지 않음(`SecretStr`).
