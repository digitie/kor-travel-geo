# T-027: 실 데이터 전체 적재 검증 플랜

## 목적

`F:\dev\python-kraddr-geo\data\juso` 아래의 실 주소DB(한글 전체분·위치정보요약·내비게이션·전자지도 SHP)를 WSL Docker PostGIS에 전량 적재하고, 정합성 검증(C1~C10)과 geocode/reverse/search/zipcode 연동 테스트까지 수행한다.

## 전제 조건

| 항목 | 요구사항 |
|---|---|
| OS | Windows + WSL2 (Ubuntu 22.04+) |
| Docker | Docker Desktop 또는 WSL 내 Docker CE |
| 데이터 | `F:\dev\python-kraddr-geo\data\juso\` 아래 아래 파일 필요 |
| GDAL | WSL 내 `gdal-bin`, `libgdal-dev` (SHP 로더용) |
| Python | 3.12+, venv |
| 디스크 | PostGIS 볼륨 최소 20GB 여유 |
| 메모리 | Docker에 4GB+ 할당 권장 |

### 필요 데이터 파일

```
data/juso/
├── 202604_도로명주소 한글_전체분/    # rnaddrkor_*.txt (17개 시도 파일)
│   ├── rnaddrkor_seoul.txt
│   ├── rnaddrkor_busan.txt
│   └── ...
├── 202604_위치정보요약DB_전체분.zip  # entrc_*.txt (ZIP 멤버)
├── 202604_내비게이션용DB_전체분/     # match_build_*.txt + match_rs_entrc.txt
│   ├── match_build_seoul.txt
│   ├── match_rs_entrc.txt
│   └── ...
└── 도로명주소 전자지도/              # SHP (시도별 하위 디렉토리)
    ├── 강원특별자치도/
    ├── 서울특별시/
    └── ...

data/epost/                          # (선택) 사서함·대량배달처
├── zipcode_full.zip
└── bulk_delivery.csv
```

## 실행 순서

### Step 0: 환경 준비

```bash
# WSL 터미널에서
cd /mnt/f/dev/python-kraddr-geo

# PostGIS 컨테이너 기동
docker compose up -d
docker compose ps   # db healthy 확인

# Python 환경
python -m venv .venv
source .venv/bin/activate
sudo apt-get install -y gdal-bin libgdal-dev
pip install "gdal==$(gdal-config --version)"
pip install -e ".[api,loaders,dev]"
```

### Step 1: 전체 적재 실행

```bash
export DATA_DIR=/mnt/f/dev/python-kraddr-geo/data
export YYYYMM=202604          # 데이터 기준월에 맞게 조정
export BATCH_SIZE=10000       # 기본 5000, 메모리 여유 있으면 올려서 속도 향상

bash scripts/fullload_test.sh 2>&1 | tee fullload_$(date +%Y%m%d_%H%M%S).log
```

스크립트가 수행하는 8단계:

| Phase | 내용 | 예상 시간 |
|---|---|---|
| 0 | 데이터 경로 존재 확인 | 즉시 |
| 1 | DDL — 스키마·확장·인덱스 생성 | ~5초 |
| 2 | 텍스트 3종 COPY 적재 (juso 600만+, locsum 600만+, navi 600만+) | **20~40분** |
| 3 | SHP 9 레이어 GDAL 적재 (시도별) | 10~30분 |
| 4 | Pobox + Bulk (선택) | ~1분 |
| 5 | geometry link 해소 + MV refresh | 5~15분 |
| 6 | 테이블별 row count 출력 | 즉시 |
| 7 | C1~C10 정합성 검증 | 3~10분 |
| 8 | geocode/reverse/search/zipcode smoke test | ~3초 |

**총 예상: 40분~1.5시간** (디스크 I/O에 크게 의존)

### Step 2: 결과 확인

#### 기대 row count (202604 전체분 기준 추정)

| 테이블 | 예상 건수 |
|---|---|
| `tl_juso_text` | 6,200,000+ |
| `tl_locsum_entrc` | 6,000,000+ |
| `tl_navi_buld_centroid` | 6,000,000+ |
| `tl_navi_entrc` | 700,000+ |
| `mv_geocode_target` | 6,000,000+ |
| `tl_spbd_buld_polygon` | 6,000,000+ (SHP 적재 시) |

#### C1~C10 정합성

- **C1~C3**: 텍스트-SHP 조인 불일치. 전체분이면 INFO/WARN 수준 허용.
- **C4~C5**: 출입구-polygon 거리. threshold 이내면 OK.
- **C6**: 우편번호-기초구역 불일치. 소수 WARN 허용.
- **C7**: 행정구역-출입구 불일치. 경계 행정동 사례로 소수 발생 가능.
- **C8**: 도로명폴리라인-출입구 인접성. SHP 미적재 시 SKIP.
- **C9**: PNU 형식 오류. 0건이어야 함.
- **C10**: 적재 기준월 불일치. 동일 YYYYMM이면 0건.

severity_max가 **ERROR**이면 적재 데이터 또는 파서에 문제가 있으므로 sample을 확인해야 한다.

### Step 3: 속도 튜닝 항목 (후속)

적재 완료 후 측정할 항목:

```bash
# geocode 벤치마크
python -c "
import asyncio, time
from kraddr.geo.client import AsyncAddressClient

ADDRESSES = [
    '서울특별시 종로구 자하문로 94',
    '부산광역시 해운대구 해운대해변로 264',
    '경기도 성남시 분당구 판교역로 235',
    '대전광역시 유성구 대학로 99',
    '제주특별자치도 제주시 첨단로 242',
]

async def main():
    async with AsyncAddressClient() as c:
        # warmup
        for addr in ADDRESSES:
            await c.geocode(addr)
        # bench
        start = time.perf_counter()
        N = 100
        results = await c.geocode_many(ADDRESSES * (N // len(ADDRESSES)), concurrency=8)
        elapsed = time.perf_counter() - start
        ok = sum(1 for r in results if r.status == 'OK')
        print(f'{ok}/{len(results)} OK, {elapsed:.2f}s, {len(results)/elapsed:.0f} QPS')

asyncio.run(main())
"
```

#### 튜닝 대상 체크리스트

| 영역 | 확인 항목 | 도구 |
|---|---|---|
| **인덱스** | `mv_geocode_target` GiST 히트율, trigram GIN 효율 | `EXPLAIN (ANALYZE, BUFFERS)` |
| **MV** | refresh 소요 시간, swap vs concurrent | `\timing` |
| **Connection pool** | pool_size 10이 충분한지, overflow 빈도 | `pg_stat_activity` |
| **COPY 속도** | batch_size 5000 vs 10000 vs 50000 | `fullload_test.sh` 로그 |
| **쿼리 플랜** | geocode 시 seq scan 여부, 역지오코딩 GiST 활용 | `/admin/explain` |
| **캐시** | geo_cache hit rate, TTL 적정성 | `/admin/cache/metrics` |
| **statement timeout** | 5초 기본값이 실 쿼리에 충분한지 | slow query 로그 |

## docker-compose.yml 튜닝 포인트

현재 설정:
- `shared_buffers=512MB` — 총 메모리의 25% 기준. Docker에 4GB 할당 시 적정.
- `work_mem=64MB` — 정렬/해시 조인용. geocode 쿼리 특성상 충분.
- `maintenance_work_mem=256MB` — COPY/인덱스 빌드 속도에 직결. 메모리 여유 있으면 512MB.
- `max_wal_size=2GB` — 대량 COPY 시 WAL 쓰기 감소.
- `random_page_cost=1.1` — SSD 기준. HDD면 4.0.

## 예상 이슈와 대응

| 이슈 | 증상 | 대응 |
|---|---|---|
| NTFS → WSL I/O 병목 | COPY 적재가 예상보다 2~3배 느림 | `wsl --mount` 또는 WSL ext4 파일시스템으로 데이터 복사 |
| SHP 인코딩 오류 | `UnicodeDecodeError` 또는 깨진 한글 | `ENCODING=CP949` 확인, GDAL ≥ 3.6 확인 |
| PostGIS 확장 누락 | `function ST_Transform does not exist` | `CREATE EXTENSION postgis` 확인 |
| 메모리 부족 | Docker OOM kill | `docker compose` 에서 `deploy.resources.limits.memory` 설정 |
| MV refresh 장시간 | 30분+ 소요 | `--swap` 전략 사용 (기존 MV 유지하며 새로 빌드) |
| C4/C5 ERROR | 출입구-polygon 거리 초과 다수 | SHP 누락 확인, threshold 조정 |
