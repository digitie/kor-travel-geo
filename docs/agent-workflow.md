# 에이전트 개발 워크플로 런북 — WSL 코딩/테스트 + NTFS git

> **목적**: NTFS 고정 worktree에서 편집·git을, WSL ext4 미러에서 설치·테스트를 수행하는 **현재 방식**을 새 에이전트(특히 WSL의 Codex)가 그대로 따라할 수 있게 정리한다. 배경·세부는 `docs/dev-environment.md`, git 환경 정책은 `docs/dev-environment.md` §1.1, 포트는 `docs/ports.md`.
>
> 이 문서는 "내가 손에 든 셸에서 어떤 순서로 무엇을 치면 동작하는 개발 루프가 되는가"에 답한다. 사양/이론이 아니라 런북이다.

## 0. 큰 그림 — 두 위치를 절대 헷갈리지 말 것

| 위치 | 정체 | 여기서 하는 것 | 여기서 하지 않는 것 |
|------|------|----------------|---------------------|
| **NTFS 고정 worktree** (에이전트별) | git source of truth | 편집, branch, commit, push, PR | `pip install`, `pytest`, `npm`, `uvicorn` 같은 무거운 실행 |
| **WSL ext4 테스트 미러** | 실행 산출물 전용 사본 | 의존성 설치, pytest, ruff/mypy, frontend 검증, 장기 실행 | commit, push, PR (여기 변경은 worktree로 되가져온다) |

- 에이전트별 worktree는 **고정 이름**이다(ADR-041): Codex=`python-kraddr-geo-codex`, Claude=`python-kraddr-geo-claude`, Antigravity=`python-kraddr-geo-antigravity`. idle branch는 `agent/<agent>-idle`.
- **폐기된 옛 방식**(문서에서 보이면 무시): `geo-*` worktree 접두사, `~/kraddr-geo-data` ext4 데이터 레이아웃, 단일 `~/dev/python-kraddr-geo` ext4 클론. 대용량 `data/`는 NTFS main repo의 `data/`가 기준이고, 미러는 거기에 symlink로 참조한다.
- **NTFS worktree에서 직접 무거운 테스트/설치를 돌리지 않는다.** `/mnt` NTFS는 대량 I/O·파일워치·임시파일 처리에서 반복 문제를 낸다. 그래서 미러가 따로 있다.

## 1. 먼저 없애야 할 두 함정 (이게 매번 발목을 잡는다)

새 에이전트가 가장 자주 헤매는 지점이다. 셋업 첫 단계에서 한 번에 해결한다.

### (A) Windows npm/node shim이 PATH를 가린다
WSL PATH에 `/mnt/c/Users/.../AppData/Roaming/npm`이 먼저 잡히면 `node: not found`나 UNC 경로 경고가 나고, 프론트 검증이 통째로 실패/스킵된다.
- 프론트 검증은 **반드시 `scripts/frontend_check.sh`로** 실행한다. 이 스크립트는 `npm`이 `/mnt/*`·`*.exe`·`*.cmd`면 즉시 `exit 2`로 막아 "Windows npm으로 잘못 돌리는" 사고를 차단한다.
- 그 전에 **Linux Node를 PATH 앞에** 둔다(nvm 또는 로컬 Linux Node 설치). 예: `export PATH=<linux-node-bin>:$PATH`.
- Playwright·실제 브라우저 렌더링·스크린샷은 **Windows Node/브라우저에서만** 한다. WSL headless Chromium은 `libasound.so.2` 등 공유 라이브러리 누락으로 반복 실패한다.

### (B) TMP/TEMP가 Windows Temp를 가리킨다
WSL 셸의 기본 `TMP`/`TEMP`가 `/mnt/c/...`이면 pytest capture가 테스트 시작 전에 `FileNotFoundError`로 죽는다.
- 셸에서 한 번 `export TMPDIR=/tmp TMP=/tmp TEMP=/tmp`.

### 한 번에: `source scripts/agent_env.sh`
미러 루트에서 셸을 열면 매번 다음 한 줄로 (A)·(B)를 같이 해결한다.

```bash
source scripts/agent_env.sh   # TMPDIR=/tmp 고정 + .venv 활성화 + (nvm 있으면) Linux Node 우선 + npm 경고
```

`agent_env.sh`는 현재 셸에만 영향을 준다. Linux npm이 PATH 앞에 없으면 경고를 출력하니, 그때 `export PATH=<linux-node-bin>:$PATH`로 보정한다.

## 2. 셋업 — 미러 만들기/갱신 (세션 시작마다)

NTFS worktree 기준으로 ext4 미러를 rsync하고, 대용량 `data/`는 symlink로 잇는다. (상세·정확한 exclude 목록은 `docs/dev-environment.md` §1.)

```bash
# 1) 미러 디렉터리(예: 홈 아래 ext4 경로)를 만들고 worktree에서 rsync
#    (.git/.codegraph/.venv/node_modules/.next/data는 제외)
mkdir -p <wsl-test-mirror>
rsync -a --delete \
  --exclude .git --exclude .codegraph --exclude .venv \
  --exclude node_modules --exclude kraddr-geo-ui/.next --exclude data \
  <ntfs-worktree>/ <wsl-test-mirror>/

cd <wsl-test-mirror>

# 2) 대용량 data/는 NTFS main repo의 data/를 symlink로 참조 (복사하지 않는다)
test -e data || ln -s <ntfs-main-repo>/data data

# 3) Python 환경 (최초 1회). GDAL 핀 절차는 dev-environment.md §3.
uv venv && . .venv/bin/activate
uv pip install -e ".[api,dev]"        # loaders가 필요하면 dev-environment.md §3의 gdal 핀 절차

# 4) 셸 환경 보정 (매 셸)
source scripts/agent_env.sh
```

> 미러에서 발견한 수정 필요 사항은 **NTFS worktree에 반영**하고, commit/push도 NTFS worktree에서만 한다. 미러는 버려도 되는 실행 사본이다.

## 3. 작업 루프 (편집은 NTFS, 실행은 미러)

```
편집/branch/commit/push/PR  ── NTFS worktree (<ntfs-worktree>)
        │   (변경을 미러로 rsync 또는 같은 파일을 미러에서 편집하지 말 것 — 단방향)
        ▼
검증                         ── WSL ext4 미러 (<wsl-test-mirror>)
  backend:  source scripts/agent_env.sh 후
            pytest -q · ruff check . · mypy src/kraddr/geo scripts/export_openapi.py · lint-imports
  openapi:  python scripts/export_openapi.py --check --output openapi.json
  frontend: scripts/frontend_check.sh        # Linux Node 강제, gen:types→lint→type-check→test→build
  browser:  Playwright/스크린샷은 Windows에서만, 명령·경로를 journal에 기록
        │
        ▼
기록                         ── journal.md(append) + resume.md 갱신 (NTFS worktree)
```

검증 명령은 `source scripts/agent_env.sh`를 먼저 했다면 `TMPDIR=...` 접두를 매번 붙일 필요가 없다. 스니펫을 안 썼다면 각 명령 앞에 `TMPDIR=/tmp TMP=/tmp TEMP=/tmp`를 직접 붙인다.

## 4. git worktree 환경 정책 (Windows Git metadata 기준)

worktree의 `.git` 포인터에는 **만든 환경의 절대경로**가 박힌다(WSL은 `/mnt/...`, Windows 네이티브 git은 `F:/...`). 둘이 섞이면 다른 환경 git이 `fatal: not a git repository`를 내고 `git worktree list`에서 `prunable`로 보인다. 이를 막기 위해 **모든 worktree의 Git metadata는 Windows Git 기준(`F:/dev/...`)으로 통일**한다(`docs/dev-environment.md` §1).

- worktree의 `.git`/`gitdir`은 `F:/dev/...`를 가리킨다. **WSL 편의를 위해 `/mnt/f/...`로 고치지 않는다.**
- WSL에서 worktree에 git 작업(status·branch·commit)이 필요하면 Windows `git.exe`를 쓴다. 예: `"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/python-kraddr-geo-<agent> status -sb`.
- 포인터가 `/mnt/f`로 틀어져 git이 깨지면 Windows에서 `git -C F:/dev/python-kraddr-geo worktree repair F:/dev/python-kraddr-geo-<agent>` 한 번으로 복구한다.
- ⚠️ `git worktree prune`은 **Windows에서만** 실행한다. WSL에서 돌리면 `F:/` 기준의 정상 worktree가 `prunable`로 보여 등록이 삭제될 수 있다.
- 커밋되는 문서/코드에는 절대경로를 넣지 않는다(사용자명·머신 구조 노출). 상대경로나 `<placeholder>`를 쓴다.
- 자주 재발하는 환경/도구 실패 패턴(WSL `git`이 NTFS worktree에서 실패, `exec_command`의 `CreateProcess ... os error 2`, inline rewrite의 escape 손상 등)은 `docs/agent-failure-patterns.md`에 정리돼 있다. 같은 증상이면 프로젝트 버그로 보기 전에 먼저 확인한다.

## 5. 공식 로컬 포트 (ADR-040)

| 표면 | host 포트 | 비고 |
|------|-----------|------|
| PostgreSQL + PostGIS | `15434` | DSN `postgresql+psycopg://addr:addr@localhost:15434/kraddr_geo` |
| FastAPI 백엔드 | `8888` | `uvicorn kraddr.geo.api.app:app --host 127.0.0.1 --port 8888` |
| `kraddr-geo-ui` | `13088` | `npm run dev -- --port 13088`, Playwright base URL도 13088 |

기본 `5432`/`3000`은 다른 프로젝트와 충돌하므로 외부 진입점으로 쓰지 않는다.

## 6. 붙여넣기용 체크리스트

```bash
# --- WSL ext4 미러에서 ---
cd <wsl-test-mirror>
source scripts/agent_env.sh

# backend
pytest -q
ruff check .
mypy src/kraddr/geo scripts/export_openapi.py
lint-imports
python scripts/export_openapi.py --check --output openapi.json

# frontend (Linux Node 강제)
scripts/frontend_check.sh            # 의존성 재설치가 필요하면 --install

# CodeGraph (NTFS는 watcher 비활성 → branch 전환·pull·rebase 뒤 수동)
codegraph sync && codegraph status
```

```bash
# --- NTFS worktree에서 (편집/git) ---
cd <ntfs-worktree>
git fetch origin && git switch -c agent/<agent>-<task> origin/main
# ...편집...
git add -p && git commit && git push -u origin HEAD
```

## 참고

- `docs/dev-environment.md` — 시스템 패키지(GDAL 핀), 미러 rsync exclude 전체, CodeGraph 설치, 알려진 함정 전체.
- `docs/agent-guide.md` — 문서화·재개 프로토콜(이 런북은 그 §B4.1 환경 부분을 구체화한 것).
- `docs/ports.md` — 포트 실행 예시.
- `docs/windows-reinstall-recovery.md` / `docs/dev-environment-recovery.md` — 재설치/환경 복구.
