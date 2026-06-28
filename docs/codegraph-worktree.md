# CodeGraph + 에이전트 Worktree 운영 룰

본 문서는 AI 에이전트(Claude Code / ChatGPT Codex / Google Antigravity 2.0)가 `kor-travel-geo`에서 작업할 때 에이전트별 고정 worktree와 CodeGraph 로컬 인덱스를 어떻게 운영하는지 정리한다. `AGENTS.md`의 "에이전트별 고정 worktree와 CodeGraph"가 1쪽 정본이고, 본 문서는 절차를 풀어 쓴다.

> 이 문서가 `AGENTS.md`와 어긋나면 `AGENTS.md`가 정본이다. 현재 정책은 Linux-only 개발 환경(ADR-065)이다.

## 1. 왜 에이전트별 고정 worktree인가

여러 AI 에이전트가 같은 저장소에서 순차·병행으로 일할 때 하나의 checkout을 번갈아 쓰면 다음 문제가 생긴다.

1. branch 컨텍스트 충돌: 한 에이전트가 작업 중인 디렉터리에서 다른 에이전트가 branch를 바꾸면 미커밋 변경과 세션 상태가 깨진다.
2. CodeGraph 인덱스 동기화 비용: branch를 자주 갈아끼우면 diff가 커져 sync 비용이 늘어난다.
3. 테스트 미러 재빌드: 각 worktree는 자기 WSL ext4 테스트 미러를 갖는다.

해결(ADR-065): 에이전트별 worktree 1개를 고정하고, 작업마다 그 worktree 안에서 branch만 새로 딴다. 각 worktree는 자기 `.codegraph/`와 자기 테스트 미러를 갖는다. `geo-*` 옛 접두사는 폐기됐고 `kor-travel-geo-*`로 통일한다.

## 2. worktree 표

| AI 에이전트 | 고정 worktree | idle branch | 작업 branch 예시 |
|-------------|---------------|-------------|------------------|
| ChatGPT Codex | `/mnt/f/dev/kor-travel-geo-codex` | `agent/codex-idle` | `agent/codex-t110-source-validate` |
| Claude Code | `/mnt/f/dev/kor-travel-geo-claude` | `agent/claude-idle` | `agent/claude-t206-match-set` |
| Google Antigravity 2.0 | `/mnt/f/dev/kor-travel-geo-antigravity` | `agent/antigravity-idle` | `agent/antigravity-ui-sync` |

- 기준 clone(`/mnt/f/dev/kor-travel-geo`)은 main 동기화와 worktree 관리용이다.
- worktree는 영속이며 작업마다 `git switch -c agent/<agent>-<task> origin/main`으로 branch만 새로 딴다.
- 같은 branch를 두 worktree에서 동시에 checkout하지 않는다.
- Git/CodeGraph 명령은 Linux shell에서 실행한다.

## 3. 최초 setup

worktree 생성은 Linux `git`으로 기준 clone에서 한다. CodeGraph 초기화는 각 worktree에서 1회 수행한다.

```bash
cd /mnt/f/dev/kor-travel-geo
git fetch origin main
git worktree add ../kor-travel-geo-codex       -b agent/codex-idle       origin/main
git worktree add ../kor-travel-geo-claude      -b agent/claude-idle      origin/main
git worktree add ../kor-travel-geo-antigravity -b agent/antigravity-idle origin/main

curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
hash -r
codegraph --version

cd /mnt/f/dev/kor-travel-geo-codex
codegraph init -i
codegraph status
```

`.codegraph/`는 로컬 SQLite 인덱스다. `.gitignore`에 포함돼야 하며 커밋하지 않는다. `.claude/`도 로컬 상태/secret이므로 커밋하지 않는다.

## 4. 과거 Windows Git 포인터 복구

과거 정책 아래 만들어진 worktree는 `.git` 또는 `.git/worktrees/<name>/gitdir`이 `F:/...` 경로를 가리킬 수 있다. 현재 정책에서는 Windows 드라이브 경로를 유지하지 않는다. Linux Git이 읽을 수 있도록 repair한다.

```bash
cd /mnt/f/dev/kor-travel-geo
git worktree repair /mnt/f/dev/kor-travel-geo-codex
git -C /mnt/f/dev/kor-travel-geo-codex status --short --branch
```

repair 전에는 `git worktree prune`을 실행하지 않는다. 먼저 살아있는 worktree를 valid 상태로 만든 뒤, 폴더가 실제로 사라진 등록만 정리한다.

## 5. 작업 사이클

```bash
cd /mnt/f/dev/kor-travel-geo-codex

git fetch origin main
git switch -c agent/codex-<task> origin/main

codegraph sync
codegraph status

# 편집 / 구현
# 검증은 docs/runbooks/agent-workflow.md에 따라 WSL ext4 테스트 미러에서 실행

git add -p
git commit -m "<message>"
git push -u origin HEAD
```

`codegraph sync`와 `codegraph status`를 병렬로 실행하지 않는다. sync가 끝난 뒤 status를 본다.

## 6. 자주 쓰는 CodeGraph CLI

```bash
# 동기화 상태 확인
codegraph status

# 변경 영향 분석 — file path가 아니라 export symbol 이름을 전달한다
codegraph impact AsyncAddressClient

# 누가 부르는지 / 무엇을 부르는지
codegraph callers normalize_road_address
codegraph callees AsyncAddressClient.geocode

# AI 에이전트용 컨텍스트 빌드
codegraph context "v2 후보 목록 API에 좌표 정밀도 필드 추가"
```

## 7. MCP 서버 등록

프로젝트 루트에는 CodeGraph MCP stdio 서버 설정을 둔다. 저장소별로 공유 가능한 개발 도구 설정이며 API key나 비밀값을 포함하지 않는다.

```toml
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

단, WSL에서 Windows npm shim이 먼저 잡히면 `npx`가 UNC 경로 경고를 내거나 프로젝트 경로를 제대로 넘기지 못할 수 있다. 이 저장소 기본값은 Linux standalone `codegraph serve --mcp` 방식이다. 설정을 추가한 뒤에는 에이전트 클라이언트(Codex Desktop 등)를 재시작해야 MCP 도구가 현재 세션에 노출된다.

## 8. 수정 전 영향도 평가

`kor-travel-geo-ui`의 React 컴포넌트, `components/vworld/*`, App Router client component, 공용 UI primitive, 지도 wrapper 소비 경계를 바꾸기 전에는 CodeGraph MCP의 `codegraph_explore`를 먼저 호출해 영향도를 평가한다.

최소 확인 범위:

- 수정 대상 파일을 import하는 호출자와 page route
- 같은 props/type을 공유하는 컴포넌트
- 관련 unit/component 테스트와 Playwright 시나리오
- upstream으로 옮길 수 있는 범용 기능과 이 저장소에 남아야 하는 domain wrapper 기능

백엔드 쪽에서도 `AsyncAddressClient`, `kortravelgeo.dto` 공개 DTO, repository `_SQL` 상수처럼 호출자가 여러 곳에 퍼진 심볼을 바꾸기 전에는 `codegraph_callers` / `codegraph_impact` / `codegraph_callees`로 호출자와 `import-linter` 계약 영향을 먼저 본다.

MCP가 아직 노출되지 않은 세션에서는 그 사실을 작업 로그(`docs/journal.md`)나 PR 설명에 남기고, 임시로 `codegraph sync` → `codegraph status` → `codegraph context <task>` 또는 `codegraph impact <symbol>` CLI로 확인한다.

## 9. CI / 빌드와의 관계

- `.codegraph/`는 로컬 전용이다. CI에서 CodeGraph를 돌리지 않는다.
- 4 게이트(`ruff check` / `mypy` / `lint-imports` / `pytest`)와 프론트엔드 게이트, OpenAPI drift 검증은 CodeGraph와 무관하게 그대로 돈다.
- CodeGraph는 에이전트의 컨텍스트 절약·영향도 평가용 도구이지 검증 도구가 아니다.

## 10. 참고

- `AGENTS.md` — 1쪽 정본 요약
- `docs/dev-environment.md` — worktree 생성·CodeGraph 설치 reference
- `docs/runbooks/agent-workflow.md` — Linux Git + WSL 검증 표준 루프
- `docs/runbooks/agent-failure-patterns.md` — 반복 실패 패턴과 복구
- [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) — CodeGraph 공식 저장소
- [git worktree 공식 문서](https://git-scm.com/docs/git-worktree)
