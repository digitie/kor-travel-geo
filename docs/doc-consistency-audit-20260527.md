# 문서 정합성 재검토 — 2026-05-27

## 목적

`main` 최신 상태에서 문서가 실제 코드, 최근 ADR, 후속 task 순서와 어긋나는 부분이 있는지 다시 점검했다. 이번 변경은 코드 구현이 아니라 문서 정합성과 다음 작업 순서를 바로잡는 작업이다.

## 점검 범위

- 저장소 진입 문서: `README.md`, `SKILL.md`
- 핵심 설계 문서: `docs/architecture.md`, `docs/backend-package.md`, `docs/frontend-package.md`, `docs/data-model.md`, `docs/decisions.md`
- 재개·작업 문서: `docs/tasks.md`, `docs/resume.md`, `docs/journal.md`, `CHANGELOG.md`
- 보조 안내 문서: `docs/code-guide-for-beginners.md`, `docs/agent-guide.md`, `docs/geocoding-readiness.md`, `docs/reverse-geocoding.md`, `docs/address-db-schema.md`, `docs/spatialite-vworld-implementation.md`
- 실제 CLI 표면: `src/kraddr/geo/cli/main.py`의 `load all-sidos`, `refresh mv`, `validate` 명령 시그니처

## 발견 및 반영

| 항목 | 문제 | 반영 |
|------|------|------|
| 브랜치 명칭 | 현재 기본 브랜치는 `main`인데 여러 현재형 문서가 `master`를 기준으로 설명했다. | 현재형 설명은 `main`으로 수정했다. `master table`처럼 DB 도메인 용어이거나 과거 작업 일지에 남은 기록은 그대로 두었다. |
| README 현재 상태 | T-005~T-026까지만 포함한다고 적혀 있어 T-027~T-049 문서/검증 흐름이 빠져 있었다. | T-005~T-041 구현·실데이터 검증, T-042~T-049 후속 계획이 문서화된 상태로 갱신했다. |
| README/SKILL quick start | `kraddr-geo load all-sidos ./data/jusoMap/202605 --mode full --pg-conn ...` 예시는 현재 Typer 명령 시그니처와 맞지 않는다. | 실제 CLI 옵션인 `--juso`, `--jibun`, `--locsum`, `--navi`, `--shp-root`, `--yyyymm` 예시로 바꿨다. |
| UI 패키지 설명 | `SKILL.md`가 “이 저장소는 백엔드만 다룬다”고 설명해, 같은 저장소의 `kraddr-geo-ui`와 충돌했다. | `kraddr-geo-ui`는 같은 저장소에서 관리하는 별도 Node.js 패키지이며 REST API만 호출한다는 설명으로 정리했다. |
| ADR 목록 | README 핵심 ADR 표에 ADR-032가 빠져 있었다. | `maplibre-vworld-js` 최신 소비와 `kraddr-geo` 특화 기능 경계 원칙을 ADR-032로 추가했다. |
| 백업 artifact 명칭 | ADR-033 이후 T-046 백업 metadata는 `ops.artifacts`로 수렴하는데 일부 흐름도와 후속 항목이 `db_backup_artifacts`를 기본처럼 설명했다. | 신규 구현 기본값은 `ops.artifacts`이며 전용 `db_backup_artifacts`는 compatibility/migration 대상임을 반영했다. |
| 운영 UI/API 표면 | T-049는 `/v1/admin/ops/*`와 `/admin/ops`를 요구하지만, 백엔드/프론트엔드 사양의 주요 화면·엔드포인트 목록에는 빠져 있었다. | `docs/backend-package.md`에 `ops` 엔드포인트 후보를, `docs/frontend-package.md`에 `/admin/ops` 후보 화면과 테스트 항목을 추가했다. |
| task 순서 | T-044 지도 UI 경계화가 T-042/T-027/T-047보다 앞에 있어, 데이터·운영 gate가 늦어질 수 있었다. | T-049 → T-045 → T-046 → T-042 → T-027 → T-047 → T-044 순서로 재정렬했다. T-043 리뷰 audit은 사용자 지시상 가장 앞에 유지했다. |

## 조정된 후속 순서

1. T-043 PR #23~최신 PR 리뷰 코멘트 일괄 audit/fixup
2. T-049 운영 메타데이터·감사·릴리스 스키마 구현
3. T-045 원천 자료 기준월 선택과 대용량 업로드/적재 UX
4. T-046 적재 완료 DB 백업/복원 및 UI
5. T-042 `TL_SPPN_MAKAREA` 국가지점번호 보조 데이터 적재/조회
6. T-027 최종 실 데이터 클린 적재 검증
7. T-047 전국 적재 후 쿼리 성능 벤치마크와 튜닝
8. T-044 디버그 UI를 최신 `maplibre-vworld-js` 기반 domain wrapper로 경계화

## 남겨 둔 것

- `docs/journal.md`의 과거 `master` 표현은 당시 작업 기록이므로 수정하지 않았다.
- `docs/reflection-summary.md`의 과거 문맥은 첨부 사양 반영 당시 회고 성격이 강해 이번 정합성 수정 범위에서 제외했다.
- 실제 코드나 DDL은 바꾸지 않았다. 이번 PR의 목적은 문서와 task 순서 정렬이다.

## 검증

- `git diff --check` 통과.
- `python -m pytest -q`, `python -m ruff check .`는 현재 WSL 환경에 `python` alias가 없어 실행되지 않았다.
- `python3 -m pytest -q`, `python3 -m ruff check .`는 각각 `pytest`, `ruff` 모듈이 설치되어 있지 않아 실행되지 않았다. 이번 변경은 문서 전용이지만, 후속 구현 작업 전에는 `uv` 또는 프로젝트 가상환경을 복구해 전체 게이트를 다시 실행한다.
