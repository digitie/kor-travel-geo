# 개발 환경 복구 가이드 (Windows 재설치 후)

Windows 재설치/새 PC에서 이 프로젝트를 이어서 작업하기 위한 빠른 순서다. 세션 handoff, Git/PR 기준, Codex `resume`/`fork`를 포함한 상세 절차는 `docs/windows-reinstall-recovery.md`를 우선한다.

재설치 후 DB를 복구하려면 백업에서 restore하거나(ADR-030/036) `scripts/fullload_test.sh`로 다시 적재한다. 전체 적재(T-027)는 이미 완료된 일반 작업이므로 별도 승인 없이 진행할 수 있다.

## 1. WSL2 설치

```powershell
wsl --install -d Ubuntu-24.04
```

## 2. WSL 내 기본 도구 설치

```bash
sudo apt-get update && sudo apt-get install -y \
  git python3.12 python3.12-venv python3-pip \
  gdal-bin libgdal-dev \
  p7zip-full
```

## 3. Docker Desktop 설치

Windows에서 Docker Desktop 설치 후 Settings → Resources → WSL Integration에서 Ubuntu 활성화.
또는 WSL 내에서 직접 Docker CE 설치.

## 4. 레포 클론 + Python 환경

```bash
cd ~
git clone https://github.com/digitie/python-kraddr-geo.git
cd python-kraddr-geo

python3.12 -m venv .venv
source .venv/bin/activate
pip install "gdal==$(gdal-config --version)"
pip install -e ".[api,loaders,dev]"
```

## 5. 데이터 복구

### 원본 데이터 (NTFS main, ADR-041)

NTFS 위의 main 레포가 git source of truth다. 데이터는 레포의 `data/` 디렉터리 아래에 둔다(`data/juso`, `data/backups`, `data/geoip` 등).
Windows 재설치 시 해당 드라이브가 포맷되지 않았다면 데이터는 그대로 있다.

### WSL ext4 테스트 미러 (ADR-041)

장시간 적재/테스트는 일회용 WSL ext4 테스트 미러에서 수행한다. 이 미러는 레포의 `data/`로 symlink를 걸어 데이터를 공유하므로, 미러 자체는 언제든 폐기할 수 있다.
레포 `data/` 아래에 원본이 있으면 작업 사본을 다시 만들 때 그대로 사용한다.

```bash
# 데이터가 레포 data/ 아래에 있는 상태에서 테스트 미러 준비
bash scripts/fullload_test.sh --copy-data
```

### PostgreSQL 데이터 복구

DB 복구는 백업에서 restore하거나(ADR-030/036) 전체 적재를 다시 수행한다.
Docker 컨테이너를 삭제(`docker compose down`)해도 named volume의 DB 데이터는 유지된다.
단, `docker compose down -v`는 named volume까지 삭제하므로 이 경우 restore 또는 재적재가 필요하다.
재적재 소요 시간은 40분~1.5시간이며, 백업이 있으면 restore가 더 빠른 복구 방법이다.

## 6. Docker PostGIS 기동

```bash
cd python-kraddr-geo

# 기동 (격리된 스택이 필요하면 -p <name>을 추가)
docker compose up -d

# 상태 확인
docker compose ps
```

기존 DB 데이터가 남아 있으면 이전 상태로 바로 올라온다.
호스트 PostgreSQL 포트(ADR-040)는 기본 15434다(컨테이너 내부 5432). `docker-compose.yml`은 `KRADDR_GEO_DB_PORT`(기본 15434)를 사용하며, `scripts/fullload_test.sh`는 `KRADDR_GEO_PG_DSN`이 없으면 이 포트 값으로 DSN을 만든다.

기존 DB를 재사용하는 경우 먼저 schema migration을 적용한다.

```bash
docker compose up -d
export KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kraddr_geo
alembic upgrade head
```

`0002_t027_shp_schema_fixups`는 SHP 보조 테이블의 natural key 컬럼과 geometry 타입을 보정한다. `tl_spbd_buld_polygon.bjd_cd`/`rncode_full` generated column 재생성은 기존 row 수에 따라 시간이 걸릴 수 있다. 구 스키마로 `tl_sprd_rw`에 `MULTILINESTRING` 데이터가 들어 있으면 `MULTIPOLYGON`으로 cast할 수 없으므로 migration은 해당 테이블에 non-polygon row가 있는 경우 `tl_sprd_rw`를 먼저 비운 뒤 타입을 바꾼다. 이미 구 스키마로 SHP를 적재했다면 migration 후 `kraddr-geo load shp-all ... --mode full`로 SHP 9개 테이블을 다시 적재한다.

DB를 새로 적재하려면(기존 DB를 버려도 되는 경우) volume을 비우고 다시 적재한다.

```bash
# 기존 DB 초기화
docker compose down -v
docker compose up -d

# 전체 적재 + 검증
bash scripts/fullload_test.sh
```

## 7. 환경변수 (.env)

```bash
cp .env.example .env
# .env에서 API 키 등 시크릿 복원
```

## 디렉터리 구조 요약

```
<repo>/                            # NTFS main — git source of truth (ADR-041)
└── data/                          # 데이터 루트 (레포 아래)
    ├── juso/                      # 행안부 주소DB 원본/작업본
    │   ├── 202603_도로명주소 한글_전체분/
    │   ├── 202604_위치정보요약DB_전체분.zip
    │   ├── 202604_내비게이션용DB_전체분/
    │   └── 도로명주소 전자지도/
    ├── backups/                   # DB 백업 (ADR-030/036)
    └── geoip/                     # GeoIP 데이터

<wsl-test-mirror>/                 # 일회용 WSL ext4 테스트 미러 — data/로 symlink (ADR-041)
```

## 체크리스트

- [ ] WSL2 + Ubuntu 설치
- [ ] Docker Desktop 또는 Docker CE 설치
- [ ] `git clone` + venv + pip install
- [ ] GDAL 설치 확인 (`gdalinfo --version`)
- [ ] 백업에서 DB restore (ADR-030/036) 또는 아래 적재 단계 진행
- [ ] `bash scripts/fullload_test.sh --copy-data` (레포 `data/` → 테스트 미러)
- [ ] `docker compose up -d`
- [ ] `bash scripts/fullload_test.sh` (적재 + 검증)
- [ ] `.env` 시크릿 복원
