# T-162 런타임 예열 자동화

## 목적

T-162는 API 프로세스 재기동 또는 서빙 MV/database swap 직후 읽기 경로가 차가운 상태에서 p99가 튀는 문제를 줄이기 위한 런타임 예열 경로다. T-146은 적재 직후 maintenance plan/report이며, `pg_prewarm`과 hot query replay 자동화는 이 문서의 범위다.

이 저장소는 PostgreSQL/PostGIS를 직접 재시작하지 않는다. 따라서 T-162는 다음 두 가지를 제공한다.

- API lifespan에서 opt-in 백그라운드 예열 pass를 실행한다.
- 운영자가 재기동 직후 REST benchmark와 예열 이후 REST benchmark를 비교해 p99 비율 gate를 남긴다.

## 구현

`src/kortravelgeo/loaders/runtime_warm.py`는 다음 순서의 report를 만든다.

1. `catalog.available` — `pg_prewarm` extension과 서빙 relation 존재 여부를 읽는다.
2. `buffer.pg_prewarm` — `runtime_warm_prewarm_enabled`가 켜졌고 extension이 있으면 설정된 relation을 `pg_prewarm(..., 'buffer')`로 데운다.
3. `query.geocode_exact` — `mv_geocode_target`의 도로명 exact index/heap page를 상한 있는 probe로 읽는다.
4. `query.search_text` — `mv_geocode_text_search`의 text-search/trigram path를 transaction-local `pg_trgm.similarity_threshold`와 상한 있는 probe로 읽는다.
5. `query.reverse_nearest` — `mv_geocode_target.pt_5179` KNN nearest path를 읽는다.
6. `query.region_radius` — `region_radius_parts` 공간 path를 읽는다.

모든 쿼리 예열은 `LIMIT :sample_limit`과 transaction-local `statement_timeout`을 사용한다. Relation이 없으면 해당 step만 `skipped`로 기록하고, `pg_prewarm` extension이 없으면 buffer 예열만 `skipped`로 둔다. `CREATE EXTENSION`은 실행하지 않는다.

API lifespan의 scheduler는 기본 비활성이다. 켜진 경우에도 `RUNTIME_WARM` PostgreSQL advisory lock을 잡은 worker 하나만 실행한다.

## 설정

| 설정 | 기본값 | 의미 |
|------|--------|------|
| `KTG_RUNTIME_WARM_ON_STARTUP` | `false` | API 시작 직후 예열 pass를 1회 실행한다. |
| `KTG_RUNTIME_WARM_INTERVAL_MINUTES` | `0` | 0보다 크면 주기적으로 예열 pass를 반복한다. |
| `KTG_RUNTIME_WARM_QUERY_LIMIT` | `32` | 쿼리 예열 profile별 대표 probe 상한. |
| `KTG_RUNTIME_WARM_STATEMENT_TIMEOUT_MS` | `30000` | 예열 쿼리 transaction-local timeout. |
| `KTG_RUNTIME_WARM_PREWARM_ENABLED` | `false` | 선택형 `pg_prewarm` 단계를 실행한다. |
| `KTG_RUNTIME_WARM_PREWARM_RELATIONS` | `mv_geocode_target,mv_geocode_text_search,region_radius_parts` | `pg_prewarm` 대상 relation. |

## 수동 실행

계획만 확인:

```bash
python scripts/run_t162_runtime_warm.py --mode plan --output artifacts/perf/t162-runtime-warm-plan/report.json
```

읽기 전용 예열 pass 실행:

```bash
python scripts/run_t162_runtime_warm.py \
  --mode execute \
  --query-limit 32 \
  --output artifacts/perf/t162-runtime-warm-execute/report.json
```

`pg_prewarm`까지 포함:

```bash
python scripts/run_t162_runtime_warm.py \
  --mode execute \
  --prewarm \
  --prewarm-relations mv_geocode_target,mv_geocode_text_search,region_radius_parts \
  --output artifacts/perf/t162-runtime-warm-prewarm/report.json
```

Benchmark artifact로 등록하려면 `--register-artifact`와 `--output`을 함께 쓴다.

## p99 비율 gate

재기동 직후 cold REST run과 예열 pass 이후 REST run은 기존 `scripts/benchmark_api_latency.py`로 같은 corpus/동시성/iteration 조건에서 만든다. 그 뒤 두 `api-report.json`을 비교한다.

```bash
python scripts/evaluate_t162_cold_warm_ratio.py \
  --cold-report artifacts/perf/t162-cold-rest/api-report.json \
  --warm-report artifacts/perf/t162-warm-rest/api-report.json \
  --max-ratio 2.0 \
  --absolute-slack-ms 25 \
  --mode enforce \
  --output artifacts/perf/t162-cold-warm-ratio/ratio-report.json
```

판정 기준은 각 `(group, sql_name, concurrency)`별로 다음 식을 만족하는지다.

```text
cold_p99_ms <= warm_p99_ms * max_ratio + absolute_slack_ms
```

기본 gate는 `max_ratio=2.0`, `absolute_slack_ms=25`다. 실제 운영 기준은 장비와 corpus가 고정된 뒤 더 좁힐 수 있다.

## 검증

- Windows focused unit: `tests/unit/test_t162_runtime_warm.py`, `tests/unit/test_settings.py`
- Ruff: 런타임 예열 source, API lifespan, settings, scripts, tests
- WSL ext4 미러 전체 검증: `pytest -q` 955 passed/54 skipped, Ruff, mypy, `lint-imports`, OpenAPI check 통과
- WSL 읽기 전용 execute smoke: `artifacts/perf/t162-runtime-warm-execute-smoke/report.json`
  - `pg_prewarm` extension 없음 → `buffer.pg_prewarm` skipped
  - `query.geocode_exact`, `query.search_text`, `query.reverse_nearest`, `query.region_radius` 모두 succeeded

## 운영 메모

- `pg_prewarm`은 extension이 이미 설치된 경우에만 호출한다. 설치·재시작·shared_preload 설정 변경은 이 저장소가 수행하지 않는다.
- 시작 시 예열은 readiness를 막지 않는 background task다. 실패해도 API 시작을 실패시키지 않고 report metric을 로그로 남긴다.
- `KTG_RUNTIME_WARM_PREWARM_ENABLED=true`는 shared buffer를 강제로 채우므로, 저사양 장비에서는 먼저 쿼리 예열만 실행해 p99 비율을 확인한다.
