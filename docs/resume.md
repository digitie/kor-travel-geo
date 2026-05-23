# RESUME — 작업 재개 가이드

새 에이전트 세션이 시작될 때 "지금 어디까지 했고, 다음은 뭐 하면 되나"를 한 화면에서 답한다.

## 현재 진척도 (2026-05-23 갱신, by codex)

- ✅ 이전 SpatiaLite 기반 `kraddr.geo` 구현을 `v1` 브랜치로 이관
- ✅ master 브랜치를 문서·repo 설정만 남도록 정리
- ✅ 신규 사양(`kraddr.geo` 패키지의 PostgreSQL+PostGIS 재구현 + `kraddr-geo-ui` 프론트엔드) 문서 골격을 master에 반영
- ✅ 식별자 정정 및 WSL/NTFS 개발 정책, NTFS의 `data/` 정책을 모든 문서에 명시
- ✅ `pyproject.toml` 신규 작성 — `name = "python-kraddr-geo"`, scripts `kraddr-geo = "kraddr.geo.cli.main:app"`
- ✅ 기본 패키지 스캐폴드 작성 — `src/kraddr/geo/`, 계층별 빈 패키지, `AsyncAddressClient` 자리표시자, Typer CLI 진입점
- ✅ `Settings` + `.env.example` 작성 — `KRADDR_GEO_` prefix, DB/API/외부 API/cache/log/loader 설정
- ✅ `dto/common.py`, `dto/address.py` 작성 — CRS 정규화, 불변 DTO, vworld 주소 구조 + 단위 테스트
- ✅ 나머지 DTO(`geocode`, `reverse`, `search`, `zipcode`, `pobox`, `admin`) 구현
- ✅ `data/juso/도로명주소 전자지도` 실제 SHP/DBF 파일 헤더·필드 검사 테스트 추가 (`강원특별자치도/51000`)
- ✅ DDL/Alembic 적용 (`sql/ddl/`, `alembic/versions/0001_text_primary_postgis_schema.py`)
- ✅ `infra/engine.py`, raw SQL repo(`geocode/reverse/search/zip/pobox/admin`) 구현
- ✅ `core/normalize.py`, `core/geocoder.py`, `reverse/search/zipcode/pobox` 코어 구현
- ✅ `AsyncAddressClient` 실제 기능 연결 — geocode/reverse/search/zipcode/pobox, load job 조회/등록/취소, consistency report 조회
- ✅ FastAPI 앱/라우터 구현 — `/v1/address/*`, `/v1/admin/loads`, `/v1/admin/consistency/*`
- ✅ 텍스트 정본 로더 구현 — `juso_hangul_loader.py`, `locsum_loader.py`, `navi_loader.py`
- ✅ SHP 보조 로더/후처리 구현 — `polygons_loader.py`, `delta_loader.py`, `postload.py`, `consistency.py`
- ✅ epost 보조 우편번호 로더 구현 — `pobox_loader.py`, `bulk_loader.py`
- ✅ 실제 `data/juso` 파일 검증 — 도로명주소 한글 서울 파일, 위치정보요약DB ZIP member, 내비게이션용DB 서울 파일, 강원 SHP load plan
- ✅ 실제 PostgreSQL(PostGIS) 샘플 적재 검증 — 별도 테스트 DB에서 DDL 적용 → 실제 파일 COPY 샘플 load → 링크 해소 → MV 생성 확인
- ✅ PR #10 리뷰 반영 — `load_jobs` batch DAG(`load_batch_id`, `parent_job_id`, `full_load_batch`), C1~C10 정합성 검증, PNU NULL guard, reverse `both`, 인코딩 fallback, `log_tail` 갱신 경로 구현
- ✅ ADR-017(batch DAG + 정합성 게이트)과 ADR-018(`x_extension` 스키마 격리) 문서화
- ✅ T-018 CLI 운영 명령 구현 — `load all-sidos`, `load shp/shp-all`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope`
- ✅ T-019 외부 API 폴백 구현 — `fallback="api"`일 때 로컬 `NOT_FOUND` 후 vworld → juso 검색+좌표 순서로 호출
- ✅ T-020 OpenAPI export 구현 — `scripts/export_openapi.py`, committed `openapi.json`, `.github/workflows/openapi.yml` drift 검사
- ✅ PR #11 후속 반영 — `full_load_batch` REST/라이브러리 공유 DAG 경로 확인, enqueue 전 child payload fail-fast 검증, PR 코멘트용 검증 근거 정리
- ✅ PR #12 기반 보강 — PR #11을 main에 머지하고, 후속 의견은 PR #12로 이관
- ✅ T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩 — Next.js 16 + React 18 + Tailwind + TanStack Query + `react-kakao-maps-sdk`
- ✅ T-022 디버그 페이지 구현 — `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain`
- ✅ T-023 관리 페이지 구현 — `/admin/load`, `/admin/tables`, `/admin/cache`, `/admin/logs`
- ✅ T-024 품질 게이트 추가 — 루트 `pre-commit`, 통합 CI, frontend `gen:types` drift 검사, lint/type/test/build
- ✅ T-025 Prometheus 메트릭 구현 — `/metrics`, 외부 API 호출 counter, cache/load job gauge
- ✅ T-026 정합성 UI 구현 — `/admin/consistency`에서 C1~C10 report 목록·상세·재검증 enqueue 확인
- ✅ FastAPI admin 보강 — `/v1/admin/tables`, `/v1/admin/explain`, `/v1/admin/cache/metrics`, `/v1/admin/logs`, `/v1/admin/upload/sido-zip`, `/v1/admin/maintenance/refresh-mv`

## 다음 한 작업 (1시간 이내 분량)

PR #12 리뷰를 기다린다. 리뷰가 없으면 다음 후보는 `/admin/load`의 장기 실행 UX 보강이다.

- `fetch` 기반 raw upload는 backend와 일치하지만 업로드 진행률 이벤트가 없다. 운영자가 대용량 ZIP을 올릴 때 필요하면 XHR 기반 progress bar를 추가한다.
- `/admin/logs`는 현재 `load_jobs.log_tail` 최근 라인 조회다. 장기적으로 WebSocket/Server-Sent Events tail을 붙일 수 있다.
- `/debug/reverse`는 Kakao 지도 클릭으로 좌표를 채우되 자동 조회는 하지 않는다. 클릭 즉시 reverse 호출이 필요하면 명시적 UX 결정 후 추가한다.

## 작업 시작 전 확인할 것

- [ ] `AGENTS.md`의 "식별자" 표와 "개발 환경 정책" 다시 읽기
- [ ] `SKILL.md` §4 "DO NOT" 룰 다시 읽기
- [ ] `docs/architecture.md`의 의존 방향 확인
- [ ] `docs/decisions.md`의 ADR-001 ~ ADR-019 확인 (특히 **ADR-012 텍스트 정본 + SHP polygon 하이브리드**, ADR-017 batch DAG, ADR-018 `x_extension` 스키마, ADR-019 Next.js 16 보안 하한선)
- [ ] 마지막 `docs/journal.md` 엔트리 읽기
- [ ] NTFS의 `data/` 디렉토리가 준비되어 있고 ext4에서 심볼릭 링크 또는 절대경로로 접근 가능한지

## 알려진 함정

- **WSL/NTFS 분리**: ext4 작업 디렉토리에서 NTFS의 `data/`로 심볼릭 링크를 둘 때 권한/inotify 이슈 발생 가능. 절대경로 사용을 권장.
- `pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` — 전역 변경 금지 (SKILL.md §4-3)
- 좌표 입력은 `(lon, lat)` 순서. `(lat, lon)`으로 받으면 한국 밖으로 가서 `InvalidCoordinateError` 발생
- `ogr2ogr -append`와 `-overwrite`를 같이 쓰지 말 것 (GDAL Python binding으로 대체)
- `MVM_RES_CD` 매핑은 코드 상수가 아닌 settings 또는 DB `load_codes` 테이블에서 읽는다
- PostgreSQL DB 이름은 `kraddr_geo` (dot 불가). 환경변수 prefix는 `KRADDR_GEO_`.
- 현재 셸처럼 `TMP`/`TEMP`가 Windows Temp(`/mnt/c/...`)를 가리키면 pytest 캡처가 `FileNotFoundError`로 실패할 수 있다. WSL에서는 `TMPDIR=/tmp TMP=/tmp TEMP=/tmp python -m pytest`처럼 Linux `/tmp`를 지정한다.
- **GDAL 버전 미스매치**: Python `gdal` 패키지가 시스템 GDAL과 다른 버전이면 `ImportError: undefined symbol`. `pip install "gdal==$(gdal-config --version)"`로 핀(ADR-008, `docs/dev-environment.md`).
- **`libgdal-dev` 누락**: `pip install -e ".[loaders]"`가 `gdal-config: command not found`로 실패. WSL에서는 `sudo apt install libgdal-dev gdal-bin` 후 재시도.
- **위치정보요약DB에는 `bd_mgt_sn`이 직접 없다**: 실제 `entrc_*.txt`는 `sig_cd`, `ent_man_no`, `bjd_cd`, `rncode_full`, 건물번호, 우편번호, 좌표를 제공한다. 로더는 원본 키를 보존하고 `postload.resolve_text_geometry_links()`에서 `tl_juso_text`와 조인해 `bd_mgt_sn`을 해소한다.
- **일부 위치정보요약DB 행은 좌표가 비어 있다**: `tl_locsum_entrc.geom`은 `NOT NULL`이므로 로더는 X/Y가 모두 있는 행만 적재한다. 좌표 결측 비율은 정합성 리포트(C3 확장)에서 별도 집계할 수 있다.
- **실제 DB 적재 검증**: 로컬 PostGIS가 준비되어 있으면 `KRADDR_GEO_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_load.py -q`로 실제 `data/juso` 샘플 COPY와 MV 생성을 확인한다.
- **프론트엔드 TypeScript 캐시**: `kraddr-geo-ui/tsconfig.tsbuildinfo`는 생성물이다. `.gitignore` 대상이며 PR에 포함하지 않는다.
- **Next.js 16 Route Handler context**: `app/api/proxy/[...path]/route.ts`의 `params`는 Promise다. Next.js 14 예시처럼 동기 객체로 받으면 type-check가 실패한다.

## 작업 후 의무사항

1. `docs/journal.md`에 항목 추가 (날짜·요약·관련 파일·결정·다음 작업)
2. 본 `docs/resume.md`의 진척도 토글 갱신
3. 변경된 결정이 있다면 `docs/decisions.md`에 ADR 추가
4. 사용자 가시 변경이면 `CHANGELOG.md` 갱신
5. 스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
