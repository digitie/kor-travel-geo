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
| API | `api_title`, `api_cors_origins`, `api_default_radius_m`, `api_max_search_size` | |
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
- `POST /v1/admin/explain` — `SELECT`/`WITH`만 허용, `EXPLAIN(FORMAT JSON [, ANALYZE, BUFFERS])`
- `POST /v1/admin/maintenance/refresh-mv` — `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target`
- `POST /v1/admin/maintenance/analyze?table=...` — 테이블명 화이트리스트 검증(`isalnum`)
- `POST /v1/admin/upload/sido-zip` — 시도 ZIP 스트리밍 업로드(SHA256 해시 반환)
- `POST /v1/admin/load/sido-batch` — 업로드된 시도들을 작업 큐에 직렬 등록
- `GET  /v1/admin/jobs`, `GET /v1/admin/jobs/{id}`, `POST /v1/admin/jobs/{id}/cancel`
- `GET  /v1/admin/cache/metrics` — `geo_cache` 통계

### 에러 핸들러

`KraddrGeoError`, `NotFoundError`를 `ORJSONResponse`로 변환. 응답 본문은 `{"response": {"status": "...", "errorCode": "Exxxx", "errorMessage": "...", "hint": "..."}}` 구조.

## 9. 파일 로더

### 매니페스트 (`loaders/manifest.py`)

`LoadManifest`는 파일/DB 양쪽에 미러링. 핵심: `last_full_load_at`, `last_delta_at`, `last_mvmn_de`(YYYYMMDD), `source_checksum`(sha256).

### 시도 로더 (`loaders/sido_loader.py`)

원칙:

- `ogr2ogr` subprocess 제거. `osgeo.gdal.VectorTranslate` in-process (ADR-005).
- CP949 디코딩: `open_options=["ENCODING=CP949"]`.
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
- 핸들러 등록: `queue.register(kind, handler)`. `sido_load`, `pobox_load`, `bulk_load`, `mv_refresh` 등.

#### `load_jobs` 영속 테이블 (ADR-011)

`load_manifest`는 "성공한 적재의 watermark"로 유지하고, 작업 실행 상태는 별도 테이블로 분리한다.

```sql
CREATE TABLE load_jobs (
  job_id         TEXT PRIMARY KEY,
  kind           TEXT NOT NULL,
  payload        JSONB NOT NULL,
  state          TEXT NOT NULL CHECK (state IN ('queued','running','done','failed','cancelled')),
  progress       NUMERIC(3,2) NOT NULL DEFAULT 0.0,
  current_stage  TEXT,
  source_checksum TEXT,
  error_message  TEXT,
  started_at     TIMESTAMPTZ,
  finished_at    TIMESTAMPTZ,
  heartbeat_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_load_jobs_state ON load_jobs (state) WHERE state IN ('queued','running');
```

`JobQueue._run`은 상태 전이 시점(`queued → running → done|failed|cancelled`)마다 `load_jobs`에 UPDATE를 보낸다. 진행률·current_stage는 1~5초 단위 throttle로 갱신해 부하 회피.

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
        # 2) QUEUED는 payload 파일이 살아있으면 재큐잉, 아니면 FAILED
        rows = (await conn.execute(text(
            "SELECT job_id, kind, payload FROM load_jobs WHERE state = 'queued'"
        ))).mappings().all()
    for r in rows:
        if _payload_still_resolvable(r["payload"]):
            await queue.enqueue(r["kind"], r["payload"], job_id=r["job_id"])
        else:
            async with engine.begin() as conn:
                await conn.execute(text(
                    "UPDATE load_jobs SET state='failed', "
                    "error_message='payload missing on restart', finished_at=now() "
                    "WHERE job_id = :j"
                ), {"j": r["job_id"]})
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

1. **업로드**: 시도별 ZIP을 `POST /v1/admin/upload/sido-zip`(multipart, 64KB 청크 스트리밍). 업로드된 경로/사이즈/sha256을 반환.
2. **처리**: 모든 업로드 완료 후 `POST /v1/admin/load/sido-batch`로 batch 등록. 큐가 직렬 처리. 진행률은 `/v1/admin/jobs` 폴링.

업로드 디렉토리는 `settings.loader_data_dir/uploads/`. `upload_id = "{timestamp}_{sido_name}"`로 충돌 방지. 30일 이상 된 ZIP은 cron이 정리.

## 10. CLI

데이터 경로는 NTFS의 프로젝트 디렉토리 `data/`를 가리킨다. WSL에서 작업할 때는 ext4 작업 디렉토리에 `ln -s /mnt/<drive>/projects/python-kraddr-geo/data data`로 심볼릭 링크를 두거나 절대경로(`/mnt/<drive>/projects/python-kraddr-geo/data/...`)로 참조한다.

```bash
# 전체 적재 (root에 시도별 폴더 또는 ZIP들이 섞여 있어도 OK)
kraddr-geo load all-sidos ./data/jusoMap/202605 --mode full \
  --pg-conn "host=localhost dbname=kraddr_geo user=addr password=..."

# 단일 시도 (ZIP 직접 입력)
kraddr-geo load sido ./data/jusoMap/202605/seoul.zip --mode full --pg-conn "..."

# 증분 (변동분 SHP가 별도 폴더에 제공된다고 가정)
kraddr-geo load sido ./data/jusoMap/delta/202605/seoul --mode delta --pg-conn "..."

# 보조 우편번호
kraddr-geo load pobox ./data/postal/202605/JUSO_사서함.txt
kraddr-geo load bulk  ./data/postal/202605/도로명주소_zipcode.txt

# 후처리
kraddr-geo refresh mv
kraddr-geo refresh vacuum

# 무결성 검증
kraddr-geo validate all

# 헬스 + 통계
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

- ruff (lint + format)
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
  - run: ruff check . && ruff format --check .
  - run: mypy src/kraddr/geo
  - run: lint-imports
  - run: pytest -q --maxfail=1
```

### OpenAPI export

`scripts/export_openapi.py`가 `create_app().openapi()`를 `openapi.json`에 저장. CI에서 `git diff --exit-code openapi.json`으로 변경 누락 방지. 프론트엔드는 본 파일을 받아 `gen:types`.

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
