# ADR-065: 개발 명령은 Linux 환경에서만 실행한다

- 상태: accepted
- 날짜: 2026-06-28
- 결정자: 사용자 요청, codex

## 컨텍스트

ADR-041은 NTFS worktree를 Git source of truth로 두고 Git metadata를 Windows Git 기준 경로로 유지하도록 정했다. 이후 실제 작업에서 WSL Git, CodeGraph, GitHub CLI가 `F:/...` 포인터를 읽지 못해 반복적으로 실패했다. 사용자는 모든 개발을 WSL을 포함한 Linux 환경에서만 진행하고, Git과 CodeGraph도 Linux에서 실행하도록 정책을 바꾸라고 요청했다.

Playwright는 과거 Windows 브라우저 실행을 표준으로 두었지만, 현재 운영 검증의 1차 대상은 n150 Linux 환경이다. Windows Playwright는 n150에서 실행할 수 없을 때의 fallback으로만 남긴다.

## 결정

1. 모든 개발 명령은 Linux 환경에서 실행한다. WSL은 허용되는 Linux 환경이다.
2. Git worktree 생성, repair, branch, commit, push, PR 준비는 Linux `git`으로 수행한다.
3. `.git`/`gitdir`이 `F:/...` 같은 Windows 경로를 가리키는 기존 worktree는 Linux에서 `git worktree repair <worktree>`를 실행하거나 재생성해 `/mnt/f/...` 또는 ext4 경로로 맞춘다.
4. CodeGraph는 Linux standalone 또는 Linux Node/npm 기반 실행만 사용한다. branch 전환·pull·merge 뒤에는 `codegraph sync` 후 `codegraph status`를 순서대로 실행한다.
5. 의존성 설치, 테스트, 장기 실행은 WSL ext4 테스트 미러에서 수행한다. 고정 worktree가 `/mnt/f/...`에 있어도 무거운 실행은 미러로 분리한다.
6. Playwright와 실제 브라우저 검증은 n150 Linux 환경에서 먼저 수행한다. n150에서 실행할 수 없는 경우에만 Windows Playwright를 fallback으로 사용하고, fallback 사유와 실행 명령을 작업 기록에 남긴다.

## 근거

- Linux Git 경로로 통일하면 WSL Git, CodeGraph, GitHub CLI가 같은 repository metadata를 읽는다.
- Windows Git 포인터를 유지하는 예외 규칙이 사라져 새 에이전트가 같은 실패 패턴을 반복할 가능성이 줄어든다.
- 무거운 실행을 ext4 테스트 미러로 분리하는 장점은 유지하면서, 개발 도구 실행 주체를 Linux로 단순화한다.
- n150은 실제 운영 검증에 가까운 Linux 환경이므로 브라우저 e2e의 1차 실행지로 적합하다.

## 결과(긍정)

- Git/CodeGraph/gh 경로 해석 실패가 줄어든다.
- 문서와 실제 셸 실행 기준이 Linux로 맞춰진다.
- Playwright 결과가 운영 환경에 더 가까워진다.

## 결과(부정)

- 기존 Windows Git 기준 worktree는 한 번 repair 또는 재생성이 필요하다.
- n150 브라우저 실행 준비가 안 된 경우 fallback 판단과 기록이 추가로 필요하다.

## 후속

- (open) 각 에이전트 worktree의 `.git`/`gitdir` 포인터를 Linux 경로로 repair하고 `git status --short --branch`를 확인한다.
- (open) n150 Playwright 실행에 필요한 Node/browser/secret 준비 상태를 별도 운영 runbook에서 점검한다.
