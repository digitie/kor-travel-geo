# 반복되는 에이전트 실패 패턴과 재발 방지

본 문서는 NTFS source-of-truth + WSL ext4 테스트 미러 정책(ADR-041) 아래에서 AI 에이전트가 자주 부딪히는 **환경/도구 계층 실패**를 정리한다. 여기서 다루는 증상은 대개 프로젝트 코드 버그가 아니라, Git metadata 포인터, Codex `exec_command` 런처, NTFS 파일 편집 경로의 상호작용에서 생긴다.

## 1. 한눈에 보는 분류

| 증상 | 실제 원인 | 1차 대응 |
|------|-----------|-----------|
| `fatal: not a git repository: ... F:/dev/.../.git/worktrees/...` | NTFS worktree의 Git metadata가 Windows 경로를 가리키는데 WSL `git`로 읽음 | NTFS worktree에서는 Windows `git.exe -C F:/...`만 사용 |
| `CreateProcess ... os error 2` 가 셸 진입 전 발생 | `exec_command` 런처가 복잡한 quoting, heredoc, `workdir`, Windows exe 실행 패턴을 안정적으로 못 띄움 | 명령을 단순화하고 `cd ... &&` + 단일 바이너리 패턴으로 재시도 |
| `apply_patch`가 `/mnt/f/...` 파일을 못 찾음 | 현재 세션의 patch helper가 NTFS mount 경로를 일관되게 해석하지 못함 | 작은 범위 치환 명령으로 대체하고 즉시 파일 재확인 |
| `"\n"`, regex backslash가 코드 안에서 깨짐 | inline shell/Python 멀티라인 편집에서 escape가 여러 번 해석됨 | bulk rewrite 대신 line-oriented edit + `sed` 재확인 + lint/type-check 즉시 실행 |

## 2. 패턴 A — NTFS worktree에서 WSL `git` 실패

### 증상

- `git -C /mnt/f/dev/python-kraddr-geo-codex status`가 실패한다.
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
"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/python-kraddr-geo-codex status --short --branch
"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/python-kraddr-geo-codex switch -c agent/codex-next
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
- 특히 `/mnt/f/dev/python-kraddr-geo-codex/...` 아래 파일에서 간헐적으로 발생한다.

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
