# Windows 재설치 후 작업 재개 가이드

본 문서는 Windows 재설치, WSL 초기화, 새 PC 이전 뒤에도 `kor-travel-geo` 작업을 끊기지 않게 이어가기 위한 복구 절차다. 목표는 새 세션이나 사람이 `git pull` 후 같은 개발 환경(Git branch/worktree, NTFS `data/`, `.env`, 로컬 DB)을 재현하는 것이다.

T-027 실 데이터 전체 적재는 이미 완료됐다(2026-05-29 클린 재적재, `mv_geocode_target=6,416,642`). 재설치 후 빈 DB가 필요하면 백업 복원(ADR-030/ADR-036) 또는 `scripts/fullload_test.sh` 재실행이 정상적인 운영 절차이며, 별도 금지선이 있는 작업이 아니다.

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
git status --short --branch
git diff --check

git add <변경한 파일>
git commit -m "..."
git push origin HEAD
```

작업 중인 에이전트 worktree에서 idle branch가 최신 `origin/main`과 동기화돼 있는지 확인한다.

```bash
git fetch origin
git switch <작업 branch>
git pull --ff-only
git push origin <작업 branch>
```

`git status --short`에 남은 추적 대상 변경이 없어야 한다. 단, `data/`, `artifacts/`, `web/`처럼 `.gitignore` 대상이거나 의도적으로 추적하지 않는 로컬 산출물은 Git 복구 대상이 아니므로 별도 백업 여부를 판단한다.

### 2.2 Git에 넣지 않는 자료 백업

다음 자료는 저장소에 커밋하지 않는다. Windows 재설치 전에 별도 드라이브, NAS, 암호화된 압축 파일, 비밀번호 관리자, 기관 보안 저장소 중 하나에 백업한다.

| 대상 | 예시 | 백업 이유 |
|------|------|-----------|
| 원천 데이터 | NTFS main repo의 `data/juso/...` | 저장소에 포함하지 않는 대용량 자료 |
| 환경 파일 | `.env`, `.env.local`, systemd `EnvironmentFile` | DB DSN, API 키, 로컬 경로 |
| API 키 | vworld, juso, epost, 프론트엔드 VWorld WMTS | 평문 커밋 금지 |
| DB 백업 아카이브 | T-027 적재 완료 DB의 `pg_dump -Fd` + `tar.zst` (ADR-030/ADR-036) | 재적재 없이 빠르게 복원 |
| WSL distro export | 재현 비용이 큰 개발 환경 | 패키지/셸 설정을 통째로 보존 |

원천 데이터는 현재 정책상 NTFS main repo의 `data/` 아래에 둔다. 이 경로가 재설치 대상 디스크와 같은 물리 디스크에 있으면 반드시 외부 매체에 한 번 더 복사한다. T-027 적재 완료 DB는 `ktgctl backup`으로 만든 아카이브로 백업해 두면 재설치 후 전체 재적재 없이 복원할 수 있다.

`.env`는 Git에 넣지 않는다. 백업할 때는 파일 권한과 보관 위치를 별도로 관리한다. 재설치 후에는 `.env.example`을 기준으로 새 `.env`를 만들고 필요한 값만 옮긴다.

### 2.3 WSL 전체 백업이 필요할 때

WSL ext4 안의 가상환경, apt 패키지, shell 설정까지 그대로 보존하고 싶으면 Windows PowerShell에서 distro를 export한다.

```powershell
wsl --list --verbose
wsl --shutdown
wsl --export Ubuntu D:\backup\wsl-ubuntu-kor-travel-geo.tar
```

이 백업은 편의 수단일 뿐, 저장소의 공식 source of truth는 GitHub 원격 브랜치다. export 파일에는 로컬 비밀값이 들어갈 수 있으므로 공유하지 않는다.

### 2.4 PR에 남길 요약

진행 중인 작업이 있다면 재설치 직전 PR 코멘트에 다음 정보를 남긴다.

- 현재 브랜치와 마지막 commit hash
- 실제 실행한 검증 명령과 결과
- 로컬 데이터 경로와 기준월
- 다음 사람이 바로 시작할 첫 명령

DB 상태를 보존하려면 적재 완료 DB의 백업 아카이브 위치(또는 생성 방법)도 함께 남긴다.

## 3. 재설치 후 기본 복구 절차

### 3.1 Windows/WSL/Docker 준비

1. Windows에 Git, WSL2, Ubuntu, Docker Desktop 또는 Docker Engine을 설치한다.
2. WSL Ubuntu를 열고 시스템 패키지를 준비한다.
3. Git source of truth는 NTFS의 `F:\dev\kor-travel-geo` main repo와 `F:\dev\kor-travel-geo-*` 에이전트 worktree로 복구한다.
4. 테스트와 장기 실행용으로 WSL ext4 테스트 미러(`~/dev/kor-travel-geo-<agent>-test`)를 만들고, NTFS worktree를 `rsync --delete`로 복사해 사용한다.
5. 대용량 `data/`는 NTFS 경로에 복원하고 WSL에서는 절대경로 또는 심볼릭 링크로 접근한다.

```bash
sudo apt update
sudo apt install -y build-essential python3-dev libgdal-dev gdal-bin
gdal-config --version
```

AGENTS.md 정책상 Git 작업은 NTFS worktree에서 수행하고, `pip`/`npm test`/`uvicorn` 같은 테스트·장기 실행은 ext4 테스트 미러에서 수행한다. NTFS main repo를 직접 지우거나 dirty 변경을 되돌리기 전에 worktree와 로컬 secret 파일을 먼저 백업한다.

### 3.2 저장소 복구

```bash
mkdir -p /mnt/f/dev
cd /mnt/f/dev
git clone https://github.com/digitie/kor-travel-geo.git
cd kor-travel-geo

git fetch --all --prune
git worktree add ../kor-travel-geo-codex -b agent/codex-idle origin/main
git worktree add ../kor-travel-geo-claude -b agent/claude-idle origin/main
git worktree add ../kor-travel-geo-antigravity -b agent/antigravity-idle origin/main

cd /mnt/f/dev/kor-travel-geo-claude
git fetch origin
git switch agent/claude-idle
git pull --ff-only
```

이미 작업 branch가 있으면 다음처럼 fast-forward만 허용한다.

```bash
git switch <작업 branch>
git pull --ff-only
```

`--ff-only`가 실패하면 원격과 로컬이 갈라진 상태다. 이때는 임의로 rebase/reset하지 말고 `git status`, `git log --oneline --decorate --graph --max-count=20 --all` 결과를 확인한 뒤 진행한다.

### 3.3 새 세션에서 반드시 읽을 문서

재설치 후 새 세션이나 사람이 작업을 이어갈 때는 아래 순서로 읽는다.

1. `AGENTS.md`
2. `README.md`
3. `SKILL.md`
4. `docs/resume.md`
5. `docs/journal.md`의 최신 항목
6. `docs/dev-environment.md`
7. `docs/windows-reinstall-recovery.md`
8. 관련 ADR이 있는 `docs/decisions.md`

빈 DB를 다시 만들어야 하면 `docs/t027-fullload-plan.md`의 기준월 분리, 산출물 경로, 백업/복원(ADR-030/ADR-036) 절차를 참고한다.

### 3.4 Python 개발 환경 복구

`uv`를 쓰는 경우:

```bash
mkdir -p ~/dev/kor-travel-geo-codex-test
rsync -a --delete --exclude .git --exclude .codegraph --exclude .venv --exclude node_modules --exclude kor-travel-geo-ui/.next --exclude data --exclude artifacts \
  /mnt/f/dev/kor-travel-geo-codex/ ~/dev/kor-travel-geo-codex-test/
cd ~/dev/kor-travel-geo-codex-test
test -e data || ln -s /mnt/f/dev/geodata data

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

NTFS에 백업해 둔 Juso 원천은 공용 데이터 루트 `F:\dev\geodata\juso`로 복원한다. 현재 쓰지 않는 파일은 삭제하지 않고 `F:\dev\geodata\juso\unused\` 아래에 둔다.

```bash
ls -la /mnt/f/dev/geodata/juso
```

ext4 테스트 미러에서 `data`를 심볼릭 링크로 둘 수 있다.

```bash
cd <테스트 미러>
test -e data || ln -s /mnt/f/dev/geodata data
```

링크를 만들지 않는다면 `scripts/fullload_test.sh` 실행 시 `DATA_ROOT`를 절대경로로 넘긴다.

```bash
DATA_ROOT=/mnt/f/dev/geodata/juso bash scripts/fullload_test.sh
```

## 4. 재설치 후 DB 복구 (선택)

T-027 전체 적재는 이미 완료된 상태이므로, 재설치 후 DB가 필요할 때는 보존 강도에 따라 두 경로 중 하나를 쓴다.

먼저 현재 상태를 확인한다.

```bash
git status --short --branch
git log --oneline --decorate --max-count=5
git diff --check
bash -n scripts/fullload_test.sh
```

빠른 복구가 목표면 적재 완료 DB 백업 아카이브를 복원한다(ADR-030/ADR-036).

```bash
ktgctl restore --archive <백업 아카이브 경로>
```

처음부터 다시 적재해 검증까지 하려면 미리 경로/기준월을 확인하고 full-load를 실행한다.

```bash
PLAN_ONLY=1 bash scripts/fullload_test.sh   # 경로·기준월·필수 파일 확인
bash scripts/fullload_test.sh               # 적재+검증
```

`PLAN_ONLY=1`은 경로, 기준월, 필수 파일 존재 여부, compose/volume/log 경로 계획만 확인하는 preflight 단계다. 적재 결과는 `JUSO_YYYYMM`/`LOCSUM_YYYYMM`/`NAVI_YYYYMM` 기준월이 다를 수 있으므로 C10 등 정합성 리포트가 WARN/ERROR를 낼 수 있다(버그 아님). 기준월 분리와 산출물 경로는 `docs/t027-fullload-plan.md`를 참고한다.

## 5. Codex 레벨에서 저장할 수 있는 방법

Codex가 재설치 후에도 안정적으로 이어가게 하려면 "Codex 내부 기억"보다 저장소와 PR에 상태를 남기는 방식이 가장 안전하다.

### 5.1 권장: 저장소 안에 상태를 남기기

이 저장소에서 Codex가 우선 읽는 파일은 다음이다.

- `AGENTS.md`: 저장소 전역 지시, DO NOT, 읽을 문서 순서
- `SKILL.md`: 작업 방식, 금지 규칙, 도메인 어휘
- `docs/resume.md`: 현재 진척도와 다음 한 작업
- `docs/journal.md`: 시간순 작업 기록과 검증 결과
- `docs/t027-fullload-plan.md`: 전체 적재/검증 절차와 기준월 분리
- `docs/windows-reinstall-recovery.md`: 재설치 후 복구 절차

Codex 세션에서 중요한 판단이 생기면 `docs/journal.md`와 `docs/resume.md`를 갱신하고 커밋한다. 결정의 성격이 바뀌면 `docs/decisions.md`에 ADR로 남긴다. 이렇게 하면 다른 AI agent나 사람이 GitHub만 보고도 같은 맥락을 복구할 수 있다.

### 5.2 권장: PR 코멘트에 handoff 남기기

PR은 Codex 세션보다 오래 남는 협업 표면이다. 작업 중단 전 PR 코멘트에 아래 형식으로 handoff를 남긴다.

```markdown
재설치/세션 재개용 handoff

- 브랜치: `<작업 branch>`
- 마지막 커밋: `<hash>`
- 현재 상태: <진행 중 작업 요약>
- 검증: <실행한 명령과 결과>
- 다음 명령: <다음 사람이 바로 시작할 첫 명령>
- DB: T-027 적재 완료. 빈 DB가 필요하면 백업 복원 또는 `scripts/fullload_test.sh`
- 참고 문서: `docs/resume.md`, `docs/windows-reinstall-recovery.md`
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
codex resume --last -C ~/dev/kor-travel-geo
```

작업 디렉토리 필터를 풀고 과거 세션 목록에서 고르려면 다음을 쓴다.

```bash
codex resume --all
```

세션 ID를 알고 있으면 직접 지정할 수 있다.

```bash
codex resume <SESSION_ID> -C ~/dev/kor-travel-geo
```

기존 세션을 보존한 채 새 갈래에서 이어가려면 `fork`를 쓴다.

```bash
codex fork --last -C ~/dev/kor-travel-geo
codex fork <SESSION_ID> -C ~/dev/kor-travel-geo
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

## 6. 새 세션에 붙여 넣을 프롬프트

재설치 뒤 새 세션에게 아래 문장을 그대로 전달하면 안전하게 시작할 수 있다.

```text
이 저장소는 Windows 재설치 후 복구 상태다. AGENTS.md, README.md, SKILL.md, docs/resume.md, docs/journal.md 최신 항목, docs/dev-environment.md, docs/windows-reinstall-recovery.md를 먼저 읽고 개발 환경(Git worktree, NTFS data/, .env, 로컬 DB)을 복구하라. T-027 전체 적재는 이미 완료됐으니, 빈 DB가 필요하면 백업 복원 또는 scripts/fullload_test.sh 재실행으로 정상 처리한다.
```

필요하면 현재 작업 branch도 같이 지정한다.

```text
브랜치는 <작업 branch> 이고, 관련 PR이 있으면 함께 확인한다.
```

## 7. 복구 후 첫 검증 명령

복구가 끝나면 git/스크립트 상태를 먼저 확인한다.

```bash
git status --short --branch
git diff --check
bash -n scripts/fullload_test.sh
```

빈 DB가 필요하면 백업 복원 또는 full-load로 진행한다(§4 참고).
