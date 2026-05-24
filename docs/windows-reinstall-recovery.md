# Windows 재설치 후 작업 재개 가이드

본 문서는 Windows 재설치, WSL 초기화, 새 PC 이전 뒤에도 `python-kraddr-geo` 작업을 끊기지 않게 이어가기 위한 복구 절차다. 목표는 새 Codex 세션이나 사람이 `git pull` 후 같은 상태를 재현하고, 실제 `data/juso` 전체 적재 검증을 안전하게 재개할 수 있게 하는 것이다.

현재 PR #13/T-027의 원칙은 **실제 Docker 전체 적재 실행을 멈추고 문서/계획과 preflight만 보강**하는 것이다. 재설치 뒤에도 별도 지시 전까지 Docker DB 생성, 전체 적재, 대용량 COPY, materialized view swap은 실행하지 않는다.

## 1. 영속 상태의 기준

재설치 후 살아남아야 하는 상태는 다음 순서로 남긴다.

| 우선순위 | 저장 위치 | 용도 | 재설치 후 신뢰도 |
|----------|-----------|------|------------------|
| 1 | Git commit + GitHub PR branch | 코드, 문서, 스크립트의 확정 상태 | 가장 높음 |
| 2 | GitHub PR 설명/코멘트 | 리뷰어·에이전트용 진행 상황과 남은 결정 | 높음 |
| 3 | `docs/resume.md`, `docs/journal.md` | 새 세션의 현재 위치와 다음 작업 | 높음 |
| 4 | 로컬 백업의 `data/`, `.env`, API 키 | Git에 넣을 수 없는 입력 데이터와 비밀값 | 백업 방식에 의존 |
| 5 | Codex 로컬 설정·세션 캐시 | 사용자 편의, 커스텀 skill/plugin, 이전 대화 힌트 | 낮음 |

Git과 PR에 들어가지 않은 변경은 재설치 시 사라질 수 있다고 본다. 특히 Codex 대화 내용, 로컬 작업 디렉토리의 미커밋 diff, Docker volume, `.venv`, `node_modules`, `.env`는 Git 복구 대상이 아니다.

## 2. 재설치 전 체크리스트

### 2.1 Git 상태 확정

작업 중인 브랜치에서 먼저 추적 대상 변경을 모두 커밋하고 원격에 푸시한다.

```bash
cd ~/dev/python-kraddr-geo
git status --short --branch
git diff --check

git add <변경한 파일>
git commit -m "..."
git push origin HEAD
```

PR #13 작업 중이라면 기준 브랜치는 다음이다.

```bash
git switch claude/t027-docker-fullload-plan
git pull --ff-only
git push origin claude/t027-docker-fullload-plan
```

`git status --short`에 남은 추적 대상 변경이 없어야 한다. 단, `data/`, `artifacts/`, `web/`처럼 `.gitignore` 대상이거나 의도적으로 추적하지 않는 로컬 산출물은 Git 복구 대상이 아니므로 별도 백업 여부를 판단한다.

### 2.2 Git에 넣지 않는 자료 백업

다음 자료는 저장소에 커밋하지 않는다. Windows 재설치 전에 별도 드라이브, NAS, 암호화된 압축 파일, 비밀번호 관리자, 기관 보안 저장소 중 하나에 백업한다.

| 대상 | 예시 | 백업 이유 |
|------|------|-----------|
| 원천 데이터 | `F:\dev\python-kraddr-geo\data\juso\...` | 저장소에 포함하지 않는 대용량 자료 |
| 환경 파일 | `.env`, `.env.local`, systemd `EnvironmentFile` | DB DSN, API 키, 로컬 경로 |
| API 키 | vworld, juso, epost, 프론트엔드 VWorld WMTS | 평문 커밋 금지 |
| Docker volume dump | `kraddr_geo` 운영/검증 DB가 이미 의미 있는 상태일 때만 | Docker volume은 재설치로 사라질 수 있음 |
| WSL distro export | 재현 비용이 큰 개발 환경 | 패키지/셸 설정을 통째로 보존 |

원천 데이터는 현재 정책상 NTFS의 프로젝트 디렉토리 아래에 둔다. PR #13 기준 실제 검증 대상은 `F:\dev\python-kraddr-geo\data\juso`다. 이 경로가 재설치 대상 디스크와 같은 물리 디스크에 있으면 반드시 외부 매체에 한 번 더 복사한다.

`.env`는 Git에 넣지 않는다. 백업할 때는 파일 권한과 보관 위치를 별도로 관리한다. 재설치 후에는 `.env.example`을 기준으로 새 `.env`를 만들고 필요한 값만 옮긴다.

### 2.3 WSL 전체 백업이 필요할 때

WSL ext4 안의 가상환경, apt 패키지, shell 설정까지 그대로 보존하고 싶으면 Windows PowerShell에서 distro를 export한다.

```powershell
wsl --list --verbose
wsl --shutdown
wsl --export Ubuntu D:\backup\wsl-ubuntu-python-kraddr-geo.tar
```

이 백업은 편의 수단일 뿐, 저장소의 공식 source of truth는 GitHub 원격 브랜치다. export 파일에는 로컬 비밀값이 들어갈 수 있으므로 공유하지 않는다.

### 2.4 PR에 남길 요약

재설치 직전 PR 코멘트에 다음 정보를 남긴다.

- 현재 브랜치와 마지막 commit hash
- 실제 실행한 검증 명령과 결과
- 아직 실행하지 말아야 할 명령
- 로컬 데이터 경로와 기준월
- 다음 사람이 바로 시작할 첫 명령

PR #13의 현재 다음 명령은 전체 적재가 아니라 아래 preflight다.

```bash
PLAN_ONLY=1 bash scripts/fullload_test.sh
```

## 3. 재설치 후 기본 복구 절차

### 3.1 Windows/WSL/Docker 준비

1. Windows에 Git, WSL2, Ubuntu, Docker Desktop 또는 Docker Engine을 설치한다.
2. WSL Ubuntu를 열고 시스템 패키지를 준비한다.
3. 코드는 가능하면 WSL ext4의 `~/dev/python-kraddr-geo`에 둔다.
4. 대용량 `data/`는 NTFS 경로에 복원하고 WSL에서는 절대경로 또는 심볼릭 링크로 접근한다.

```bash
sudo apt update
sudo apt install -y build-essential python3-dev libgdal-dev gdal-bin
gdal-config --version
```

AGENTS.md 정책상 NTFS 마운트에서 직접 `git`/`pip`/`uvicorn`을 실행하지 않는다. 현재 임시 작업 위치가 `/mnt/f/dev/python-kraddr-geo`라면 복구 후 장기 작업은 ext4로 옮기는 것을 우선 검토한다.

### 3.2 저장소 복구

```bash
mkdir -p ~/dev
cd ~/dev
git clone https://github.com/digitie/python-kraddr-geo.git
cd python-kraddr-geo

git fetch --all --prune
git switch --track origin/claude/t027-docker-fullload-plan
git pull --ff-only
```

이미 로컬 브랜치가 있으면 다음처럼 fast-forward만 허용한다.

```bash
git switch claude/t027-docker-fullload-plan
git pull --ff-only
```

`--ff-only`가 실패하면 원격과 로컬이 갈라진 상태다. 이때는 임의로 rebase/reset하지 말고 `git status`, `git log --oneline --decorate --graph --max-count=20 --all` 결과를 확인한 뒤 진행한다.

### 3.3 새 세션에서 반드시 읽을 문서

재설치 후 새 Codex 세션이나 사람이 작업을 이어갈 때는 아래 순서로 읽는다.

1. `AGENTS.md`
2. `README.md`
3. `SKILL.md`
4. `docs/resume.md`
5. `docs/journal.md`의 최신 항목
6. `docs/t027-fullload-plan.md`
7. `docs/windows-reinstall-recovery.md`
8. 관련 ADR이 있는 `docs/decisions.md`

PR #13을 이어갈 때는 특히 `docs/t027-fullload-plan.md`의 실행 금지선, 기준월 분리, 산출물 경로, 중단 기준을 먼저 확인한다.

### 3.4 Python 개발 환경 복구

`uv`를 쓰는 경우:

```bash
cd ~/dev/python-kraddr-geo
uv venv
source .venv/bin/activate

uv pip install -e ".[api,dev]"
GDAL_VER=$(gdal-config --version)
uv pip install "gdal==${GDAL_VER}"
uv pip install -e ".[loaders]"
```

`uv`가 아직 없다면 `python -m venv`와 `pip`로도 복구할 수 있다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[api,dev]"
python -m pip install "gdal==$(gdal-config --version)"
python -m pip install -e ".[loaders]"
```

검증:

```bash
python -c "from osgeo import gdal; print(gdal.__version__)"
python -c "from osgeo import ogr; ogr.UseExceptions(); print('ok')"
```

### 3.5 데이터 경로 복구

NTFS에 백업해 둔 `data/juso`를 복원한다. 예시는 현재 PR #13에서 쓰는 Windows 경로다.

```bash
# WSL에서 Windows F: 드라이브 접근
ls -la /mnt/f/dev/python-kraddr-geo/data/juso
```

ext4 작업 디렉토리에서 `data`를 심볼릭 링크로 둘 수 있다.

```bash
cd ~/dev/python-kraddr-geo
ln -s /mnt/f/dev/python-kraddr-geo/data data
```

링크를 만들지 않는다면 `scripts/fullload_test.sh` 실행 시 `DATA_ROOT`를 절대경로로 넘긴다.

```bash
DATA_ROOT=/mnt/f/dev/python-kraddr-geo/data/juso PLAN_ONLY=1 bash scripts/fullload_test.sh
```

## 4. PR #13/T-027 재개 순서

재설치 직후에는 실제 DB 적재를 실행하지 말고 문서/스크립트 상태부터 확인한다.

```bash
git status --short --branch
git log --oneline --decorate --max-count=5
git diff --check
bash -n scripts/fullload_test.sh
```

그 다음 사용자 또는 리뷰어가 허용한 경우에만 preflight를 실행한다.

```bash
PLAN_ONLY=1 bash scripts/fullload_test.sh
```

`PLAN_ONLY=1`은 경로, 기준월, 필수 파일 존재 여부, Docker project/volume/log 경로 계획을 확인하는 단계다. 이 모드에서도 실제 PostgreSQL 컨테이너 기동, DDL 적용, COPY 적재, 정합성 검증, MV swap은 수행하지 않는다.

전체 적재 실행은 다음 조건이 모두 충족될 때만 진행한다.

- `docs/t027-fullload-plan.md`를 사람 또는 리뷰어가 확인했다.
- `PLAN_ONLY=1` 결과가 PR에 공유됐다.
- Docker volume 이름, 로그 경로, 중단 기준, 재개 기준이 확정됐다.
- `JUSO_YYYYMM`, `LOCSUM_YYYYMM`, `NAVI_YYYYMM` 기준월 불일치 영향을 받아들일지 결정했다.
- 사용자가 명시적으로 실제 Docker full-load 실행을 지시했다.

## 5. Codex 레벨에서 저장할 수 있는 방법

Codex가 재설치 후에도 안정적으로 이어가게 하려면 "Codex 내부 기억"보다 저장소와 PR에 상태를 남기는 방식이 가장 안전하다.

### 5.1 권장: 저장소 안에 상태를 남기기

이 저장소에서 Codex가 우선 읽는 파일은 다음이다.

- `AGENTS.md`: 저장소 전역 지시, DO NOT, 읽을 문서 순서
- `SKILL.md`: 작업 방식, 금지 규칙, 도메인 어휘
- `docs/resume.md`: 현재 진척도와 다음 한 작업
- `docs/journal.md`: 시간순 작업 기록과 검증 결과
- `docs/t027-fullload-plan.md`: PR #13의 실제 전체 적재 계획
- `docs/windows-reinstall-recovery.md`: 재설치 후 복구 절차

Codex 세션에서 중요한 판단이 생기면 `docs/journal.md`와 `docs/resume.md`를 갱신하고 커밋한다. 결정의 성격이 바뀌면 `docs/decisions.md`에 ADR로 남긴다. 이렇게 하면 다른 AI agent나 사람이 GitHub만 보고도 같은 맥락을 복구할 수 있다.

### 5.2 권장: PR 코멘트에 handoff 남기기

PR은 Codex 세션보다 오래 남는 협업 표면이다. 작업 중단 전 PR 코멘트에 아래 형식으로 handoff를 남긴다.

```markdown
재설치/세션 재개용 handoff

- 브랜치: `claude/t027-docker-fullload-plan`
- 마지막 커밋: `<hash>`
- 현재 상태: 문서/계획 보강만 완료, 실제 Docker full-load 미실행
- 검증: `git diff --check`, `bash -n scripts/fullload_test.sh`
- 다음 명령: `PLAN_ONLY=1 bash scripts/fullload_test.sh`
- 금지선: 사용자 명시 전 Docker 컨테이너 기동, 전체 COPY, MV swap 실행 금지
- 참고 문서: `docs/t027-fullload-plan.md`, `docs/windows-reinstall-recovery.md`
```

### 5.3 Codex CLI 세션/프로젝트 복원 명령

Codex CLI는 이전 interactive session을 다시 여는 `resume`과, 기존 세션에서 새 흐름을 분기하는 `fork`를 제공한다. 재설치 전후에는 먼저 설치 상태를 확인한다.

```bash
codex --help
codex doctor --summary
```

`codex --help` 기준으로 Git commit/PR처럼 프로젝트 상태를 명시적으로 저장하는 별도 `save project` 명령은 없다. 프로젝트 단위 복구는 `git clone`/`git switch`로 처리하고, Codex는 `-C <DIR>`로 작업 루트를 지정해 해당 저장소에서 세션을 이어간다.

가장 최근 세션을 같은 프로젝트에서 이어가려면 작업 디렉토리를 명시한다.

```bash
codex resume --last -C ~/dev/python-kraddr-geo
```

작업 디렉토리 필터를 풀고 과거 세션 목록에서 고르려면 다음을 쓴다.

```bash
codex resume --all
```

세션 ID를 알고 있으면 직접 지정할 수 있다.

```bash
codex resume <SESSION_ID> -C ~/dev/python-kraddr-geo
```

기존 세션을 보존한 채 새 갈래에서 이어가려면 `fork`를 쓴다.

```bash
codex fork --last -C ~/dev/python-kraddr-geo
codex fork <SESSION_ID> -C ~/dev/python-kraddr-geo
```

`codex resume`은 로컬 또는 계정에 기록된 이전 session을 여는 명령이지, 프로젝트 상태를 Git처럼 영구 저장하는 명령은 아니다. 프로젝트 복구의 기준은 여전히 Git branch, PR, `docs/resume.md`, `docs/journal.md`다.

Codex Cloud를 쓰는 환경이라면 cloud task 목록과 적용 가능한 diff를 확인할 수 있다. 이 기능은 CLI에서 experimental로 표시될 수 있으므로, 실제 사용 전 `codex cloud --help`와 계정 상태를 확인한다.

```bash
codex cloud list
codex cloud status <TASK_ID>
codex cloud diff <TASK_ID>
codex cloud apply <TASK_ID>
```

### 5.4 가능하지만 보조적: Codex 로컬 디렉토리 백업

Codex Desktop/CLI의 로컬 설정, 캐시, 커스텀 skill/plugin은 `CODEX_HOME` 또는 사용자 홈 아래의 `.codex` 계열 디렉토리에 있을 수 있다. Windows에서는 보통 `%USERPROFILE%\.codex`, WSL/Linux에서는 보통 `~/.codex`를 먼저 확인한다.

Windows 재설치 전에 이 디렉토리를 백업하면 커스텀 skill이나 플러그인 캐시를 일부 복구하는 데 도움이 될 수 있다. 다만 이 위치는 로컬 구현 세부사항에 가깝고, 세션 대화/상태가 완전하게 복구된다고 보장할 수 없다. API 키나 민감 정보가 섞였을 가능성도 있으므로 백업 파일은 외부에 공유하지 않는다.

```powershell
Compress-Archive -Path "$env:USERPROFILE\.codex" -DestinationPath "D:\backup\codex-home.zip"
```

복원할 때는 새 Codex가 만든 디렉토리 구조와 충돌하지 않는지 확인하고, 필요한 skill/plugin만 선택적으로 옮긴다.

```powershell
Expand-Archive -Path "D:\backup\codex-home.zip" -DestinationPath "$env:USERPROFILE\.codex-restored"
```

복원 후에는 `codex doctor --summary`로 설치·인증·설정 상태를 다시 확인한다.

### 5.5 비권장: Codex 대화만 믿기

Codex 대화 기록은 OS 재설치, 앱 재설치, 계정/워크스페이스 변경, 캐시 삭제에 따라 접근성이 달라질 수 있다. 따라서 "중요한 작업 상태"는 대화에만 두지 않는다. 반드시 Git commit, PR 코멘트, `docs/resume.md`, `docs/journal.md` 중 하나에 남긴다.

## 6. 새 Codex 세션에 붙여 넣을 프롬프트

재설치 뒤 새 Codex에게 아래 문장을 그대로 전달하면 안전하게 시작할 수 있다.

```text
이 저장소는 Windows 재설치 후 복구 상태다. AGENTS.md, README.md, SKILL.md, docs/resume.md, docs/journal.md 최신 항목, docs/t027-fullload-plan.md, docs/windows-reinstall-recovery.md를 먼저 읽고 PR #13/T-027을 이어가라. 현재 원칙은 문서/계획 보강과 PLAN_ONLY preflight까지만이며, 내가 명시하기 전까지 Docker 컨테이너 기동, 전체 data/juso 적재, MV swap은 실행하지 마라.
```

필요하면 현재 브랜치도 같이 지정한다.

```text
브랜치는 claude/t027-docker-fullload-plan 이고, PR은 https://github.com/digitie/python-kraddr-geo/pull/13 이다.
```

## 7. 복구 후 첫 검증 명령

문서와 스크립트 수준에서만 확인하려면 다음까지 실행한다.

```bash
git status --short --branch
git diff --check
bash -n scripts/fullload_test.sh
```

사용자가 preflight를 허용하면 다음을 추가한다.

```bash
PLAN_ONLY=1 bash scripts/fullload_test.sh
```

사용자가 실제 전체 적재를 명시하기 전에는 여기서 멈춘다.
