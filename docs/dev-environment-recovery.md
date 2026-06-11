# 개발 환경 복구 가이드 (Windows 재설치 후)

Windows 재설치/새 PC에서 이 프로젝트를 이어서 작업하기 위한 빠른 순서다. 세션 handoff, Git/PR 기준, Codex `resume`/`fork`를 포함한 상세 절차는 `docs/windows-reinstall-recovery.md`를 우선한다.

재설치 후 DB를 복구하려면 백업에서 restore하거나(ADR-030/036) `scripts/fullload_test.sh`로 다시 적재한다. 단, 이 저장소는 PostgreSQL/PostGIS와 RustFS를 직접 구동하지 않으므로 먼저 이미 동작 중인 DB와 bucket 접속 정보를 확보한다.

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

## 3. 인프라 접속 정보 확인

PostgreSQL/PostGIS와 RustFS는 이 저장소 밖에서 이미 동작 중이어야 한다. 이 프로젝트에는 접속 설정만 저장한다.

```bash
cp .env.example .env
$EDITOR .env
```

필수 확인 값:

- `KRADDR_GEO_PG_DSN`
- `KRADDR_GEO_RUSTFS_ENABLED`
- `KRADDR_GEO_RUSTFS_ENDPOINT_URL`
- `KRADDR_GEO_RUSTFS_BUCKET`
- `KRADDR_GEO_RUSTFS_PREFIX`
- `KRADDR_GEO_RUSTFS_ACCESS_KEY`
- `KRADDR_GEO_RUSTFS_SECRET_KEY`

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
재적재 소요 시간은 40분~1.5시간이며, 백업이 있으면 restore가 더 빠른 복구 방법이다.

## 6. DB 연결과 schema migration

기존 DB를 재사용하는 경우 먼저 schema migration을 적용한다.

```bash
export KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:5432/kraddr_geo
alembic upgrade head
```

`0002_t027_shp_schema_fixups`는 SHP 보조 테이블의 natural key 컬럼과 geometry 타입을 보정한다. `tl_spbd_buld_polygon.bjd_cd`/`rncode_full` generated column 재생성은 기존 row 수에 따라 시간이 걸릴 수 있다. 구 스키마로 `tl_sprd_rw`에 `MULTILINESTRING` 데이터가 들어 있으면 `MULTIPOLYGON`으로 cast할 수 없으므로 migration은 해당 테이블에 non-polygon row가 있는 경우 `tl_sprd_rw`를 먼저 비운 뒤 타입을 바꾼다. 이미 구 스키마로 SHP를 적재했다면 migration 후 `kraddr-geo load shp-all ... --mode full`로 SHP 9개 테이블을 다시 적재한다.

DB를 새로 적재하려면 `KRADDR_GEO_PG_DSN`이 새로 준비된 빈 DB를 가리키게 한 뒤 적재한다.

```bash
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
- [ ] `git clone` + venv + pip install
- [ ] GDAL 설치 확인 (`gdalinfo --version`)
- [ ] 이미 동작 중인 PostgreSQL/PostGIS와 RustFS bucket 접속 정보 확인
- [ ] 백업에서 DB restore (ADR-030/036) 또는 적재 단계 진행
- [ ] `bash scripts/fullload_test.sh --copy-data` (레포 `data/` → 테스트 미러)
- [ ] `bash scripts/fullload_test.sh` (적재 + 검증)
- [ ] `.env` 시크릿 복원
