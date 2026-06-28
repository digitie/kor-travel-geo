# 반복되는 에이전트 실패 패턴과 재발 방지

본 문서는 Linux-only 개발 정책(ADR-065) 아래에서 AI 에이전트가 자주 부딪히는 환경/도구 계층 실패를 정리한다. 여기서 다루는 증상은 대개 프로젝트 코드 버그가 아니라 Git metadata 포인터, Codex `exec_command` 런처, `/mnt` 파일시스템, Node/npm PATH, Playwright 실행지 차이에서 생긴다.

## 1. 한눈에 보는 분류

| 증상 | 실제 원인 | 1차 대응 |
|------|-----------|-----------|
| `fatal: not a git repository: ... F:/dev/.../.git/worktrees/...` | worktree Git metadata가 과거 Windows 경로를 가리킴 | Linux main repo에서 `git worktree repair <worktree>` 후 Linux `git status` 재확인 |
| `gh pr view`가 `.../mnt/f/.../F:/...` 경로 오류를 냄 | `gh`가 로컬 Git metadata를 읽다가 실패 | `gh ... --repo digitie/kor-travel-geo`로 repo 명시, branch/commit/push는 Linux `git` |
| `CreateProcess ... os error 2`가 셸 진입 전 발생 | `exec_command` 런처가 복잡한 quoting, heredoc, `workdir`, 외부 exe 호출 패턴을 안정적으로 못 띄움 | 명령을 단순화하고 `cd ... && <단일 명령>` 형태로 재시도 |
| `apply_patch`가 `/mnt/f/...` 파일을 못 찾음 | patch helper가 mount 경로를 일관되게 해석하지 못함 | 같은 방식 반복 금지. 작은 범위 치환 또는 파일 단위 재시도 후 즉시 재확인 |
| `"\n"`, regex backslash가 코드 안에서 깨짐 | inline shell/Python 멀티라인 편집에서 escape가 여러 번 해석됨 | bulk rewrite 대신 line-oriented edit + `sed` 재확인 + lint/type-check |
| WSL에서 `node: command not found` | Linux Node가 PATH에 없거나 Windows npm/node shim이 먼저 잡힘 | `source ~/.nvm/nvm.sh` 또는 `source scripts/agent_env.sh` |
| `npm run start --hostname ...`가 인자를 못 받음 | npm script 인자는 `--` 뒤에만 하위 명령으로 전달됨 | `npm run start -- --hostname 0.0.0.0 --port 12505` |
| n150 Playwright가 실행 불가 | n150 브라우저/권한/네트워크/secret 준비가 안 됨 | 사유를 기록하고 Windows Playwright fallback 실행 |
| `codegraph status`가 sync 직후에도 pending | `codegraph sync`가 끝나기 전에 status를 봄 | sync 종료를 기다린 뒤 status 실행. `impact`는 file path가 아니라 symbol 이름 전달 |
| `next-env.d.ts`가 `.next/dev/types/routes.d.ts`로 바뀜 | Next dev/build가 자동 생성 reference를 로컬 실행 모드에 맞게 고침 | 커밋 전 tracked 기준으로 되돌리고 generated reference 변경은 제외 |

## 2. 패턴 A — Windows Git 포인터가 남아 Linux Git이 실패

### 증상

- `git -C /mnt/f/dev/kor-travel-geo-codex status`가 실패한다.
- 오류 메시지에 `F:/dev/.../.git/worktrees/...` 같은 Windows 경로가 섞여 나온다.
- `git worktree list`에서 살아있는 worktree가 `prunable`처럼 보인다.

### 원인

worktree의 `.git` 파일과 main repo `.git/worktrees/<name>/gitdir`에는 worktree를 만든 환경 기준 절대경로가 들어간다. 과거 Windows Git 정책 아래 만들어진 worktree는 `F:/...`를 가리킬 수 있다. 현재 정책은 Linux-only이므로 이 상태를 유지하지 않는다.

### 대응

```bash
cd /mnt/f/dev/kor-travel-geo
git worktree repair /mnt/f/dev/kor-travel-geo-codex
git -C /mnt/f/dev/kor-travel-geo-codex status --short --branch
```

repair 전에 `git worktree prune`을 실행하지 않는다. 먼저 살아있는 worktree를 Linux 기준으로 valid 상태로 만든 뒤, 실제로 폴더가 사라진 등록만 정리한다.

## 3. 패턴 B — `exec_command`의 `CreateProcess ... os error 2`

### 증상

- `python3 - <<'PY' ... PY`, `python3 -c '...'`, 긴 pipe, 복잡한 quote를 쓴 호출이 셸 실행 전 단계에서 실패한다.
- 같은 바이너리도 더 단순한 형태로는 정상 동작한다.

### 대응

1. 명령은 가능한 한 단순한 한 줄로 유지한다.
2. `workdir`가 흔들리면 `cd <repo> && <command>` 형태를 쓴다.
3. heredoc보다 `rg`, `sed`, `cat`, `git -C`, `npm run ...` 같은 단일 바이너리 호출을 우선한다.
4. 같은 실패 명령을 같은 형태로 반복하지 않는다.

## 4. 패턴 C — mount 경로에서 patch/helper가 흔들림

### 증상

- `apply_patch`가 `No such file or directory`를 반환하지만 `sed -n`은 같은 파일을 읽는다.
- `/mnt/f/dev/kor-travel-geo-codex/...` 아래 파일에서 간헐적으로 발생한다.

### 대응

1. 원칙상 `apply_patch`를 먼저 시도한다.
2. 동일 파일이 `sed`로는 읽히는데 `apply_patch`만 실패하면 같은 호출을 반복하지 않는다.
3. 작은 범위의 치환 명령으로 대체하고 바로 해당 줄을 다시 연다.
4. 대량 rewrite보다 targeted replace를 우선한다.

## 5. 패턴 D — inline rewrite에서 escape 손상

### 증상

- `.join("\n")`가 실제 파일에는 줄바꿈 리터럴로 들어간다.
- regex backslash가 줄거나 사라진다.
- `sed` 출력과 의도한 문자열이 다르다.

### 대응

1. `apply_patch`가 되면 그 경로를 우선한다.
2. fallback edit가 필요하면 한 번에 큰 파일을 다시 쓰지 말고 한 토큰/한 블록씩 치환한다.
3. `\n`, regex, Windows path처럼 backslash가 많은 문자열은 수정 직후 `sed -n`으로 해당 줄을 확인한다.
4. escape가 많은 수정 뒤에는 lint/type-check를 먼저 돌린다.

## 6. GitHub CLI

`gh`는 현재 디렉터리의 Git metadata를 읽으려다 실패할 수 있다. PR 조회·머지는 repo를 명시한다.

```bash
gh pr view <PR_NUMBER> --repo digitie/kor-travel-geo --json number,state,mergeable,statusCheckRollup
gh pr merge <PR_NUMBER> --repo digitie/kor-travel-geo --merge --delete-branch
```

Git 자체는 Linux `git`을 쓴다.

```bash
cd /mnt/f/dev/kor-travel-geo-codex
git status --short --branch
git add -p
git commit -m "<message>"
git push -u origin HEAD
```

## 7. npm server parameter 전달

npm script에 전달할 Next.js 옵션은 반드시 `--` 뒤에 둔다.

```bash
cd <wsl-test-mirror>/kor-travel-geo-ui
source ~/.nvm/nvm.sh
npm run dev -- --hostname 0.0.0.0 --port 12505
npm run start -- --hostname 0.0.0.0 --port 12505
```

다음 형태는 쓰지 않는다.

```bash
npm run start --hostname 0.0.0.0 --port 12505
npm run dev --hostname 0.0.0.0 --port 12505
```

## 8. Playwright 실행지

Playwright와 실제 브라우저 검증은 n150 Linux 환경에서 먼저 수행한다. n150에서 실행할 수 없는 경우에만 Windows Playwright를 fallback으로 사용한다.

Fallback을 쓰면 다음을 기록한다.

- n150에서 실행하지 못한 구체적 이유
- 실행한 Windows 명령
- 브라우저 project(`chromium`, `firefox`)
- 결과와 screenshot/report 경로

## 9. Linux Node/npm 환경

WSL 기본 shell에서 bare `node`가 없을 수 있다. Node가 필요한 명령은 다음 중 하나를 먼저 실행한다.

```bash
source ~/.nvm/nvm.sh
# 또는 테스트 미러 루트에서
source scripts/agent_env.sh
```

VWorld 키는 절대 출력하지 않는다. 문서와 로그에는 `nonempty`, `length`처럼 존재 여부만 남긴다.

## 10. 서버 종료

장기 실행 `exec_command` session의 stdin이 닫히면 `Ctrl-C`를 보낼 수 없다. 포트 기준으로 PID를 확인하고 종료한다.

```bash
ss -ltnp | rg ':12505'
kill <PID>
ss -ltnp | rg ':12505' || true
```

## 11. 반복 시도 제한 규칙

같은 실패 명령을 같은 형태로 여러 번 반복하지 않는다. 한 번 실패하면 원인을 먼저 분류하고, 두 번째 실행은 다른 접근 방식이어야 한다.

| 실패 유형 | 같은 방식 재시도 한도 | 바로 바꿀 방식 |
|-----------|----------------------|----------------|
| Linux `git`가 `F:/...` 포인터 때문에 실패 | 0회 | `git worktree repair <worktree>` |
| `gh`가 로컬 Git repository 오류를 냄 | 0회 | `gh ... --repo digitie/kor-travel-geo` |
| bare `node`/`npm`이 없음 | 0회 | `source ~/.nvm/nvm.sh` 또는 `source scripts/agent_env.sh` |
| npm script가 server option을 못 받음 | 0회 | `npm run <script> -- --hostname ... --port ...` |
| n150 Playwright 실행이 불가 | 1회 | 사유 기록 후 Windows fallback |
| long-running server가 Ctrl-C로 안 꺼짐 | 0회 | `ss -ltnp | rg ':<PORT>'`로 PID 확인 후 `kill <PID>` |
| CodeGraph가 pending으로 보임 | 0회 | sync 종료 대기 후 status 재실행 |
| generated file이 실행 모드 때문에 바뀜 | 0회 | tracked 기준으로 복구하고 커밋 제외 |
