# TASKS — 백로그

작업 항목은 `T-NNN` 형식의 ID로 관리한다. 새 작업은 "대기"의 우선순위 순서대로 들어가고, 진행 중이 되면 담당자를 표시한다. 완료된 작업은 "완료" 섹션 상단에 누적한다.

## 진행 중
- (없음)

## 대기 (우선순위 순)
- [ ] T-006 PostGIS 11개 마스터 + 보조 테이블 DDL을 `sql/ddl/`과 `alembic/versions/0001_*.py`에 작성
- [ ] T-007 `mv_geocode_target` MV 정의 + `REFRESH MATERIALIZED VIEW CONCURRENTLY` 통합 테스트
- [ ] T-008 `infra/geocode_repo.py` 구현 + Fake repo 단위 테스트
- [ ] T-009 `core/normalize.py` (주소 정규화 순수 함수)
- [ ] T-010 `core/geocoder.py` 구현 + Fake repo 단위 테스트
- [ ] T-011 `client.py` (`AsyncAddressClient`) 구현 + 통합 테스트
- [ ] T-012 `api/app.py`, `api/routers/geocode.py` 작성 + e2e 테스트
- [ ] T-013 `loaders/sido_loader.py` (GDAL Python binding) 작성 + 작은 시도 1개로 시연
- [ ] T-014 `loaders/delta_loader.py` (MVM_RES_CD 머지) 작성 + 통합 테스트
- [ ] T-015 `api/_jobs.py` 작업 큐 + `/v1/admin/upload/sido-zip`, `/v1/admin/load/sido-batch` 엔드포인트
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

## 완료
- [x] T-005 `infra/engine.py` (async engine factory) + 단위 테스트 (2026-05-23)
- [x] T-004 `dto/geocode.py`, `dto/reverse.py`, `dto/search.py`, `dto/zipcode.py`, `dto/pobox.py`, `dto/admin.py` 작성 (2026-05-23)
- [x] T-003 `dto/common.py`, `dto/address.py` 작성 + 단위 테스트 (2026-05-22)
- [x] T-002 `Settings` (pydantic-settings) + `.env.example` 작성 (2026-05-22)
- [x] T-001 `pyproject.toml` 작성 (`kraddr-geo` 패키지, optional extras `api`/`loaders`/`dev`) (2026-05-22)

## 사양 참조
- 백엔드 세부: `docs/backend-package.md`
- 프론트엔드 세부: `docs/frontend-package.md`
- 데이터 모델: `docs/data-model.md`
- 외부 API: `docs/external-apis.md`
