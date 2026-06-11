# T-055: N150 / Odroid 운영 환경 비교 준비

## 상태

- 상태: 사전작업 구현 완료 (하드웨어 도착 후 실측 대기)
- 대상 브랜치: `codex/t055-n150-odroid-plan`
- 사용자 RFC: 2026-05-27 — "N150 16GB, NVMe 1TB Ubuntu 26.04 환경 검토 odroid 환경과 더불어 함께 검토 예정임."

## 목적

`python-kraddr-geo`는 WSL2 개발 환경에서 동작하지만, 운영 배포는 작은 폼팩터 박스(N150 또는 Odroid)에서 single-host로 돌리는 시나리오를 검토 중이다. 본 task는 두 운영 환경의 envelope과 성능 측정 계획을 미리 문서화하고, 하드웨어 도착 후 실측을 수행한다.

T-055의 이번 PR 범위는 **실측 준비**다. 실제 N150/Odroid 장비가 없으면 full-load/serving 수치를 직접 만들 수 없으므로, 같은 git SHA와 같은 데이터 snapshot에서 반복 가능한 runbook, 시스템 envelope 캡처 스크립트, 산출물 구조를 먼저 고정한다. 장비 도착 뒤의 실측 실행은 후속 `T-063 N150/Odroid 실측 실행`으로 분리한다.

### 후보 환경

| 항목 | N150 박스 | Odroid (H4 Plus 가정) |
|------|-----------|------------------------|
| CPU | Intel N150 (4 cores, x86_64) | Intel N97 또는 N305 |
| RAM | 16 GB DDR5 | 8~32 GB DDR5 |
| Storage | NVMe 1 TB | NVMe 또는 SATA |
| OS | Ubuntu 26.04 LTS | Ubuntu 26.04 또는 Debian 12 |
| 네트워크 | 2.5 GbE | 2.5 GbE |
| 전력 | ~6~12W TDP | ~6~10W TDP |

두 환경 모두 single-host. WSL과 달리 ext4 직접, Docker는 native.

## 이번 PR의 사전 구현

- `scripts/capture_deployment_envelope.py`를 추가했다.
- 기본 실행은 `uname`/`lscpu`/`free`/`lsblk`/`df`/`swapon`/Docker/GDAL/PostgreSQL/fio/sysbench/zstd 버전처럼 부하가 낮은 시스템 정보를 `system-envelope.json`과 `system-envelope.md`로 저장한다.
- `fio`와 `sysbench`는 장비에 부하를 줄 수 있으므로 기본 실행에서는 **명령 계획만 기록**한다. 실제 probe는 `--run-probes`를 명시한 경우에만 실행한다.
- `fio` 기본 probe는 8 KiB random read, `iodepth=32`, `numjobs=4`, `runtime=30s`, `size=1G`, `direct=1`이다. 장비별 NVMe 성능 차이를 보기 위한 시작점이며, 운영 디스크에서 실행하기 전 여유 공간과 마모 정책을 확인한다.
- `sysbench` 기본 probe는 CPU 4 thread 30초, memory 4 thread 30초다.
- `scripts/fullload_test.sh`는 native Linux에서도 `DATA_DIR`, `EXT4_DATA`, `KRADDR_GEO_DB_PORT`, `KRADDR_GEO_PG_DSN` override로 그대로 사용할 수 있음을 runbook에 고정했다.

## 측정 envelope

### 1. Full-load 시간 (T-027 baseline 재현)

목표: WSL 환경에서 측정한 T-027 baseline(3,934초)을 두 환경에서 재현. NVMe random IOPS와 CPU 코어 수의 영향을 분리해 본다.

측정 항목(phase별 wall clock):

- DDL/init-db
- juso text (도로명주소 한글)
- locsum (위치정보요약DB)
- navi (내비게이션용DB)
- shp (도로명주소 전자지도 9 레이어)
- parcel_link (T-038)
- daily delta 1회 적용 (T-028)
- sppn_makarea (T-042)
- MV refresh (CONCURRENTLY vs shadow swap)
- C1~C10 정합성
- data-quality export

기록:

- 같은 git commit SHA (T-055 시점 main).
- 같은 `data/juso` snapshot (NTFS 또는 NAS에서 동기화).
- 1차 기준은 현재 접속 대상과 같은 PostGIS 16+3.5로 고정. PostgreSQL 17 비교는 별도 trial로 분리.
- `/usr/bin/time -v` 출력 + dstat/iostat 1초 간격 sample.

### 2. Serving latency (T-047 corpus 활용)

`scripts/benchmark_query_performance.py`(T-047)를 같은 corpus로 두 환경에서 실행:

- 9 query 군(Q1/Q2/Q3/Q4/Q5/Q6/Q7/Q8/Q11) × 4 concurrency (1, 4, 16, 64) × 30 iterations.
- p50/p90/p95/p99/max + buffer + timeout.
- `EXPLAIN ANALYZE BUFFERS` 1회 추가 기록.

특히:

- N150 4 cores → concurrency 64에서 CPU saturation 정도.
- NVMe random read IOPS → fuzzy geocode `pg_trgm` 인덱스 scan 영향.
- 16 GB RAM → `shared_buffers` 기본값(전체 25%)에서 entire MV가 메모리 hot인지.
- T-061 `mv_geocode_text_search` helper는 6,416,637행 기준 heap 854MiB, index 1,572MiB, total 2,426MiB다. shadow swap 중 temp는 +57 files / +11.67GiB였으므로 N150/Odroid 측정에서는 target MV와 helper MV를 합친 디스크, swap peak temp 여유, GIN index build의 `maintenance_work_mem`/temp spill을 별도 표로 남긴다.

### 3. 백업/복원 (T-046 cycle)

- 대구광역시 부분 DB(83MiB archive) backup + restore: WSL과 비교.
- 전국 26GB DB의 backup 예상 시간(`pg_dump -Fd --jobs=4` 기준).
- `tar.zst` compression CPU 영향.

### 4. 시스템 envelope

- NVMe: `fio --rw=randread --bs=8k --iodepth=32 --numjobs=4 --runtime=30 --size=1G` IOPS.
- CPU: `sysbench cpu --threads=4`, `sysbench memory`.
- ext4 vs btrfs (btrfs는 PostgreSQL 비권장이지만 비교 차원에서 측정).
- swap 또는 zram 활성화 영향.
- NUMA 영향(N150은 single socket이라 NUMA 영향 거의 없음).

### 5. Probe와 benchmark 실행 runbook

아래 명령은 장비별로 `<env>`를 `n150`, `odroid-h4`, `wsl-baseline`처럼 바꿔 실행한다. 같은 날짜의 같은 비교 묶음은 동일한 `RUN_ROOT` 아래에 둔다.

```bash
RUN_ROOT=artifacts/perf/n150-vs-odroid-$(date +%Y%m%d)
ENV_LABEL=n150
DATA_DIR=/data/kraddr-geo-data
mkdir -p "$RUN_ROOT/$ENV_LABEL"
```

시스템 envelope만 먼저 캡처한다. 이 명령은 `fio`/`sysbench` 부하 probe를 실행하지 않는다.

```bash
python scripts/capture_deployment_envelope.py \
  --env-label "$ENV_LABEL" \
  --data-dir "$DATA_DIR" \
  --output-dir "$RUN_ROOT/$ENV_LABEL"
```

장비가 비어 있고 운영 디스크 부하를 허용할 수 있을 때만 probe를 켠다.

```bash
python scripts/capture_deployment_envelope.py \
  --env-label "$ENV_LABEL" \
  --data-dir "$DATA_DIR" \
  --output-dir "$RUN_ROOT/$ENV_LABEL" \
  --run-probes
```

full-load는 먼저 `PLAN_ONLY=1`로 경로와 도구만 확인한다.

```bash
PLAN_ONLY=1 \
DATA_DIR="$DATA_DIR" \
KRADDR_GEO_DB_PORT=5432 \
KRADDR_GEO_PG_DSN=postgresql+psycopg://addr:addr@localhost:5432/kraddr_geo \
bash scripts/fullload_test.sh
```

실행 가능 상태가 확인되면 `/usr/bin/time -v`로 OS envelope를 같이 남긴다.

```bash
/usr/bin/time -v -o "$RUN_ROOT/$ENV_LABEL/fullload-time.txt" \
  bash scripts/fullload_test.sh \
  2>&1 | tee "$RUN_ROOT/$ENV_LABEL/fullload.log"
```

SQL benchmark는 같은 corpus를 생성하거나, 기준 환경에서 만든 corpus를 `--corpus`로 재사용한다.

```bash
python scripts/benchmark_query_performance.py \
  --cases-per-group 100 \
  --iterations 30 \
  --warmup 2 \
  --concurrency 1 \
  --concurrency 4 \
  --concurrency 16 \
  --concurrency 64 \
  --output-dir "$RUN_ROOT/$ENV_LABEL/sql"
```

REST e2e benchmark는 위 SQL benchmark의 `corpus.json`을 입력으로 쓴다. API 서버는 별도 터미널에서 같은 DB를 바라보도록 기동한다.

```bash
uvicorn kraddr.geo.api.app:app --host 127.0.0.1 --port 8888
```

```bash
python scripts/benchmark_api_latency.py \
  --base-url http://127.0.0.1:8888 \
  --corpus "$RUN_ROOT/$ENV_LABEL/sql/corpus.json" \
  --iterations 30 \
  --warmup 2 \
  --concurrency 1 \
  --concurrency 4 \
  --concurrency 16 \
  --concurrency 64 \
  --output-dir "$RUN_ROOT/$ENV_LABEL/rest"
```

MV refresh/swap은 full-load 완료 DB에서 별도 trial로 실행한다.

```bash
python scripts/benchmark_mv_refresh.py \
  --strategy swap \
  --trial-index 1 \
  --cache-warm-hint warm-after-fullload \
  --output "$RUN_ROOT/$ENV_LABEL/mv-refresh-swap-1.json"
```

## PostgreSQL 설정 비교

| 파라미터 | WSL 기본 | N150 권장 | Odroid 권장 |
|----------|----------|------------|--------------|
| `shared_buffers` | 128 MB | 4 GB | 2 GB |
| `effective_cache_size` | 4 GB | 12 GB | 6 GB |
| `work_mem` | 4 MB | 64 MB | 32 MB |
| `maintenance_work_mem` | 64 MB | 1 GB | 512 MB |
| `max_parallel_workers` | 8 | 4 | 2 |
| `max_parallel_workers_per_gather` | 2 | 4 | 2 |
| `random_page_cost` | 4.0 | 1.1 (NVMe) | 1.5 |
| `effective_io_concurrency` | 1 | 200 | 100 |
| `wal_compression` | off | zstd | zstd |
| `checkpoint_timeout` | 5min | 15min | 15min |

모든 값은 측정으로 검증해 docs에 인용. PostgreSQL Tuning Guide + `pgtune` 결과를 시작점으로.

T-055 실측의 1차 비교는 PostGIS 16+3.5 계열을 고정하고, PostgreSQL 17 비교는 별도 trial로만 둔다. 서로 다른 major version 결과를 같은 표의 직접 비교 기준으로 쓰지 않는다.

## 인프라 운영 결정

두 환경 모두 single-host로 두되, PostgreSQL/PostGIS 구동 생명주기는 이 저장소 밖에서 관리한다.

- `data/` 디렉터리는 host bind mount(별도 NVMe 파티션 권장).
- PostgreSQL `unix_socket_directories` host 노출 가능성 검토(애플리케이션 UDS 사용 시 latency 절감).
- `huge_pages = try`로 2MB 페이지 활용 검토.

## 측정 산출물

`artifacts/perf/n150-vs-odroid-<date>/`에 다음 보존:

- `<env>/system-envelope.md`, `<env>/system-envelope.json`: OS/CPU/메모리/NVMe/Docker 버전 + probe 계획/결과.
- `fullload-phases.csv`: phase × env × wall_clock_seconds × max_rss_bytes.
- `<env>/sql/benchmark.json`: T-047 SQL corpus 결과(`scripts/benchmark_query_performance.py` JSON 형식).
- `<env>/rest/benchmark.json`: REST e2e 결과(`scripts/benchmark_api_latency.py` JSON 형식).
- `<env>/mv-refresh-*.json`: MV refresh/swap 결과(`scripts/benchmark_mv_refresh.py` JSON 형식).
- `backup-restore.md`: 두 환경의 backup/restore 시간 + archive 크기.
- `summary.md`: 의사결정 요약 — 어느 환경이 어떤 use case에 적합한가.

## 결정 기준

본 task는 즉시 결정을 내리지 않는다. 측정 완료 후 다음 ADR(가칭 ADR-040)에서:

1. 두 환경의 serving p95/p99가 운영 목표(T-047에서 정의)를 만족하는가.
2. Full-load 시간이 운영 batch window 안에 들어가는가.
3. 백업 archive 크기와 복원 시간이 SLO 안에 있는가.
4. 비용/전력/공간 측면 trade-off.

위 4가지 답을 표로 정리한 뒤 어느 환경을 1차 운영 표준으로 둘지 결정한다.

## 하드웨어 도착 전 작업

도착 전까지 수행 가능한 것은 이번 PR에서 완료했다.

- 본 문서의 측정 envelope/명령/산출물 구조 확정.
- `scripts/capture_deployment_envelope.py`로 시스템 envelope 캡처 자동화.
- `scripts/benchmark_query_performance.py`, `scripts/benchmark_api_latency.py`, `scripts/benchmark_mv_refresh.py`, `scripts/fullload_test.sh`의 실제 이름과 입력/출력 파일을 runbook에 고정.
- Ubuntu 26.04 + Docker PostGIS 16+3.5는 실측 1차 기준으로 고정. native Linux 차이는 장비 도착 뒤 envelope에 기록.
- Docker rootless mode는 1차 기준에서 제외한다. PostgreSQL bind mount, shared memory, I/O 관측이 단순한 rootful Docker Compose를 먼저 재현하고, rootless는 운영 보안 요구가 생기면 별도 trial로 비교한다.

## 검증 기준

- 두 환경에서 T-027 fullload_test.sh 1회 완주(end-to-end).
- T-047 benchmark corpus 1 round (30 iterations × 4 concurrency × 9 query 군).
- 측정 결과 차이가 노이즈가 아님을 보이기 위해 각 환경 최소 3회 재측정 + variance.
- `artifacts/perf/n150-vs-odroid-<date>/`에 raw data + summary 모두 보존.

## 이번 PR 검증

- `ruff check scripts/capture_deployment_envelope.py tests/unit/test_capture_deployment_envelope.py`
- `pytest tests/unit/test_capture_deployment_envelope.py -q` → `5 passed`
- `python scripts/capture_deployment_envelope.py --env-label wsl-smoke --data-dir data --output-dir /tmp/kraddr-t055-envelope-smoke`
- `ruff check .`
- `pytest -q` → `273 passed, 8 skipped`
- `mypy --no-incremental src/kraddr/geo`
- `lint-imports`

## 남은 위험

- N150 박스의 정확한 NVMe 모델(예: Gen4 vs Gen3)이 random IOPS에 영향.
- Odroid 환경의 RAM이 8GB라면 `shared_buffers` 줄어들고 fuzzy query에서 cache miss 증가.
- 두 환경 사이에 동일한 git commit + 동일한 `data/juso` snapshot을 보장해야 비교 가능.
- 측정 시점의 PostgreSQL major version이 다르면 plan 차이가 크다. 같은 major로 고정.
- 운영 배포 결정은 측정 결과뿐 아니라 운영 SLA, 백업/장애 정책, 네트워크 위치(사내망 위치)까지 고려해야 한다.

## 관련 ADR/Task

- T-027: 측정 기준이 되는 final clean load.
- T-047: serving 성능 benchmark corpus.
- T-046: backup/restore cycle 측정에 활용.
- T-053: `/admin/stats`에서 환경별 측정 결과 시각화 가능성.
- T-049: 측정 결과를 `ops.artifacts(artifact_type='perf_report')`에 등록.
