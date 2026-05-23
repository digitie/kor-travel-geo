# TASKS — 백로그

작업 항목은 `T-NNN` 형식의 ID로 관리한다. 새 작업은 "대기"의 우선순위 순서대로 들어가고, 진행 중이 되면 담당자를 표시한다. 완료된 작업은 "완료" 섹션 상단에 누적한다.

## 진행 중
- (없음)

## 대기 (우선순위 순)
- [ ] T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩 (`docs/frontend-package.md` §A2)
- [ ] T-022 프론트엔드 `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain` 페이지
- [ ] T-023 프론트엔드 `/admin/load`(업로드 + 처리 워크플로), `/admin/tables`, `/admin/cache`, `/admin/logs`
- [ ] T-024 `pre-commit`, `import-linter`, `mypy --strict` CI 정착
- [ ] T-025 `prometheus-client` 메트릭(외부 API 호출, 캐시 hit rate, 적재 작업)
- [ ] **T-026** 디버그 UI `/admin/consistency` 페이지(`docs/frontend-package.md` 후속 PR) — 백엔드 C1~C10 검증 SQL, `ConsistencyReport` 빌더, CLI/API 표면은 PR #10 fixup에서 완료
## 완료
- [x] T-020 OpenAPI export 스크립트 + `openapi.json` 생성 + GitHub Actions drift 검사 (`scripts/export_openapi.py`, `.github/workflows/openapi.yml`) 구현 (2026-05-23)
- [x] T-019 외부 API 폴백(`fallback="api"`) — vworld 주소 좌표 API와 juso 검색+좌표 API 어댑터 구현. 로컬 `NOT_FOUND`일 때만 호출하고 `x_extension.source`에 공급자 출처 기록 (2026-05-23)
- [x] T-018 CLI 운영 명령 구현 — `load all-sidos`, `load shp`, `load shp-all`, `load pobox`, `load bulk`, `load epost --kind=full`, `refresh mv --swap`, `validate consistency --cases/--scope` (2026-05-23)
- [x] PR #10 리뷰 fixup: ADR-017 batch DAG(`load_batch_id`, `parent_job_id`, `full_load_batch`), C1~C10 정합성 검증, PNU `mntn_yn IS NULL` guard, reverse `both`, 인코딩 fallback, `load_jobs.log_tail` 갱신 경로, ADR-018 문서화 (2026-05-23)
- [x] T-017 `loaders/pobox_loader.py`, `loaders/bulk_loader.py` (epost 보조 우편번호 COPY 로더) 구현 (2026-05-23)
- [x] T-016 reverse / search / zipcode / pobox 코어와 raw SQL repo, REST 라우터 구현 (2026-05-23)
- [x] T-015 `api/_jobs.py` 작업 큐(`load_jobs` 영속화, startup running 복구, advisory lock + `FOR UPDATE SKIP LOCKED`)와 `/v1/admin/loads`, `/v1/admin/consistency/*` 표면 구현 (2026-05-23)
- [x] T-014 `loaders/shp/delta_loader.py` (settings/DB 기반 `MVM_RES_CD` action 매핑을 받는 polygon delta merge helper) 구현 (2026-05-23)
- [x] T-013d `loaders/shp/polygons_loader.py` (GDAL `VectorTranslate`, ADR-012 보조 SHP 9종 load plan) 구현 + 실제 강원 SHP load plan 검증 (2026-05-23)
- [x] T-013c `loaders/text/navi_loader.py` (내비게이션용DB centroid + 진입점 parser/COPY) 구현 + 실제 서울 파일 검증 (2026-05-23)
- [x] T-013b `loaders/text/locsum_loader.py` (위치정보요약DB 출입구 좌표 parser/COPY, `bd_mgt_sn` 후해소 구조) 구현 + 실제 ZIP member 검증 (2026-05-23)
- [x] T-013a `loaders/text/juso_hangul_loader.py` (도로명주소 한글_전체분 parser/COPY, NULL-safe PNU 검증) 구현 + 실제 서울 파일 검증 (2026-05-23)
- [x] T-012 `api/app.py`, geocode/reverse/search/zipcode/pobox/admin 라우터 구현 (2026-05-23)
- [x] T-011 `AsyncAddressClient` 실제 engine/repo 연결, geocode/reverse/search/zipcode/pobox/load/consistency 메서드 구현 (2026-05-23)
- [x] T-010 `core/geocoder.py` 구현 + Fake repo 단위 테스트 (2026-05-23)
- [x] T-009 `core/normalize.py` 주소 정규화 순수 함수 구현 (2026-05-23)
- [x] T-008 `infra/geocode_repo.py` 및 reverse/search/zip/pobox/admin raw SQL repo 구현 (2026-05-23)
- [x] T-007 `mv_geocode_target` MV 정의(`pt_5179`/`pt_4326`/`pt_source`, partial GiST index) + 실제 PostgreSQL 샘플 load/MV 생성 검증 (2026-05-23)
- [x] T-006 텍스트 4 + SHP polygon/폴리라인 9 + 보조 2 + 메타 5 = 20개 테이블 DDL + Alembic 0001 작성. `tl_juso_text.pnu` NULL-safe generated column, `load_jobs`, `load_consistency_reports` 포함 (2026-05-23)
- [x] T-005 `infra/engine.py` async engine factory 작성 (`Settings.normalize_pg_dsn` 신뢰, `x_extension` search_path, statement timeout) (2026-05-23)
- [x] T-004 `dto/geocode.py`, `dto/reverse.py`, `dto/search.py`, `dto/zipcode.py`, `dto/pobox.py`, `dto/admin.py` 작성 (2026-05-23)
- [x] T-003 `dto/common.py`, `dto/address.py` 작성 + 단위 테스트 (2026-05-22)
- [x] T-002 `Settings` (pydantic-settings) + `.env.example` 작성 (2026-05-22)
- [x] T-001 `pyproject.toml` 작성 (`kraddr-geo` 패키지, optional extras `api`/`loaders`/`dev`) (2026-05-22)

## 사양 참조
- 백엔드 세부: `docs/backend-package.md`
- 프론트엔드 세부: `docs/frontend-package.md`
- 데이터 모델: `docs/data-model.md`
- 외부 API: `docs/external-apis.md`
