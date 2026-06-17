# agent-guide.md — 에이전트 작업·문서화 가이드

이 문서는 AI 에이전트(Claude Code / ChatGPT Codex / Google Antigravity 2.0)가
`kor-travel-geo`에서 작업할 때의 행동 지침이다. `AGENTS.md`, `SKILL.md`와 함께
읽는다. 환경·도구의 1차 reference는 `docs/dev-environment.md`, worktree +
CodeGraph는 `docs/codegraph-worktree.md`, 표준 1-PR 운영 절차는
`docs/runbooks/agent-workflow.md`, task 운영 규칙은 `docs/tasks-rule.md`다 —
본 문서는 그것들을 **진입·문서화·PR 규약으로 엮는다**(중복 서술하지 않는다).

## 1. 첫 진입 프로토콜 (10분 안에 컨텍스트 확보)

새 세션이 들어오면 이 순서로 컨텍스트를 확보한다.

1. `README.md` — 정체성, 빠른 시작, 문서 지도
2. `AGENTS.md` — 지시 우선순위, 개발 환경 정책, DO NOT 룰
3. `SKILL.md` — DO NOT 룰, 자주 묻는 작업, 도메인 어휘
4. `docs/architecture/architecture.md` 목차 — 두 패키지 관계, 의존 방향, 데이터 흐름
5. `docs/resume.md` — "현재 진척도" + "다음 한 작업"
6. `docs/journal.md` 최신 3 엔트리 — 직전 컨텍스트
7. `docs/tasks-rule.md` + `docs/tasks.md` — task 번호 체계·병행 순서·PR 루프와,
   resume이 가리키는 현재 항목
8. 관련 ADR (`docs/decisions.md`)
9. 직결 docs (loader면 `docs/architecture/backend-package.md`, UI면 `docs/architecture/frontend-package.md`,
   외부 API면 `docs/architecture/external-apis.md`, 적재면 `docs/t027-fullload-plan.md` /
   `docs/t213-data-preservation.md`)
10. **운영 runbook** (`docs/runbooks/`) — 에이전트 공용. 실제 작업 전
    [agent-workflow.md](runbooks/agent-workflow.md)(표준 1-PR 흐름)와
    [agent-failure-patterns.md](runbooks/agent-failure-patterns.md)(반복 실패
    회피)는 훑고 들어간다. 게이트가 깨지면 failure-patterns부터 본다.

### 1.1 코드 수정 우선순위

코드 작성·수정은 **최소 코드 변경**이나 **기존 임시 계약과의 호환성**보다
완성도, 최적 구조, 확장성, 안정성을 우선한다. 문제를 발견하면 호출부만 맞추는
shim, 임시 adapter, 런타임 추정값으로 덮기 전에 DTO, migration, repository,
API schema, 테스트가 같은 계약을 공유하는지 먼저 본다. PR scope는 작게
유지하되, 그 scope 안에서는 production으로 이어질 구조를 택한다. (단순 전달용
래퍼/장기 호환 별칭/임시 facade를 만들지 않는다 — `AGENTS.md` §제공자 API
사용 원칙.)

### 1.2 자기 worktree로 이동

이 저장소는 **에이전트별 고정 worktree** 정책을 쓴다(ADR-041,
`docs/codegraph-worktree.md`). 컨텍스트 확보 직전에 자기 worktree로 이동하고
CodeGraph 인덱스를 맞춘다. NTFS worktree의 Git metadata는 Windows Git
기준(`F:/dev/...`)이므로 git 명령은 Windows `git.exe`로 한다.

```bash
# 어떤 AI 에이전트인지에 따라 (Windows git.exe 사용)
"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/kor-travel-geo-codex       status -sb   # ChatGPT Codex
"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/kor-travel-geo-claude      status -sb   # Claude Code
"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/kor-travel-geo-antigravity status -sb   # Google Antigravity 2.0
```

worktree가 없으면 `docs/codegraph-worktree.md` §3 "최초 setup". CodeGraph
인덱스는 새 branch 직후 `codegraph sync` → `codegraph status`(있으면) /
`codegraph init -i`(최초). 사용자가 직접 작업할 때는 기준 clone
(`/mnt/f/dev/kor-travel-geo`)을 쓰고 `kor-travel-geo-*` worktree에는 들어가지
않는다.

## 2. 결정·기록 5종 (필수 유지)

| 파일 | 역할 | 갱신 시점 |
|------|------|----------|
| `docs/decisions.md` | ADR 누적 | 결정이 발생할 때마다 |
| `docs/resume.md` | 진척도 + "다음 한 작업" | 작업 마무리마다 |
| `docs/journal.md` | 작업 로그 (역시간순 append) | 작업 끝낼 때마다 |
| `docs/tasks.md` + `docs/tasks-done.md` | 진행/대기 백로그 + 완료·종료 이력 | 작업 추가/시작/완료 시 (규칙은 `docs/tasks-rule.md`) |
| `CHANGELOG.md` | 릴리즈 노트 (사용자 가시 변경) | 사용자 가시 변경 시 |

코드/문서를 바꿨는데 위 중 관련된 것이 하나도 갱신되지 않았다면 그 PR은
불완전하다. DTO/스키마를 바꿨으면 `docs/architecture/data-model.md`도 DDL과 동기로 갱신한다.

## 3. ADR 작성 규약

번호: `ADR-NNN` 연번. 현재 번호는 `docs/decisions.md` 맨 위에서 확인한다(다음
후보는 그 최댓값 + 1).

```markdown
## ADR-NNN: <결정 요약>

- 상태: proposed | accepted | superseded by ADR-XXX
- 날짜: YYYY-MM-DD
- 결정자: <agent | human> 또는 둘 모두

### 컨텍스트
무엇이 문제였고 왜 결정이 필요했는지.

### 결정
무엇을 하기로 했는지. 구체적으로.

### 근거
왜 이 결정인지. 대안과의 비교.

### 결과 (긍정 / 부정)
- ...

### 후속
- 어떤 코드/문서/테스트가 변경되어야 하는지.
```

결정이 뒤집힐 때는 새 ADR을 추가하고 옛 ADR의 상태를 `superseded by ADR-XXX`로
표시한다. **옛 ADR 본문은 지우지 않는다** — 결정 이력을 남긴다.

## 4. journal.md 엔트리 형식

역시간순으로 위에서 아래로 append. 가장 위가 가장 최근. 기존 항목은 수정하지
않는다 — 잘못된 결정조차 기록으로 남는 것이 가치다.

```markdown
## 2026-06-16 14:30 (claude)
**작업**: v2 후보 목록 API에 좌표 정밀도 필드 추가 (T-NNN)
**변경 파일**:
- src/kortravelgeo/dto/candidate.py (필드 추가)
- src/kortravelgeo/api/v2/routes.py
- tests/unit/test_dto_candidate.py
- openapi.json (export 재실행)
- docs/architecture/data-model.md / docs/resume.md
**결정**: 정밀도는 x_extension이 아니라 v2 자체 스키마에만 노출 (v1 vworld 호환 유지)
**발견**: v1 응답은 x_extension 외 자체 필드 추가 금지(ADR-003) — v2에만 추가
**다음**: 프론트엔드 gen:types 재생성 후 UI 표면 반영
```

`작업/변경/결정/발견/다음` 5개 필드 유지. 빈 필드는 생략 가능. 세션이
중단되면 가장 최근 journal 엔트리가 핸드오프 노트 역할을 한다(§11).

## 5. resume.md 형식

```markdown
# resume.md

## 현재 진척도
현재 상태는 `docs/resume.md`와 `docs/tasks.md`를 정본으로 본다.
전국 실 데이터 적재·검증 완료(T-027). 관련 ADR은 `docs/decisions.md`.

## 다음 한 작업
(1시간 이내 분량. 시작 파일 / 검증 방법 포함)

## 작업 시작 전 확인할 것
- 관련 ADR, 관련 docs

## 알려진 함정
- TMPDIR가 Windows Temp를 가리키면 pytest capture가 FileNotFoundError로 죽는다
- WSL에서 Playwright headless Chromium은 공유 라이브러리 누락으로 실패한다

## 차단 사유 / 결정 대기
- T-063 N150/Odroid 실측은 실제 장비가 준비되면 진행 (하드웨어 보류)
```

## 6. tasks.md / tasks-done.md

task 문서(`tasks.md`/`tasks-done.md`)의 작성·유지 규약 — 번호 체계(T-1xx /
T-2xx), 두 에이전트 병행 순서, PR/리뷰 루프, 사양 참조 — 은
[`docs/tasks-rule.md`](tasks-rule.md)가 정본이다. 본 가이드는 그 규칙을
다시 적지 않는다. task를 추가/시작/완료할 때는 먼저 `tasks-rule.md`를 본다.

## 7. 변경 분류별 체크리스트

### 7.1 ADR 추가만

- [ ] `docs/decisions.md`에 추가
- [ ] `docs/journal.md` 엔트리
- [ ] `docs/resume.md` "다음 한 작업" 갱신

### 7.2 docs 신규/수정

- [ ] 한국어 산문 (코드 식별자·API 필드명·명령어·URL만 영문 — `AGENTS.md`
      §문서 언어 정책)
- [ ] 관련 ADR 링크
- [ ] `docs/journal.md` 엔트리

### 7.3 DTO 추가/변경

- [ ] **수정 전 영향도 평가** — MCP `codegraph_explore` 또는 CLI
      `codegraph callers <sym>` + `codegraph impact <symbol>`로 호출자 파악
      (`docs/codegraph-worktree.md` §7).
- [ ] `dto/` 모듈 + Pydantic validator. 외부 인터페이스 좌표는 모두 `(lon,
      lat)` (DO NOT §5)
- [ ] `tests/unit/test_dto_*.py` validator branch 커버
- [ ] v1 응답이면 `x_extension` 외 자체 필드 추가 금지(ADR-003); 자체 통합
      필드는 v2 스키마에만 (ADR-038/039)
- [ ] `docs/architecture/data-model.md` 갱신 (DDL과 동기)
- [ ] `python scripts/export_openapi.py --check --output openapi.json`
      재실행 → 프론트엔드 `npm run gen:types`
- [ ] ADR (어느 정도 큰 변경이면) + journal + resume

### 7.4 raw SQL 추가/변경 (ADR-004)

- [ ] `infra/*_repo.py`의 `_SQL` 상수에 추가 (ORM에 비즈니스 로직 금지)
- [ ] 트랜잭션 단위로만 `SET LOCAL pg_trgm.similarity_threshold` (전역 변경 금지)
- [ ] `tests/integration/`에 EXPLAIN 검증 테스트 1개 이상 (인덱스 사용 확인)
- [ ] `docs/performance.md` 패턴/안티패턴 갱신 (필요 시)
- [ ] journal + resume

### 7.5 loader / 적재 변경

- [ ] GDAL Python binding 사용 (ADR-005, `ogr2ogr` subprocess 호출 금지),
      CP949 디코딩 명시
- [ ] `MVM_RES_CD` 등 코드 매핑은 `load_codes` 테이블 또는 settings (하드코드 금지)
- [ ] `tests/integration/test_load_*.py`
- [ ] `docs/architecture/backend-package.md` / `docs/t027-fullload-plan.md` 갱신 (필요 시)
- [ ] 재적재가 필요하면 `scripts/fullload_test.sh` (적재 자체는 T-027 완료)
- [ ] journal + resume

### 7.6 프론트엔드 (`kor-travel-geo-ui`) 변경

- [ ] **수정 전 영향도 평가** — 컴포넌트/공용 primitive/`maplibre-vworld-js`
      소비 경계면 `codegraph_explore` 먼저 (`docs/codegraph-worktree.md` §7)
- [ ] DB 드라이버 추가 금지 — UI는 REST API만 호출 (DO NOT §10)
- [ ] 백엔드 DTO가 바뀌었으면 `npm run gen:types`로 타입 재생성
- [ ] `scripts/frontend_check.sh` (Linux Node 강제, gen:types→lint→type-check
      →test→build) + `npx react-doctor@latest . --offline --verbose --json`
- [ ] Playwright e2e는 Windows에서 WSL UI 서버 대상으로 (chromium/firefox)
- [ ] journal + resume

## 7.5 PR 워크플로 (ADR-021, 필수)

main에 직접 push 금지. 모든 변경은 작업 branch + PR. 표준 운영 절차(worktree →
branch → NTFS 편집 → WSL 게이트 → PR → CI green → 머지 → 동기화)의 단계별
런북은 `docs/runbooks/agent-workflow.md`다.

### 7.5.1 시작 (NTFS worktree, Windows git.exe)

```bash
cd /mnt/f/dev/kor-travel-geo-<agent>
git fetch origin main
git switch -c agent/<agent>-<task> origin/main
codegraph sync && codegraph status
```

### 7.5.2 작업

- 짧은 commit + 명확한 메시지. 첫 줄 70자 이내.
  ```
  <scope> <verb>: <object> (#T-NNN 또는 ADR-NNN)

  본문 — "왜" 위주. 변경 내용은 diff가 알려준다.

  Refs: ADR-XXX, journal YYYY-MM-DD
  ```
  - `<scope>`: `api` / `core` / `infra` / `loaders` / `cli` / `dto` / `client` /
    `ui` / `docs` / `ci` / `chore`
  - `<verb>`: `add` / `fix` / `refactor` / `remove` / `rename` / `perf` /
    `test` / `chore`
- 작업 단위로 `docs/journal.md`, `docs/resume.md`, (필요 시) `docs/decisions.md`,
  `CHANGELOG.md` 갱신.
- 4 게이트 + 해당 시 추가 게이트를 통과 확인(§9).

### 7.5.3 PR 작성

표준 PR 본문(`.github/PULL_REQUEST_TEMPLATE.md`와 동기):

```bash
git push -u origin HEAD
gh pr create --repo digitie/kor-travel-geo \
  --title "<scope> <verb>: <요약 (≤70자)>" --body "$(cat <<'EOF'
## 동기 / 무엇이 문제였나
- 무엇을 바꾸는지 + 왜 (한 문단)

## 변경 내용 (한 줄 요약)
- 파일/모듈별 핵심 변경
- 새 DTO/엔드포인트/스키마/ADR 있으면 명시

## 영향 범위
- BREAKING 여부 (DTO 시그니처, DB schema, OpenAPI, v1 vworld 호환)
- kor-travel-geo-ui / loader / 외부 API 어느 쪽에 변경 필요한지

## 검증
- [ ] pytest -q
- [ ] ruff check . / mypy src/kortravelgeo / lint-imports
- [ ] (해당 시) pytest tests/integration -q + EXPLAIN 인덱스 검증
- [ ] (해당 시) python scripts/export_openapi.py --check --output openapi.json
- [ ] (UI) scripts/frontend_check.sh + react-doctor + Playwright e2e

## 문서
- [ ] docs/journal.md 엔트리
- [ ] docs/resume.md 진척도 갱신
- [ ] (결정 있음) docs/decisions.md 새 ADR
- [ ] (사용자 가시 변경) CHANGELOG.md
- [ ] (DTO/스키마 변경) docs/architecture/data-model.md

## 관련
- ADR-XXX / T-NNN / (외부 spec 링크)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### 7.5.4 branch 명명 규약

| 형식 | 용도 |
|------|------|
| `agent/<agent>-<task>` | 에이전트 작업 branch (기본). `<agent>`=`codex`/`claude`/`antigravity` |
| `agent/<agent>-idle` | 각 worktree의 idle branch (origin/main 동기) |

`agent/<agent>-` 접두로 소유자를 명시한다. 같은 branch를 두 worktree에서 동시
checkout하지 않는다.

### 7.5.5 리뷰 / merge

- CI green이어도 즉시 머지하지 않는다. PR 페이지에서 변경을 한 번 더 확인하고,
  리뷰 반영 여유를 둔 뒤 머지한다.
- 머지 방식: **Squash and merge** 권장(main 히스토리 깔끔). 머지 commit 제목은
  PR 제목과 동일하게.
- `gh pr merge`를 파이프로 감싸지 않는다(머지 실패를 숨김). `MERGED` 상태를
  확인한 뒤에만 branch를 정리한다.
  ```bash
  gh pr view <PR> --repo digitie/kor-travel-geo --json number,state,mergeable,statusCheckRollup
  gh pr merge <PR> --repo digitie/kor-travel-geo --merge --delete-branch
  ```
- WSL `gh`가 현재 worktree의 Windows Git metadata를 읽다 실패하면 같은 명령을
  반복하지 말고 `--repo digitie/kor-travel-geo`로 repo를 명시한다.

### 7.5.6 main 직접 push 차단

GitHub branch protection(운영자 수동 설정): PR 필수, required status checks
(ruff / mypy / lint-imports / pytest / OpenAPI drift / frontend) 통과, force-push
차단. 설정해 두면 `git push origin main`은 서버에서 거부된다.

## 8. 검증 게이트 (4 게이트 + 프론트엔드)

설치·테스트·장기 실행은 **WSL ext4 테스트 미러**에서 한다. NTFS worktree는
편집·branch·commit·PR 기준이다. 미러 셸에서 `source scripts/agent_env.sh`를
먼저 실행하면 `TMPDIR`·venv·Node PATH 함정을 한 번에 없앤다(`docs/runbooks/
agent-workflow.md` §1).

```bash
# 백엔드 4 게이트 (WSL ext4 미러)
pytest -q
ruff check .
mypy src/kortravelgeo scripts/export_openapi.py
lint-imports

# OpenAPI drift (DTO/스키마 변경 시)
python scripts/export_openapi.py --check --output openapi.json

# 프론트엔드 (Linux Node 강제 — gen:types → lint → type-check → test → build)
scripts/frontend_check.sh           # 의존성 재설치 필요 시 --install
cd kor-travel-geo-ui && npx react-doctor@latest . --offline --verbose --json

# Playwright e2e (Windows에서 WSL UI 서버 대상, chromium/firefox)
```

import 루트는 `from kortravelgeo import ...`(flat 금지), 의존 방향은 `dto →
core → infra → client → api/cli` 한 방향(`lint-imports` 강제). 자세한 검증
명령과 함정은 `docs/runbooks/agent-workflow.md`·`docs/dev-environment.md`.

## 9. NTFS Git vs WSL 실행 흐름

- 편집·branch·commit·push·PR은 NTFS worktree에서. Git metadata는 Windows Git
  기준이므로 git 명령은 Windows `git.exe`로 한다.
- 의존성 설치·테스트·lint·type-check·build·`uvicorn`·Node/npm·`gh`는 WSL ext4
  테스트 미러에서. 미러에서는 commit/push하지 않는다(단방향: 수정 필요 사항은
  NTFS worktree에 반영).
- Playwright e2e와 브라우저는 Windows에서만. WSL UI 서버(`--hostname
  0.0.0.0`)에 `PLAYWRIGHT_BASE_URL`로 붙인다.
- 이 저장소는 PostgreSQL/PostGIS와 RustFS를 **직접 구동하지 않는다**(DO NOT
  §11). 이미 동작 중인 DB/bucket에 `KTG_PG_DSN`, `KTG_RUSTFS_*`로 접속한다.
- 대용량 Juso 원천은 NTFS 공용 루트 `F:\dev\geodata\juso`가 기준이고, 미러는
  `data -> /mnt/f/dev/geodata` symlink로 참조한다(git에 넣지 않는다).

상세는 `docs/dev-environment.md`, `docs/runbooks/agent-workflow.md`.

## 10. PR 리뷰 확인 프로토콜 (세 표면)

PR 리뷰를 반영할 때 GitHub의 "Conversation comment", "Review body", "Inline
review thread"는 서로 다른 표면이다. `gh pr view --json comments`만 보면 정식
review body(`latestReviews`/`reviews`)나 inline thread를 놓칠 수 있다. 특히
리뷰 제목이 `# PR #NN 리뷰 — ...` 형태로 review body에 들어간 경우 conversation
comment 목록에는 보이지 않는다.

필수 절차:

1. PR 번호와 head branch 확인:
   ```bash
   gh pr view <PR> --repo digitie/kor-travel-geo \
     --json number,title,url,state,headRefName,baseRefName,reviewDecision,statusCheckRollup
   ```
2. thread-aware 스크립트로 세 표면을 한 번에 저장하고 `conversation_comments`,
   `reviews[].body`, `review_threads[]`를 모두 읽는다. review body 첫 줄(제목)도
   별도 항목으로 체크한다.
3. 항목을 `High` / `Medium` / `Low` / `Optional` / `설명만 필요`로 분류하고,
   반영 여부를 `docs/journal.md` 또는 PR 코멘트에 남긴다.
4. `review_threads`가 비어 있어도 review body의 H/M/L 섹션은 actionable일 수
   있다. "thread 없음"은 "리뷰 없음"이 아니다. 마지막 conversation comment도
   별도 확인한다.

WSL `gh`가 현재 worktree의 Windows Git metadata 충돌로 실패하면 같은 명령을
반복하지 말고 `--repo digitie/kor-travel-geo`로 repo를 명시한다.

리뷰 반영(fixup) PR에는 추가 리뷰를 붙이지 않는다(리뷰→fixup→fixup의 리뷰…
무한 루프 방지). 반영 중 발견한 새 결함은 별도 Task/issue로 분리한다(정본 규칙은
`docs/tasks-rule.md` §병행 운영 원칙).

## 11. 핸드오프 / 막힐 때

- 세션이 중단되거나 새 에이전트가 인수받을 때 `docs/journal.md`의 가장 최근
  엔트리가 핸드오프 노트다. **무엇을 했는지 / 무엇이 남았는지 / 어떤 결정이
  보류 중인지 / 어떤 파일을 먼저 봐야 하는지**를 모두 포함한다. PR 핸드오프
  표준 포맷은 `docs/windows-reinstall-recovery.md` §4.
- 같은 실패 명령을 같은 형태로 여러 번 반복하지 않는다. 한 번 실패하면
  `docs/runbooks/agent-failure-patterns.md`의 대응 패턴으로 전환한다.
- 사용자 요청이 모호하면 `AskUserQuestion` 사용. 코드 작성 요청이 `AGENTS.md`
  규칙과 충돌하면 충돌을 명시하고 대안을 제시한다. 모르는 도메인 어휘는
  `SKILL.md` §도메인 어휘 → 없으면 사용자에게 질의. 같은 결정이 두 번째로
  흔들리면 ADR-NNN으로 박는다.

## 12. 마침

이 가이드는 살아 있는 문서다. 작업하면서 빠진 룰이 발견되면 ADR과 함께 추가
하거나 이 문서를 직접 수정한다.

## 다음 에이전트에게 보내는 한 문장

> 문서를 갱신하지 않은 작업은 절반만 끝난 작업이다. 미래의 너 자신과, 너를
> 이어받을 다음 에이전트를 위해 `journal.md`와 `resume.md`를 반드시 채워라.
> 그것이 컨텍스트를 잃어도 끊기지 않는 유일한 방법이다.
