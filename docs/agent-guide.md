# AI 에이전트 작업·문서화 가이드

본 문서는 첨부 사양서(2026-05-22 작성) Part B를 master 문서 체계로 정리한 것이다. AI 에이전트가 이 저장소에서 일관되게 작업하기 위한 표준이다.

## B1. 원칙: 컨텍스트가 휘발돼도 문서로 회복한다

### B1.1 왜 이 가이드가 필요한가

LLM 기반 에이전트는 매 대화가 끝나면 기억을 잃는다. 같은 에이전트가 며칠 뒤 이어받거나, 전혀 다른 에이전트가 처음 본다고 가정해야 한다. 의지할 수 있는 건 오직 저장소 안의 파일이다. 따라서 **"문서"의 1차 독자는 사람이 아니라 다음 에이전트**다.

두 보장:

- **Recoverability(회복성)**: 작업 중간에 컨텍스트가 끊겨도 다음 세션은 30분 안에 같은 상태로 복귀
- **Continuity(연속성)**: 이전 결정을 모르고도 일관된 선택. 결정의 "근거"가 코드와 함께 살아 있음

### B1.2 5가지 원칙

| 원칙 | 의미 | 안티패턴 |
|------|------|----------|
| 문서가 진실의 원천 (DocAsCode) | README와 ADR이 코드와 함께 PR에 들어간다 | 구두 결정, 채팅 스레드만 남는 결정 |
| 디렉토리는 자기설명적 | 이름과 위치만 봐도 무엇이 들어 있는지 짐작 | `utils/`, `helpers/`, `common/`, `misc/` |
| 불변 결정은 분리 | `architecture.md` / `decisions.md`에 분리 | README가 비대해져 가독성 잃음 |
| 진행상태는 명시적 | `resume.md`, `journal.md` 항상 최신 | PR 설명에만 적힌 진척도 |
| 자동 검증 | pre-commit과 CI가 컨벤션 강제 | 사람 리뷰만으로 룰 유지 시도 |

### B1.3 에이전트가 묻기 전에 알아야 할 5가지

새로 들어온 에이전트가 가장 먼저 검색해야 할 정보:

1. 이 프로젝트는 무엇인가 → `README.md` 첫 단락
2. 내가 지금 손대도 되는 가장 작은 일은 무엇인가 → `docs/tasks.md` 또는 `docs/resume.md`
3. 절대 깨면 안 되는 규칙은 무엇인가 → `SKILL.md`의 "DO NOT" 섹션
4. 이전에 어떤 결정이 있었나 → `docs/decisions.md` (ADR)
5. 작업을 끝내면 어디에 기록하나 → `docs/journal.md` (append-only)

## B2. 문서 계층

### B2.1 파일의 역할 분담

문서를 늘리는 게 목적이 아니다. 각 파일은 명확히 다른 질문에 답하므로 합치면 검색 비용이 오른다. 한 파일이 두 가지 역할을 떠안기 시작하면 분리 신호.

| 파일 | 목적 | 수정 주기 | 1차 독자 |
|------|------|-----------|---------|
| `README.md` | 5분 안에 프로젝트 파악, 빠른 시작 | 월 단위 | 신규 합류자 |
| `SKILL.md` | 에이전트가 작업 전 반드시 읽는 매뉴얼 | 필요 시 즉시 | AI 에이전트 |
| `docs/architecture.md` | 변하지 않는 큰 구조 설계 | 분기 단위 | 에이전트, 리뷰어 |
| `docs/decisions.md` | ADR — 왜 그렇게 결정했나 | 결정 발생 시 | 미래의 에이전트 |
| `docs/data-model.md` | 스키마·도메인 모델 reference | 스키마 변경 시 | 에이전트, DBA |
| `docs/tasks.md` | 현재 백로그·우선순위 | 수시 | 에이전트, PM |
| `docs/resume.md` | 지금 어디까지 했나, 다음은 무엇 | 작업 단위 (필수) | AI 에이전트 |
| `docs/journal.md` | append-only 작업 일지 | 작업 단위 (필수) | 에이전트, 자신 |
| `CHANGELOG.md` | 릴리즈 노트 (사용자 가시) | 릴리즈 시 | 이용자, 통합자 |

### B2.2 README.md — 5분 안의 약속

스크롤 한 번이면 6가지를 알 수 있어야 한다.

1. 프로젝트가 무엇이고 무엇이 아닌지 (1~2 문단)
2. 빠른 시작 (3~5 줄 셸 명령)
3. 주요 진입점 (api 서버 / CLI / lib import 등)
4. 디렉토리 한 줄 설명
5. 기여 안내 — `SKILL.md`, `docs/tasks.md`, `docs/journal.md` 링크
6. 라이선스와 연락처

README는 마케팅 문서가 아니라 사용자 매뉴얼이다.

### B2.3 architecture vs decisions

둘 다 "왜"를 다루지만 시간 차원이 다르다.

- `docs/architecture.md`: **현재 시점**에 적용되는 구조 — "우리는 이렇게 설계한다". 대체로 변하지 않는 큰 그림. 시퀀스 다이어그램, 계층, 데이터 흐름.
- `docs/decisions.md` (ADR): **결정의 역사** — "우리는 왜 그렇게 정했나, 무엇을 포기했나". 결정이 뒤집힐 때도 이전 기록은 지우지 않고 `superseded by ADR-XXX`로 표시.

### B2.4 resume.md — 작업 재개의 진입점

새 에이전트 세션 시작 시 "지금 어디까지 했고, 다음은 뭐 하면 되나"를 한 화면에서 답한다. 표준 섹션:

- 현재 진척도 (✅ / 🟡 / ⬜ 토글)
- 다음 한 작업 (1시간 이내 분량, 시작 파일/검증 방법 포함)
- 작업 시작 전 확인할 것 (관련 ADR, 사양 절)
- 알려진 함정
- 작업 후 의무사항

### B2.5 journal.md — append-only 작업 일지

새 항목은 항상 파일 맨 위에 추가(역시간순). 기존 항목은 절대 수정하지 않는다 — 잘못된 결정조차 기록으로 남는 것이 가치.

표준 엔트리:

```
## YYYY-MM-DD HH:MM (agent-or-human)
**작업**:
**변경 파일**:
**결정**:
**발견**:
**다음**:
```

### B2.6 tasks.md — 현재 백로그

진행 중 / 대기(우선순위 순) / 완료(최근 10건). 작업 ID는 `T-NNN`. PR/commit에서 참조.

## B3. SKILL.md — 에이전트의 작업 매뉴얼

표준 섹션 (`SKILL.md` 본문에 적용된 그대로):

| 섹션 | 내용 | 분량 |
|------|------|------|
| 1. 정체성 | 프로젝트가 무엇이고 무엇이 아닌지 | 3~5 문장 |
| 2. 빠른 시작 | 셸 명령 5줄 이내 | 코드 블록 1개 |
| 3. 디렉토리 지도 | 트리 + 각 디렉토리 1줄 설명 | 최대 1 페이지 |
| 4. 절대 하지 말 것 (DO NOT) | 5~10개 룰 | 리스트 |
| 5. 자주 묻는 작업 → 어디서 시작 | 키워드 → 파일/명령 매핑 | 테이블 |
| 6. 도메인 어휘 | 약어 사전 | 테이블 |
| 7. 작업 후 체크리스트 | journal/resume/테스트 | 3~5 항목 |

## B4. 재개 프로토콜

### B4.1 새 세션의 첫 5분 (총 10분 안에 컨텍스트 확보)

| 순서 | 행동 | 시간 |
|------|------|------|
| 1 | `README.md` 처음부터 끝까지 | 2분 |
| 2 | `SKILL.md` (특히 §4 DO NOT, §5 자주 묻는 작업) | 3분 |
| 3 | `docs/architecture.md` 목차 훑기 | 1분 |
| 4 | `docs/resume.md` "현재 진척도" + "다음 한 작업" | 1분 |
| 5 | `docs/journal.md` 최근 3 엔트리 | 2분 |
| 6 | `docs/tasks.md`에서 resume이 가리키는 항목 확인 | 1분 |

### B4.2 작업 사이클

```
작업 1건 ─┬─→ [읽기] resume → architecture 관련 절 → 관련 ADR
          │
          ├─→ [코드] 변경 (한 PR / 한 commit 단위)
          │
          ├─→ [검증] pytest -q + ruff + mypy + lint-imports
          │
          ├─→ [기록] journal 엔트리 추가 (작업/변경/결정/다음)
          │
          ├─→ [갱신] resume 진척도 토글, tasks 상태 변경
          │
          ├─→ [선택] ADR 추가 (decisions.md), CHANGELOG (사용자 가시 시)
          │
          └─→ [커밋] [scope] verb: object (#issue-id)
```

### B4.3 컨텍스트 손실 시뮬레이션

주기적으로(예: 매주 금요일):

1. 새 브랜치를 열고 `README.md`와 `docs/`만 본다.
2. `docs/resume.md`의 "다음 한 작업"을 그대로 수행할 수 있는가?
3. 필요 정보 중 못 찾은 게 있다면 그건 **문서의 결함**이다. 작업 전에 문서부터 보강.

## B5. 코드 주석 정책

### "왜"만 적는다

```python
# 나쁨: 코드 그대로 다시 쓰기
i = i + 1  # increment i

# 좋음: 직관에 반하는 선택의 이유
# pg_trgm.similarity가 0.3 미만이면 노이즈가 많아 polluting.
# 데이터 검증 후 0.42로 고정.
SET LOCAL pg_trgm.similarity_threshold = 0.42;
```

### 모듈 docstring 의무

핵심 가정·함정·관련 문서를 명시:

```python
"""Incremental loader using MVM_RES_CD (이동사유코드).

본 모듈은 변동분 SHP을 staging 스키마에 적재한 후, MVM_RES_CD 값에 따라
master 테이블로 INSERT/UPDATE/DELETE를 머지한다.

핵심 가정:
  - 변동분 SHP는 본 SHP과 동일 컬럼 + MVM_RES_CD, MVMN_DE 추가
  - PK는 PK_MAP 상수로 테이블별로 명시
  - 코드 매핑(MVM_RES_INSERT/UPDATE/DELETE)은 settings에서 덮어쓰기 가능

함정:
  - mvm_res_cd가 NULL인 행은 무시 (master에 영향 주지 않음)
  - DELETE는 RETURNING 사용하지 않음 (대량 삭제 시 비용)

관련 문서: docs/data-model.md, ADR-006
"""
```

### TODO 규약

"언젠가 고침"이 아닌, 추적 가능한 TODO만:

```python
# TODO(T-046): MVM_RES_CD 매핑을 실제 변동분 데이터로 검증
# FIXME(T-099): pool_recycle이 statement_timeout과 충돌. PG 16.4+에서만 재현.
# XXX: PostGIS 3.4 미만에서 ST_PointOnSurface가 polygon 외부 점 반환 가능 — 3.4+ 강제
```

### 함수 docstring (pydantic 활용)

`Args` / `Returns` / `Raises` / `Notes` 섹션. fallback 동작, 좌표 순서 같은 비명시적 규칙은 `Notes`에.

## B6. 검증 자동화

### 강제할 수 있는 룰만 룰이다

| 룰 | 도구 | 단계 |
|----|------|------|
| Python 스타일 | ruff format / ruff check | pre-commit + CI |
| 타입 | mypy --strict | CI (느려서 pre-commit은 선택) |
| 의존 방향 | import-linter | CI |
| TS 타입 | tsc --noEmit | CI |
| TS 스타일 | eslint + prettier | pre-commit + CI |
| 백엔드↔프론트 스키마 동기 | `openapi.json` diff + ts-to-zod 산출 diff | CI |
| 문서 누락 (journal/resume) | custom pre-commit hook | pre-commit |
| 테스트 | pytest, vitest, playwright | CI |
| SQL DDL 유효성 | testcontainers + DDL apply 테스트 | CI |

### OpenAPI ↔ Zod 동기 검증 (CI)

`scripts/export_openapi.py` → frontend `gen:types` → `git diff --exit-code` 패턴. drift 즉시 발견.

### "journal 갱신 잊기 방지" hook

코드 변경(`src/`, `app/`, `components/`, `tests/`)이 있는데 `docs/journal.md` 변경이 없으면 pre-commit 경고. `BYPASS=1`로 일회 우회 가능.

## B7. 커밋·PR 컨벤션

### 커밋 메시지

```
<scope> <verb>: <object> (#<task-id>)

[본문 — 선택. 왜 이 변경이 필요한가]

[참조 — 선택. 관련 ADR, journal 엔트리]
```

예:

```
api add: /v1/zipcode router (#T-042)

bd_mgt_sn을 받으면 다량배달처 lookup을 우선시함.
사양서 §3.7.3 우선순위 표 그대로 구현.

Refs: ADR-007, journal 2026-05-22
```

- scope: `api / core / infra / loaders / cli / dto / ui / docs / ci / chore`
- verb: `add / fix / refactor / remove / rename / perf / test / chore`

### PR 템플릿 (`.github/PULL_REQUEST_TEMPLATE.md`)

```
## 동기 / 무엇이 문제였나
## 변경 내용 (한 줄 요약)
- 
## 영향 범위
- 깨질 수 있는 곳:
- 마이그레이션 필요 여부:
- 외부 API 호환성:
## 검증
- [ ] pytest -q 통과
- [ ] ruff / mypy / lint-imports 통과
- [ ] (UI) playwright e2e 통과
- [ ] (스키마 변경 시) testcontainers DDL 통과
## 문서
- [ ] docs/journal.md 추가
- [ ] docs/resume.md 진척도 갱신
- [ ] (결정 있음) docs/decisions.md 새 ADR
- [ ] (사용자 가시 변경) CHANGELOG.md
## 관련
- 작업: #T-???
- ADR: ADR-???
```

## B8. 부록 — 새 모듈 작성 체크리스트

- [ ] 모듈 docstring (왜, 핵심 가정, 함정, 관련 문서)
- [ ] 공개 심볼은 `__all__`로 명시
- [ ] 의존 방향 점검 (lint-imports)
- [ ] 단위 테스트 작성 (Fake repo 또는 mock)
- [ ] DTO 또는 Protocol 변경이 있다면 백엔드↔프론트 스키마 동기 재생성
- [ ] `docs/data-model.md` 또는 `docs/architecture.md`에 변경 반영
- [ ] `docs/journal.md` 항목 추가

## 다음 에이전트에게 보내는 한 문장

> 문서를 갱신하지 않은 작업은 절반만 끝난 작업이다. 미래의 너 자신과, 너를 이어받을 다음 에이전트를 위해 `journal.md`와 `resume.md`를 반드시 채워라. 그것이 컨텍스트를 잃어도 끊기지 않는 유일한 방법이다.
