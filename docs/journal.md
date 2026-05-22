# JOURNAL — 작업 일지

새 항목은 항상 파일 맨 위에 추가(역시간순). 기존 항목은 절대 수정하지 않는다 — 잘못된 결정조차 기록으로 남는 것이 가치다.

## 2026-05-22 (human, 추가 명시)

**작업**: 사용자 추가 지시 반영 — 프로젝트/패키지 식별자 정정, WSL/NTFS 개발 정책, 데이터 위치(NTFS의 `data/`) 명시

**변경 파일**:
- 갱신: `README.md`, `AGENTS.md`, `SKILL.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/backend-package.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reflection-summary.md` 외 일괄 치환 대상 전부

**결정**:
- 식별자 통일: GitHub/PyPI = `python-kraddr-geo`, Python import = `kraddr.geo`, CLI = `kraddr-geo`, env prefix = `KRADDR_GEO_`, PostgreSQL DB = `kraddr_geo`, 프론트엔드 패키지 = `kraddr-geo-ui`
- PC 개발은 WSL ext4 위에서, 작업 완료 시 NTFS로 카피. 데이터(`data/`)는 NTFS 측에만 두고 ext4 작업 디렉토리는 심볼릭 링크/절대경로로 참조
- 테스트(특히 통합/e2e/전국 검증)는 NTFS의 `data/`를 reference로 삼는다

**참고**: 이번 변경은 코드를 새로 만들기 전 사양 단계에서의 명확화이며, ADR은 추가하지 않음(향후 결정이 뒤집힐 때 ADR로 별도 기록).

**다음**: T-001 (`pyproject.toml` 신규 작성). pyproject.toml의 `name = "python-kraddr-geo"`, scripts `kraddr-geo = "kraddr.geo.cli.main:app"`, importlinter `root_package = "kraddr.geo"`로 시작.

---

## 2026-05-22 (human)

**작업**: 신규 사양(`kraddr.geo` 패키지의 PostgreSQL+PostGIS 재구현 + `kraddr-geo-ui` 프론트엔드)을 master 문서에 반영

**변경 파일**:
- 신규: `SKILL.md`, `CHANGELOG.md`
- 신규 (`docs/`): `architecture.md`, `decisions.md`, `data-model.md`, `tasks.md`, `resume.md`, `journal.md`, `backend-package.md`, `frontend-package.md`, `agent-guide.md`, `external-apis.md`
- 갱신: `AGENTS.md`, `README.md`, `docs/address-db-schema.md`, `docs/code-guide-for-beginners.md`, `docs/geocoding-readiness.md`, `docs/reverse-geocoding.md`, `docs/spatialite-vworld-implementation.md`
- 신규: `docs/reflection-summary.md` (반영 내용 요약)

**결정**:
- ADR-001 ~ ADR-006, ADR-013을 `docs/decisions.md`에 초기 기록
- 응답 구조는 vworld와 1:1 호환, 자체 확장은 `x_extension`만 (ADR-003)
- 라이브러리 API는 async-only (ADR-002)
- 로더는 GDAL Python binding 사용, `ogr2ogr` subprocess 폐기 (ADR-005)

**참고**: 첨부받은 두 docx 사양서가 우선이며, 기존 SpatiaLite 문서와 충돌하는 부분은 모두 PostgreSQL + PostGIS / `kraddr-geo` 기준으로 갱신함.

**다음**: T-001 (`pyproject.toml` 신규 작성).

---

## 2026-05-22 (human, 이전)

**작업**: 기존 SpatiaLite 기반 구현(`kraddr.geo`)을 `v1` 브랜치로 이관하고 master를 문서·repo 설정만 남도록 정리

**변경 파일**: 삭제 — `alembic/`, `alembic.ini`, `debug-ui/`, `pyproject.toml`, `src/`, `tests/`

**메모**: master는 새 사양으로 처음부터 다시 구현한다. 이전 구현은 `v1` 브랜치에서 참조 가능.
