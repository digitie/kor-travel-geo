# 백엔드 패키지 사양서 — `kor-travel-geo` (`kortravelgeo`)

본 문서는 첨부 사양서(2026-05-22 작성)를 `main` 브랜치 문서 체계로 옮긴 정리본이다. 구현 시 본 문서를 1차 reference로 본다. GitHub 저장소 이름은 `kor-travel-geo`, Python import는 `kortravelgeo`, CLI는 `kor-travel-geo`, 환경변수 prefix는 `KTG_`다.

## 1. 개요

`kor-travel-geo`(이하 본 패키지)는 한 코어(`core/`) 위에 두 인터페이스를 노출한다.

- **Python 라이브러리 API**: `AsyncAddressClient` — asyncio 컨텍스트 매니저, 주소 조회는 후보 목록 응답만 공개
- **REST API**: FastAPI 라우터가 core/repository 경로를 호출하는 얇은 wrapper. `/v1/*`는 vworld 호환, `/v2/*`는 후보 목록 응답. 공개 주소 API는 외부/비신뢰 클라이언트에 query parameter `key`를 요구한다. trusted proxy identity가 확인된 요청은 key 검증을 우회한다.

두 인터페이스는 같은 코어 함수(`core.geocoder.geocode`, `core.reverse_geocoder.reverse_geocode` 등)를 호출하므로 동작이 갈리지 않는다. REST v1 호환 응답은 `AsyncAddressClient`의 내부 adapter에서만 사용하고, 공개 Python API는 v2 candidate schema로 투영한다. 코어는 DB 어댑터(Repository Protocol)를 받아 작동하므로 단위 테스트 시 in-memory Fake 어댑터로 교체 가능하다.

### 핵심 원칙

- **All async** — 동기 라이브러리 API는 만들지 않는다(ADR-002).
- **Pydantic v2 DTO** — 입력/출력은 모두 pydantic 모델. `ConfigDict(frozen=True)`로 불변. 직렬화는 `model_dump(mode='json')`. mypy strict.
- **응답 = vworld 호환** — 자체 확장은 `x_extension` 필드로만(ADR-003).
- **Repository 패턴** — core는 Protocol에만 의존, infra가 SQLAlchemy/GeoAlchemy 구현 제공(ADR-004).
- **로더 분리** — `loaders/`는 일반 쿼리 경로와 완전 분리.
- **CLI 분리** — `cli/`는 라이브러리에 의존하지 않는다.

## 2. 패키지 구조

```
kor-travel-geo/
├── pyproject.toml
├── README.md
├── SKILL.md
├── CHANGELOG.md
├── docs/
│   ├── architecture/          # architecture.md, data-model.md, backend-package.md, frontend-package.md ...
│   ├── adr/                   # NNN-<slug>.md + README.md (ADR 인덱스)
│   ├── runbooks/              # agent-workflow.md, agent-failure-patterns.md, restore-drill-runbook.md
│   ├── decisions.md           # docs/adr/README.md 포인터
│   ├── tasks.md
│   ├── resume.md
│   └── journal.md
├── src/kortravelgeo/
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
│   │   ├── address/
│   │   │   ├── __init__.py
│   │   │   └── codes.py
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
name = "kor-travel-geo"
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
kor-travel-geo = "kortravelgeo.cli.main:app"

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
root_package = "kortravelgeo"
[[tool.importlinter.contracts]]
name = "Layered architecture"
type = "layers"
layers = ["kortravelgeo.api", "kortravelgeo.cli", "kortravelgeo.client",
          "kortravelgeo.loaders", "kortravelgeo.infra",
          "kortravelgeo.core", "kortravelgeo.dto"]
ignore_imports = ["kortravelgeo.api.routers.admin -> kortravelgeo.loaders"]
```

### 3.2 `Settings` (pydantic-settings)

`KTG_` prefix. 외부 API 키는 `SecretStr`. 전체 필드는 첨부 사양 §3.2 참조. 핵심:

| 카테고리 | 키 | 비고 |
|----------|----|------|
| DB | `pg_dsn`, `pg_pool_size`, `pg_max_overflow`, `pg_pool_timeout_ms`, `pg_statement_timeout_ms`, `pg_pool_recycle_s`, `pg_prepare_threshold` | `postgresql+psycopg://...`. `pg_pool_timeout_ms` 기본값은 1000ms이며 pool 포화 시 API는 HTTP 503 + `E0500`으로 fail-fast한다. `pg_prepare_threshold` 기본값은 psycopg 기본과 같은 `5`이고, `0`은 즉시 prepare, `none`/`off`는 server-side prepared statement 비활성화다. DB 드라이버/연결 오류도 HTTP 503 + `E0500`으로 구조화한다. |
| API | `api_title`, `api_cors_origins`, `api_default_radius_m`, `api_max_search_size`, `api_max_upload_bytes`, `api_explain_timeout_ms`, `api_max_concurrency`, `api_geocode_max_concurrency`, `api_reverse_max_concurrency`, `api_search_max_concurrency`, `api_zipcode_max_concurrency`, `api_pobox_max_concurrency`, `api_regions_max_concurrency`, `api_admission_timeout_ms`, `api_readiness_timeout_ms` | 업로드 기본 상한 2GiB, EXPLAIN 기본 timeout 3초. `api_max_concurrency`는 unset이면 비활성화하며 `/v1/address/*`와 `/v2/*` 공개 주소 API 전체를 process별 semaphore로 제한한다. endpoint별 cap은 geocode/reverse/search/zipcode/pobox/regions scope에만 적용된다. `api_readiness_timeout_ms`는 `/v1/readyz` DB probe timeout이며 기본값은 1000ms다. 공개 API key는 요청마다 DB의 활성 hash를 조회해 폐기 상태를 즉시 반영한다. |
| GeoIP gate | `geoip_db_path`, `geoip_gate_mode`, `geoip_allow_cidrs`, `geoip_deny_cidrs`, `geoip_open_paths`, `geoip_trusted_proxies`, `geoip_audit_denials` | T-054. 외부 공용 IP는 GeoIP country `KR`만 허용하고, 내부/loopback은 허용한다. 기본 mode는 `strict`라 DB 부재 시 공용 IP를 차단한다. |
| 외부 | `juso_api_key`, `juso_search_url`, `juso_coord_url`, `juso_coord_api_key`, `vworld_api_key`, `vworld_url`, `epost_api_key`, `epost_download_url` | 모두 `SecretStr` 또는 URL. 활성 DB 공개 API key가 없으면 `vworld_api_key`가 v1/v2 공개 REST API의 기본 `key`다. |
| Admin proxy | `admin_trusted_proxy_cidrs`, `admin_proxy_secret` | `/v1/admin/*` role header를 신뢰할 proxy CIDR과 optional shared secret. secret이 설정되면 `X-KTG-Admin-Proxy-Secret`이 일치해야 한다. |
| 캐시 | `cache_enabled`, `cache_ttl_days` | `geo_cache` 테이블을 geocode/reverse local OK 결과 캐시로 사용한다. Cache hit는 v1에서 `source="cache"`로 표시하고 v2 source는 `local`로 유지한다. `refresh_mv()` 성공 후 cache를 비워 적재/MV swap 뒤 stale 응답을 막는다. |
| 로깅 | `log_level`, `log_format` | `json` 권장 |
| 로더 | `loader_data_dir`, `loader_batch_size`, `loader_temp_schema` | |
| 운영 table stats | `ops_table_stats_capture_interval_minutes`, `ops_table_stats_capture_limit`, `ops_table_stats_capture_on_startup` | API lifespan의 `ops.table_stats_snapshots` opt-in 주기 capture. 기본 interval 0은 비활성 |
| 운영 pg_stat_statements | `ops_pg_stat_statements_capture_interval_minutes`, `ops_pg_stat_statements_capture_limit`, `ops_pg_stat_statements_capture_on_startup`, `ops_pg_stat_statements_retention_days` | API lifespan의 `ops.pg_stat_statements_snapshots` 주기 capture. 기본 5분 주기·시작 시 1회 capture이며, 기본 7일보다 오래된 snapshot은 capture transaction 안에서 정리한다. Prometheus label에는 query 원문을 노출하지 않는다. |
| 느린 요청·쿼리 표본 | `ops_slow_samples_enabled`, `ops_slow_query_ms`, `ops_slow_sample_rate`, `ops_slow_sample_min_interval_ms`, `ops_slow_sample_queue_size`, `ops_slow_sample_flush_interval_ms`, `ops_slow_sample_flush_batch_size`, `ops_slow_query_explain_enabled`, `ops_slow_query_explain_timeout_ms` | T-158. 느린 API 요청, admission overload, 느린 DB query를 sampled 구조화 로그와 `ops.slow_observability_samples`에 저장한다. 기본은 비활성이며 원문 SQL·파라미터·주소 문자열은 저장하지 않는다. `EXPLAIN`은 opt-in이고 `ANALYZE`를 쓰지 않는다. |
| 런타임 예열 | `runtime_warm_on_startup`, `runtime_warm_interval_minutes`, `runtime_warm_query_limit`, `runtime_warm_statement_timeout_ms`, `runtime_warm_prewarm_enabled`, `runtime_warm_prewarm_relations` | T-162. API 시작/swap 직후 cold p99 spike를 줄이기 위한 opt-in 백그라운드 예열. 기본은 비활성이며, 쿼리 예열은 상한 있는 읽기 전용 probe만 실행한다. `pg_prewarm`은 extension이 이미 있고 명시 설정이 켜진 경우에만 호출한다. |
| 백업/복원 | `backup_allowed_dirs`, `backup_temp_dir`, `backup_default_jobs`, `backup_artifact_ttl_days`, `backup_callback_allowed_hosts`, `backup_callback_secret`, `backup_callback_max_attempts`, `backup_callback_backoff_ms` | T-046/T-050. 서버 측 allowlist 경로에만 `.tar.zst` artifact 저장, callback은 HMAC 서명과 retry/backoff 적용 |
| RustFS 업로드 저장소 | `rustfs_enabled`, `rustfs_endpoint_url`, `rustfs_bucket`, `rustfs_region`, `rustfs_prefix`, `rustfs_access_key`, `rustfs_secret_key`, `rustfs_config_path`, `rustfs_materialize_dir`, `rustfs_retention_days`, `rustfs_local_import_roots` | T-076/ADR-044. upload set을 S3 호환 RustFS에 저장하고, 기존 로컬 파일 sync/prefix import/materialized cache를 제공한다. 이 프로젝트는 RustFS를 직접 구동하지 않고 이미 동작 중인 bucket 접속 설정만 사용한다. |
| 성능 벤치마크 | `perf_artifact_dir`, `perf_default_iterations`, `perf_default_concurrency`, `perf_query_timeout_ms` | T-047. 전국 DB query benchmark 산출물과 기본 반복 횟수 |

`get_settings()`는 lazy 싱글톤. 테스트에서는 `reset_settings()`로 싱글톤을 비우고, 명시 주입이 필요할 때만 `set_settings(settings)`를 사용한다.

### 3.3 예외

`KorTravelGeoError` (base) 아래 사용자 입력 오류(`InvalidInputError`, `InvalidAddressError`, `InvalidCoordinateError`, `RateLimitError`), 결과 부재(`NotFoundError`), 인프라 오류(`DatabaseError`, `ExternalApiError`, `LoaderError`, `ConfigError`).

각 예외는 `code: str`(E0xxx)과 `http_status: int`를 가진다. `api/responses.py`가 핸들러 등록.

SQLAlchemy pool checkout timeout은 전용 메시지 `database connection pool checkout timed out` + HTTP 503으로 반환하고 `kor_travel_geo_pg_pool_checkout_timeouts_total{method,route}`에 기록한다. 그 밖의 `DBAPIError` 계열은 운영 장애와 내부 오류로 나눈다(T-178D): 연결/운영 오류(`OperationalError` 또는 `connection_invalidated=True`)는 고정 메시지 `database operation failed` + HTTP 503으로, 그 밖(`ProgrammingError`/`IntegrityError` 등 SQL·스키마·제약 오류)은 고정 메시지 `database statement failed` + HTTP 500으로 반환한다. 세 경우 모두 `code="E0500"`이며 `kor_travel_geo_api_db_errors_total{method,route,error_type}`에 기록하고, SQL 문장·파라미터·DSN은 응답에 노출하지 않는다. VWorld 호환 경로는 `response.error.code="SYSTEM_ERROR"` envelope를 유지한다.

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
- 공개 geocode text 입력은 ASCII control character를 DTO 단계에서 거절한다. `%00`/NUL 같은 값이 SQL parameter 경로까지 내려가 DB 드라이버 오류로 번지는 것을 막기 위한 T-173 안전성 계약이다.

### `AddressStructure` (vworld 호환)

`level0`(="대한민국"), `level1`(시도), `level2`(시군구), `level3`(미사용), `level4L`(법정동), `level4LC`(법정동코드10), `level4A`(행정동), `level4AC`(행정동코드10), `level5`(도로명), `detail`(본번-부번).

### Geocode

- `GeocodeInput`: `address`, `type`, `crs`, `refine`, `simple`, `fallback ∈ {"off","local_only","api"}`
- `GeocodeResult(crs, point)`
- `GeocodeExtension`: `source`, `confidence (0..1)`, `bd_mgt_sn`, `rncode_full`, `bjd_cd`, `zip_no`, `zip_source`, `buld_nm`
- `GeocodeResponse(service, status, input, refined?, result?, x_extension?)`

### Reverse / Search / Zipcode / Pobox

- `ReverseInput`: `point`, `crs`, `type ∈ {"both","road","parcel"}`, `zipcode: bool`, `radius_m (1..2000)`. `model_validator`로 한국 좌표 범위(`123<x<132, 32<y<39`) 검증. v2 `ReverseV2Input`도 같은 bounds와 finite 좌표 검증을 DTO 단계에서 수행한다. T-142 이후 reverse nearest는 KNN 후보 CTE 뒤 `distance_m <= radius_m`으로 반경을 적용하므로 `distance_m == radius_m` 경계 후보를 포함한다. `type="both"`는 SQL base row `limit`을 먼저 적용한 뒤 각 row를 `road`, `parcel` 순으로 펼치며, 주소 후보가 없어도 국가지점번호 context가 있으면 v2 `match_kind="sppn"` 후보를 담아 `OK`를 반환한다.
- `SearchInput(Page)`: `query`, `type ∈ {"address","place","district","road"}`, `category`, `crs`, `bbox?`.
- `ZipcodeInput`: `address | point | bd_mgt_sn` 중 하나 필수(`model_validator(mode="after")`), `include_bulk`.
- `PoboxInput(Page)`: `query`, `si_nm`, `sgg_nm`, `kind ∈ {"PO","PG","ALL"}`.

### Admin/디버깅

`TableStat`, `NormalizeRequest/Response`, `ExplainRequest/Response`, `LoadJobStatus`, `CacheMetrics`. 자세한 정의는 첨부 §4.6.

## 5. 라이브러리 API

```python
from kortravelgeo import AsyncAddressClient

async with AsyncAddressClient() as client:    # .env에서 DSN 자동 로드
    r = await client.geocode(query="서울특별시 강남구 테헤란로 152")
    if r.status == "OK" and r.candidates:
        candidate = r.candidates[0]
        print(candidate.point)       # Point(x=127.028..., y=37.500...)
        print(candidate.address.full if candidate.address else None)
        print(candidate.source)      # 'local', 'vworld', 'juso', ...
```

`AsyncAddressClient`의 공개 메서드: `geocode`, `reverse`, `search`, `zipcode`, `pobox`, `geocode_many(queries, concurrency=8)`. 편의 헬퍼 `open_client()`도 제공.

`geocode`, `reverse`, `search`는 T-057 이후 선택 `sig_cd`/`bjd_cd` hint를 받는다. `sig_cd`는 2자리 시도 prefix 또는 5자리 시군구 코드, `bjd_cd`는 8자리 법정동 prefix 또는 10자리 법정동 코드다. 현재 serving MV에는 물리 `sig_cd` 컬럼이 없으므로 SQL에서는 `bjd_cd` prefix filter로 적용한다. 예를 들어 `sig_cd="11680"`은 `bjd_cd LIKE '11680%'`로 좁힌다. T-175 이후 두 hint를 함께 주면 `bjd_cd`가 `sig_cd` prefix로 시작해야 하며, 서로 다른 지역을 가리키는 조합은 DB 조회 전 `E0100`/HTTP 400 입력 오류로 거절한다.

```python
await client.geocode(query="테헤란로 152", sig_cd="11680")
await client.search(query="선릉로", sig_cd="11680")
await client.reverse(127.0, 37.5, sig_cd="11")
await client.geocode(query="왕산로 189-4", sig_cd="11230", bjd_cd="1123010700")
```

배치 호출은 내부 `asyncio.Semaphore(concurrency)`로 동시성 제한.

동기 호출이 필요하면 호출자가 `asyncio.run`으로 한 줄 래퍼를 둔다.

## 6. 코어 비즈니스 로직

### Repository Protocol

`core/protocols.py`에 `GeocodeRepo`, `ReverseRepo`, `SearchRepo`, `ZipRepo`, `PoboxRepo`를 Protocol로 정의. core는 이들에만 의존. `@runtime_checkable` 마크.

### 주소 정규화 (`core/normalize.py`)

- 입력: raw 문자열. 출력: `AddrParts(frozen dataclass)`.
- 처리: NFKC 정규화, 전각 숫자·대시 변형 접기, 쉼표류 구분자와 공백 정규화, 괄호 노트 분리, 시도 별칭·구/신 표기 정규화(`서울시→서울특별시`, `강원도→강원특별자치도`, `전라북도→전북특별자치도` 등), 시군구 매칭, 도로명/지번 분기 (`ROAD_RE`/`JIBUN_RE`). T-165 이후 도로명과 건물번호 사이 공백이 없는 `성복1로35`, 본번-부번 주변 공백이 있는 `189 - 4`, `번`/`번지` 접미, 괄호·영문 혼용 prefix는 exact lookup에 필요한 `road_nrm`/`mnnm`/`slno`를 유지한다.
- 산물: `si`, `sgg`, `sgg_nrm`, `emd`, `li`, `road`, `road_nrm`, `mnnm`, `slno`, `mt`(산 여부), `under`(지하), `detail`, `bracket_note`, `is_road`.

### 주소 코드 helper (`core/address/`, T-056)

`python-legacy-address-base`의 Address 표면을 확인한 결과 원본 패키지는 GPL-3.0-or-later이고 Git checkout이 아니었으므로 코드를 복사하지 않았다. 본 저장소는 `core/address/codes.py`에 시군구/법정동/도로명관리번호/도로명주소관리번호 helper를 공개 주소 코드 규칙 기반 독립 구현으로 둔다. 사용자 확인에 따라 T-056의 "조합/분리"는 주소 문자열이 아니라 코드 식별자의 조합·분해·정규화를 뜻한다.

- `SigunguCode`, `LegalDongCode`, `RoadNameCode`, `RoadNameAddressCode`, `AddressCodeSet`
- `admCd`, `rnMgtSn`, `udrtYn`, `buldMnnm`, `buldSlno`, `bdMgtSn` mapping helper
- Juso fallback 좌표 API 호출 전 파라미터 정규화

### `core/geocoder.py` 흐름

1. `parse_address` → `AddrParts`. `sgg_nrm` 없으면 `InvalidAddressError`.
2. `type=="road"`: 도로명/본번/부번/지하구분 검증 → `repo.lookup_by_road(...)`. 실패 시 `fallback != "off"`면 `repo.fuzzy_roads(...)`로 5개 후보 재시도 (`confidence = sim`). T-171 이후 fuzzy fallback도 `buld_mnnm`/`buld_slno`/`buld_se_cd`를 모두 맞춘 뒤 `similarity DESC → entrance 우선 → bd_mgt_sn` 순서로 결정적으로 정렬한다.
3. `type=="parcel"`: 동/번지 검증 → `repo.lookup_by_jibun(...)`.
4. 결과 없으면 `GeocodeResponse(status="NOT_FOUND")`.
5. `RefinedAddress(text, structure)` 빌드. `GeocodeExtension(source="local", confidence, bd_mgt_sn, rncode_full, bjd_cd, zip_no, zip_source, buld_nm)`.

Confidence 산정은 T-172 이후 `kortravelgeo.core.confidence`가 담당한다. Local exact 기본값은 `1.0`이고, `pt_source="centroid"`는 `0.82` cap을 적용한다. 국가지점번호 10m grid cell 후보는 geocode/reverse 모두 `0.72`, VWorld fallback은 `0.70`, Juso fallback은 `0.65`다. Reverse v2 주소 후보는 `1 - distance_m / radius_m` 선형식으로 거리 증가에 따라 단조 감소한다.

`fallback="api"`는 core가 직접 HTTP를 호출하지 않는다. `AsyncAddressClient.geocode()`가 내부 v1 호환 geocode 경로를 실행하다가 로컬 core 결과가 `NOT_FOUND`일 때만 `infra/external_api.py::ExternalGeocodeClient`를 호출하고, 결과를 후보 schema로 투영한다. 호출 순서는 vworld 주소 좌표 API → juso 검색 + 좌표 API다. Juso 좌표 API의 `admCd`/`rnMgtSn`/`udrtYn`/`buldMnnm`/`buldSlno`는 `core.address.AddressCodeSet`으로 정규화한 뒤 전달한다(T-056). 외부 응답은 내부적으로 `GeocodeResponse` DTO로 변환한 뒤 공개 응답에서는 `CandidateV2.source = "vworld" | "juso"`로 노출한다. 단, T-057 region hint가 명시된 요청에서는 외부 provider가 hint를 보존하지 못하므로 로컬 `NOT_FOUND` 뒤에도 외부 fallback을 호출하지 않는다.

T-064 이후 `/v2/geocode`는 상세번호가 없는 상위 주소 입력도 별도 endpoint 없이 처리한다. 일반 도로명/지번 parser가 번호 부재로 실패하면 같은 입력을 `search(type="district")`로 넘기고, `tl_scco_ctprvn/sig/emd/li` polygon 후보를 `CandidateV2.match_kind="region"`으로 반환한다. 대표점은 `ST_PointOnSurface`를 사용한다. `ST_Centroid`는 polygon 밖으로 나갈 수 있어 화면 선택 후보의 기본 대표점으로 쓰지 않는다.

T-170 이후 v2 geocode producer는 public `candidates` tuple 안에서 복수 후보를 반환할 수 있다. local v1 primary 후보와 보조 road geometry 후보를 병합하고, 국가지점번호·건물관리번호·도로명코드·행정구역 코드 등 안정 키로 dedup한 뒤 `limit`을 적용한다. REST v1 호환 응답과 내부 `GeocodeResponse` 계약은 바꾸지 않는다.

`reverse_geocoder`, `searcher`, `zipcoder`, `poboxer`도 같은 패턴. Reverse nearest SQL은 T-142 이후 `knn_candidates` CTE에서 `t.pt_5179 <-> p.geom` KNN 후보를 먼저 추출하고, outer query에서 `distance_m`, `pt_source='entrance'`, `bd_mgt_sn`, `rncode_full`, `bjd_cd`로 동률을 깨서 같은 DB snapshot에서 후보 순서가 흔들리지 않게 한다. Q6 reverse radius benchmark는 별도 `_RADIUS_SQL`로 `ST_DWithin` prefilter 경로를 계속 측정한다.

## 7. DB 어댑터

### 엔진 (`infra/engine.py`)

```python
# Settings.pg_dsn은 이미 normalize_pg_dsn validator로 'postgresql+psycopg://' 형식이
# 보장된다. engine factory에서 중복 보정하지 않는다.
engine = create_async_engine(
    settings.pg_dsn,
    pool_size=settings.pg_pool_size,
    max_overflow=settings.pg_max_overflow,
    pool_timeout=settings.pg_pool_timeout_ms / 1_000,
    pool_pre_ping=True,
    pool_recycle=settings.pg_pool_recycle_s,
    poolclass=AsyncAdaptedQueuePool,
    connect_args={
        "options": f"-c statement_timeout={settings.pg_statement_timeout_ms}",
        "prepare_threshold": settings.pg_prepare_threshold,
    },
    json_serializer=lambda o: orjson.dumps(o).decode(),
    json_deserializer=orjson.loads,
)
```

DSN 정규화는 `Settings.normalize_pg_dsn` 단일 책임이다. 어떤 경로로 들어와도 (`.env`, env var, 직접 인자) settings가 한 번 보정하고, 다른 모듈은 그 결과를 신뢰한다.

### Repository 구현 (`infra/*_repo.py`)

raw SQL 상수(`_LOOKUP_ROAD`, `_LOOKUP_JIBUN`, `_FUZZY_ROADS` 등)를 `text(...)`로 정의하고 `engine.connect()`로 실행. `pg_trgm.similarity_threshold` 변경은 `SET LOCAL`(트랜잭션 단위).

자세한 SQL은 첨부 §7.3 참조 (`mv_geocode_target`을 단일 lookup 대상으로).

T-057 region hint filter는 geocode/search/reverse repository에 공통 바인드 파라미터로 들어간다.

| 입력 | SQL 적용 |
|------|----------|
| `sig_cd=11` | `bjd_cd LIKE '11%'` |
| `sig_cd=11680` | `bjd_cd LIKE '11680%'` |
| `bjd_cd=11110101` | `bjd_cd LIKE '11110101%'` |
| `bjd_cd=1111010100` | `bjd_cd = '1111010100'` |

T-175 이후 `RegionHint`는 `sig_cd`와 `bjd_cd`의 prefix 일관성을 검증한다. `sig_cd=11230` + `bjd_cd=1123010700`은 유효하지만, `sig_cd=11680` + `bjd_cd=1123010700`은 조용한 `NOT_FOUND`가 아니라 입력 오류다. 같은 규칙은 v1 query parameter, v2 request body, Python 라이브러리 API에 동일하게 적용된다.

## 8. REST API

### 앱 팩토리

```python
app = FastAPI(
    title="kor-travel-geo", version="0.1.0",
    default_response_class=ORJSONResponse, lifespan=lifespan,
    docs_url="/v1/docs", openapi_url="/v1/openapi.json",
)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(LoggingMiddleware)
register_exception_handlers(app)
install_geoip_gate(app, settings)
app.include_router(healthz.router, prefix="/v1")
app.include_router(geocode.router, prefix="/v1")
# ... reverse, search, zipcode, pobox
app.include_router(admin.router, prefix="/v1/admin")
```

`lifespan`에서 `AsyncAddressClient`를 `__aenter__` 후 `app.state.client`에 보관. shutdown 시 `__aexit__`.

### 헬스와 readiness

- `GET /v1/healthz`: process liveness. DB checkout이나 SQL probe를 수행하지 않는다.
- `GET /v1/readyz`: DB와 SQLAlchemy pool readiness. DB 단절·timeout·API client 미시작은 HTTP 503, `ready=false`, `degraded=true`로 반환한다. Pool 포화 상태에서는 새 DB checkout을 시도하지 않고 HTTP 503으로 fail-fast하며 database component는 `status="skipped"`가 된다. Pool utilization 0.8 이상은 HTTP 200을 유지하지만 `degraded=true`로 운영 경고를 노출한다. Admission control이 활성화된 경우 `components.admission`에 scope별 `limit`/`in_use`/`available`/`utilization`을 포함하며, scope 포화는 HTTP 200 + `degraded=true`로 노출한다. DB 단절·slow probe·복구 시나리오는 `scripts/run_t159_db_fault_injection.py`로 실제 DB 생명주기를 제어하지 않고 재현한다.

### Admission control과 overload 응답

공개 주소 API(`/v1/address/*`, `/v2/*`)는 process-local admission control을 선택적으로 사용할 수 있다. `api_max_concurrency`는 전체 공개 주소 API cap이고, `api_geocode_max_concurrency`/`api_reverse_max_concurrency`/`api_search_max_concurrency`/`api_zipcode_max_concurrency`/`api_pobox_max_concurrency`/`api_regions_max_concurrency`는 endpoint scope별 cap이다. endpoint cap과 전체 cap을 함께 설정하면 요청은 endpoint scope를 먼저 얻고 전역 `address` scope를 나중에 얻는다.

Admission timeout은 `RateLimitError(E0200, HTTP 429)`로 반환한다. `/v1/address/geocode`와 `/v1/address/reverse`는 VWorld 호환 `OVER_REQUEST_LIMIT` envelope를 유지한다. 응답 header에는 `Retry-After: 1`, `Cache-Control: no-store`를 넣는다. 서버 내부에서 overload 요청을 자동 재시도하지 않는다.

T-158 이후 `ops_slow_samples_enabled=true`이면 admission timeout은 `sample_type="overload"` 표본으로도 남는다. 표본에는 `method`, `route`, `status_code=429`, `context.scope`만 저장하고 원문 요청 값은 저장하지 않는다.

Prometheus 지표는 다음을 노출한다.

- `kor_travel_geo_api_admission_wait_seconds{method,route,scope,outcome}` histogram
- `kor_travel_geo_api_admission_rejections_total{method,route,scope}` counter
- `kor_travel_geo_api_admission_in_progress{scope}` gauge

### Client disconnect와 query cancellation

공개 주소 API(`/v1/address/*`, `/v2/*`)는 ASGI `http.disconnect` 메시지를 감지하면 진행 중인 요청 task를 cancel한다. 이 범위는 대용량 admin upload body를 미리 읽지 않도록 주소 API로 제한한다. 취소는 `asyncio.CancelledError`로 내부 코루틴에 전파되며, 성능 middleware는 요청 metric을 `status_code=499`로 남기고 예외를 다시 raise한다.

Prometheus 지표는 다음을 노출한다.

- `kor_travel_geo_api_request_cancellations_total{method,route}` counter
- `kor_travel_geo_db_query_cancellations_total{operation,query_fingerprint}` counter
- 기존 `kor_travel_geo_db_queries_total`/`kor_travel_geo_db_query_duration_seconds`의 `status="cancelled"` label

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
    sig_cd:  str | None = Query(default=None, pattern=r"^(\d{2}|\d{5})$"),
    bjd_cd:  str | None = Query(default=None, pattern=r"^(\d{8}|\d{10})$"),
    client:  AsyncAddressClient = Depends(get_client),
) -> GeocodeResponse:
    return await client._geocode_v1(address, type=type, crs=crs,
                                    refine=refine, simple=simple, fallback=fallback,
                                    sig_cd=sig_cd, bjd_cd=bjd_cd)
```

reverse / search 라우터도 `sig_cd`/`bjd_cd`를 같은 의미로 받는다. zipcode / pobox 라우터는 기존 표면을 유지한다. 검증은 DTO와 query parameter schema가 맡고, 두 hint의 상호 prefix 검증은 `RegionHint`가 공통으로 수행한다. 코어 호출은 한 줄이다.

### Admin 라우터

내부망 전용(ADR-013). `AsyncAddressClient.engine`을 그대로 사용 — 디버거 EXPLAIN과 운영 쿼리가 같은 환경에서 평가됨을 보장.

주요 엔드포인트:

- `POST /v1/admin/normalize` — 주소 정규화 디버거
- `GET  /v1/admin/tables` — `pg_class` 기반 통계
- `POST /v1/admin/explain` — `SELECT`/`WITH`만 허용, `EXPLAIN(FORMAT JSON [, ANALYZE, BUFFERS])`, `api_explain_timeout_ms`를 `SET LOCAL`로 적용
- `POST /v1/admin/maintenance/refresh-mv` — `kor-travel-geo`의 MV orchestration으로 `mv_geocode_target`과 T-061 이후 `mv_geocode_text_search` helper를 함께 갱신한다.
- `POST /v1/admin/maintenance/analyze?table=...` — 테이블명 화이트리스트 검증(`isalnum`)
- `POST /v1/admin/upload/sido-zip?filename=...&sido=...` — 시도 ZIP raw body 스트리밍 업로드(SHA256 해시 반환). `filename`과 `sido`는 path token으로 정규화하고 `loader_data_dir/uploads` 밖으로 resolve되면 거절한다. `api_max_upload_bytes` 초과 시 partial file을 삭제하고 실패한다.
- `POST /v1/admin/uploads`, `PUT /v1/admin/uploads/{upload_set_id}/files`, `GET /v1/admin/uploads/{upload_set_id}`, `POST /v1/admin/uploads/{upload_set_id}/cancel` — T-045 대용량 다중 파일 업로드 세션. 모든 파일 저장과 checksum 확인이 끝난 뒤 source set 분석으로 넘어간다.
- `GET/PATCH /v1/admin/storage/rustfs/config`, `POST /v1/admin/storage/rustfs/check`, `POST /v1/admin/storage/rustfs/import-prefix`, `POST /v1/admin/storage/rustfs/sync-local` — T-076 RustFS 업로드 저장소 설정·연결 확인·기존 object 목록 import·로컬 파일 sync. secret 원문은 조회 응답에 노출하지 않는다.
- `POST /v1/admin/auth-events` — Next.js login/logout route가 trusted proxy identity로 호출해 `admin_auth.login`/`admin_auth.logout` 감사 이벤트를 append-only `ops.audit_events`에 저장한다. client IP와 user-agent는 hash 컬럼에만 저장한다.
- `GET/POST/DELETE /v1/admin/public-api-keys*` — v1/v2 공개 REST API용 `key`를 생성·조회·폐기한다. DB에는 SHA-256 hash와 hint만 저장하고 plaintext key는 생성 응답에서 한 번만 반환한다.
- `POST /v1/admin/load-sources/discover` — 디렉터리 또는 upload set을 읽어 원천 후보, 기준월, 필수 원천 누락, 기준월 불일치 여부를 반환한다.
- `POST /v1/admin/load-sources/plan` — 사용자가 선택한 원천별 기준월/경로와 혼합 기준월 확인 정보를 검증해 `SourceSetPlan`을 만든다.
- `POST /v1/admin/loads` — 업로드된 시도 또는 full-load batch payload를 작업 큐에 직렬 등록
- `GET  /v1/admin/jobs`, `GET /v1/admin/jobs/{id}`, `POST /v1/admin/jobs/{id}/cancel`
- `GET  /v1/admin/ops/audit-events` — T-049 운영 감사 이벤트 조회. payload는 redacted 형태만 반환한다.
- `GET  /v1/admin/ops/snapshots` — source set, row count, consistency/performance/artifact 연결 상태 조회.
- `GET  /v1/admin/ops/releases`, `POST /v1/admin/ops/releases/{id}/rollback-plan` — active serving release와 rollback lineage 조회/계획. active release는 DB 제약으로 한 건만 허용한다.
- `GET  /v1/admin/ops/artifacts` — backup, restore log, consistency export, performance report, source inventory 공통 artifact metadata 조회.
- `GET  /v1/admin/ops/maintenance-windows`, `POST /v1/admin/ops/maintenance-windows`, `POST /v1/admin/ops/maintenance-windows/{id}/end` — destructive restore, schema migration, full reset 같은 위험 작업을 위한 maintenance window 등록/종료. typed confirmation은 hash로만 저장한다.
- `GET  /v1/admin/ops/table-stats`, `POST /v1/admin/ops/table-stats/capture` — table/MV/index size와 추정 row count snapshot 조회/수집. `snapshot_id`를 생략하면 현재 active serving release snapshot에 연결하며, API scheduler 설정을 켜면 같은 capture 경로를 주기 실행한다. 동시 실행은 PostgreSQL advisory transaction lock으로 한 번만 통과시킨다.
- `GET  /v1/admin/ops/pg-stat-statements`, `POST /v1/admin/ops/pg-stat-statements/capture` — persisted `pg_stat_statements` top-N snapshot 조회/수집. API scheduler 기본값은 5분 주기·시작 시 1회 capture이며, Admin 응답의 `query_preview`는 literal/숫자 마스킹 후 500자로 제한한다. Prometheus는 최신 snapshot을 `rank`/`operation`/`query_fingerprint` label로만 노출한다.
- `POST /v1/admin/backups` — T-046 DB 백업 작업 등록. `pg_dump -Fd --jobs` 결과를 `tar.zst` artifact로 저장한다.
- `GET  /v1/admin/backups`, `GET /v1/admin/backups/{artifact_id}` — 백업 artifact 목록과 metadata 조회
- `GET  /v1/admin/backups/{artifact_id}/download` — 완료된 artifact streaming 다운로드. token과 allowlist 검증을 요구한다.
- `POST /v1/admin/backups/{artifact_id}/delete` — artifact metadata와 파일 삭제. 진행 중 job artifact는 삭제하지 않는다.
- `POST /v1/admin/restores` — T-046 DB 복원 작업 등록. 기본 모드는 새 빈 DB에 `pg_restore -Fd --jobs`로 복원한다.
- `GET  /v1/admin/jobs/{id}/events` — 대형 관리 작업 진행률 SSE. T-046 1차 UI는 polling을 사용하고, SSE 기반 실시간 연결과 fallback 전환은 후속 UI 고도화에서 붙인다.
- `POST /v1/admin/performance/benchmarks` — T-047 query benchmark 작업 등록. 전국 full-load DB에서 corpus를 반복 실행하고 artifact를 남긴다.
- `GET  /v1/admin/performance/benchmarks`, `GET /v1/admin/performance/benchmarks/{run_id}` — benchmark run summary와 threshold 초과 query군 조회
- `GET  /v1/admin/performance/benchmarks/{run_id}/plans/{case_id}` — 저장된 `EXPLAIN` JSON plan 조회
- `GET  /v1/admin/cache/metrics` — `geo_cache` 통계

### 에러 핸들러

`KorTravelGeoError`, `NotFoundError`를 `ORJSONResponse`로 변환. 응답 본문은 `{"response": {"status": "...", "errorCode": "Exxxx", "errorMessage": "...", "hint": "..."}}` 구조.

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

T-045 이후 `source_set`은 단순 메모가 아니라 적재 계획의 감사 단위다. 원천별 업데이트 시점이 서로 다를 수 있으므로 다음 정보를 구조화해서 남긴다.

```json
{
  "source_set_id": "20260526T120000Z_abc123",
  "yyyymm_by_kind": {
    "juso": "202603",
    "parcel_link": "202603",
    "locsum": "202604",
    "navi": "202604",
    "shp": "202604",
    "roadaddr_entrance": "202605"
  },
  "mixed_yyyymm": true,
  "mixed_yyyymm_acknowledged": true,
  "acknowledged_by": "ui",
  "acknowledged_at": "2026-05-26T12:00:00Z",
  "candidate_paths": {
    "juso": ".../202603_도로명주소 한글_전체분",
    "locsum": ".../202604_위치정보요약DB_전체분.zip"
  },
  "candidate_sha256": {
    "locsum": "..."
  }
}
```

`mixed_yyyymm=True`이면서 `mixed_yyyymm_acknowledged`가 없으면 `full_load_batch` 등록 또는 C10 정합성 gate에서 실패해야 한다. 의도적으로 혼합한 경우에도 C10 리포트에는 기준월 표와 확인 주체를 남긴다.

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

- full snapshot: `ktgctl load parcel-links <도로명주소 한글 전체분 경로> --yyyymm 202603`
- daily delta: `ktgctl load daily-parcel-links <daily ZIP 또는 디렉터리>`
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
ktgctl load roadaddr-entrances "./data/juso/도로명주소 출입구 정보" --yyyymm 202605
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

`tl_roadaddr_entrc`가 채워져도 기준월이 다른 direct 출입구를 즉시 serving 좌표로 승격하지 않는다. `mv_geocode_target` 대표 좌표는 `tl_locsum_entrc` → same-month `tl_roadaddr_entrc` → `tl_navi_buld_centroid` 순서로 선택한다. 여기서 same-month는 `tl_roadaddr_entrc.source_yyyymm`이 현재 `tl_juso_text.source_yyyymm` 집합에 포함되는 경우다. API 응답 호환성을 위해 `pt_source`는 direct 출입구와 위치정보요약DB 출입구 모두 `entrance`로 유지한다. T-134/ADR-055 이후 direct 여부나 C11 여부를 응답에 노출해야 하면 `pt_source` enum을 확장하지 않고 `coord_source_detail`로 분리한다. direct 여부를 더 자세히 분석해야 하는 경우에는 `tl_roadaddr_entrc.source_file`, `source_yyyymm`, 정합성 sample의 `source_kind='roadaddr'`를 본다.

적재 결과를 기존 DB의 serving MV에 반영할 때는 `ktgctl refresh mv --swap`을 권장한다. T-039/T-027 이전에 만들어진 MV에 단순 `REFRESH CONCURRENTLY`만 수행하면 옛 MV 정의가 그대로 새로고침되어 same-month direct fallback 규칙이 적용되지 않는다.

주의: 현재 로컬 direct 출입구 원천은 `202605`, 도로명주소 한글/위치정보요약DB/내비/SHP 검증 원천은 `202603~202604`다. 이 자료를 기본 `full_load_batch`에 자동 포함하면 C10 기준월 불일치가 곧바로 운영 gate에 섞이고, T-027 실제 재검증에서 C4/C6/C7 오류도 증가했다. 그래서 handler와 명시적 child 검증은 제공하지만, 기본 `BATCH_SOURCE_KINDS`에는 포함하지 않는다. 같은 기준월의 전체분이 확보되었거나 운영자가 의도적으로 direct 출입구를 섞어 분석하려는 경우에는 `children` 또는 `child_jobs`로 명시 등록한다. 기준월이 다르면 적재는 되지만 기본 MV/정합성 serving CTE에는 반영되지 않는다.

#### 별도 도형 묶음 (T-030 후속)

`건물군 내 상세주소 동 도형`, `구역의 도형`, `도로명주소 건물 도형`은 현재 full-load source child에 포함하지 않는다. T-030/T-041 실제 파일 검토 결과, 이 자료들은 기준월과 레이어 의미가 다르므로 기본 serving path에 즉시 섞지 않고 후속 분석 대상으로 분리했다.

- T-040: 완료. `도로명주소 건물 도형` address polygon/entrance/connection bundle은 `scripts/compare_building_shape_bundle.py`로 전자지도와 비교할 수 있지만, serving loader는 보류한다.
- T-041: 완료. 상세주소 동 도형은 `scripts/compare_extra_shape_layers.py`로 전자지도 건물과 비교할 수 있고, `구역의 도형`은 중복 5개 레이어와 추가 2개 레이어를 구분해 비교할 수 있다. 상세주소 동과 `TL_SCCO_GEMD`는 기본 full-load/MV에는 섞지 않는다.
- ADR-027/T-042: `TL_SPPN_MAKAREA`는 지점번호표기 의무지역 polygon이므로 단순 overlay 후보에서 국가지점번호 보조 geocode/reverse 데이터로 승격했다. 구현 후에도 `mv_geocode_target`에는 union하지 않고 `tl_sppn_makarea` 별도 테이블과 `x_extension` 확장으로 연결한다.

상세 근거는 ADR-023과 `docs/t030-extra-shape-sources.md`를 본다.

#### 국가지점번호 표기 의무지역 (`TL_SPPN_MAKAREA`, T-042 구현)

`TL_SPPN_MAKAREA`는 건물이 없어 도로명주소가 부여되지 않는 산악·해안·도서·하천 주변 등에서 국가지점번호를 표기해야 하는 의무지역 polygon이다. 이름은 `SPPN`(Spot Point Position Number) + `MAKAREA`(Marking Area)로 해석한다.

구현 원칙:

- `tl_sppn_makarea` 별도 테이블로 적재한다.
- primary key는 실제 세종/경남 파일에서 distinct로 확인한 `SIG_CD + MAKAREA_ID`를 사용한다.
- `MAKAREA_NM`은 표시명으로만 보존하고 unique key로 쓰지 않는다.
- reverse geocode는 도로명/지번 후보 유무와 별개로 `ST_Covers(tl_sppn_makarea.geom, target_pt_5179)`로 국가지점번호 표기 의무지역 문맥을 보조 조회한다.
- geocode는 국가지점번호 문자열 parser가 EPSG:5179 10m cell 중심 좌표를 계산한 뒤, 계산점을 EPSG:4326으로 투영해 좌표를 반환한다. `TL_SPPN_MAKAREA`는 좌표 생성 gate가 아니라 `x_extension.sppn_makarea` 구역 문맥 enrich로만 사용한다(T-166).
- reverse geocode는 입력 좌표를 EPSG:5179로 투영한 뒤 formatter로 `x_extension.national_point_number`를 노출한다. 해당 좌표가 표기 의무지역에 속하면 기존처럼 `x_extension.sppn_makarea` 구역 문맥도 붙인다(T-168).
- parser/formatter는 한국 SPPN 지원 envelope 밖의 명백한 바다·국경 밖 grid code를 거절한다(T-167).
- EPSG:5179 좌표를 국가지점번호 문자열로 바꾸는 formatter도 제공한다. 실제 polygon 내부 점 기반 테스트와 향후 지도 UI 표시에서 사용한다.
- 이 레이어는 개별 국가지점번호판 point 목록이 아니므로, `MAKAREA_NM`만으로 정밀 좌표를 만들지 않는다. 구역명 검색이 필요하면 centroid/bbox 기반 낮은 confidence `search` 기능으로 분리한다.

구현 표면:

| 표면 | 내용 |
|------|------|
| DDL | `tl_sppn_makarea`, `idx_sppn_makarea_geom`, `idx_sppn_makarea_sig`, Alembic `0007_t042_sppn_makarea` |
| loader | `load_sppn_makarea()` — ZIP/디렉터리/SHP 입력, GDAL `VectorTranslate`, staging insert-select, `MultiPolygon 5179` 정규화 |
| CLI | `ktgctl load sppn-makarea <path> --yyyymm YYYYMM --mode full\|append\|delta` |
| API queue | `sppn_makarea_load` job kind |
| source set | optional `sppn_makarea` source가 발견되면 `sppn_makarea_load` child를 만들고 `mode="full"`을 넣음 |
| geocode | 국가지점번호 parser → `GeocodeRepository.project_sppn_point_4326()` → `GeocodeResponse.result.point`; 선택적으로 `lookup_sppn_area()` → `x_extension.sppn_makarea` |
| reverse | `ReverseRepository.project_reverse_point_5179()` → `ReverseResponse.x_extension.national_point_number`; 선택적으로 `sppn_areas()` → `x_extension.sppn_makarea` |

실제 검증은 세종 `구역의 도형/구역의도형_전체분_세종특별자치시.zip`으로 수행했다. Docker PostGIS에서 146행을 적재했고, 모든 key가 distinct이며 모든 geometry가 valid `MultiPolygon`이었다. `금이산` polygon 내부 점을 formatter로 `다바 7363 4856`으로 만든 뒤 geocode/reverse 보조 조회가 같은 `sppn_makarea` 문맥을 반환하는 것도 확인했다. 상세 로그는 `docs/t042-sppn-makarea.md`를 본다.
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
- T-065 이후 `match_build_*.txt`의 20번째 컬럼(`시군구용건물명`)은 `sigungu_buld_nm`으로 보존한다. `sigungu_buld_nm_nrm`은 공백 제거 generated column이며, `mv_geocode_text_search`의 exact/broad 검색 후보에 포함된다. 이 값은 `buld_nm`을 대체하는 공식 주소 필드가 아니라, 지역 문맥의 별칭·동명·시설명을 찾기 위한 검색 보강 필드다.
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

`TL_SPBD_BULD`도 T-037부터 예외 경로를 탄다. 이 레이어는 건물 polygon geometry를 보존해야 하므로 DBF 직접 COPY로 대체하지 않는다. 대신 GDAL이 `public._ktg_stage_spbd_buld_polygon` staging table을 `accessMode="overwrite"`로 만들고, 기존 `SQLStatement` projection을 적용해 필요한 key 컬럼과 geometry만 COPY한다. 이후 PostgreSQL 내부 `INSERT ... SELECT`로 `tl_spbd_buld_polygon`에 옮기며, 이때 `ST_Multi(geom)::geometry(MultiPolygon, 5179)`, 문자열 trim/NULL 정규화, 건물번호 integer cast를 명시한다. PostGIS extension이 `x_extension`에 있으므로 insert transaction에서는 `SET LOCAL search_path = public, x_extension`를 설정한다. staging table은 시작 전과 종료 `finally`에서 모두 drop한다.

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
    layerName="_ktg_stage_spbd_buld_polygon",
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
FROM _ktg_stage_spbd_buld_polygon
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

### 후처리 (`loaders/postload.py`, `loaders/postload_maintenance.py`)

T-146 이후 적재 직후 read-mostly maintenance는 다음 순서를 표준으로 둔다.

1. `scripts/run_t146_postload_maintenance.py --mode plan`으로 source/MV/index catalog 상태와 warning을 먼저 남긴다.
2. 필요할 때만 `--mode execute-safe --vacuum-analyze`로 source relation `VACUUM (ANALYZE)`를 실행한다.
3. `resolve_text_geometry_links()`로 geometry link를 해소한다.
4. `ktgctl refresh mv`, `/v1/admin/maintenance/refresh-mv`, 또는 `refresh_mv(strategy=...)`로 `mv_geocode_target`과 helper MV를 같은 세대로 갱신한다.
5. `ops.table_stats_snapshots` capture와 T-146 report를 artifact로 남긴다.

`REINDEX CONCURRENTLY`는 invalid/bloated index 증거가 있을 때만 수동으로 실행한다. Raw `CLUSTER`는 live relation에 강한 잠금을 요구하므로 기본 runbook에서는 shadow rebuild 또는 `pg_repack`류 대안을 우선 검토한다. `pg_prewarm`과 hot query warm 자동화는 T-162 범위다.

T-061 이후에는 `mv_geocode_text_search`가 `mv_geocode_target`에서 파생되는 read-only helper MV다. 운영자가 psql에서 `REFRESH MATERIALIZED VIEW mv_geocode_target`만 직접 실행하면 helper가 stale해질 수 있으므로 raw 단독 refresh는 금지하고 `ktgctl refresh mv`, `/v1/admin/maintenance/refresh-mv`, `refresh_mv(strategy=...)` 경로를 사용한다.

T-035 이후 MV 갱신 성능 비교는 `scripts/benchmark_mv_refresh.py`로 재현한다. 실제 전국 DB `kor_travel_geo_t033` 기준 `CONCURRENTLY`는 1분 49.64초, shadow swap은 2분 16.28초였고, shadow swap의 rename/index rename 구간은 약 0.016초였다. `shadow_swap_mv()`는 rename transaction과 `ANALYZE` transaction을 분리해 swap lock window에 통계 갱신 시간을 포함하지 않는다. 상세 수치와 phase별 index build 시간은 `docs/t035-mv-refresh-benchmark.md`를 본다.

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
- 핸들러 등록: `queue.register(kind, handler)`. 핸들러 시그니처는 `(payload, cancel_event, progress_cb)`이며, `progress_cb(progress?, stage?, message?)`를 호출하면 `load_jobs.progress`, `current_stage`, `heartbeat_at`, `log_tail`이 함께 갱신된다. 기본 앱은 `juso_text_load`, `daily_juso_delta`, `juso_parcel_link_load`, `juso_parcel_link_delta`, `roadaddr_entrance_load`, `locsum_load`, `navi_load`, `shp_polygons_load`, `pobox_load`, `bulk_load`, `consistency_check`, `mv_refresh`, `db_backup`, `db_restore` 핸들러를 등록한다. T-047 구현 후에는 같은 큐에 `query_benchmark` 핸들러도 등록한다. 이 중 `roadaddr_entrance_load`는 선택 child라 기본 `full_load_batch` 6종에는 들어가지 않는다.

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

T-059 이후 주요 운영 handler는 `infra.concurrency.cross_process_lock()`으로 PostgreSQL session advisory lock을 함께 잡는다. 같은 lock key를 CLI와 API job handler가 공유하므로 같은 파일/target DB/MV refresh/backup/restore 작업이 두 process에서 동시에 시작되면 두 번째 작업은 `ConcurrentExecutionError(E0409, HTTP 409)`로 fail-fast한다. CLI는 같은 오류를 stderr에 출력하고 exit code 2로 종료한다. API queue handler는 lock 충돌 시 `lock_conflict` progress event를 먼저 남기고 job을 `failed`로 닫는다. CLI 단독 실행을 `load_jobs` row로 노출하는 운영 가시화와 서로 다른 job kind가 같은 물리 table을 쓰는 경합의 table 단위 lock은 후속으로 둔다.

ADR-017에 따라 `full_load_batch`는 실행 핸들러가 없는 root job으로 남고, 실제 실행은 child job이 담당한다. source child 6종이 모두 `done`이 되면 큐가 `consistency_check`를 자동 등록한다. 정합성 리포트가 `ERROR`가 아니고 `source_set.load_batch_id`가 확인되면 `mv_refresh`를 `strategy='swap'`으로 등록한다. child 실패 또는 취소가 발생하면 root는 `failed`, 아직 대기 중인 같은 batch child는 `cancelled`가 된다.

T-050 4차 이후 `mv_refresh` handler가 성공하면 `ops.dataset_snapshots`와 `ops.serving_releases`를 자동 기록한다. `full_load_batch`가 등록한 swap은 root payload의 `source_set`, 최신 consistency report, 주요 row count를 snapshot으로 고정하고 `release_kind='full_load'` active release를 만든다. 단독 refresh는 `release_kind='manual_rebuild'`로 기록한다. 새 active release를 만들기 전 기존 active release는 같은 transaction에서 `superseded`로 전환하며, 변경 이력은 `ops.audit_events`에 남긴다.

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

restore job은 기본적으로 새 빈 DB에 복원하므로 복원 완료만으로 serving이 바뀌지는 않는다. T-050 4차 이후 `db_restore` 성공 시 현재 운영 DB의 ops metadata에는 `validated` dataset snapshot과 `pending` restore release 후보만 기록한다. 해당 후보에는 target database, restore artifact id, 원본 backup manifest의 source set/row count/runtime 정보가 들어간다. T-058 1차에서는 `/v1/admin/restores/hot-swap-plan`으로 같은 cluster 안 `ALTER DATABASE ... RENAME` 절차의 typed confirmation, rollback confirmation, SQL, blocker를 먼저 산출한다. 실제 active 승격 실행 API는 ops metadata 위치와 worker별 engine refresh 검증 뒤 후속으로 분리한다.

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

프론트엔드 워크플로는 T-045부터 4단계로 본다.

1. **업로드 세션 생성**: UI가 `POST /v1/admin/uploads`로 `upload_set_id`를 만든다. 같은 화면에서 고른 다중 파일과 drag and drop 파일은 한 upload set에 묶인다.
2. **파일 저장**: 각 파일을 `PUT /v1/admin/uploads/{upload_set_id}/files?filename=...&relative_path=...`로 raw stream 업로드한다. `storage_kind="local"`이면 서버는 `*.part`로 쓰고, byte count와 SHA256을 계산한 뒤 완료 시 atomic rename한다. `storage_kind="rustfs"`이면 같은 검증 후 RustFS object로 put하고 manifest에는 `rustfs://<bucket>/<prefix>/...`, object key, etag를 기록한다. 업로드는 `api_max_upload_bytes`(기본 2GiB)를 넘을 수 없고, `filename`/`relative_path` 정규화 후에도 upload set 경계 밖으로 resolve되면 거절한다.
3. **source set 분석/확인**: 모든 파일 저장이 끝나면 `POST /v1/admin/load-sources/discover`가 upload set 또는 서버 디렉터리를 읽어 원천 후보와 기준월을 반환한다. 기준월이 섞여 있으면 UI/CLI가 사용자 확인을 받은 뒤 `POST /v1/admin/load-sources/plan`으로 `SourceSetPlan`을 만든다.
4. **처리**: 확정된 `SourceSetPlan.batch_payload`만 `POST /v1/admin/loads`에 `kind="full_load_batch"`로 등록한다. 큐가 직렬 처리한다. 진행률은 `/v1/admin/loads` 또는 compatibility alias `/v1/admin/jobs`로 폴링한다.

기존 `POST /v1/admin/upload/sido-zip?filename=...&sido=...`는 단일 시도 ZIP 업로드 호환 경로로 유지할 수 있지만, `/admin/load`의 대용량 full-load UX는 upload set API를 우선 사용한다. 로컬 업로드 디렉토리는 `settings.loader_data_dir/uploads/`이고 RustFS upload set은 `rustfs_prefix/uploads/<upload_set_id>/files/` 아래 object를 사용한다. `upload_set_id = "{timestamp}_{short_hash}"`로 충돌을 방지하고, 완료되지 않은 partial file과 TTL이 지난 로컬 upload set은 `ktgctl uploads cleanup` cron이 정리한다. RustFS 보존기간은 기본 무기한(`rustfs_retention_days=0`)이다.

T-050 1차 hardening 이후 cleanup은 `load_jobs.state IN ('queued','running')` payload에서 `upload_set_id` 또는 upload set 경로를 찾으면 해당 디렉터리를 삭제하지 않는다. 기본 TTL은 `KTG_UPLOAD_SET_TTL_DAYS=30`, active grace는 `KTG_UPLOAD_SET_ACTIVE_GRACE_MINUTES=360`이다. 운영자는 먼저 `ktgctl uploads cleanup --dry-run`으로 삭제 후보를 확인한 뒤 실제 cleanup을 실행한다.

업로드 진행률과 적재 진행률은 같은 값이 아니다. UI는 업로드 단계에서는 브라우저가 전송한 byte 기준 퍼센트를 표시하고, 적재 단계에서는 root/child `load_jobs.progress`의 가중 평균을 표시한다. 업로드 취소는 upload set cancel과 클라이언트 전송 abort로 처리하고, 적재 취소는 root `full_load_batch`에 대한 `/v1/admin/loads/{job_id}/cancel`로 처리한다.

### Source set 발견/계획 — 라이브러리·API 표면 (ADR-029)

API와 라이브러리는 사용자에게 직접 묻지 않는다. 대신 발견, 계획, 큐 등록을 분리한다.

```python
class AsyncAddressClient:
    async def discover_load_sources(
        self,
        root_path: str | None = None,
        *,
        upload_set_id: str | None = None,
        include_optional: bool = True,
    ) -> SourceSetDiscovery: ...

    async def build_full_load_source_set_plan(
        self,
        *,
        root_path: str | None = None,
        upload_set_id: str | None = None,
        versions: dict[str, str],
        explicit_paths: dict[str, str] | None = None,
        allow_mixed_yyyymm: bool = False,
        confirmation_token: str | None = None,
    ) -> SourceSetPlan: ...

    async def submit_full_load_source_set(
        self,
        plan: SourceSetPlan,
    ) -> LoadJobStatus: ...
```

DTO 요약:

```python
class SourceCandidate(FrozenModel):
    kind: Literal["juso","parcel_link","locsum","navi","shp","roadaddr_entrance","sppn_makarea"]
    path: str
    inferred_yyyymm: str | None
    sido_count: int | None = None
    file_count: int | None = None
    byte_size: int | None = None
    sha256: str | None = None
    confidence: Literal["high","medium","low"]
    note: str | None = None

class SourceSetDiscovery(FrozenModel):
    candidates: tuple[SourceCandidate, ...]
    recommended: dict[str, SourceCandidate]
    missing_required: tuple[str, ...]
    mixed_yyyymm: bool
    yyyymm_by_kind: dict[str, str | None]
    warning: str | None = None

class SourceSetPlan(FrozenModel):
    source_set_id: str
    yyyymm_by_kind: dict[str, str]
    mixed_yyyymm: bool
    mixed_yyyymm_acknowledged: bool
    batch_payload: dict[str, Any]
```

REST 경로:

```text
POST /v1/admin/load-sources/discover
POST /v1/admin/load-sources/plan
POST /v1/admin/loads
```

`discover`는 적재를 시작하지 않는다. `plan`은 기준월 불일치와 확인 token을 검증하지만 큐에 작업을 만들지 않는다. `loads`만 `load_jobs` row를 만든다.

### DB 백업/복원 작업 — 라이브러리·API 표면 (ADR-030, T-046)

백업/복원은 적재가 아니지만, 실행 시간이 길고 진행률·취소·재시작 복구가 필요하므로 초기 구현은 `load_jobs` 영속 큐를 재사용한다. 외부 표면은 작업 성격을 더 정확히 드러내기 위해 `/v1/admin/backups`, `/v1/admin/restores`, `/v1/admin/jobs/*`를 사용한다.

기본 백업 형식은 `pg_dump -Fd --jobs <N>` directory dump를 만든 뒤 `manifest.json`, checksum, job log와 함께 `tar.zst`로 묶는 `directory_tar_zstd`다. plain SQL/DDL dump는 대용량 운영 기본값으로 두지 않는다. 복원은 archive를 풀어 `pg_restore -Fd --jobs <N>`로 새 빈 DB에 수행한다.

T-238 이후 `ktgctl backup reconcile-source`는 백업 artifact 또는 `manifest.json`의 `source_match_set` per-file을 현재 DB `ops.source_files`와 RustFS `HEAD` 결과에 대조한다. 기본 백업/복원 흐름에는 영향을 주지 않는 opt-in 점검이며, RustFS 비활성 또는 `source_match_set` 없는 legacy manifest는 `skipped=true` report로 graceful 처리한다. RustFS `HEAD` 404만 `missing`으로 보고, 비-404 오류나 `content-length`가 없는 불완전 응답은 `head_error`로 분리한다.

라이브러리 1차 표면:

```python
class AsyncAddressClient:
    async def submit_backup(
        self,
        *,
        destination_dir: str,
        profile: Literal["serving-ready", "lean-serving", "forensic"] = "serving-ready",
        jobs: int | None = None,
        compression_level: int = 3,
        callback_url: str | None = None,
    ) -> LoadJobStatus: ...

    async def list_backup_artifacts(
        self,
        *,
        limit: int = 50,
    ) -> list[BackupArtifact]: ...

    async def submit_restore(
        self,
        *,
        artifact_id: str,
        target_database: str,
        mode: Literal["new_database"] = "new_database",
        jobs: int | None = None,
        run_smoke_test: bool = True,
        run_consistency: bool = False,
        callback_url: str | None = None,
    ) -> LoadJobStatus: ...
```

REST 1차 표면:

```text
POST /v1/admin/backups
GET  /v1/admin/backups
GET  /v1/admin/backups/{artifact_id}
GET  /v1/admin/backups/{artifact_id}/download
POST /v1/admin/backups/{artifact_id}/delete

POST /v1/admin/restores

GET  /v1/admin/jobs/{job_id}
GET  /v1/admin/jobs/{job_id}/events
POST /v1/admin/jobs/{job_id}/cancel
```

백업 진행률은 `preflight → dump → dump checksum → archive → checksum → finalize`, 복원 진행률은 `preflight → extract → restore → analyze → validate → finalize` 단계로 보고한다. `pg_dump`와 `pg_restore`는 정확한 row progress를 제공하지 않으므로 progress는 phase별 추정값이다. UI와 API는 추정 progress뿐 아니라 `current_stage`, 현재 처리 object/file, dump 디렉터리 크기, archive 입력/출력 byte, checksum byte, elapsed time을 함께 노출해야 한다.

복원은 기본적으로 새 빈 DB에만 허용한다. 현재 연결 중인 운영 DB와 같은 target은 preflight에서 거절한다. T-050 6차부터 `replace_current`는 숨김 위험 경로로만 남기되, `target_dsn`을 받지 않고 target DB 이름이 현재 DB 이름과 같고 확인 문구가 `RESTORE <현재 DB 이름>`이며 같은 확인 문구 hash를 가진 active `restore` maintenance window가 있을 때만 preflight를 통과한다. 선행 백업과 hot-swap은 T-058의 plan/preflight 표면에서 `HOT_SWAP <current> FROM <restore>` 확인 문구와 `previous_alias` rollback 문구를 먼저 산출한 뒤 운영자가 절차를 실행한다.

구현 검증은 전국 full-load를 다시 실행하지 않고 대구광역시 부분 적재 DB로 수행했다. `kor_travel_geo_t046_daegu`를 백업하고 `kor_travel_geo_t046_daegu_restore`에 복원한 뒤 row count, `mv_geocode_target`, 대구 주소 geocode/reverse smoke test를 비교했다. 검증 결과 `tl_juso_text=228,875`, `tl_juso_parcel_link=26,594`, `tl_locsum_entrc=228,610`, `tl_navi_buld_centroid=291,281`, `mv_geocode_target=228,875`가 원본과 복원 DB에서 일치했고, 백업 artifact는 86,752,398 bytes였다. smoke 주소 `대구광역시 중구 공평로 88`은 geocode/reverse 모두 `OK`였다.

### 쿼리 성능 벤치마크 — 라이브러리·API 표면 (ADR-031, T-047)

T-047은 전국 full-load 이후 로컬 DB query latency를 운영 gate로 측정한다. 외부 API fallback은 baseline에서 끄고, `mv_geocode_target`과 후보 보조 view/MV를 사용하는 repo SQL의 순수 성능을 먼저 본다.

라이브러리 후보 표면:

```python
class AsyncAddressClient:
    async def run_query_benchmark(
        self,
        *,
        corpus_path: str,
        iterations: int = 30,
        concurrency: tuple[int, ...] = (1, 4, 16, 64),
        include_explain: bool = True,
        output_dir: str | None = None,
    ) -> PerformanceBenchmarkRun: ...

    async def benchmark_status(self, run_id: str) -> PerformanceBenchmarkRun: ...

    async def benchmark_plan(
        self,
        run_id: str,
        case_id: str,
    ) -> dict[str, Any]: ...
```

REST 후보 표면:

```text
POST /v1/admin/performance/benchmarks
GET  /v1/admin/performance/benchmarks
GET  /v1/admin/performance/benchmarks/{run_id}
GET  /v1/admin/performance/benchmarks/{run_id}/plans/{case_id}
```

benchmark job은 `load_jobs(kind="query_benchmark")` 또는 후속 generic job table에 등록한다. 실행 결과는 `artifacts/perf/<run_id>/`에 JSON/CSV/Markdown으로 남기고, PR에는 핵심 summary만 문서로 옮긴다.

측정 대상은 도로명 exact, 지번 exact, fuzzy geocode, 통합 search, reverse nearest, reverse radius, zipcode lookup, no-result/invalid 경로다. 각 query군은 p50/p90/p95/p99/max, timeout, error rate, `EXPLAIN ANALYZE BUFFERS`, `pg_stat_statements`, plan hash를 기록한다.

T-141 이후 장시간 고부하 검증은 `scripts/run_t141_load_matrix.py`가 담당한다. 이 runner는
SQL/REST workload를 `steady`/`burst`/`recovery`/`soak` phase로 묶고, T-163 기준
`--soak-guard-mode enforce`를 사용하면 soak profile의 runner process RSS 증가,
CPU seconds, `/proc/self/io` read/write budget, RSS leak 판정 실패 시 exit code `2`로
종료한다. T-164 기준 `scripts/evaluate_t164_p99_regression.py`는 baseline/current
`matrix-report.json`의 같은 `profile_id`를 비교해 p99 회귀 임계 초과 시 exit code `2`로
종료한다. API 서버나 PostgreSQL 서버의 별도 process 자원은 이 guard의 직접 측정 범위가
아니다.

목표를 초과하면 다음 순서로 실험한다.

1. query rewrite: exact와 fuzzy 경로 분리, `UNION ALL` branch 분리, early limit, KNN 후보 추출.
2. index: btree composite/`INCLUDE`, `gin_trgm_ops`, partial index, GiST 5179 geometry.
3. read-only 보조 view/MV: `mv_geocode_exact_key`, `mv_geocode_text_search`, `mv_reverse_point_5179`, `mv_zipcode_lookup`.

보조 view/MV는 source of truth가 아니며, 기존 master table 또는 `mv_geocode_target`에서 재생성 가능해야 한다. 도입 PR은 전후 p95/p99, plan, buffer, index/MV size, refresh/swap 시간 영향, T-046 backup/restore 영향을 모두 기록한다. T-061에서 `mv_geocode_text_search`가 실제 helper MV로 추가됐으며, Q3 fuzzy geocode와 Q4 broad search fallback의 후보 추출에 사용한다. T-171 이후 이 helper는 fuzzy geocode가 exact 조회와 같은 건물번호 계약을 유지하도록 `buld_mnnm`/`buld_slno`/`buld_se_cd`를 포함한다. Q4 exact preflight는 기존 `mv_geocode_target` exact index를 유지하되, T-143 이후 `rn_nrm`/`buld_nm_nrm`/`sigungu_buld_nm_nrm` branch를 `UNION ALL`로 분리한다.

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

적재 표면은 `/v1/admin/loads`가 표준 경로다. 단, T-046/T-047부터 `db_backup`, `db_restore`, `query_benchmark`처럼 적재가 아닌 대형 관리 작업도 같은 영속 큐를 쓰므로, 상태 조회·취소·SSE는 중립 alias `/v1/admin/jobs/*`를 함께 둔다. `kor-travel-geo-ui /admin/load` 페이지(`docs/architecture/frontend-package.md` §A6.3)는 `/v1/admin/loads`를, `/admin/backups`와 `/admin/performance` 페이지는 `/v1/admin/jobs/*`를 우선 사용한다.

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
        "db_backup", "db_restore", "query_benchmark",
    ]
    state:         Literal["queued","running","done","failed","cancelled"]
    progress:      float = Field(default=0.0, ge=0.0, le=1.0)
    current_stage: str | None = None
    source_yyyymm: str | None = None
    source_set:    dict[str, Any] | None = None   # ADR-029 SourceSetPlan 요약. 원천별 기준월/확인 여부 포함.
    started_at:    datetime | None = None
    finished_at:   datetime | None = None
    heartbeat_at:  datetime | None = None
    error_message: str | None = None
    log_tail:      tuple[str, ...] = Field(default_factory=tuple)  # 최근 200줄
    payload_summary: dict[str, Any] | None = None  # 민감 정보 제거된 요약
```

`log_tail`은 `Job.log_tail`(deque maxlen=200)을 그대로 직렬화 — 진행 중 작업도 마지막 N줄을 즉시 확인 가능.

### 9.9 정합성 검증 — 라이브러리·API 표면 (ADR-016)

ADR-012의 텍스트 ↔ SHP 정합성 케이스(C1~C10, `docs/architecture/data-model.md` "정합성 검증")를 라이브러리 사용자와 디버그 UI가 직접 트리거·조회할 수 있다.

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
    source_set:   dict[str, Any]          # {yyyymm_by_kind, mixed_yyyymm, mixed_yyyymm_acknowledged, ...}
    started_at:   datetime
    finished_at:  datetime | None = None
    cases:        tuple[ConsistencyCase, ...]
    generated_by: Literal["cli","api","cron"]
```

#### 검증 함수 (`loaders/consistency.py`)

각 케이스 C1~C10은 단일 SQL로 표현하고 결과를 `ConsistencyCase`로 환원한다. 표는 `docs/architecture/data-model.md` "정합성 케이스 분류" 참조.

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
    source_set: dict[str, Any] | None = None,  # batch DAG와 ADR-029 SourceSetPlan 중첩 JSON
    on_progress: ProgressReporter | None = None,
) -> ConsistencyReport:
    """각 케이스의 count/ratio/threshold/metric/sample을 채우고 리포트를 DB에 저장."""
```

#### 디버그 UI 노출

`kor-travel-geo-ui /admin/consistency` 페이지(신규)는 `GET /v1/admin/consistency`로 리스트 + 클릭 시 `GET /v1/admin/consistency/{report_id}`로 상세를 받아 케이스별 severity·count·sample을 카드로 표시한다. `POST /v1/admin/consistency/run`은 우측 상단 "정합성 재검증" 버튼에서 트리거. 화면 사양은 `docs/architecture/frontend-package.md`에 후속 PR로 추가.

### 9.10 적재 진행도 로그·리포트 정책

- **JSON 라인 로그**: `structlog`. 키는 `event`, `job_id`, `kind`, `stage`, `progress`, `rows`, `bytes`, `severity`. 작업 시작/단계 전환/완료/실패 4 시점은 필수, 나머지 진행 갱신은 5초~1MB throttle.
- **`load_jobs.log_tail` JSONB**: 최근 200줄을 DB에 직접 보관한다. 작업 시작, 단계 전환, 완료, 실패, handler의 `progress_cb(..., message=...)` 호출 시 tail을 갱신한다. 프로세스 재시작 후에도 마지막 로그 단서가 남아야 하므로 메모리 전용 deque에 의존하지 않는다.
- **`ops.slow_observability_samples`**: T-158의 opt-in sampled 관측 테이블. 느린 API 요청, admission overload, 느린 DB query의 endpoint·fingerprint·마스킹 preview·선택적 `EXPLAIN (FORMAT JSON)` plan을 저장한다. raw SQL, query parameter, 주소 문자열은 저장하지 않는다.
- **`load_consistency_reports.cases`**: JSONB로 전체 케이스 결과를 한 행에 보관. 시계열 회귀는 `started_at` 인덱스로 조회.
- **알람 정책**(ADR-011 후속, 운영 단계): `severity_max IN ('ERROR')`인 리포트가 생성되면 Prometheus alert (T-025).

## 10. CLI

데이터 경로는 NTFS의 프로젝트 디렉토리 `data/`를 가리킨다. WSL에서 작업할 때는 ext4 작업 디렉토리에 `ln -s /mnt/<drive>/projects/kor-travel-geo/data data`로 심볼릭 링크를 두거나 절대경로(`/mnt/<drive>/projects/kor-travel-geo/data/...`)로 참조한다.

CLI는 운영자가 WSL shell에서 직접 실행하는 **동기 관리 명령**이다. API의 `/v1/admin/loads`는 `load_jobs` 큐와 batch DAG를 통해 백그라운드 실행을 담당한다. 두 경로 모두 같은 loader/core/repository 코드를 쓰지만, CLI는 장기 실행 프로세스가 끊기면 shell exit code로 실패를 전달하고, API 큐는 `load_jobs` 상태로 실패를 남긴다.

```bash
# === 텍스트 정본 적재 (ADR-012, GDAL 무의존) ===
ktgctl load juso  ./data/juso/202603_도로명주소\ 한글_전체분 --yyyymm 202603
ktgctl load locsum ./data/juso/202604_위치정보요약DB_전체분 --yyyymm 202604
ktgctl load navi   ./data/juso/202604_내비게이션용DB_전체분 --yyyymm 202604
ktgctl load daily-juso ./data/juso/daily/20260401_dailyjusukrdata.zip
ktgctl load roadaddr-entrances "./data/juso/도로명주소 출입구 정보" --yyyymm 202605

# === source set 기반 전국 풀로드 계획/실행 (ADR-029, T-045) ===
# 디렉터리를 스캔해 원천 후보와 기준월을 자동 매칭한다.
# 기준월이 서로 다르면 대화형 확인 문구 없이는 적재하지 않는다.
ktgctl load full-set ./data/juso --discover

# cron/CI처럼 비대화형으로 실행할 때는 각 원천 기준월과 혼합 확인을 명시한다.
ktgctl load full-set ./data/juso \
  --juso-yyyymm 202603 \
  --parcel-link-yyyymm 202603 \
  --locsum-yyyymm 202604 \
  --navi-yyyymm 202604 \
  --shp-yyyymm 202604 \
  --roadaddr-entrance-yyyymm 202605 \
  --allow-mixed-yyyymm \
  --confirm-source-set "202603/202604/202605 혼합 적재 확인"

# === 전국 단위 직접 풀로드 ===
# 기존 `all-sidos --yyyymm`는 단일 기준월을 모든 child에 적용하므로,
# 원천별 업데이트 월이 다른 운영 적재에서는 `load full-set` 사용을 우선한다.
ktgctl load all-sidos \
  --juso ./data/juso/202603_도로명주소\ 한글_전체분 \
  --locsum ./data/juso/202604_위치정보요약DB_전체분.zip \
  --navi ./data/juso/202604_내비게이션용DB_전체분 \
  --shp-root ./data/juso/도로명주소\ 전자지도 \
  --yyyymm 202604 \
  --swap

# === SHP polygon 적재 (ADR-005, GDAL 필요) ===
ktgctl load shp ./data/juso/도로명주소\ 전자지도/강원특별자치도 --mode full --yyyymm 202604
ktgctl load shp-all ./data/juso/도로명주소\ 전자지도 --mode full --yyyymm 202604

# 변동분 (SHP polygon만)
ktgctl load shp ./data/juso/delta/202605/seoul --mode delta

# 변동분 (도로명주소 한글 일변동 ZIP)
ktgctl load daily-juso ./data/juso/daily

# === 보조 우편번호 (ADR-009, 분기 1회) ===
ktgctl load pobox ./data/postal/202605/JUSO_사서함.txt
ktgctl load bulk  ./data/postal/202605/도로명주소_zipcode.txt
# 또는 epost OpenAPI 자동 다운로드
ktgctl load epost --kind=full

# === 후처리 ===
ktgctl refresh mv                        # CONCURRENTLY (평시)
ktgctl refresh mv --swap                 # shadow MV swap (분기 풀로드 후)

# T-061 이후 raw psql refresh 대신 위 orchestration을 사용한다.

# === 정합성 검증 (ADR-012, ADR-016) ===
ktgctl validate consistency               # 모든 케이스 C1~C10
ktgctl validate consistency --scope=full
ktgctl validate consistency --cases=C4,C7 # 특정 케이스만 JSON 출력

# === T-031 데이터 품질 후속 sample export ===
ktgctl validate data-quality-samples \
  --cases C2,C4,C6,C7 \
  --limit 200 \
  --output-dir artifacts/fullload/data-quality

# === 작업 큐 상태 조회 (ADR-011, ADR-016) ===
ktgctl jobs list                          # 최근 작업 목록
ktgctl jobs status <job_id>               # 단일 작업 상태/진행률/log_tail
ktgctl jobs cancel <job_id>

# === DB 백업/복원 (ADR-030, T-046) ===
# 기본값은 pg_dump -Fd --jobs + tar.zst archive다. plain SQL dump는 기본 제공하지 않는다.
ktgctl backup create \
  --destination-dir /mnt/f/backups/kor-travel-geo \
  --profile serving-ready \
  --jobs 4 \
  --callback-url http://localhost:9000/hooks/backup-complete
ktgctl backup list
ktgctl backup show <artifact_id>

# 복원은 기본적으로 새 빈 DB에만 수행한다.
ktgctl restore create \
  --artifact-id <artifact_id> \
  --target-database kor_travel_geo_t046_daegu_restore \
  --jobs 4 \
  --run-smoke-test

# === 전국 DB 쿼리 성능 벤치마크 (ADR-031, T-047) ===
# full-load 이후 로컬 DB query latency를 반복 측정한다. 외부 API fallback은 baseline에서 끈다.
ktgctl benchmark queries \
  --corpus artifacts/perf/corpus/standard.jsonl \
  --iterations 30 \
  --concurrency 1,4,16,64 \
  --include-explain \
  --output-dir artifacts/perf/$(date +%Y%m%d_%H%M%S)

# 특정 slow case의 plan만 다시 저장한다.
ktgctl benchmark explain \
  --case-id Q5_reverse_nearest_001 \
  --output artifacts/perf/plans/Q5_reverse_nearest_001.json

# === 무결성 + 헬스 ===
ktgctl validate consistency               # C1~C10 정합성(행 수·매핑·MV·기준월) 점검
ktgctl validate data-quality-samples      # C2/C4/C6/C7 표본 CSV export
ktgctl healthz
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
    env: { POSTGRES_PASSWORD: t, POSTGRES_DB: kor_travel_geo }
    options: >-
      --health-cmd pg_isready --health-interval 10s
      --health-timeout 5s --health-retries 5
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: { python-version: '3.12' }
  - run: pip install -e ".[api,loaders,dev]"
  - run: ruff check .
  - run: mypy src/kortravelgeo
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

발급 절차·정책은 `docs/architecture/external-apis.md` 참조.

### 운영 (uvicorn systemd)

```ini
[Service]
Type=simple
User=addr
WorkingDirectory=/opt/addr/app
Environment=KTG_LOG_FORMAT=json
EnvironmentFile=/etc/kor-travel-geo/env
ExecStart=/opt/addr/app/.venv/bin/uvicorn kortravelgeo.api.app:app \
          --host 127.0.0.1 --port 8888 --workers 2 --proxy-headers
Restart=always
RestartSec=3
LimitNOFILE=65535
```

### 외부 API 호출 정책

- **재시도**: `tenacity`로 5xx/timeout만 3회 지수 backoff. 4xx는 즉시 실패.
- **회로차단**: 같은 외부 서비스에 1분 내 5회 연속 실패하면 60초 폴백 호출 차단.
- **쿼터 보호**: 일 한도 80% 도달 시 Prometheus 알람. 90% 초과 시 자동으로 인터벌 늘리거나 폴백 비활성화.
- **로그**: 호출 1건당 한 줄 structlog(서비스명·응답 시간·상태·응답 크기). 키는 절대 로그에 남기지 않음(`SecretStr`).
