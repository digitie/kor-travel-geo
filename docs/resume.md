# RESUME — 작업 재개 가이드

새 에이전트 세션이 시작될 때 "지금 어디까지 했고, 다음은 뭐 하면 되나"를 한 화면에서 답한다.

## 현재 진척도 (2026-05-22 갱신, by human)

- ✅ 이전 SpatiaLite 기반 구현(`kraddr.geo`)을 `v1` 브랜치로 이관
- ✅ master 브랜치를 문서·repo 설정만 남도록 정리
- ✅ 신규 사양(`addr-kr` + `addr-kr-ui`) 문서 골격을 master에 반영 — `SKILL.md`, `CHANGELOG.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/data-model.md`, `docs/tasks.md`, `docs/resume.md`, `docs/journal.md`, `docs/backend-package.md`, `docs/frontend-package.md`, `docs/agent-guide.md`, `docs/external-apis.md`
- ⬜ `pyproject.toml` 신규 작성 (`addr-kr` 패키지)
- ⬜ DDL/Alembic 적용 (`sql/ddl/`, `alembic/`)
- ⬜ `dto/`, `core/`, `infra/`, `client.py`, `api/`, `loaders/`, `cli/` 모듈 구현
- ⬜ 프론트엔드 패키지 `addr-kr-ui` 부트스트랩

## 다음 한 작업 (1시간 이내 분량)

`docs/tasks.md#T-001`: `pyproject.toml`을 새로 작성한다.

- `docs/backend-package.md` §3.1을 기준으로 의존성, optional extras(`api`/`loaders`/`dev`), mypy/ruff/pytest/importlinter 설정을 모두 채운다.
- 패키지명은 `addr-kr`, 진입 스크립트는 `addr-kr = "addr_kr.cli.main:app"`.
- 작성 후 `pip install -e ".[api,loaders,dev]"`이 통과하는지만 확인(아직 코드가 없으므로 import 실패는 무관).

## 작업 시작 전 확인할 것

- [ ] `SKILL.md` §4 "DO NOT" 룰 다시 읽기
- [ ] `docs/architecture.md`의 의존 방향 확인
- [ ] `docs/decisions.md`의 ADR-001 ~ ADR-006 확인
- [ ] 마지막 `docs/journal.md` 엔트리 읽기

## 알려진 함정

- `pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` — 전역 변경 금지 (SKILL.md §4-3)
- 좌표 입력은 `(lon, lat)` 순서. `(lat, lon)`으로 받으면 한국 밖으로 가서 `InvalidCoordinateError` 발생
- `ogr2ogr -append`와 `-overwrite`를 같이 쓰지 말 것 (GDAL Python binding으로 대체)
- `MVM_RES_CD` 매핑은 코드 상수가 아닌 settings 또는 DB `load_codes` 테이블에서 읽는다

## 작업 후 의무사항

1. `docs/journal.md`에 항목 추가 (날짜·요약·관련 파일·결정·다음 작업)
2. 본 `docs/resume.md`의 진척도 토글 갱신
3. 변경된 결정이 있다면 `docs/decisions.md`에 ADR 추가
4. 사용자 가시 변경이면 `CHANGELOG.md` 갱신
5. 스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
