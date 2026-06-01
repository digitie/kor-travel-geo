# 개발 환경 셋업 (NTFS main + WSL ext4 테스트 미러)

본 문서는 `python-kraddr-geo`(`kraddr.geo`)를 PC에서 개발할 때 필요한 시스템 의존성과 셋업 순서를 정리한다. 현재 정책은 NTFS의 Git checkout을 source of truth로 두고, 테스트와 장기 실행은 WSL ext4 테스트 미러에서 수행하는 방식이다(ADR-041).

## 1. NTFS main repo와 WSL 테스트 미러

Git source of truth는 NTFS main repo다. Windows에서도 같은 파일을 열어 볼 수 있고, Codex/Claude/Antigravity가 각자 고정 worktree를 가진다.

```text
/mnt/f/dev/python-kraddr-geo/                 # NTFS main repo, main 동기화와 worktree 관리
/mnt/f/dev/python-kraddr-geo-codex/           # ChatGPT Codex worktree
/mnt/f/dev/python-kraddr-geo-claude/          # Claude Code worktree
/mnt/f/dev/python-kraddr-geo-antigravity/     # Google Antigravity 2.0 worktree
~/dev/python-kraddr-geo-codex-test/           # WSL ext4 테스트 미러 예시
```

NTFS worktree에서 코드 편집, branch, commit, push, PR을 수행한다. `pip`, `uv`, `npm test`, `next build`, `uvicorn` 같은 의존성 설치·검증·장기 실행은 ext4 테스트 미러에서 수행한다. NTFS worktree에서 장기 실행 테스트를 직접 돌리면 대량 I/O, 파일 감시, 권한 처리에서 반복 문제가 생길 수 있다.

Git metadata는 Windows Git 기준으로 유지한다. NTFS worktree의 `.git` 파일과 main repo `.git/worktrees/*/gitdir`은 `F:/dev/...` 경로를 가리켜야 하며, WSL `git` 편의를 위해 `/mnt/f/...`로 고치지 않는다. WSL 테스트 미러에서 벤치마크나 운영 스크립트가 commit/branch를 기록해야 하면 Windows `git.exe`를 사용한다.

```bash
# WSL에서 Windows Git으로 NTFS worktree 상태 확인
"/mnt/c/Program Files/Git/cmd/git.exe" -C F:/dev/python-kraddr-geo-codex status --short --branch

# 스크립트 Git metadata 수집 경로를 명시할 때
KRADDR_GEO_GIT_REPO=F:/dev/python-kraddr-geo-codex \
  python scripts/capture_deployment_envelope.py --env-label wsl-baseline
```

테스트 미러 갱신 예시:

```bash
mkdir -p ~/dev/python-kraddr-geo-codex-test
rsync -a --delete \
  --exclude .git \
  --exclude .codegraph \
  --exclude .venv \
  --exclude node_modules \
  --exclude kraddr-geo-ui/.next \
  --exclude data \
  /mnt/f/dev/python-kraddr-geo-codex/ \
  ~/dev/python-kraddr-geo-codex-test/
cd ~/dev/python-kraddr-geo-codex-test
test -e data || ln -s /mnt/f/dev/python-kraddr-geo/data data
```

ext4 테스트 미러는 실행 산출물 전용이다. 여기서 발견한 수정 필요 사항은 NTFS worktree에 반영하고, commit/push도 NTFS worktree에서만 수행한다. 대용량 `data/`는 NTFS main repo의 `/mnt/f/dev/python-kraddr-geo/data/`를 기준으로 두며, 테스트 미러에서는 절대경로 또는 심볼릭 링크로 참조한다.

PostgreSQL 검증은 별도 요청이 없으면 T-027 최종 적재 DB를 재사용한다. 이 DB는 `kraddr-geo-t027-final` Docker compose project와 `/home/digitie/kraddr-geo-data/pgdata-final-20260529` pgdata를 사용하며, host port는 공식 DB 포트 `15434`다.

```bash
KRADDR_PGDATA=/home/digitie/kraddr-geo-data/pgdata-final-20260529 \
KRADDR_JUSO_DATA=/home/digitie/kraddr-geo-data/juso \
KRADDR_GEO_DB_PORT=15434 \
  docker compose -p kraddr-geo-t027-final up -d db
```

새 빈 DB 클린 검증은 사용자가 명시적으로 요구할 때만 별도 pgdata와 별도 compose project로 수행한다.

## 1.1 에이전트별 고정 Git worktree

AI 에이전트가 동시에 또는 순차로 작업할 때는 같은 checkout에서 branch를 계속 갈아타지 않는다. 기준 clone(`/mnt/f/dev/python-kraddr-geo`)은 `main` 동기화와 worktree 관리용으로 두고, 실제 작업은 에이전트별 고정 worktree에서 수행한다. `geo-*` 접두사는 더 이상 쓰지 않고 `python-kraddr-geo-*` 접두사로 통일한다.

| 에이전트 | worktree 경로 | idle branch | 작업 branch 예시 |
|----------|---------------|-------------|------------------|
| ChatGPT Codex | `/mnt/f/dev/python-kraddr-geo-codex` | `agent/codex-idle` | `agent/codex-t072-ntfs-worktrees` |
| Claude Code | `/mnt/f/dev/python-kraddr-geo-claude` | `agent/claude-idle` | `agent/claude-review-fixup` |
| Google Antigravity 2.0 | `/mnt/f/dev/python-kraddr-geo-antigravity` | `agent/antigravity-idle` | `agent/antigravity-ui-sync` |

최초 1회 생성:

```bash
cd /mnt/f/dev/python-kraddr-geo
git fetch origin main
git worktree add ../python-kraddr-geo-codex -b agent/codex-idle origin/main
git worktree add ../python-kraddr-geo-claude -b agent/claude-idle origin/main
git worktree add ../python-kraddr-geo-antigravity -b agent/antigravity-idle origin/main
```

이미 worktree가 있으면 재생성하지 않는다. 새 작업은 해당 에이전트 worktree에서 작업 branch만 새로 딴다.

```bash
cd /mnt/f/dev/python-kraddr-geo-codex
git status --short                 # 변경사항이 없어야 다음 작업을 시작
git fetch origin main
git switch -c agent/codex-next origin/main
```

같은 branch를 두 worktree에서 동시에 checkout하지 말고, branch 이름에는 `agent/codex-*`, `agent/claude-*`, `agent/antigravity-*`처럼 소유자를 넣는다. NTFS main repo의 `main`에 미커밋 변경이 있으면 그대로 보존하고, 에이전트 작업은 별도 worktree에서 진행한다.

#### Windows·WSL 혼용 시 worktree 포인터 주의

각 worktree의 `.git` 파일과 `.git/worktrees/<name>/gitdir`에는 worktree를 **만든 환경 기준의 절대경로**가 기록된다. WSL에서 만들면 WSL 마운트 경로가, Windows 네이티브 git에서 만들면 드라이브 경로가 들어간다. 같은 폴더라도 두 환경의 절대경로 표기가 다르므로, 다른 환경의 git으로 같은 worktree를 다루면 `fatal: not a git repository`가 나고 `git worktree list`에는 `prunable`로 표시된다.

이 상태에서 `git worktree prune`을 그대로 돌리면 **살아있는 worktree 등록까지 지워질 수 있으니** 바로 prune하지 않는다. 복구는 실제로 사용할 환경에서 `git worktree repair <worktree 경로>`를 실행해 포인터를 그 환경 기준으로 맞춘다(`.git`과 admin `gitdir` 양방향을 함께 고친다). 정리는 repair로 살아있는 worktree를 먼저 valid 상태로 만든 뒤 prune해, 폴더가 실제로 사라진 등록만 표적 제거한다.

원칙(현재 정책): 각 worktree는 **자기 환경 전용**으로 운용한다. 에이전트 worktree는 한쪽 환경에서만 git을 다루고(예: 어떤 worktree는 Windows 네이티브 git, 다른 worktree는 WSL git), 같은 worktree를 두 환경에서 번갈아 조작하지 않는다. 특히 `git worktree prune`은 **그 worktree를 운용하는 환경에서만** 실행한다. 다른 환경에서 prune하면 정상 worktree가 그 환경 기준으로 `prunable`로 보여 등록이 삭제될 수 있다. 환경을 바꿔야 하면 먼저 `git worktree repair <worktree 경로>`로 포인터를 그 환경 기준으로 맞춘 뒤 사용한다.

### 1.1.1 반복되는 에이전트 실패 패턴

실무에서 자주 재발한 환경/도구 계층 실패는 [`docs/agent-failure-patterns.md`](./agent-failure-patterns.md)에 정리한다. 핵심은 세 가지다.

- NTFS worktree의 Git metadata는 Windows 경로를 가리키므로, `/mnt/f/...`에서 WSL `git`을 쓰지 않는다.
- `exec_command`가 `CreateProcess ... os error 2`를 내면 heredoc, 복잡한 quoting, `workdir`, Windows exe 호출을 의심하고 명령을 단순화한다.
- NTFS 파일을 inline script로 고칠 때는 `\n`, regex backslash, Windows path escape가 자주 깨지므로 수정 직후 해당 줄을 다시 읽어 확인한다.


### 로컬 secret/env 파일

로컬 키와 환경 파일은 Git에 커밋하지 않는다. 새 NTFS worktree를 만들면 다음 파일들을 main repo 또는 기존 worktree에서 같은 상대 경로로 복사한다.

- `.env`
- `kraddr-geo-ui/.env.local`
- `.claude/settings.local.json`
- 필요 시 `backend/.env.local`, `web/.env.local`

`.env*`, `.claude/`, `.codegraph/`는 ignore 대상이어야 한다. API 로컬 포트는 `8888`이므로 `KRADDR_GEO_API_INTERNAL_URL` 예시는 `http://localhost:8888`로 맞춘다.

## 1.2 CodeGraph 인덱스

CodeGraph는 저장소별 코드 지식 그래프를 `.codegraph/` 디렉터리에 만든다. 이 디렉터리는 로컬 SQLite 인덱스이며 Git에 커밋하지 않는다. `.gitignore`에는 반드시 `.codegraph/`가 포함되어야 한다.

WSL에서 `codegraph`가 없거나 `/mnt/c/Users/.../npm/codegraph` 같은 Windows npm shim을 가리켜 `node: not found`가 나면 Linux용 standalone installer를 사용한다.

```bash
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
hash -r
codegraph --version
```

각 NTFS worktree에서 최초 1회만 초기화한다.

```bash
cd /mnt/f/dev/python-kraddr-geo-codex
codegraph init -i
codegraph status
```

NTFS worktree는 WSL2 `/mnt` 경로라 recursive file watch가 비활성화될 수 있다. 따라서 작업 시작, branch 전환, `git pull`, rebase, merge 뒤에는 재초기화하지 않고 다음 명령을 수동으로 실행한다.

```bash
codegraph sync
codegraph status
```

문서 기준으로 `codegraph init -i`는 `.codegraph/`를 만들고 즉시 전체 인덱스를 생성한다. `codegraph sync`는 바뀐 파일만 증분 반영한다. NTFS에서는 watcher에 기대지 말고, 에이전트가 낡은 인덱스를 보지 않도록 branch 전환 직후 수동 `codegraph sync`를 실행한다.

### 1.2.1 Codex MCP 등록

프로젝트 루트에는 CodeGraph MCP stdio 서버 설정을 둔다. 이 설정은 저장소별로 공유 가능한 개발 도구 설정이며, API key나 비밀값을 포함하지 않는다.

```toml
[mcp_servers.codegraph]
enabled = true
command = "codegraph"
args = ["serve", "--mcp"]
```

WSL에서 Linux standalone `codegraph`가 PATH에 잡혀 있으면 위 설정을 우선 사용한다. 순수 Node/npm 환경에서 `@colbymchenry/codegraph` 패키지의 `mcp` 엔트리를 직접 쓰는 팀원은 아래처럼 바꿔도 된다.

```toml
[mcp_servers.codegraph]
enabled = true
command = "npx"
args = ["-y", "@colbymchenry/codegraph", "mcp"]
```

단, WSL에서 Windows npm shim이 먼저 잡히면 `npx`가 UNC 경로 경고를 내거나 WSL 프로젝트 경로를 제대로 넘기지 못할 수 있다. 이 저장소의 기본값은 `codegraph install --print-config codex`가 제안한 `codegraph serve --mcp` 방식이다.

설정을 추가한 뒤에는 Codex Desktop을 재시작해야 MCP 도구가 현재 세션에 노출된다. 재시작 전에도 CLI 명령은 그대로 사용할 수 있다.

### 1.2.2 작업 전 명령과 `codegraph_explore`

CodeGraph 관련 필수 명령은 다음 두 가지다.

```bash
# worktree 최초 1회 인덱싱 초기화
codegraph init -i

# 현재 인덱스 동기화 상태 확인
codegraph status
```

새 branch 생성, pull, rebase, merge 뒤에는 먼저 `codegraph sync`를 실행하고 `codegraph status`로 `Index is up to date` 상태를 확인한다.

`kraddr-geo-ui`의 React 컴포넌트, `components/vworld/*`, 공용 UI primitive, `maplibre-vworld-js` 소비 경계를 바꾸기 전에는 CodeGraph MCP의 `codegraph_explore` 도구를 먼저 호출해 영향도를 평가한다. 최소 확인 범위는 다음과 같다.

- 수정 대상 파일을 import하는 호출자와 page route
- 같은 props/type을 공유하는 컴포넌트
- 관련 unit/component 테스트와 Playwright 시나리오
- `maplibre-vworld-js`로 옮길 수 있는 범용 기능과 이 저장소에 남아야 하는 domain wrapper 기능

MCP가 아직 노출되지 않은 세션에서는 작업 로그에 "MCP 미노출로 CLI 대체"를 남기고, 임시로 `codegraph context <task>` 또는 `codegraph impact <symbol>`를 사용한다. 다음 Codex Desktop 재시작 뒤에는 `codegraph_explore`를 우선 사용한다.

## 1.3 공식 로컬 포트

이 저장소의 PC/WSL 개발 환경은 다음 host 포트를 공식값으로 사용한다. PostgreSQL 기본 포트 `5432`와 Next.js 기본 포트 `3000`은 다른 프로젝트와 충돌하기 쉬우므로 외부 진입점으로 고정하지 않는다.

| 표면 | 공식 host 포트 | 내부 포트 | 비고 |
|------|----------------|-----------|------|
| PostgreSQL + PostGIS | `15434` | `5432` | `docker-compose.yml`의 기본 `KRADDR_GEO_DB_PORT` |
| FastAPI 백엔드 | `8888` | `8888` | `uvicorn kraddr.geo.api.app:app --host 127.0.0.1 --port 8888` |
| `kraddr-geo-ui` | `13088` | `3000` | Docker는 `-p 13088:3000`, local dev는 `npm run dev -- --port 13088` |

상세 실행 예시는 `docs/ports.md`에 둔다.

## 2. 시스템 패키지 (Ubuntu/WSL)

```bash
sudo apt update
sudo apt install -y \
    build-essential python3-dev \
    libgdal-dev gdal-bin            # ← loaders extra가 필요로 함
gdal-config --version    # 예: 3.8.4
```

`gdal-config`는 `libgdal-dev`가 제공하는 CLI 도구로, Python `gdal` 패키지(C++ 확장)가 빌드 시 GDAL 헤더·라이브러리 경로를 찾는 데 사용한다. 이게 PATH에 없으면 `pip install -e ".[loaders]"`가 `gdal-config: command not found`로 실패한다(ADR-005, ADR-008).

## 3. Python 의존성

아래 명령은 NTFS worktree가 아니라 WSL ext4 테스트 미러에서 실행한다.

```bash
uv venv && source .venv/bin/activate

# 기본 + API + dev (loaders 제외)
uv pip install -e ".[api,dev]"

# loaders extra — Python gdal 바인딩을 시스템 GDAL과 정확히 같은 버전으로 핀
GDAL_VER=$(gdal-config --version)
uv pip install "gdal==${GDAL_VER}"     # 시스템 버전과 매치
uv pip install -e ".[loaders]"
```

버전이 어긋나면 `from osgeo import gdal` 시 `ImportError: undefined symbol`이 발생한다. 사양 §3.1의 `gdal>=3.8`은 lower bound일 뿐, **시스템 GDAL 버전에 핀하는 것이 사실상 의무**다.

## 4. 대안 (충돌이 잦으면)

### 4.1 conda/mamba (forge)

```bash
mamba create -n kraddr -c conda-forge python=3.12 gdal geopandas shapely fiona pyogrio
mamba activate kraddr
pip install -e ".[api,loaders,dev]"
```

forge 채널이 시스템 GDAL + Python 바인딩을 동일 버전으로 묶어 배포하므로 매칭 사고가 거의 없다. WSL ext4의 `~/miniforge3/envs/kraddr/`에 두면 venv와 동등하게 작동.

### 4.2 Docker (운영/CI 권장 — ADR-005)

```dockerfile
FROM osgeo/gdal:ubuntu-small-3.8.4
RUN apt-get update && apt-get install -y python3-pip
COPY . /app
WORKDIR /app
RUN pip install -e ".[api,loaders]"
```

운영 표준화는 Docker 이미지로 묶는 것이 가장 안정적(ADR-005 후속 ADR-008).

## 5. 검증

```bash
gdal-config --version          # 시스템 GDAL
python -c "from osgeo import gdal; print(gdal.__version__)"   # 두 값이 같아야 함
python -c "from osgeo import ogr; ogr.UseExceptions(); print('ok')"
```

추가로 ZIP 해제·CP949 디코딩 sanity:

```bash
python -c "
from osgeo import gdal, ogr
gdal.UseExceptions()
ds = gdal.OpenEx('./data/jusoMap/202605/seoul/TL_SPBD_BULD.shp',
                 gdal.OF_VECTOR | gdal.OF_READONLY,
                 open_options=['ENCODING=CP949'])
print(ds.GetLayer(0).GetFeatureCount())
"
```

## 6. 알려진 함정

- **TMP가 Windows Temp를 가리키는 경우**: WSL에서 `TMP=/mnt/c/...`로 셸이 열리면 pytest capture가 `FileNotFoundError`로 실패한다. `TMPDIR=/tmp TMP=/tmp TEMP=/tmp pytest -q`로 Linux `/tmp`를 명시한다(docs/resume.md "알려진 함정").
- **Playwright/UI 브라우저 테스트**: Playwright는 Windows Node/브라우저 환경에서만 실행한다. WSL에서는 `npm run test:e2e`, `npx playwright test`, screenshot, 실제 지도 상호작용 검증을 실행하지 않는다. WSL headless Chromium은 반복적으로 `libasound.so.2` 같은 공유 라이브러리 누락으로 실패하므로, WSL에서는 백엔드 검증과 Node `lint`/`type-check`/unit test/build까지만 수행하고 Windows에서 실행한 명령, 브라우저, screenshot 경로를 기록한다.
- **프론트엔드 WSL 검증 표준화**: `scripts/frontend_check.sh`를 사용하면 Windows `npm`이 PATH에 잡힌 경우 즉시 실패하고 Linux Node/npm에서 `gen:types`, lint, type-check, unit test, build를 순서대로 실행한다. 의존성 재설치가 필요하면 `scripts/frontend_check.sh --install`을 사용한다.
- **NTFS에서 직접 테스트/장기 실행**: Git source of truth는 NTFS worktree지만, `pip`/`npm test`/`uvicorn` 장기 실행은 ext4 테스트 미러에서 수행한다. NTFS worktree는 편집·branch·commit·PR의 기준으로 유지한다(AGENTS.md, SKILL.md §1).
- **GDAL Python 바인딩 버전 미스매치**: `pip install gdal>=3.8`만으로는 시스템과 다른 wheel을 받아 import 시 `undefined symbol`. 위 §3의 핀 절차 필수.
- **`libgdal-dev` 누락**: `gdal-config: command not found`. apt 설치만 하면 해결.

## 7. Windows 재설치 후 복구

Windows 재설치, WSL 초기화, 새 PC 이전 뒤에는 본 문서의 패키지 설치 절차만으로는 충분하지 않다. Git branch/PR 상태, NTFS `data/`, `.env`, Codex 세션 handoff를 함께 복구해야 한다.

자세한 절차는 `docs/windows-reinstall-recovery.md`를 따른다. T-027 실 데이터 전체 적재는 이미 완료된 상태이므로, 재설치 후 빈 DB가 필요하면 적재 완료 DB 백업 복원(ADR-030/ADR-036) 또는 `scripts/fullload_test.sh` 재실행으로 정상 복구한다. 적재 전 `git diff --check`, `bash -n scripts/fullload_test.sh`, `PLAN_ONLY=1 bash scripts/fullload_test.sh`로 경로·기준월을 먼저 확인하면 좋다.

## 참고

- `docs/geocoding-readiness.md` 0번 체크리스트 — readiness 점검 시 GDAL부터 본다.
- `docs/decisions.md` ADR-005(GDAL Python binding), ADR-008(시스템 GDAL 버전 핀).
- `docs/backend-package.md` §9.2 — `SidoLoader`에서 `gdal.VectorTranslate` 사용.
- `docs/windows-reinstall-recovery.md` — 재설치·새 세션 복구 절차(Git worktree, NTFS `data/`, `.env`, DB 백업/복원).
