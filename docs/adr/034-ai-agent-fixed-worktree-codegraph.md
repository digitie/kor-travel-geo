# ADR-034: AI 에이전트는 고정 Git worktree와 CodeGraph 인덱스를 사용한다

- 상태: superseded by ADR-041
- 날짜: 2026-05-27
- 결정자: 사용자 요청, codex

## 컨텍스트

이 프로젝트는 ChatGPT Codex, Claude Code, Google Antigravity 2.0 같은 여러 AI 에이전트가 같은 저장소를 이어서 작업하는 방식 자체도 검증 대상이다. 지금까지는 같은 checkout에서 branch를 바꾸거나, 새 세션이 임시 위치에서 작업을 시작하는 일이 있었다. 이 방식은 다음 문제를 만든다.

- 에이전트가 다른 에이전트의 미커밋 변경을 덮어쓸 위험이 있다.
- branch 전환과 PR rebase가 같은 작업 디렉터리에서 겹치면 현재 작업의 소유자가 불분명해진다.
- CodeGraph 같은 로컬 인덱스가 checkout 단위로 만들어질 때, 어느 에이전트가 어느 인덱스를 갱신해야 하는지 애매하다.
- Windows 재설치나 새 Codex 세션 후 `git pull`만으로 작업을 복구하려면 worktree 이름과 branch 생성 규칙이 문서화되어 있어야 한다.

CodeGraph 원문 문서는 `codegraph init -i`가 프로젝트의 `.codegraph/` 디렉터리를 만들고 전체 인덱스를 즉시 생성하며, 기존 프로젝트는 `codegraph sync`로 증분 갱신할 수 있다고 설명한다. `.codegraph/`는 로컬 SQLite 지식 그래프이므로 저장소 이력에 넣을 대상이 아니다.

## 결정

WSL ext4의 `~/dev` 아래에 에이전트별 고정 Git worktree를 둔다.

| 에이전트 | 고정 worktree | branch prefix |
|----------|---------------|---------------|
| ChatGPT Codex | `~/dev/geo-codex` | `agent/codex-*` |
| Claude Code | `~/dev/geo-claude` | `agent/claude-*` |
| Google Antigravity 2.0 | `~/dev/geo-antigravity` | `agent/antigravity-*` |

기준 clone(`~/dev/kor-travel-geo`)은 `main` 동기화와 worktree 관리용으로 둔다. 실제 작업은 각 에이전트의 고정 worktree에서 수행하고, 작업마다 새 branch만 만든다. worktree 자체를 작업마다 삭제하거나 재생성하지 않는다.

최초 1회 생성 절차:

```bash
cd ~/dev/kor-travel-geo
git fetch origin main
git worktree add ../geo-codex -b agent/codex-worktree origin/main
git worktree add ../geo-claude -b agent/claude-worktree origin/main
git worktree add ../geo-antigravity -b agent/antigravity-worktree origin/main
```

새 작업 시작 절차:

```bash
cd ~/dev/geo-codex
git status --short
git fetch origin main
git switch -c agent/codex-next origin/main
codegraph sync
```

로컬 `main`이 최신으로 fast-forward된 것이 확인된 경우 사용자 예시처럼 다음 축약형도 가능하다.

```bash
git fetch
git switch -c agent/codex-next main
codegraph sync
```

다만 자동화와 AI 에이전트는 여러 worktree가 `main` checkout을 동시에 요구하지 않도록 `origin/main`을 시작점으로 쓰는 절차를 기본으로 한다.

CodeGraph는 worktree마다 최초 1회만 초기화한다.

```bash
codegraph init -i
```

`.codegraph/`가 이미 있으면 재초기화하지 않고 다음 명령으로 유지한다.

```bash
codegraph sync
codegraph status
```

프로젝트 루트의 `.codex/config.toml`에는 CodeGraph MCP stdio 서버를 등록한다.

```toml
[mcp_servers.codegraph]
enabled = true
command = "codegraph"
args = ["serve", "--mcp"]
```

`codegraph install --print-config codex`가 제안하는 로컬 CLI 방식이 WSL ext4 개발 환경의 기본값이다. Node/npm만 사용하는 환경에서는 `npx -y @colbymchenry/codegraph mcp` 형태를 쓸 수 있으나, WSL에서 Windows npm shim이 먼저 잡히면 UNC 경로 문제가 생길 수 있으므로 이 저장소는 standalone `codegraph` 실행 파일을 우선한다.

Codex Desktop을 재시작해 MCP가 노출된 세션에서는 `kor-travel-geo-ui` 컴포넌트, 지도 wrapper, 공용 UI primitive, `maplibre-vworld-js` 소비 경계를 수정하기 전에 반드시 CodeGraph MCP의 `codegraph_explore`로 영향도를 확인한다. 최소 확인 범위는 호출자, props/type 공유 지점, 관련 테스트, upstream으로 옮길 수 있는 범용 기능과 이 저장소에 남길 domain wrapper 기능이다.

`.codegraph/`는 `.gitignore`에 추가한다.

## 근거

- 고정 worktree는 에이전트별 파일 시스템 상태와 Git index를 분리하므로 미커밋 변경 충돌을 줄인다.
- 작업마다 branch만 새로 만들면 PR, commit, merge 이력이 작고 추적 가능하다.
- CodeGraph 인덱스를 worktree 단위로 유지하면 에이전트가 자기 checkout의 현재 branch를 기준으로 탐색한다.
- MCP의 `codegraph_explore`를 컴포넌트 수정 전 표준 절차로 두면 UI 변경의 호출자·테스트·upstream 경계를 놓칠 가능성을 줄인다.
- `.codegraph/`를 ignore하면 로컬 SQLite DB, watcher 상태, 인덱스 재생성 산출물이 리뷰 diff에 섞이지 않는다.
- `origin/main`을 시작점으로 쓰면 `main` branch가 다른 worktree에서 checkout되어 있어도 새 작업 branch를 만들 수 있다.

## 결과

- `docs/dev-environment.md`와 `docs/agent-guide.md`에 worktree 생성, 새 branch 시작, CodeGraph 초기화/동기화 절차를 추가한다.
- 프로젝트 루트 `.codex/config.toml`에 CodeGraph MCP stdio 서버 설정을 추가한다.
- 컴포넌트 수정 전 `codegraph_explore` 영향도 평가를 에이전트 작업 규칙으로 추가한다.
- `AGENTS.md`, `SKILL.md`, `README.md`에 핵심 정책을 요약한다.
- `.gitignore`에 `.codegraph/`를 추가한다.
- 새 에이전트 세션은 작업 전 자기 worktree와 CodeGraph 상태를 먼저 확인한다.
- 이번 작업에서 실제로 `~/dev/geo-codex`, `~/dev/geo-claude`, `~/dev/geo-antigravity` worktree를 만들고, 각 worktree에서 `codegraph init -i`와 `codegraph status`를 실행했다.

## 남은 위험

- CodeGraph CLI가 Windows npm shim만 PATH에 있고 WSL Node가 없으면 `codegraph` 실행이 실패할 수 있다. WSL에서는 Linux installer 또는 Linux Node/npm 기반 설치를 우선한다.
- 이미 존재하는 worktree에 미커밋 변경이 있으면 새 작업 branch를 만들기 전에 해당 에이전트가 변경의 소유권을 확인해야 한다.
- 장기 실행 중인 PR branch가 merge되기 전에 같은 worktree에서 다음 branch를 만들면 변경 추적이 흐려진다. PR이 머지되거나 명시 보류된 뒤 새 branch를 시작한다.
