# 반복되는 에이전트 실패 패턴과 재발 방지

본 문서는 NTFS source-of-truth + WSL ext4 테스트 미러 정책(ADR-041) 아래에서 AI 에이전트가 자주 부딪히는 **환경/도구 계층 실패**를 정리한다. 여기서 다루는 증상은 대개 프로젝트 코드 버그가 아니라, Git metadata 포인터, Codex `exec_command` 런처, NTFS 파일 편집 경로의 상호작용에서 생긴다.

## 1. 한눈에 보는 분류

| 증상 | 실제 원인 | 1차 대응 |
|------|-----------|-----------|
| `fatal: not a git repository: ... F:/dev/.../.git/worktrees/...` | NTFS worktree의 Git metadata가 Windows 경로를 가리키는데 WSL `git`로 읽음 | NTFS worktree에서는 Windows `git.exe -C F:/...`만 사용 |
| `CreateProcess ... os error 2` 가 셸 진입 전 발생 | `exec_command` 런처가 복잡한 quoting, heredoc, `workdir`, Windows exe 실행 패턴을 안정적으로 못 띄움 | 명령을 단순화하고 `cd ... &&` + 단일 바이너리 패턴으로 재시도 |
| `apply_patch`가 `/mnt/f/...` 파일을 못 찾음 | 현재 세션의 patch helper가 NTFS mount 경로를 일관되게 해석하지 못함 | 작은 범위 치환 명령으로 대체하고 즉시 파일 재확인 |
| `"\n"`, regex backslash가 코드 안에서 깨짐 | inline shell/Python 멀티라인 편집에서 escape가 여러 번 해석됨 | bulk rewrite 대신 line-oriented edit + `sed` 재확인 + lint/type-check 즉시 실행 |
| `gh pr view`가 `.../mnt/f/.../F:/...` 경로 오류를 냄 | WSL `gh`가 현재 worktree의 Windows Git metadata를 로컬 git으로 읽으려 함 | `gh ... --repo digitie/kor-travel-geo`로 repo를 명시해 로컬 git 조회를 우회 |
| WSL에서 `node: command not found` | 기본 PATH에 Linux Node가 없고 Windows npm/node shim만 보이거나 아무 Node도 없음 | `source ~/.nvm/nvm.sh` 또는 `source scripts/agent_env.sh` 후 실행 |
| `npm run start --hostname ...`가 인자를 못 받음 | npm script 인자는 `--` 뒤에만 하위 명령으로 전달됨 | `npm run start -- --hostname 0.0.0.0 --port 12205` |
| Windows Playwright가 WSL 서버 URL을 못 받음 | WSL에서 `cmd.exe`로 넘기는 env var quoting이 Windows cmd 규칙과 어긋남 | `cmd.exe /V:ON /C "cd /d F:\...\kor-travel-geo-ui && set PLAYWRIGHT_BASE_URL=http://<WSL_IP>:<PORT>&& npx playwright test ..."` |
| `codegraph status`가 sync 직후에도 pending을 보임 | `codegraph sync`가 끝나기 전에 status를 병렬로 실행함 | sync 종료를 기다린 뒤 status 실행. `impact`는 file path가 아니라 symbol 이름을 전달 |
| `next-env.d.ts`가 `.next/dev/types/routes.d.ts`로 바뀜 | Next dev/build가 자동 생성 reference를 로컬 실행 모드에 맞게 고침 | 커밋 전 tracked 기준으로 되돌린다. generated reference 변경은 작업 범위가 아니다 |

## 2. 패턴 A — NTFS worktree에서 WSL `git` 실패

### 증상

- `git -C /mnt/f/dev/kor-travel-geo-codex status`가 실패한다.
- 오류 메시지에 `F:/dev/.../.git/worktrees/...` 같은 Windows 경로가 섞여 나온다.
- 같은 worktree가 어떤 환경에서는 정상인데, 다른 환경에서는 `prunable`처럼 보인다.

### 원인

현재 정책상 NTFS worktree의 `.git`와 main repo의 `worktrees/*/gitdir` 포인터는 **Windows Git 기준 절대경로**(`F:/dev/...`)를 유지한다. 이 상태는 의도된 것이다. 따라서 WSL `git`이 `/mnt/f/...` worktree를 직접 읽으면 포인터 경로를 해석하지 못해 repository 오류가 난다.

### 재발 방지

1. NTFS worktree에서 Git 상태 확인, branch 생성, commit, push, merge는 **Windows `git.exe`**만 쓴다.
2. ext4 테스트 미러에서는 Git commit/push를 하지 않는다.
3. 환경을 바꿔 같은 worktree를 다뤄야 하면 먼저 그 환경에서 `git worktree repair <worktree>`를 실행한다.
4. `git worktree prune`은 worktree를 실제로 운용하는 환경에서만 실행한다.

### 표준 명령

```bash
"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/kor-travel-geo-codex status --short --branch
"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/kor-travel-geo-codex switch -c agent/codex-next
```

## 3. 패턴 B — `exec_command`의 `CreateProcess ... os error 2`

### 증상

- `python3 - <<'PY' ... PY`, `python3 -c '...'`, `nl ... | sed ...`, `workdir=...`를 쓴 호출이 셸 실행 전 단계에서 바로 실패한다.
- 같은 바이너리(`sed`, `rg`, `npm run ...`)도 더 단순한 형태로는 정상 동작한다.
- Windows PowerShell exe를 직접 호출할 때도 런처가 프로세스를 띄우지 못하는 경우가 있다.

### 원인

이 증상은 저장소 파일 없음이 아니라 **Codex `exec_command` 런처 계층의 명령 조립/실행 한계**다. 특히 다음 패턴이 취약했다.

- heredoc, nested quote가 많은 `python -c`/`python - <<'PY'`
- `workdir`를 쓰는 호출
- 파이프/여러 셸 연산자를 섞은 긴 명령
- Windows exe 경로를 bash에서 바로 실행하는 패턴

### 재발 방지

1. 명령은 가능한 한 **단순한 한 줄**로 유지한다.
2. `workdir` 대신 `cd ... && <command>`를 우선 쓴다.
3. heredoc보다 `sed`, `rg`, `cat`, `git -C`, `npm run ...` 같은 단일 바이너리 호출을 우선한다.
4. 동일 작업을 더 단순한 명령으로 표현할 수 있으면 먼저 그 형태로 재시도한다.
5. 이 오류가 나오면 프로젝트 버그로 오판하지 말고 **런처 실패**로 분류한다.

### 권장 순서

1. 읽기: `rg`, `sed`, `cat`
2. Git: Windows `git.exe -C F:/...`
3. Node 검증: `cd <mirror> && npm run ...`
4. 그 외 복잡한 편집/생성: 작은 치환 명령 또는 repo 스크립트 사용

## 4. 패턴 C — `apply_patch`가 NTFS 파일을 못 찾는 경우

### 증상

- `apply_patch`가 `No such file or directory`를 반환하지만, 바로 이어서 `sed -n`은 같은 파일을 읽을 수 있다.
- 특히 `/mnt/f/dev/kor-travel-geo-codex/...` 아래 파일에서 간헐적으로 발생한다.

### 원인

현재 세션의 patch helper가 NTFS mount 경로를 일관되게 해석하지 못하는 경우가 있다. 이는 저장소 파일 존재 여부와 별개인 **도구 계층 문제**다.

### 재발 방지

1. 원칙상 `apply_patch`를 먼저 시도한다.
2. 동일 파일이 `sed`로는 읽히는데 `apply_patch`만 실패하면, 같은 명령을 반복하지 않는다.
3. 이 경우 **작은 범위의 치환 명령**으로 대체하고, 바로 해당 줄을 다시 연다.
4. 대량 파일 rewrite보다 targeted replace를 우선한다.

## 5. 패턴 D — inline rewrite에서 escape 손상

### 증상

- `.join("\n")`가 실제 파일에는 줄바꿈 리터럴로 들어간다.
- regex backslash가 줄거나 사라진다.
- `sed` 출력과 의도한 문자열이 다르다.

### 원인

JSON 문자열 → bash → Python 문자열 → TypeScript 문자열처럼 **escape가 여러 계층에서 연속 해석**되면서 손상된다. NTFS 원본을 inline script로 고칠 때 자주 발생했다.

### 재발 방지

1. `apply_patch`가 되면 그 경로를 우선한다.
2. fallback edit가 필요하면 한 번에 큰 파일을 다시 쓰지 말고 **한 토큰/한 블록씩 치환**한다.
3. `\n`, regex, Windows path처럼 backslash가 많은 문자열은 수정 직후 `sed -n`으로 해당 줄을 재확인한다.
4. escape가 많은 수정 뒤에는 `lint`, `type-check`를 먼저 돌려 문법 오류를 조기 발견한다.

## 6. 표준 fallback 순서

1. **Git/branch/commit**: NTFS worktree + Windows `git.exe`
2. **검증**: ext4 테스트 미러에서 `pytest`, `npm run lint`, `npm run build`
3. **읽기/탐색**: `rg`, `sed`, `codegraph sync/status/impact`
4. **패치**: `apply_patch` 우선
5. **patch helper 실패 시**: 작은 치환 명령 + 즉시 재열기
6. **문서화**: 새 실패 패턴이 재현되면 `docs/journal.md`와 이 문서에 추가

## 7. 이번 세션에서 확인된 실전 규칙

- `git -C /mnt/f/...`는 쓰지 않는다. NTFS worktree에서는 처음부터 Windows `git.exe -C F:/...`로 간다.
- `exec_command`가 `CreateProcess ... os error 2`를 내면, 먼저 quoting과 실행 형식을 단순화한다.
- `workdir`가 되는지 먼저 실험하지 않는다. 이미 `cd ... &&`가 안정적이면 그 패턴을 유지한다.
- multiline inline rewrite 뒤에는 반드시 같은 파일을 다시 열어 escape 손상을 확인한다.
- 테스트 미러에서 검증이 통과해도, source-of-truth 수정은 항상 NTFS worktree에 반영했는지 다시 확인한다.

## 8. 반복 시도 제한 규칙

같은 실패 명령을 같은 형태로 여러 번 반복하지 않는다. 한 번 실패하면 원인을 먼저 분류하고, 두 번째 실행은 다른 접근 방식이어야 한다.

| 실패 유형 | 같은 방식 재시도 한도 | 바로 바꿀 방식 |
|-----------|----------------------|----------------|
| WSL `git`가 NTFS worktree에서 실패 | 0회 | Windows `git.exe -C F:/...` |
| `gh`가 로컬 git repository 오류를 냄 | 0회 | `gh ... --repo digitie/kor-travel-geo` |
| bare `node`/`npm`이 WSL에서 없음 | 0회 | `source ~/.nvm/nvm.sh` 또는 `source scripts/agent_env.sh` |
| npm script가 server option을 못 받음 | 0회 | `npm run <script> -- --hostname ... --port ...` |
| Windows Playwright env var가 안 먹음 | 1회 | 검증된 `cmd.exe /V:ON /C "set VAR=value&& ..."` 형태 |
| long-running server가 Ctrl-C로 안 꺼짐 | 0회 | `ss -ltnp | rg ':<PORT>'`로 PID 확인 후 `kill <PID>` |
| CodeGraph가 pending으로 보임 | 0회 | sync 종료 대기 후 status 재실행 |
| generated file이 실행 모드 때문에 바뀜 | 0회 | tracked 기준으로 복구하고 커밋 제외 |

## 9. 이번 세션 복기 — CLI·서버·환경 표준

### GitHub CLI

WSL shell에서 `gh`를 쓰더라도 현재 디렉터리의 `.git`은 Windows 경로를 가리킨다. 따라서 `gh pr view 114`처럼 repo를 생략하면 `gh`가 로컬 git을 읽다가 다음과 같은 오류를 낼 수 있다.

```text
failed to run git: fatal: not a git repository: /mnt/f/.../F:/dev/...
```

표준 명령은 repo를 명시하는 형태다.

```bash
gh pr view <PR_NUMBER> --repo digitie/kor-travel-geo --json number,state,mergeable,statusCheckRollup
gh pr merge <PR_NUMBER> --repo digitie/kor-travel-geo --merge --delete-branch
```

Git 자체는 계속 Windows `git.exe`를 쓴다. `gh`는 PR/Actions API 조회에만 쓰고, local branch/status/commit/push는 Windows `git.exe` 기준으로 유지한다.

### npm server parameter 전달

npm script에 전달할 Next.js 옵션은 반드시 `--` 뒤에 둔다. 아래가 표준이다.

```bash
cd <wsl-test-mirror>/kor-travel-geo-ui
source ~/.nvm/nvm.sh
npm run dev -- --hostname 0.0.0.0 --port 12205
npm run start -- --hostname 0.0.0.0 --port 12205
```

다음 형태는 쓰지 않는다.

```bash
npm run start --hostname 0.0.0.0 --port 12205
npm run dev --hostname 0.0.0.0 --port 12205
```

Windows Playwright가 붙어야 하는 UI 서버는 WSL에서 `--hostname 0.0.0.0`으로 띄운다. 실제 지도 로딩 e2e는 HMR origin 차단 변수를 줄이기 위해 `npm run build` 후 production `next start` 서버를 우선 사용한다.

### Windows Playwright 실행

Playwright와 실제 브라우저는 Windows에서만 실행한다. WSL에서는 UI 서버만 띄운다.

```bash
# WSL: IP 확인
hostname -I | awk '{print $1}'

# Windows Playwright를 WSL shell에서 호출할 때 검증된 형태
cmd.exe /V:ON /C "cd /d F:\dev\kor-travel-geo-codex\kor-travel-geo-ui && set PLAYWRIGHT_BASE_URL=http://<WSL_IP>:12205&& npx playwright test --config playwright.config.ts --project chromium --workers 1"
```

`set PLAYWRIGHT_BASE_URL=...&&` 뒤에 공백을 넣지 않는다. 공백은 값 끝에 포함될 수 있다. WSL에서 Windows `cmd.exe`를 호출할 때 env var 전달이 흔들리면 이 형태로 고정한다.

### Linux Node/npm 환경

WSL 기본 shell에서 bare `node`가 없을 수 있다. Node가 필요한 명령은 다음 중 하나를 먼저 실행한다.

```bash
source ~/.nvm/nvm.sh
# 또는 테스트 미러 루트에서
source scripts/agent_env.sh
```

runtime config 확인처럼 간단한 one-off Node 명령도 bare `node -e ...`로 시작하지 않는다.

```bash
source ~/.nvm/nvm.sh
node -e "fetch('http://127.0.0.1:12205/api/runtime-config').then(r=>r.json()).then(j=>console.log(Boolean(j.vworldApiKey), String(j.vworldApiKey || '').length))"
```

VWorld 키는 절대 출력하지 않는다. 문서와 로그에는 `nonempty`, `length`처럼 존재 여부만 남긴다.

### 서버 종료

장기 실행 `exec_command` session의 stdin이 닫히면 `Ctrl-C`를 보낼 수 없다. `pkill -f`도 Next.js process name이 `next-server`로 바뀌어 실패할 수 있다. 포트 기준으로 PID를 확인하고 종료한다.

```bash
ss -ltnp | rg ':12205'
kill <PID>
ss -ltnp | rg ':12205' || true
```

작업 종료 전에는 사용한 dev/prod UI 서버가 남아 있지 않은지 확인한다.

### CodeGraph

`codegraph sync`와 `codegraph status`를 병렬로 실행하면 status가 sync 전 상태를 보고 `Pending Changes`를 표시할 수 있다. 순서는 고정한다.

```bash
codegraph sync
codegraph status
codegraph impact RegionsWithinRadiusDebugger
```

`codegraph impact` 인자는 file path가 아니라 symbol 이름이다. 새 컴포넌트 파일 전체 영향도를 보고 싶으면 대표 export symbol 이름을 사용한다.

### generated/stat noise 정리

Next.js 실행 뒤 `kor-travel-geo-ui/next-env.d.ts`가 `.next/types/routes.d.ts`에서 `.next/dev/types/routes.d.ts`로 바뀔 수 있다. 이 파일은 자동 생성 reference이므로 기능 변경으로 보지 않고 tracked 기준으로 되돌린다.

내용 diff 없이 Windows Git status에만 남는 파일은 먼저 `git.exe diff --raw -- <file>`과 `git.exe diff -- <file>`로 실제 변경 여부를 확인한다. 실제 diff가 없으면 index stat만 맞추고 커밋에 넣지 않는다.
