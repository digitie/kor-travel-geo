# CodeGraph + 에이전트 Worktree 운영 룰

본 문서는 AI 에이전트(Claude Code / ChatGPT Codex / Google Antigravity 2.0)가
`kor-travel-geo`에서 작업할 때 **에이전트별 고정 worktree** + **CodeGraph 로컬
인덱스**를 어떻게 운영하는지 박는다. `AGENTS.md` §"에이전트별 고정 worktree와
CodeGraph"가 권위 있는 1쪽 요약이고, 본 문서는 그 운영 절차를 풀어 쓴 것이다.
`docs/dev-environment.md` §1.1·§1.2(환경·설치 reference)와 `docs/agent-guide.md`
(진입·문서화 규약)가 본 문서를 참조한다.

> 이 문서가 `AGENTS.md`와 어긋나면 `AGENTS.md`가 정본이다. 본 문서는 절차의
> 살을 붙일 뿐 정책을 새로 만들지 않는다.

## 1. 왜 에이전트별 고정 worktree인가

여러 AI 에이전트가 같은 저장소에서 순차·병행으로 일할 때, 하나의 checkout을
번갈아 쓰면 다음 문제가 생긴다.

1. **branch 컨텍스트 충돌** — Codex가 `agent/codex-next`에서 작업 중인데
   Claude가 같은 디렉터리에서 다른 branch로 `git switch` 하면 Codex의
   미커밋 변경/세션 상태가 깨진다.
2. **CodeGraph 인덱스 동기화 비용** — `codegraph sync`는 변경된 파일만 증분
   반영하지만, 매번 branch를 갈아끼우면 diff가 커져 sync 비용이 폭증한다.
3. **테스트 미러 재빌드** — 각 worktree는 자기 WSL ext4 테스트 미러를 갖는다.
   branch를 자주 바꾸면 rsync diff와 의존성 재설치가 늘어난다.

해결(ADR-041): **에이전트별 worktree 1개 고정**, **작업마다 그 worktree
안에서 branch만 새로** 딴다. 각 worktree는 자기 `.codegraph/`와 자기 테스트
미러를 갖는다. `geo-*` 옛 접두사는 폐기됐고 `kor-travel-geo-*`로 통일한다.

## 2. worktree 표 (정본: AGENTS.md)

| AI 에이전트 | 고정 worktree (NTFS) | idle branch | 작업 branch 예시 |
|-------------|----------------------|-------------|------------------|
| ChatGPT Codex | `/mnt/f/dev/kor-travel-geo-codex` (`F:\dev\kor-travel-geo-codex`) | `agent/codex-idle` | `agent/codex-t110-source-validate` |
| Claude Code | `/mnt/f/dev/kor-travel-geo-claude` (`F:\dev\kor-travel-geo-claude`) | `agent/claude-idle` | `agent/claude-t206-match-set` |
| Google Antigravity 2.0 | `/mnt/f/dev/kor-travel-geo-antigravity` (`F:\dev\kor-travel-geo-antigravity`) | `agent/antigravity-idle` | `agent/antigravity-ui-sync` |

- 기준 clone(`/mnt/f/dev/kor-travel-geo`)은 **사람 전용** — `main` 동기화와
  worktree 관리용이다. 에이전트는 자기 worktree만 만진다.
- worktree는 **영속**, 작업마다 그 안에서 `git switch -c agent/<agent>-<task>
  origin/main`으로 branch만 새로 딴다.
- 같은 branch를 두 worktree에서 동시에 checkout하지 않는다. branch 이름에는
  `agent/<agent>-<task>`처럼 소유자를 넣는다.

worktree는 NTFS(`F:\dev\`) 아래 기준 clone의 **형제**(sibling)로 둔다.

```text
F:\dev\
├── kor-travel-geo/              # 기준 clone (사람 전용, main 동기화·worktree 관리)
├── kor-travel-geo-codex/        # ChatGPT Codex 전용
├── kor-travel-geo-claude/       # Claude Code 전용
└── kor-travel-geo-antigravity/  # Google Antigravity 2.0 전용
```

## 3. 최초 setup (worktree마다 1회)

worktree 생성은 기준 clone에서 한다. CodeGraph 초기화는 각 worktree에서 1회.

```bash
# 1) 기준 clone에서 worktree 생성 (최초 1회). 이미 있으면 재생성하지 않는다.
cd /mnt/f/dev/kor-travel-geo
git fetch origin main
git worktree add ../kor-travel-geo-codex       -b agent/codex-idle       origin/main
git worktree add ../kor-travel-geo-claude      -b agent/claude-idle      origin/main
git worktree add ../kor-travel-geo-antigravity -b agent/antigravity-idle origin/main

# 2) WSL에 Linux standalone CodeGraph 설치 (Windows npm shim을 가리켜
#    node: not found이 나면 standalone installer를 쓴다)
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
hash -r
codegraph --version

# 3) 자기 worktree에서 최초 인덱싱 1회
cd /mnt/f/dev/kor-travel-geo-claude   # 예: Claude Code
codegraph init -i
codegraph status
```

`codegraph init -i`는 `.codegraph/` 디렉터리를 만들고 즉시 전체 인덱스를
생성한다. `-i`가 없으면 인덱스 빌드는 생략하고 디렉터리만 만든다. `codegraph
init -i`는 **최초 1회 인덱싱용**이지 상태 확인용이 아니다 — 상태는 `codegraph
status`로 본다.

`.codegraph/`는 로컬 SQLite 인덱스다. `.gitignore`에 포함돼야 하며 **커밋하지
않는다**. `.claude/`도 마찬가지로 로컬 상태/secret이므로 커밋하지 않는다.
각 worktree가 자기 인덱스를 갖는다.

로컬 secret/env 파일(`.env`, `kor-travel-geo-ui/.env.local`,
`.claude/settings.local.json`)은 새 worktree를 만들면 기준 clone 또는 기존
worktree에서 같은 상대경로로 복사한다. Git에 커밋하지 않는다.

## 4. 작업 사이클 (PR 1건마다)

NTFS worktree는 편집·branch·commit·PR 기준이다. 무거운 설치·테스트·장기 실행은
WSL ext4 테스트 미러에서 한다(`docs/dev-environment.md` §1, `docs/runbooks/
agent-workflow.md`). CodeGraph는 NTFS worktree 쪽에서만 유지한다.

```bash
# 0) 자기 worktree에 들어와 있다고 가정 (Claude는 /mnt/f/dev/kor-travel-geo-claude)
cd /mnt/f/dev/kor-travel-geo-claude

# 1) 최신 main에서 작업 branch 생성
git fetch origin main
git switch -c agent/claude-<task> origin/main

# 2) CodeGraph 인덱스 증분 동기 (재초기화 X) — sync 종료 후 status 확인
codegraph sync
codegraph status        # "Index is up to date" 확인

# 3) <편집 / 코드 작성>은 NTFS worktree에서, <설치/테스트>는 WSL 미러에서
#    (검증 명령 전체는 docs/runbooks/agent-workflow.md)

# 4) commit + push + PR (Windows git.exe / gh)
git add -p && git commit && git push -u origin HEAD
gh pr create --repo digitie/kor-travel-geo --title "..." --body "..."

# 5) PR 머지 후 다음 작업: 위 1)부터 반복.
#    .codegraph/는 그대로 둔다 — codegraph sync로만 따라잡는다.
```

**Key point**: `.codegraph/`는 worktree마다 **딱 한 번** 만들고(`codegraph
init -i`), 이후에는 `codegraph sync`로만 따라잡는다. **다시 `codegraph init`을
돌리지 않는다**(시간·디스크 낭비).

예외: `.codegraph/codegraph.db`가 손상됐거나 인덱스 스키마가 CodeGraph CLI
새 버전과 호환되지 않으면, `.codegraph/`를 통째로 지우고 `codegraph init -i`를
다시 한다.

## 5. NTFS `/mnt` watcher 비활성 — 수동 sync 규율

NTFS worktree는 WSL2 `/mnt` 경로라 recursive file watch가 비활성화될 수 있다.
live watch에 기대지 말고, 에이전트가 낡은 인덱스를 보지 않도록 **작업 시작·
branch 전환·`git pull`·rebase·merge 직후 수동으로** 동기화한다.

```bash
codegraph sync
codegraph status
```

`codegraph sync`와 `codegraph status`를 병렬로 실행하지 않는다 — sync가 끝나기
전에 status를 보면 sync 직후에도 pending으로 보일 수 있다. sync 종료를 기다린
뒤 status를 본다.

자주 쓰는 CLI(MCP가 없을 때 또는 사람 직접 작업):

```bash
# 동기화 상태 확인 (Files / Nodes / Edges / DB Size / 최신 여부)
codegraph status

# 변경 영향 분석 — file path가 아니라 export symbol 이름을 전달한다
codegraph impact AsyncAddressClient

# 누가 부르는지 / 무엇을 부르는지
codegraph callers normalize_road_address
codegraph callees AsyncAddressClient.geocode

# AI 에이전트용 컨텍스트 빌드 (task 단위, markdown 출력)
codegraph context "v2 후보 목록 API에 좌표 정밀도 필드 추가"
```

## 6. MCP 서버 등록 (에이전트 통합)

프로젝트 루트에는 CodeGraph MCP stdio 서버 설정을 둔다. 저장소별로 공유 가능한
개발 도구 설정이며 API key나 비밀값을 포함하지 않는다.

```toml
# .codex/config.toml — WSL Linux standalone codegraph가 PATH에 있을 때 (기본값)
[mcp_servers.codegraph]
enabled = true
command = "codegraph"
args = ["serve", "--mcp"]
```

순수 Node/npm 환경에서 `@colbymchenry/codegraph` 패키지를 직접 쓰는 경우:

```toml
[mcp_servers.codegraph]
enabled = true
command = "npx"
args = ["-y", "@colbymchenry/codegraph", "mcp"]
```

단, WSL에서 Windows npm shim이 먼저 잡히면 `npx`가 UNC 경로 경고를 내거나 WSL
프로젝트 경로를 제대로 넘기지 못할 수 있다. 이 저장소 기본값은 `codegraph
install --print-config codex`가 제안한 `codegraph serve --mcp` 방식이다.
Claude Code 쪽 등록은 `codegraph install --print-config claude` 출력을 쓴다.
설정을 추가한 뒤에는 에이전트 클라이언트(Codex Desktop 등)를 재시작해야 MCP
도구가 현재 세션에 노출된다. 재시작 전에도 CLI 명령은 그대로 쓸 수 있다.

## 7. 수정 전 영향도 평가 (UI / 공용 코드)

`kor-travel-geo-ui`의 React 컴포넌트, `components/vworld/*`, App Router client
component, 공용 UI primitive, `maplibre-vworld-js`(git URL pin) 소비 경계를
바꾸기 **전에는** CodeGraph MCP의 `codegraph_explore`를 먼저 호출해 영향도를
평가한다. 최소 확인 범위:

- 수정 대상 파일을 import하는 호출자와 page route
- 같은 props/type을 공유하는 컴포넌트
- 관련 unit/component 테스트와 Playwright 시나리오
- `maplibre-vworld-js`로 옮길 수 있는 범용 기능 vs 이 저장소에 남아야 하는
  domain wrapper 기능(책임 경계)

백엔드 쪽에서도 `AsyncAddressClient`, `kortravelgeo.dto`의 공개 DTO, repository
`_SQL` 상수처럼 호출자가 여러 곳에 퍼진 심볼을 바꾸기 전에는
`codegraph_callers` / `codegraph_impact` / `codegraph_callees`로 호출자와
`import-linter` 계약 영향을 먼저 본다(의존 방향: `dto → core → infra → client
→ api/cli`).

MCP가 아직 노출되지 않은 과도기 세션(예: Codex Desktop 재시작 전)에서는 그
사실을 작업 로그(`docs/journal.md`)나 PR 설명에 남기고, 임시로 `codegraph
sync` → `codegraph status` → `codegraph context <task>` 또는 `codegraph impact
<symbol>` CLI로 확인한다. 다음 세션에서는 `codegraph_explore`를 우선한다.

예외: 신규 파일만 추가하고 기존 공개 심볼 시그니처가 그대로면 영향도 평가를
생략할 수 있다.

## 8. CI / 빌드와의 관계

- `.codegraph/`는 **로컬 전용**. CI에서 CodeGraph를 돌리지 않는다.
- 4 게이트(`ruff check` / `mypy` / `lint-imports` / `pytest`)와 프론트엔드
  게이트, OpenAPI drift 검증은 CodeGraph와 무관하게 그대로 돈다.
- CodeGraph는 **에이전트의 컨텍스트 절약·영향도 평가용 도구**이지 검증 도구가
  아니다.

## 9. Windows Git + WSL 실행 호환

`docs/dev-environment.md` §1과 동일 정책이다.

- **worktree 본체**(코드/`.codegraph/`): NTFS(`F:\dev\kor-travel-geo-*`).
- **Git 메타데이터**: Windows Git 기준(`F:/dev/...`). WSL 편의를 위해 `.git`/
  `gitdir`을 `/mnt/f/...`로 고치지 않는다. WSL에서 worktree git 작업이 필요하면
  Windows `git.exe`를 쓴다(`"/mnt/c/Program Files/Git/cmd/git.exe" -C
  F:/dev/kor-travel-geo-<agent> ...`).
- `git worktree prune`은 **Windows에서만** 실행한다 — WSL에서 돌리면 `F:/`
  기준의 정상 worktree가 `prunable`로 보여 등록이 삭제될 수 있다. 포인터가
  `/mnt/f`로 틀어져 깨졌으면 Windows에서 `git worktree repair <경로>`로 복구한다.
- **설치/테스트/장기 실행**: WSL ext4 테스트 미러에서 한다. `.codegraph/`는
  미러 rsync에서 제외한다(미러는 CodeGraph를 두지 않는다).
- 반복 실패 패턴은 `docs/runbooks/agent-failure-patterns.md`에 정리돼 있다 —
  같은 증상이면 프로젝트 버그로 보기 전에 먼저 확인한다.

## 10. 사용자가 직접 작업할 때

사용자가 AI 에이전트를 거치지 않고 직접 작업하는 경우는 기준 clone
(`/mnt/f/dev/kor-travel-geo`)을 쓴다. `kor-travel-geo-*` worktree는 **각 AI
에이전트의 sandbox**다 — 사용자가 그 안에서 직접 수정하면 에이전트의 context와
충돌하므로 피한다.

## 11. 참고

- `AGENTS.md` §"에이전트별 고정 worktree와 CodeGraph" — 1쪽 정본 요약
- `docs/dev-environment.md` §1.1·§1.2 — worktree 생성·CodeGraph 설치 reference
- `docs/runbooks/agent-workflow.md` — NTFS 편집 + WSL 검증 표준 루프
- `docs/runbooks/agent-failure-patterns.md` — 반복 실패 패턴과 복구
- [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) — CodeGraph 공식 저장소
- [git worktree 공식 문서](https://git-scm.com/docs/git-worktree)
