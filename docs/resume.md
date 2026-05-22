# RESUME — 작업 재개 가이드

새 에이전트 세션이 시작될 때 "지금 어디까지 했고, 다음은 뭐 하면 되나"를 한 화면에서 답한다.

## 현재 진척도 (2026-05-22 갱신, by human)

- ✅ 이전 SpatiaLite 기반 `kraddr.geo` 구현을 `v1` 브랜치로 이관
- ✅ master 브랜치를 문서·repo 설정만 남도록 정리
- ✅ 신규 사양(`kraddr.geo` 패키지의 PostgreSQL+PostGIS 재구현 + `kraddr-geo-ui` 프론트엔드) 문서 골격을 master에 반영
- ✅ 식별자 정정 및 WSL/NTFS 개발 정책, NTFS의 `data/` 정책을 모든 문서에 명시
- ⬜ `pyproject.toml` 신규 작성 — `name = "python-kraddr-geo"`, scripts `kraddr-geo = "kraddr.geo.cli.main:app"`
- ⬜ DDL/Alembic 적용 (`sql/ddl/`, `alembic/`)
- ⬜ `dto/`, `core/`, `infra/`, `client.py`, `api/`, `loaders/`, `cli/` 모듈 구현 (모두 `src/kraddr/geo/` 하위)
- ⬜ 프론트엔드 패키지 `kraddr-geo-ui` 부트스트랩

## 다음 한 작업 (1시간 이내 분량)

`docs/tasks.md#T-001`: WSL ext4 작업 디렉토리(`~/dev/python-kraddr-geo/`)에서 `pyproject.toml`을 새로 작성한다.

- `docs/backend-package.md` §3.1을 기준으로 의존성, optional extras(`api`/`loaders`/`dev`), mypy/ruff/pytest/importlinter 설정을 모두 채운다.
- 프로젝트 이름은 `python-kraddr-geo`, 진입 스크립트는 `kraddr-geo = "kraddr.geo.cli.main:app"`, importlinter `root_package = "kraddr.geo"`.
- 작성 후 `pip install -e ".[api,loaders,dev]"`이 통과하는지만 확인(아직 코드가 없으므로 import 실패는 무관).

## 작업 시작 전 확인할 것

- [ ] `AGENTS.md`의 "식별자" 표와 "개발 환경 정책" 다시 읽기
- [ ] `SKILL.md` §4 "DO NOT" 룰 다시 읽기
- [ ] `docs/architecture.md`의 의존 방향 확인
- [ ] `docs/decisions.md`의 ADR-001 ~ ADR-006 확인
- [ ] 마지막 `docs/journal.md` 엔트리 읽기
- [ ] NTFS의 `data/` 디렉토리가 준비되어 있고 ext4에서 심볼릭 링크 또는 절대경로로 접근 가능한지

## 알려진 함정

- **WSL/NTFS 분리**: ext4 작업 디렉토리에서 NTFS의 `data/`로 심볼릭 링크를 둘 때 권한/inotify 이슈 발생 가능. 절대경로 사용을 권장.
- `pg_trgm.similarity_threshold`는 트랜잭션 단위로만 `SET LOCAL` — 전역 변경 금지 (SKILL.md §4-3)
- 좌표 입력은 `(lon, lat)` 순서. `(lat, lon)`으로 받으면 한국 밖으로 가서 `InvalidCoordinateError` 발생
- `ogr2ogr -append`와 `-overwrite`를 같이 쓰지 말 것 (GDAL Python binding으로 대체)
- `MVM_RES_CD` 매핑은 코드 상수가 아닌 settings 또는 DB `load_codes` 테이블에서 읽는다
- PostgreSQL DB 이름은 `kraddr_geo` (dot 불가). 환경변수 prefix는 `KRADDR_GEO_`.

## 작업 후 의무사항

1. `docs/journal.md`에 항목 추가 (날짜·요약·관련 파일·결정·다음 작업)
2. 본 `docs/resume.md`의 진척도 토글 갱신
3. 변경된 결정이 있다면 `docs/decisions.md`에 ADR 추가
4. 사용자 가시 변경이면 `CHANGELOG.md` 갱신
5. 스키마 변경이면 `scripts/export_openapi.py` 재실행 → 프론트엔드 `gen:types`
