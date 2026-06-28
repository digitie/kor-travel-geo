# 에이전트 개발 워크플로 런북 — Linux Git/CodeGraph + WSL 테스트 미러

> **목적**: 새 에이전트가 현재 개발 루프를 그대로 따라 할 수 있게 정리한다. 모든 개발 명령은 Linux 환경에서 실행한다(ADR-065). WSL은 허용되는 Linux 환경이며, Windows native `git.exe`/Node/npm/Python/CodeGraph는 표준 경로가 아니다.
>
> 이 문서는 "내가 손에 든 Linux 셸에서 어떤 순서로 무엇을 치면 동작하는가"에 답한다. 배경과 reference는 `docs/dev-environment.md`, 포트는 `docs/ports.md`를 본다.

## 0. 큰 그림

| 위치 | 정체 | 여기서 하는 것 | 여기서 하지 않는 것 |
|------|------|----------------|---------------------|
| **고정 worktree** (에이전트별) | Linux `git` source of truth | 편집, branch, commit, push, PR 준비, CodeGraph sync | `pip install`, `pytest`, `npm`, `uvicorn` 같은 무거운 실행 |
| **WSL ext4 테스트 미러** | 실행 산출물 전용 사본 | 의존성 설치, pytest, ruff/mypy, frontend 검증, 장기 실행 | commit, push, PR |
| **n150 Linux 환경** | 브라우저 e2e 우선 실행지 | Playwright live/mock e2e, 실제 브라우저 검증 | secret 값 문서화 |

- 에이전트별 worktree는 고정 이름이다(ADR-065): Codex=`kor-travel-geo-codex`, Claude=`kor-travel-geo-claude`, Antigravity=`kor-travel-geo-antigravity`.
- 폐기된 옛 방식: `geo-*` worktree 접두사, Windows Git/Windows CodeGraph 포인터, Windows Playwright 우선 실행.
- `/mnt/f/dev/...`처럼 NTFS mount 위의 worktree를 사용할 수는 있지만, Git metadata는 Linux 경로(`/mnt/f/...`)로 repair되어 있어야 한다.
- 대용량 Juso 원천은 `/mnt/f/dev/geodata/juso`가 기준이고, 미러는 `data -> /mnt/f/dev/geodata` symlink로 참조한다.

## 1. 먼저 없애야 할 함정

### (A) Windows npm/node shim이 PATH를 가린다

WSL PATH에 `/mnt/c/Users/.../AppData/Roaming/npm`이 먼저 잡히면 `node: not found`나 UNC 경로 경고가 나고 프론트 검증이 실패한다.

- 프론트 검증은 `scripts/frontend_check.sh`로 실행한다. 이 스크립트는 `npm`이 `/mnt/*`·`*.exe`·`*.cmd`면 즉시 실패시킨다.
- 그 전에 Linux Node를 PATH 앞에 둔다. 예: `source ~/.nvm/nvm.sh`.
- `next dev`/`next start`, lint, type-check, unit test, build, React Doctor는 WSL ext4 미러의 Linux Node/npm에서 한다.

### (B) TMP/TEMP가 Windows Temp를 가리킨다

WSL 셸의 기본 `TMP`/`TEMP`가 `/mnt/c/...`이면 pytest capture가 테스트 시작 전에 실패할 수 있다.

```bash
export TMPDIR=/tmp TMP=/tmp TEMP=/tmp
```

### 한 번에: `source scripts/agent_env.sh`

미러 루트에서 셸을 열면 매번 다음 한 줄로 TMP·venv·Linux Node PATH를 같이 보정한다.

```bash
source scripts/agent_env.sh
```

## 2. 작업 시작

고정 worktree에서 Linux Git 상태를 먼저 확인한다. `.git` 또는 `gitdir`이 `F:/...`를 가리켜 실패하면 main repo에서 repair한다.

```bash
cd /mnt/f/dev/kor-travel-geo-codex
git status --short --branch

# 필요할 때만
cd /mnt/f/dev/kor-travel-geo
git worktree repair /mnt/f/dev/kor-travel-geo-codex
```

새 작업 branch는 최신 `origin/main`에서 만든다.

```bash
cd /mnt/f/dev/kor-travel-geo-codex
git fetch origin main
git switch -c agent/codex-<task> origin/main
codegraph sync
codegraph status
```

`codegraph sync`와 `codegraph status`는 병렬로 실행하지 않는다. sync가 끝난 뒤 status를 본다.

## 3. 테스트 미러 만들기/갱신

고정 worktree 기준으로 ext4 미러를 rsync하고, 대용량 `data/`는 symlink로 잇는다.

```bash
mkdir -p ~/dev/kor-travel-geo-codex-test
rsync -a --delete \
  --exclude .git --exclude .codegraph --exclude .venv \
  --exclude node_modules --exclude kor-travel-geo-ui/.next \
  --exclude data --exclude artifacts \
  /mnt/f/dev/kor-travel-geo-codex/ ~/dev/kor-travel-geo-codex-test/

cd ~/dev/kor-travel-geo-codex-test
test -e data || ln -s /mnt/f/dev/geodata data
uv venv && . .venv/bin/activate
uv pip install -e ".[api,dev]"
source scripts/agent_env.sh
```

T-213처럼 후속 benchmark의 기준 입력이 되는 live run 산출물은 미러 `artifacts/`를 유일한 보관소로 두지 않는다. `docs/t213-data-preservation.md`에 따라 전용 DB/RustFS prefix와 `/mnt/f/dev/geodata/t213-baseline/<run-id>/` 사본으로 보존한다.

## 4. 작업 루프

```
편집/branch/commit/push/PR  ── 고정 worktree (Linux git)
        │   (변경을 미러로 rsync, 미러에서 발견한 수정은 worktree에 다시 반영)
        ▼
검증                         ── WSL ext4 미러
  backend:  pytest -q · ruff check . · mypy src/kortravelgeo scripts/export_openapi.py · lint-imports
  openapi:  python scripts/export_openapi.py --check --output openapi.json
  frontend: scripts/frontend_check.sh
  browser:  n150 Linux Playwright 우선, 불가 시 Windows fallback 사유 기록
        │
        ▼
기록                         ── docs/journal.md(append) + docs/resume.md 갱신
```

검증 명령은 `source scripts/agent_env.sh`를 먼저 했다면 `TMPDIR=...` 접두를 매번 붙일 필요가 없다.

## 5. 프론트엔드 서버와 Playwright

Next.js 서버 옵션은 `--` 뒤에 둔다.

```bash
cd ~/dev/kor-travel-geo-codex-test/kor-travel-geo-ui
source ~/.nvm/nvm.sh
npm run build
npm run start -- --hostname 0.0.0.0 --port 12505
```

다음 형태는 인자가 npm script로 전달되지 않으므로 쓰지 않는다.

```bash
npm run start --hostname 0.0.0.0 --port 12505
npm run dev --hostname 0.0.0.0 --port 12505
```

Playwright와 실제 브라우저 검증은 n150 Linux 환경에서 먼저 수행한다. PR 완료 전 e2e는 Chrome 기준 `chromium` project와 Firefox 기준 `firefox` project를 모두 실행한다. n150에서 실행할 수 없는 경우에만 Windows Playwright를 fallback으로 사용하고, fallback 사유와 명령을 PR 설명 또는 `docs/journal.md`에 남긴다.

```bash
# n150 Linux 예시
cd ~/kor-travel-geo/kor-travel-geo-ui
export LIVE_E2E=1
export PLAYWRIGHT_BASE_URL=http://127.0.0.1:12505
npx playwright test --config playwright.config.ts --project chromium --workers 1 tests/e2e/live
npx playwright test --config playwright.config.ts --project firefox --workers 1 tests/e2e/live
```

VWorld 키는 값 자체를 출력하지 않고 존재 여부와 길이만 확인한다.

```bash
node -e "fetch('http://127.0.0.1:12505/api/runtime-config').then(r=>r.json()).then(j=>console.log('vworld_key_nonempty=' + Boolean(j.vworldApiKey) + ', length=' + String(j.vworldApiKey || '').length))"
```

서버 종료는 포트에서 PID를 찾아 종료한다.

```bash
ss -ltnp | rg ':12505'
kill <PID>
ss -ltnp | rg ':12505' || true
```

## 6. GitHub CLI와 PR

`gh`가 로컬 Git metadata를 읽다가 실패하면 repo를 명시한다. branch/status/commit/push는 Linux `git`으로 수행한다.

```bash
gh pr view <PR_NUMBER> --repo digitie/kor-travel-geo --json number,state,mergeable,statusCheckRollup
gh pr merge <PR_NUMBER> --repo digitie/kor-travel-geo --merge --delete-branch
```

```bash
cd /mnt/f/dev/kor-travel-geo-codex
git add -p
git commit -m "<message>"
git push -u origin HEAD
```

## 7. 붙여넣기용 체크리스트

```bash
# --- 고정 worktree에서 ---
cd /mnt/f/dev/kor-travel-geo-codex
git status --short --branch
git fetch origin main
git switch -c agent/codex-<task> origin/main
codegraph sync
codegraph status
```

```bash
# --- WSL ext4 미러에서 ---
cd ~/dev/kor-travel-geo-codex-test
source scripts/agent_env.sh

pytest -q
ruff check .
mypy src/kortravelgeo scripts/export_openapi.py
lint-imports
python scripts/export_openapi.py --check --output openapi.json
scripts/frontend_check.sh
```

```bash
# --- 고정 worktree에서 ---
git add -p
git commit -m "<message>"
git push -u origin HEAD
```

## 참고

- `docs/dev-environment.md` — 시스템 패키지(GDAL 핀), 미러 rsync exclude 전체, Linux Git/CodeGraph, 알려진 함정.
- `docs/agent-guide.md` — 문서화·재개 프로토콜.
- `docs/ports.md` — 포트 실행 예시.
- `docs/runbooks/agent-failure-patterns.md` — 반복 실패 패턴과 복구.
- `docs/windows-reinstall-recovery.md` / `docs/dev-environment-recovery.md` — 재설치/환경 복구.
