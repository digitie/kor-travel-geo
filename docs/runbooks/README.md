# 에이전트 운영 Runbook

`kor-travel-geo`를 편집하는 **AI 에이전트 공용** runbook 모음이다. Claude Code /
ChatGPT Codex / Google Antigravity 2.0가 **같은 파일을 공유**한다 — 내용은
에이전트 중립이며, 에이전트별로 다른 부분(고정 worktree 경로, `agent/<agent>-*`
branch)은 표로 분기한다.

> 이 디렉터리는 "내가 손에 든 셸에서 어떤 순서로 무엇을 치면 동작하는가"에
> 답하는 **운영 절차**다. 환경·도구·문서화의 1차 reference는 별도이며(인덱스
> 아래 블록 참조), 본 runbook은 그것들을 절차로 엮는다.

## 1. 필독 (작업 전 2개)

실제 작업을 시작하기 전에 다음 두 개를 훑고 들어간다.

- **[agent-workflow.md](./agent-workflow.md)** — 표준 1-PR 작업 흐름.
- **[agent-failure-patterns.md](./agent-failure-patterns.md)** — 반복 실패 패턴
  회피. 게이트나 도구가 깨지면 프로젝트 버그로 보기 전에 여기부터 본다.

## 2. 인덱스

| 파일 | 범위 |
|------|------|
| [agent-workflow.md](./agent-workflow.md) | 표준 1-PR 작업 흐름 (Linux worktree → branch → WSL ext4 미러에서 4 게이트 → PR → CI green → 머지 → 동기화). 미러 셋업, `source scripts/agent_env.sh`, 프론트엔드/n150 Playwright/`gh`/CodeGraph 표준 명령 포함 |
| [agent-failure-patterns.md](./agent-failure-patterns.md) | 반복된 **환경/도구 계층 실패 패턴**과 회피·복구 (Windows Git 포인터 repair, `CreateProcess ... os error 2`, `/mnt` inline 편집 escape 손상, `gh` 로컬 git metadata 충돌, Windows npm shim, n150 Playwright fallback, CodeGraph 순서 등) |
| [restore-drill-runbook.md](./restore-drill-runbook.md) | 복원 드릴 (T-242). `ktgctl backup restore-drill`로 운영 serving DB를 건드리지 않고 백업이 실제 복원 가능한지 throwaway DB(`<base>_restoretest_<ts>`, `new_database` 모드)에서 증명 — reconcile(T-233) + smoke test + PASS/FAIL artifact, FAIL이면 비0 exit |

> **환경·도구·문서화의 1차 reference는 별도다** — 본 runbook은 그걸 운영 절차로
> 엮는다.
> - 개발 환경(Linux-only/WSL ext4 미러, GDAL 핀, 함정 전체): [`../dev-environment.md`](../dev-environment.md)
> - 에이전트 worktree + CodeGraph: [`../codegraph-worktree.md`](../codegraph-worktree.md)
>   + `AGENTS.md` §"에이전트별 고정 worktree와 CodeGraph"
> - 진입·문서화·PR 규약: [`../agent-guide.md`](../agent-guide.md)
> - task 번호·병행·리뷰 루프: [`../tasks-rule.md`](../tasks-rule.md)
> - DO NOT 룰 / 도메인 어휘: `SKILL.md`, `AGENTS.md` §절대 하지 말 것

## 3. 에이전트별 분기 (공유 표)

| AI 에이전트 | 고정 worktree | idle branch | 작업 branch 예시 |
|-------------|----------------------|-------------|------------------|
| ChatGPT Codex | `/mnt/f/dev/kor-travel-geo-codex` | `agent/codex-idle` | `agent/codex-<task>` |
| Claude Code | `/mnt/f/dev/kor-travel-geo-claude` | `agent/claude-idle` | `agent/claude-<task>` |
| Google Antigravity 2.0 | `/mnt/f/dev/kor-travel-geo-antigravity` | `agent/antigravity-idle` | `agent/antigravity-<task>` |

- **worktree는 영속**, 작업마다 그 안에서 **branch만 새로** 딴다
  (`git switch -c agent/<agent>-<task> origin/main`). 기준 clone
  (`/mnt/f/dev/kor-travel-geo`)은 사람 전용 — 에이전트는 자기 worktree만 만진다.
- 모든 에이전트는 PR을 **`main`** 으로 올린다. 같은 branch를 두 worktree에서
  동시 checkout하지 않는다. 자세한 setup은 [`../codegraph-worktree.md`](../codegraph-worktree.md) §3.

## 4. 공통 정책 (요약)

| 항목 | 정책 | 근거 |
|------|------|------|
| Git source of truth | **Linux `git`이 읽는 고정 worktree**(`/mnt/f/dev/kor-travel-geo*` 또는 ext4). `.git`/`gitdir`은 Linux 경로 기준 | ADR-065, dev-environment.md §1 |
| 설치·테스트·장기 실행 | **WSL ext4 테스트 미러**(rsync 사본, `data`는 symlink). 여기서 commit/push하지 않는다 | ADR-065, agent-workflow.md |
| 4 게이트 | `ruff check` + `mypy src/kortravelgeo` + `lint-imports` + `pytest -q` (DTO/스키마 변경 시 OpenAPI drift, UI 변경 시 frontend 게이트 추가) | AGENTS.md §검증 |
| main 직접 push | **금지** — 작업 branch + PR + **CI green 후** 머지 | ADR-021 |
| import 루트 / 의존 방향 | `from kortravelgeo import ...` (flat 금지), `dto → core → infra → client → api/cli` 한 방향 | DO NOT §1 |
| DB/RustFS | **직접 구동 금지** — 이미 동작 중인 것에 `KTG_PG_DSN`/`KTG_RUSTFS_*`로 접속만 | DO NOT §11 |
| task 운영 | 모든 Task는 PR 후 머지, fixup PR 재리뷰 금지, 새 결함은 별도 Task/issue | tasks-rule.md |
| 결정·기록 5종 | 코드 바꾸면 `decisions/resume/journal/tasks` + 사용자 가시 시 `CHANGELOG` 중 관련된 것 갱신 | agent-guide.md §2 |

전체 룰은 `AGENTS.md`와 `SKILL.md`를 정본으로 본다.
