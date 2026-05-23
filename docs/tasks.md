# TASKS — 백로그

작업 항목은 `T-NNN` 형식의 ID로 관리한다. 새 작업은 "대기"의 우선순위 순서대로 들어가고, 진행 중이 되면 담당자를 표시한다. 완료된 작업은 "완료" 섹션 상단에 누적한다.

## 진행 중
- (없음)

## 대기 (우선순위 순)
- [x] T-005 `infra/engine.py` (async engine factory, `Settings.normalize_pg_dsn` 신뢰) + 통합 테스트
- [ ] T-006 텍스트 4 + SHP polygon 7 + 보조 2 + 메타 5 = 18개 테이블 DDL을 `sql/ddl/`과 `alembic/versions/0001_*.py`에 작성. `tl_juso_text.pnu` generated column(ADR-010), `load_jobs`(ADR-011), `load_consistency_reports`(ADR-016) 포함.
- [ ] T-007 `mv_geocode_target` MV 정의(텍스트 정본 + 대표 출입구 + centroid fallback, `pt_source` 컬럼) + `REFRESH CONCURRENTLY`(평시) + shadow MV swap(분기) 통합 테스트
- [ ] T-008 `infra/geocode_repo.py` 구현 + Fake repo 단위 테스트
- [ ] T-009 `core/normalize.py` (주소 정규화 순수 함수)
- [ ] T-010 `core/geocoder.py` 구현 + Fake repo 단위 테스트
- [ ] T-011 `client.py` (`AsyncAddressClient` + `load_status`/`list_load_jobs`/`submit_load`/`cancel_load` — ADR-016) 구현 + 통합 테스트
- [ ] T-012 `api/app.py`, `api/routers/geocode.py` + `api/routers/admin.py` (loads, consistency 엔드포인트) 작성 + e2e 테스트
- [ ] **T-013a** `loaders/text/juso_hangul_loader.py` (도로명주소 한글_전체분, stdlib csv + `psycopg.copy()`, ADR-012)
- [ ] **T-013b** `loaders/text/locsum_loader.py` (위치정보요약DB, 출입구 좌표 5179)
- [ ] **T-013c** `loaders/text/navi_loader.py` (내비게이션용DB, centroid + 진입점 kind)
- [ ] **T-013d** `loaders/shp/polygons_loader.py` (GDAL VectorTranslate, polygon 7종만, ADR-005)
- [ ] T-014 `loaders/shp/delta_loader.py` (MVM_RES_CD 머지, polygon만) + 텍스트 변동분 적용
- [ ] T-015 `api/_jobs.py` 작업 큐(`load_jobs` 영속화, lifespan recovery, advisory lock — ADR-011) + 텍스트/SHP/정합성 핸들러 등록 + `/v1/admin/upload/sido-zip`, `/v1/admin/load/sido-batch` 엔드포인트
- [ ] T-016 reverse / search / zipcode / pobox 코어와 라우터
- [ ] T-017 `loaders/pobox_loader.py`, `loaders/bulk_loader.py`
- [ ] T-018 CLI(`kraddr-geo load all-sidos`, `kraddr-geo refresh mv`, `kraddr-geo validate`) 구현
- [ ] T-019 외부 API 폴백(`fallback="api"`) — vworld, juso 호출 어댑터
- [ ] T-020 OpenAPI export 스크립트 + CI에서 drift 검사
- [ ] T-021 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩 (`docs/frontend-package.md` §A2)
- [ ] T-022 프론트엔드 `/debug/geocode`, `/debug/reverse`, `/debug/normalize`, `/debug/explain` 페이지
- [ ] T-023 프론트엔드 `/admin/load`(업로드 + 처리 워크플로), `/admin/tables`, `/admin/cache`, `/admin/logs`
- [ ] T-024 `pre-commit`, `import-linter`, `mypy --strict` CI 정착
- [ ] T-025 `prometheus-client` 메트릭(외부 API 호출, 캐시 hit rate, 적재 작업)
- [ ] **T-026** `loaders/consistency.py` (ADR-012, ADR-016) — C1~C10 검증 SQL, `ConsistencyReport` 빌더, `kraddr-geo validate consistency` CLI, `/v1/admin/consistency/*` 엔드포인트, 디버그 UI `/admin/consistency` 페이지(`docs/frontend-package.md` 후속 PR)

## 완료
- [x] T-004 `dto/geocode.py`, `dto/reverse.py`, `dto/search.py`, `dto/zipcode.py`, `dto/pobox.py`, `dto/admin.py` 작성 (2026-05-23)
- [x] T-003 `dto/common.py`, `dto/address.py` 작성 + 단위 테스트 (2026-05-22)
- [x] T-002 `Settings` (pydantic-settings) + `.env.example` 작성 (2026-05-22)
- [x] T-001 `pyproject.toml` 작성 (`kraddr-geo` 패키지, optional extras `api`/`loaders`/`dev`) (2026-05-22)

## 사양 참조
- 백엔드 세부: `docs/backend-package.md`
- 프론트엔드 세부: `docs/frontend-package.md`
- 데이터 모델: `docs/data-model.md`
- 외부 API: `docs/external-apis.md`
