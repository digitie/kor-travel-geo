# CHANGELOG

본 문서는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따른다. 버전은 [Semantic Versioning](https://semver.org/lang/ko/)을 따른다.

## [Unreleased]

### Fixed
- T-027 실제 SHP 적재 검증 중 발견한 GDAL/PostGIS 로더 문제를 보정한다. GDAL 3.8 호환을 위해 CP949는 `SHAPE_ENCODING` config option으로 지정하고, full SHP 적재는 운영 테이블을 한 번 `TRUNCATE`한 뒤 기존 DDL 스키마에 `append`한다. `shp-all --mode full`은 첫 시도만 full, 이후 시도는 append로 전환해 전국 적재분이 시도별 overwrite로 사라지지 않게 한다.
- T-027 실제 SHP 헤더 기준으로 `TL_SPRD_RW`를 `MULTIPOLYGON 5179` 도로면 polygon으로 바로잡는다. 기존 `MULTILINESTRING` 정의는 2026년 전자지도 실제 파일과 맞지 않아 적재 실패를 유발할 수 있었다.
- `kraddr-geo init-db`가 이미 대량 데이터가 들어간 DB에서 MV 생성 timeout을 만나도 앞선 schema DDL을 롤백하지 않도록 schema/index/MV statement를 별도 트랜잭션으로 실행하고, 경고 개수를 명시한다.
- T-027 후처리 재개성을 보강한다. `refresh mv --swap`은 기존 `mv_geocode_target`이 없는 복구 상황에서도 `mv_geocode_target_next`를 바로 승격할 수 있고, full-load 스크립트는 기본 statement timeout을 30분으로 높여 링크 해소/MV 빌드가 5초 기본값에 막히지 않게 한다.
- T-027 실제 MV 검증에서 발견한 내비 centroid fallback 누락을 수정한다. 내비게이션용DB 건물 중심점의 `bd_mgt_sn`은 실제 파일 기준 25자리이고 정본 `tl_juso_text.bd_mgt_sn`은 26자리라 직접 조인되지 않는다. MV는 `rncode_full + 건물구분 + 본번/부번 + left(bjd_cd, 8)` 기준 대표 centroid를 선택한다.
- T-027 실제 데이터로드 실행 중 발견한 로컬 PostgreSQL 포트 충돌 위험을 줄인다. `docker-compose.yml`은 `KRADDR_DB_PORT`로 외부 포트를 바꿀 수 있고, `scripts/fullload_test.sh`는 `KRADDR_GEO_PG_DSN`이 없을 때 이 포트를 반영해 DSN을 만든다.
- PR #12 리뷰 반영: `/v1/admin/upload/sido-zip`의 `sido` path traversal 가능성을 제거하고, `KRADDR_GEO_API_MAX_UPLOAD_BYTES` 초과 시 partial file을 삭제한 뒤 `InvalidInputError(E0100)`로 거절한다.
- PR #12 리뷰 반영: `kraddr-geo-ui` 프록시는 `/v1/` 하위 경로만 허용하고 `authorization`/`cookie` 등 불필요한 헤더 전달을 차단한다. 업로드 본문은 `arrayBuffer()`로 전체 버퍼링하지 않고 `ReadableStream` + `duplex: "half"`로 백엔드에 전달한다.
- PR #12 리뷰 반영: `requestJson()`은 `ApiError.status`를 보존하고 React Query retry는 4xx를 재시도하지 않는다.
- PR #12 리뷰 반영: `/v1/admin/explain` 실행 전 `SET LOCAL` 성격의 `set_config('statement_timeout', ..., true)`를 적용한다. 기본값은 `KRADDR_GEO_API_EXPLAIN_TIMEOUT_MS=3000`.
- PR #12 리뷰 반영: `LoadConsole`, `ExplainDebugger`, `ReverseDebugger`, `ConsistencyPanel`의 에러 처리와 입력 검증을 보강한다.
- PR #12 리뷰 반영: `kraddr_geo_cache_hits_total` gauge를 Prometheus 관례에 맞게 `kraddr_geo_cache_hits`로 변경한다.
- GitHub Actions backend 실패 수정: `tests/unit/test_openapi_export.py`가 CI에서도 `scripts.export_openapi`를 import할 수 있도록 `scripts/__init__.py`를 추가하고 pytest `pythonpath`에 repository root를 명시한다.
- PR #11 리뷰 반영: `AsyncAddressClient.submit_load("full_load_batch", ...)`이 root 행만 만들던 라이브러리/REST 비대칭을 해소한다. 라이브러리도 `AdminRepository.insert_load_batch`로 라우팅되어 root + 5종 child가 동시에 적재된다. `BATCH_SOURCE_KINDS`와 `batch_children()`은 `kraddr.geo.infra.batch` 모듈로 이동해 client / api 양쪽에서 공유한다.
- PR #11 후속 보강: `full_load_batch` payload를 enqueue 전에 검증한다. 기본 `payloads` 경로는 source child 5종 모두에 `path` 또는 `source_path`가 있어야 하며, 잘못된 `children`/`child_jobs` entry는 조용히 무시하지 않고 `InvalidInputError(E0100)`로 거절한다.

### Changed
- **(BREAKING)** `kraddr.geo` 패키지의 저장 엔진을 SQLite + SpatiaLite에서 PostgreSQL + PostGIS로 전환한다. 패키지 이름은 그대로지만 내부 구현은 완전히 새로 작성한다. 이전 구현은 `v1` 브랜치에 보존되어 있다.
- GitHub 저장소 이름을 `python-kraddr-geo`로 명시하고, CLI 명령은 `kraddr-geo`, 환경변수 prefix는 `KRADDR_GEO_`, PostgreSQL DB 이름은 `kraddr_geo`로 통일한다.
- 개발 정책: PC 개발은 WSL의 ext4 위에서 진행하고 작업 완료 시 NTFS의 프로젝트 디렉토리로 카피한다. 데이터(`data/`)는 NTFS 프로젝트 디렉토리 아래에 두고 테스트도 이를 참조한다.
- 기본 설정값을 백엔드 사양과 맞춘다: statement timeout 5초, reverse 기본 반경 200m, CORS 기본값 빈 목록, epost 우편번호 다운로드 OpenAPI endpoint.
- 설정 싱글톤 테스트 helper를 `reset_settings()`와 `set_settings(settings)`로 분리한다.
- base 예외명을 `KraddrGeoError`로 확정하고, `kraddr` parent package는 PEP 420 implicit namespace로 둔다.
- **(BREAKING)** 라이브러리 진입점을 동기 `SpatialiteAddressStore`에서 비동기 `AsyncAddressClient`로 교체한다. 동기 호출이 필요하면 호출자가 `asyncio.run`으로 감싼다.
- 응답 구조를 vworld와 호환되도록 정렬하고 자체 필드는 `x_extension` 네임스페이스로 격리한다.
- 디버그/관리 UI를 monorepo 내부의 `debug-ui/` 대신 별도 Node.js 패키지 `kraddr-geo-ui`(Next.js 16 + Tailwind + react-kakao-maps-sdk)로 분리한다.
- 디버그/관리 UI는 내부망 전용으로 운영하며 애플리케이션 인증을 두지 않는다(ADR-013).

### Added
- Windows 재설치·새 Codex 세션 복구 문서를 추가한다. `docs/windows-reinstall-recovery.md`는 Git/PR handoff, `data/`·`.env` 백업, WSL/GDAL 복구, Codex `resume`/`fork`/로컬 백업 명령, PR #13의 실행 금지선을 정리한다. `CLAUDE.md`와 `docs/dev-environment-recovery.md`도 실제 전체 적재는 사용자 명시 후에만 실행하도록 맞춘다.
- PR #13/T-027 계획 보강: Docker PostGIS 기반 실제 `data/juso` 전체 적재 검증 계획서를 실행 전 리뷰 가능한 수준으로 확장하고, `PLAN_ONLY=1` preflight를 지원하는 `scripts/fullload_test.sh`를 정리한다. 실제 전체 적재 실행은 아직 수행하지 않는다.
- T-021~T-026 구현: `kraddr-geo-ui` Next.js 16 패키지, 디버그 페이지(`/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain`), 관리 페이지(`/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`, `/admin/consistency`)를 추가한다.
- `kraddr-geo-ui`는 `openapi.json`에서 `types/api.gen.ts`와 `lib/schemas.gen.ts`를 생성하는 `npm run gen:types`를 제공한다. CI는 생성 결과 drift가 있으면 실패한다.
- `react-kakao-maps-sdk` 기반 좌표 지도 컴포넌트를 추가한다. `NEXT_PUBLIC_KAKAO_JS_KEY`가 없거나 지도 로딩에 실패하면 좌표 프리뷰로 대체되어 내부망/CI 환경에서도 화면이 깨지지 않는다.
- FastAPI admin 표면을 확장한다. `/v1/admin/tables`, `/v1/admin/explain`, `/v1/admin/cache/metrics`, `/v1/admin/logs`, `/v1/admin/upload/sido-zip`, `/v1/admin/maintenance/refresh-mv`를 추가하고 `AsyncAddressClient`에도 같은 조회 메서드를 연결한다.
- `/metrics` Prometheus endpoint를 추가한다. 외부 API 호출 결과, `geo_cache` entries/hits/expired, `load_jobs` kind/state 분포를 노출하며, `prometheus-client`가 없는 library-only 환경에서는 no-op fallback으로 동작한다.
- 루트 `.pre-commit-config.yaml`과 `.github/workflows/ci.yml`을 추가한다. 백엔드는 `ruff check`, `mypy`, `lint-imports`, `pytest`; 프론트엔드는 `npm ci`, `gen:types`, `lint`, `type-check`, `test`, `build`를 수행한다.
- ADR-019 추가: `kraddr-geo-ui`의 런타임 보안 하한선을 Next.js 16으로 둔다. Next.js 14 계열 production high advisory를 신규 도입 시점부터 피한다.
- PR #10 리뷰 반영: `load_jobs.load_batch_id`/`parent_job_id`와 `full_load_batch` DAG를 추가한다. source load 5종이 모두 성공하면 `consistency_check`를 자동 등록하고, 정합성 리포트가 `ERROR`가 아닐 때만 `mv_refresh`를 `strategy='swap'`으로 등록한다(ADR-017).
- PR #10 리뷰 반영: 정합성 검증을 C1~C10 전체로 확장하고, 각 케이스에 `count`, `ratio`, `threshold`, `metric`, `sample`을 채운다. batch DAG는 `source_set.load_batch_id`가 있는 리포트를 게이트로 사용한다.
- PR #10 리뷰 반영: `JobQueue` handler 시그니처에 진행률 콜백을 추가하고, `load_jobs.log_tail`을 실제로 갱신한다. FastAPI lifespan은 기본 적재/정합성/MV refresh handler를 등록한다.
- ADR-018 추가: PostGIS, `pg_trgm`, `unaccent` extension은 `x_extension` 스키마에 설치하고 모든 연결에서 `search_path=public,x_extension`를 사용한다.
- T-018 CLI 운영 명령을 추가한다. `load all-sidos`, `load shp`, `load shp-all`, `load pobox`, `load bulk`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope`를 지원한다.
- T-019 외부 API 폴백 어댑터를 추가한다. `fallback="api"`는 로컬 `NOT_FOUND` 이후 vworld 주소 좌표 API와 juso 검색+좌표 API를 순서대로 호출하며, 공급자 출처는 `x_extension.source`에만 기록한다.
- T-020 OpenAPI export와 drift 검사를 추가한다. `scripts/export_openapi.py`, committed `openapi.json`, `.github/workflows/openapi.yml`을 통해 API 스키마 변경 누락을 CI에서 잡는다.
- T-005~T-017 1차 구현: async engine factory, PostGIS/Alembic schema, `mv_geocode_target`, raw SQL repositories, core geocode/reverse/search/zipcode/pobox flows, `AsyncAddressClient`, FastAPI routers, persistent `load_jobs` queue, text/SHP/postal loaders를 추가한다.
- 실제 `data/juso` 기반 검증 테스트를 추가한다. 도로명주소 한글 서울 파일, 위치정보요약DB ZIP member, 내비게이션용DB 서울 파일, 강원 SHP load plan을 직접 읽어 컬럼 인덱스·좌표·PNU 매핑을 검증한다.
- 선택형 실제 PostgreSQL 적재 테스트를 추가한다. `KRADDR_GEO_TEST_PG_DSN`이 설정되면 DDL 적용 → 실제 파일 샘플 COPY 적재 → 위치정보↔텍스트 링크 해소 → `mv_geocode_target` 생성까지 실행한다.
- 문서 구조에 `SKILL.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/data-model.md`, `docs/tasks.md`, `docs/resume.md`, `docs/journal.md`를 도입한다.
- 외부 REST API(vworld, juso, epost, kakao maps)의 발급 절차와 호출 정책을 `docs/external-apis.md`로 정리한다.
- 시도별 ZIP 업로드와 작업 큐 기반 직렬 적재 워크플로(`/v1/admin/upload/sido-zip`, `/v1/admin/loads`)를 사양으로 명시한다.
- `pyproject.toml`, `.env.example`, `Settings`, 기본 패키지 스캐폴드, 공통/주소 DTO와 단위 테스트를 추가한다.
- `docs/dev-environment.md`를 추가하고 시스템 GDAL(`libgdal-dev`) 설치 + `pip install "gdal==$(gdal-config --version)"` 절차를 ADR-008로 명시한다.
- 우편번호 적재 정책을 ADR-009로 확정: epost OpenAPI 데이터셋 `15000302`의 `downloadKnd=1`(전체) ZIP을 분기 1회 받아 `postal_pobox`/`postal_bulk_delivery`를 TRUNCATE 후 INSERT 한다. 실시간 lookup API(`15056971`)는 도입하지 않는다.
- geocode/reverse/search/zipcode/pobox/admin DTO와 단위 테스트를 추가하고, `data/juso/도로명주소 전자지도` 실제 SHP/DBF 파일을 여는 레이어 검사 테스트를 추가한다.
- ADR-010 추가: PNU 토지구분 매핑(`mntn_yn 0→1, 1→2`)과 조립 위치(`infra/` 또는 generated stored column). `core/`는 의미론적 `mntn_yn`만 보관.
- ADR-011 추가: 적재 작업 상태를 `load_jobs` 테이블로 영속화. lifespan startup에서 잔존 `running→failed`, `queued`는 payload 존재 여부에 따라 재큐잉/`failed`. 다중 워커 안전성은 `pg_try_advisory_lock` + `FOR UPDATE SKIP LOCKED`.
- 공간 쿼리 가이드: 반경/nearest는 `pt_5179`(meter, GiST `idx_mv_geom5179`) 기준, `pt_4326`은 응답 전용. 입력 좌표는 CTE/파라미터에서 한 번만 `ST_Transform`(SKILL.md §4-11).
- MV 갱신 모드 두 가지 정의: 평시 `REFRESH CONCURRENTLY`, 분기 풀로드는 shadow MV(`mv_geocode_target_next`) 빌드 후 트랜잭션 RENAME swap.
- engine factory(`infra/engine.py`) 단순화: DSN 보정은 `Settings.normalize_pg_dsn` 단일 책임. 중복 검사 제거.
- 적재 ↔ 서빙 단일 스키마 정책 명시: 별도 `*_serving_*` 스키마 도입 금지, 평면화는 MV로만 표현(ADR-007 후속).
- **(BREAKING in spec)** ADR-012 추가: 적재를 행안부 텍스트 정본 1차(도로명주소 한글_전체분/위치정보요약DB_전체분/내비게이션용DB_전체분, `loaders/text/`, stdlib csv + `psycopg.copy()`) + SHP polygon 보조(`loaders/shp/`, GDAL Python binding 한정) 하이브리드로 전환. ADR-005는 polygon 적재로 partial supersede.
- 마스터 테이블을 텍스트 4(`tl_juso_text`, `tl_locsum_entrc`, `tl_navi_buld_centroid`, `tl_navi_entrc`) + SHP polygon/폴리라인 9 + 보조 우편번호 2 + 메타 5(`load_jobs`, `load_consistency_reports` 신규 포함)로 재구성한다.
- ADR-007 복원·재정의: 대표 출입구 선택을 위치정보요약DB의 `ent_se_cd` 기반으로 명시. MV에 `pt_source ∈ {entrance, centroid}` 컬럼 추가 — 출입구 0개 건물은 내비게이션용DB centroid를 fallback 좌표로 사용.
- ADR-016 추가: 적재 진행도(`AsyncAddressClient.load_status/list_load_jobs/submit_load/cancel_load`, `/v1/admin/loads/*` REST)와 정합성 리포트(`run_consistency_check`/`consistency_report`, `/v1/admin/consistency/*` REST, 케이스 C1~C10, `load_consistency_reports` JSONB)를 라이브러리·REST·디버그 UI에 일급 노출.
- `tl_juso_text.pnu` generated stored column으로 ADR-010 매핑(`mntn_yn 0→1, 1→2`) 박음. PNU 19자리 정합성을 정합성 케이스 C9로 검증.
- MV `mv_geocode_target` 컬럼명 변경: `ent_pt_5179`/`ent_pt_4326` → `pt_5179`/`pt_4326`. `pt_source` 신규.
- 위치정보요약DB 적재 사양을 실제 파일 기준으로 보정한다. `entrc_*.txt`에는 `bd_mgt_sn`이 직접 없으므로 원본 natural key를 적재한 뒤 `tl_juso_text`와 후처리 조인으로 `bd_mgt_sn`을 해소한다.
- SHP 보조 적재 대상 표기를 polygon 7종에서 polygon/폴리라인 9종으로 명확화한다(`tl_sprd_manage`, `tl_sprd_intrvl`, `tl_sprd_rw` 포함).
- reverse geocoding의 `type="both"`가 같은 최근접 후보를 도로명/지번 결과로 각각 반환하도록 보정한다.
- 텍스트 로더 인코딩 감지를 `utf-8-sig` BOM → `cp949` 검증 → `utf-8` 검증 순서로 보강한다.
- `tl_juso_text.pnu` generated column은 `mntn_yn IS NULL`을 명시적으로 가드한다. `bd_mgt_sn` 길이 체크는 사양 25자리와 실제 2026-03 서울 파일 26자리를 모두 수용하도록 `BETWEEN 25 AND 26`으로 좁힌다.

### Removed
- 동기 라이브러리 API, monorepo 내부 디버그 UI, `ogr2ogr` subprocess 호출 경로를 사양에서 제거한다.

## 사양 기준일
2026-05-22
