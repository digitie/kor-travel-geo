# 개발 환경 복구 가이드 (Windows 재설치 후)

Windows 재설치/새 PC에서 이 프로젝트를 이어서 작업하기 위한 순서.

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

### 원본 데이터 (NTFS)

주소DB 원본은 `F:\dev\python-kraddr-geo\data\juso`에 보관한다.
Windows 재설치 시 F 드라이브가 포맷되지 않았다면 데이터는 그대로 있다.

### ext4 작업 사본 (`~/kraddr-geo-data/`)

WSL ext4 파일시스템 위의 작업 사본은 WSL 재설치 시 소실된다.
NTFS 원본에서 다시 복사:

```bash
bash scripts/fullload_test.sh --copy-data
```

### PostgreSQL 데이터 (`~/kraddr-geo-data/pgdata/`)

DB 데이터는 WSL ext4의 `~/kraddr-geo-data/pgdata/`에 bind mount로 보관한다.
Docker 컨테이너를 삭제(`docker compose down`)해도 이 디렉터리는 유지된다.
단, `docker compose down -v`는 named volume만 삭제하므로 bind mount 디렉터리에는 영향 없다.

WSL 자체를 재설치하면 소실되므로, 전체 적재는 다시 수행해야 한다.
소요 시간은 40분~1.5시간이므로 재적재가 가장 현실적인 복구 방법이다.

## 6. Docker PostGIS 기동

```bash
cd ~/python-kraddr-geo

# 전용 project name 사용 — 다른 compose 프로젝트와 격리
docker compose -p kraddr-geo-t027 up -d

# 상태 확인
docker compose -p kraddr-geo-t027 ps
```

기존 pgdata가 `~/kraddr-geo-data/pgdata/`에 남아 있으면 DB가 이전 상태로 바로 올라온다.
새로 적재하려면:

```bash
# pgdata 초기화
rm -rf ~/kraddr-geo-data/pgdata/*
docker compose -p kraddr-geo-t027 up -d

# 전체 적재
bash scripts/fullload_test.sh
```

## 7. 환경변수 (.env)

```bash
cp .env.example .env
# .env에서 API 키 등 시크릿 복원
```

## 디렉터리 구조 요약

```
~/kraddr-geo-data/                 # WSL ext4 — 성능 최적
├── juso/                          # 주소DB 작업 사본 (NTFS에서 복사)
│   ├── 202603_도로명주소 한글_전체분/
│   ├── 202604_위치정보요약DB_전체분.zip
│   ├── 202604_내비게이션용DB_전체분/
│   └── 도로명주소 전자지도/
├── epost/                         # 우편번호 데이터
└── pgdata/                        # PostgreSQL 데이터 (bind mount)

F:\dev\python-kraddr-geo\data\     # NTFS — 원본 보관
└── juso/                          # 행안부 원본 다운로드
```

## 체크리스트

- [ ] WSL2 + Ubuntu 설치
- [ ] Docker Desktop 또는 Docker CE 설치
- [ ] `git clone` + venv + pip install
- [ ] GDAL 설치 확인 (`gdalinfo --version`)
- [ ] `bash scripts/fullload_test.sh --copy-data` (NTFS → ext4 복사)
- [ ] `docker compose -p kraddr-geo-t027 up -d`
- [ ] `bash scripts/fullload_test.sh` (적재 + 검증)
- [ ] `.env` 시크릿 복원
