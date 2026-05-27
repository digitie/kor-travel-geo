# 개발 환경 셋업 (WSL ext4 기준)

본 문서는 `python-kraddr-geo`(`kraddr.geo`)를 PC에서 개발할 때 필요한 시스템 의존성과 셋업 순서를 정리한다. WSL ext4에서 작업하고 NTFS의 `data/`를 참조한다는 정책(AGENTS.md, SKILL.md)을 전제로 한다.

## 1. WSL 작업 디렉토리

```bash
mkdir -p ~/dev && cd ~/dev
git clone <repo-url> python-kraddr-geo
cd python-kraddr-geo

# NTFS의 data/를 ext4 작업 디렉토리에서 참조
ln -s /mnt/<drive>/projects/python-kraddr-geo/data data
```

## 1.1 에이전트별 고정 Git worktree

AI 에이전트가 동시에 또는 순차로 작업할 때는 같은 checkout에서 branch를 계속 갈아타지 않는다. 기준 clone(`~/dev/python-kraddr-geo`)은 `main` 동기화와 worktree 관리용으로 두고, 실제 작업은 에이전트별 고정 worktree에서 수행한다.

| 에이전트 | worktree 경로 | idle branch 예시 | 작업 branch 예시 |
|----------|---------------|------------------|------------------|
| ChatGPT Codex | `~/dev/geo-codex` | `agent/codex-worktree` | `agent/codex-t047-benchmark` |
| Claude Code | `~/dev/geo-claude` | `agent/claude-worktree` | `agent/claude-review-fixup` |
| Google Antigravity 2.0 | `~/dev/geo-antigravity` | `agent/antigravity-worktree` | `agent/antigravity-ui-sync` |

최초 1회 생성:

```bash
cd ~/dev/python-kraddr-geo
git fetch origin main
git worktree add ../geo-codex -b agent/codex-worktree origin/main
git worktree add ../geo-claude -b agent/claude-worktree origin/main
git worktree add ../geo-antigravity -b agent/antigravity-worktree origin/main
```

이미 worktree가 있으면 재생성하지 않는다. 새 작업은 해당 에이전트 worktree에서 작업 branch만 새로 딴다.

```bash
cd ~/dev/geo-codex
git status --short                 # 변경사항이 없어야 다음 작업을 시작
git fetch origin main
git switch -c agent/codex-next origin/main
```

사용자가 로컬 `main`을 이미 fast-forward로 맞춘 상태라면 아래 축약형도 가능하다.

```bash
git fetch
git switch -c agent/codex-next main
```

다만 여러 worktree에서 `main` 자체를 checkout하려 하면 Git이 막을 수 있으므로, 자동화와 AI 에이전트에는 `origin/main`을 시작점으로 쓰는 형태를 권장한다. 같은 branch를 두 worktree에서 동시에 checkout하지 말고, branch 이름에는 `agent/codex-*`, `agent/claude-*`, `agent/antigravity-*`처럼 소유자를 넣는다.

## 1.2 CodeGraph 인덱스

CodeGraph는 저장소별 코드 지식 그래프를 `.codegraph/` 디렉터리에 만든다. 이 디렉터리는 로컬 SQLite 인덱스이며 Git에 커밋하지 않는다. `.gitignore`에는 반드시 `.codegraph/`가 포함되어야 한다.

WSL에서 `codegraph`가 없거나 `/mnt/c/Users/.../npm/codegraph` 같은 Windows npm shim을 가리켜 `node: not found`가 나면 Linux용 standalone installer를 사용한다.

```bash
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh
hash -r
codegraph --version
```

각 worktree에서 최초 1회만 초기화한다.

```bash
cd ~/dev/geo-codex
codegraph init -i
```

이후 작업 시작, branch 전환, `git pull`, rebase, merge 뒤에는 재초기화하지 않고 증분 갱신만 수행한다.

```bash
codegraph sync
codegraph status
```

문서 기준으로 `codegraph init -i`는 `.codegraph/`를 만들고 즉시 전체 인덱스를 생성한다. `codegraph sync`는 바뀐 파일만 증분 반영한다. MCP watcher가 켜진 환경에서는 자동 동기화가 되더라도, 이 저장소에서는 branch 전환 직후 수동 `codegraph sync`를 실행해 에이전트가 낡은 인덱스를 보지 않게 한다.

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
- **Playwright/UI 브라우저 테스트**: 사용자 지시에 따라 Playwright는 Windows Node/브라우저 환경에서 실행한다. WSL에서는 백엔드, Node unit/type/build 검증까지만 수행하고, 실제 브라우저 렌더링·screenshot·지도 상호작용 검증은 Windows에서 명령과 screenshot 경로를 함께 기록한다.
- **프론트엔드 WSL 검증 표준화**: `scripts/frontend_check.sh`를 사용하면 Windows `npm`이 PATH에 잡힌 경우 즉시 실패하고 Linux Node/npm에서 `gen:types`, lint, type-check, unit test, build를 순서대로 실행한다. 의존성 재설치가 필요하면 `scripts/frontend_check.sh --install`을 사용한다.
- **NTFS에서 직접 git/pip 실행**: 권한·inotify·심볼릭 링크 모두 손해. 코드/가상환경은 ext4에 두고 결과만 NTFS로 카피(AGENTS.md, SKILL.md §1).
- **GDAL Python 바인딩 버전 미스매치**: `pip install gdal>=3.8`만으로는 시스템과 다른 wheel을 받아 import 시 `undefined symbol`. 위 §3의 핀 절차 필수.
- **`libgdal-dev` 누락**: `gdal-config: command not found`. apt 설치만 하면 해결.

## 7. Windows 재설치 후 복구

Windows 재설치, WSL 초기화, 새 PC 이전 뒤에는 본 문서의 패키지 설치 절차만으로는 충분하지 않다. Git branch/PR 상태, NTFS `data/`, `.env`, Codex 세션 handoff를 함께 복구해야 한다.

자세한 절차는 `docs/windows-reinstall-recovery.md`를 따른다. 특히 PR #13/T-027은 재설치 직후 실제 Docker full-load를 실행하지 말고 `git diff --check`, `bash -n scripts/fullload_test.sh`, 필요 시 `PLAN_ONLY=1 bash scripts/fullload_test.sh` 순서까지만 확인한다.

## 참고

- `docs/geocoding-readiness.md` 0번 체크리스트 — readiness 점검 시 GDAL부터 본다.
- `docs/decisions.md` ADR-005(GDAL Python binding), ADR-008(시스템 GDAL 버전 핀).
- `docs/backend-package.md` §9.2 — `SidoLoader`에서 `gdal.VectorTranslate` 사용.
- `docs/windows-reinstall-recovery.md` — 재설치·새 Codex 세션·PR #13 handoff 복구 절차.
