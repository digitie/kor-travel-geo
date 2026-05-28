# T-047: 전국 적재 후 쿼리 성능 벤치마크와 튜닝 설계

## 범위

본 문서는 전국 전체 데이터가 적재된 PostgreSQL + PostGIS DB를 대상으로 지오코딩/역지오코딩/검색 쿼리 속도를 반복 측정하고, 병목이 확인되면 인덱스, 쿼리 재작성, 보조 view 또는 materialized view까지 적극 도입하는 성능 튜닝 계획과 실행 결과를 누적한다.

2026-05-27 1차 구현 PR에서는 benchmark harness와 deterministic corpus 저장 형식을 추가하고, T-027 최종 클린 적재 DB에서 발견한 지번 exact lookup 병목을 `idx_mv_jibun_name_exact` 인덱스로 1차 튜닝했다. 더 큰 `standard`/`stress` corpus, 동시성 64, REST API 전체 latency, T-057 region hint 비교는 후속 PR에서 이어간다.

## 2026-05-27 1차 구현 결과

### 추가한 도구

`scripts/benchmark_query_performance.py`를 추가했다. 이 스크립트는 `mv_geocode_target`과 `tl_sppn_makarea`에서 deterministic corpus를 만들거나 기존 corpus JSON을 재사용하고, raw SQL repository의 쿼리 상수를 직접 실행해 다음 artifact를 `artifacts/perf/<run-id>/`에 저장한다.

- `corpus.json`, `corpus-summary.json`
- `benchmark.json`
- `environment.json`
- `summary.md`
- query군별 slow sample `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, SETTINGS)` JSON

단위 테스트는 percentile 계산, warmup 제외 summary, corpus JSON round-trip, CLI parser 기본값을 검증한다.

### T-027 최종 클린 DB 상태

Smoke benchmark는 Docker PostgreSQL `localhost:15432/kraddr_geo`의 T-027 최종 클린 적재 DB에서 수행했다.

| 항목 | 값 |
|------|----:|
| `mv_geocode_target` | 6,416,637 |
| `tl_sppn_makarea` | 24,204 |
| `pt_source=entrance` | 2,906,372 |
| `pt_source=centroid` | 3,496,182 |
| `pg_stat_statements` | 비활성 |

### Trial 001 — 지번 exact name-key 인덱스

초기 smoke run에서 `Q2_PARCEL_EXACT` 단일 샘플의 client latency가 `2830.59ms`였다. `EXPLAIN`은 기존 `idx_mv_jibun(bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno)`를 사용했지만, 지번 주소 parser가 `bjd_cd`를 아직 모르는 상태에서 `si_nm`/`sgg_nm`/`emd_nm 또는 li_nm`으로 조회하므로 선두 컬럼을 타지 못했다. plan의 DB execution time도 `333.417ms`였고, client wall time은 cold I/O/JIT 영향까지 받아 더 컸다.

다음 인덱스를 추가했다.

```sql
CREATE INDEX idx_mv_jibun_name_exact
  ON mv_geocode_target (
    si_nm, sgg_nm, mntn_yn, lnbr_mnnm, lnbr_slno,
    emd_nm, li_nm, pt_source, bd_mgt_sn
  );
```

실제 전국 DB에서 index build time과 size는 다음과 같았다.

| 항목 | 값 |
|------|----:|
| build time | 56.03초 |
| index size | 761 MiB |

같은 corpus를 재사용한 smoke 전후 비교:

| query군 | before client | before plan execution | after client | after plan execution |
|---------|--------------:|----------------------:|-------------:|---------------------:|
| Q2 지번 exact | 2830.59ms | 333.417ms | 5.58ms | 0.100ms |

after plan은 `idx_mv_jibun_name_exact`를 사용했고, `si_nm`/`sgg_nm`/`mntn_yn`/`lnbr_mnnm`/`lnbr_slno`가 `Index Cond`로 들어갔다. `emd_nm = :emd OR li_nm = :emd`는 index scan 뒤 filter로 남지만 후보가 이미 매우 작아 sort 비용은 사실상 사라졌다.

### Post-index small concurrency run

`cases_per_group=5`, `iterations=3`, `warmup=1`, 동시성 `1/4/16`으로 55개 case corpus를 실행했다. 이 run은 `standard`가 아니라 PR 검증용 small benchmark다.

| query군 | conc | samples | errors | p50 ms | p95 ms | p99 ms | max ms |
|---------|-----:|--------:|-------:|-------:|-------:|-------:|-------:|
| Q1 도로명 exact | 1 | 15 | 0 | 3.44 | 4.73 | 5.06 | 5.14 |
| Q1 도로명 exact | 16 | 15 | 0 | 36.05 | 91.81 | 96.50 | 97.67 |
| Q2 지번 exact | 1 | 15 | 0 | 2.91 | 4.65 | 4.74 | 4.76 |
| Q2 지번 exact | 16 | 15 | 0 | 30.41 | 41.85 | 42.77 | 43.00 |
| Q3 fuzzy geocode | 1 | 15 | 0 | 7.36 | 8.29 | 8.30 | 8.31 |
| Q3 fuzzy geocode | 16 | 15 | 0 | 52.00 | 101.30 | 102.17 | 102.39 |
| Q4 통합 search | 1 | 15 | 0 | 8.49 | 10.58 | 10.79 | 10.84 |
| Q4 통합 search | 16 | 15 | 0 | 56.52 | 106.33 | 108.89 | 109.53 |
| Q5 reverse nearest | 1 | 15 | 0 | 3.09 | 4.04 | 4.34 | 4.41 |
| Q5 reverse nearest | 16 | 15 | 0 | 34.15 | 39.42 | 39.71 | 39.79 |
| Q6 reverse radius | 1 | 15 | 0 | 3.23 | 4.93 | 4.94 | 4.94 |
| Q6 reverse radius | 16 | 15 | 0 | 30.50 | 47.00 | 62.38 | 66.23 |
| Q7 zipcode address | 1 | 15 | 0 | 3.41 | 5.10 | 5.60 | 5.72 |
| Q7 zipcode point | 1 | 15 | 0 | 2.95 | 3.47 | 3.63 | 3.67 |
| Q8 no-result road | 1 | 15 | 0 | 3.56 | 5.25 | 5.28 | 5.29 |
| Q11 국가지점번호 reverse | 1 | 15 | 0 | 3.51 | 6.31 | 6.95 | 7.11 |

관찰:

- 단일 동시성 DB p95는 모든 query군이 ADR-031 1차 목표 안에 들어왔다.
- 동시성 16에서는 Q1/Q3/Q4 tail latency가 90~110ms 구간으로 증가했다. 아직 DB p95 목표를 크게 넘지는 않지만, `standard` corpus와 동시성 64에서는 Q3/Q4가 다음 튜닝 후보가 될 가능성이 높다.
- `pg_stat_statements`가 비활성이라 statement aggregate는 수집하지 못했다. 후속 run에서는 extension 활성화 여부 또는 대체 집계 방식을 먼저 확인한다.

### 남은 후속

- `stress` 10,000건 이상 corpus를 만든다.
- REST API end-to-end latency를 측정한다.
- T-057 `sig_cd`/`bjd_cd`/bbox region hint를 같은 harness에 붙여 hint vs no-hint p95/p99를 비교한다.
- Q3/Q4 search/fuzzy는 `UNION ALL` 분리, query split, text-search slim MV 후보를 별도 trial로 검증한다.
- `idx_mv_jibun_name_exact`가 MV refresh/swap, backup profile, disk envelope에 미치는 영향을 다음 full-load 회귀에서 다시 기록한다.

## 2026-05-28 standard corpus 1차 측정

PR #51 머지 후 같은 harness를 최신 `main` 위에서 실행했다. 이 run은 T-047의 `standard` 최소 규모를 처음 충족한 DB-only client wall time 측정이다.

### Corpus와 실행 조건

| 항목 | 값 |
|------|----:|
| run id | `t047-standard-20260528` |
| case count | 1,100 |
| `cases_per_group` | 100 |
| corpus sha256 | `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f` |
| measured iterations | 1 |
| warmup iterations | 1 |
| concurrency | 1, 4, 16, 64 |
| SQLAlchemy pool | 기본값 `pool_size=10`, `max_overflow=5` |
| errors | 0 |
| `pg_stat_statements` | 비활성 |

동시성 1/16/64 p95 핵심:

| query군 | p95 c1 | p95 c16 | p95 c64 |
|---------|-------:|--------:|--------:|
| Q1 도로명 exact | 8.52ms | 27.99ms | 459.16ms |
| Q2 지번 exact | 4.66ms | 24.59ms | 339.66ms |
| Q3 fuzzy geocode | 15.30ms | 41.18ms | 353.92ms |
| Q4 통합 search | 62.12ms | 116.06ms | 421.36ms |
| Q5 reverse nearest | 4.95ms | 27.97ms | 274.55ms |
| Q6 reverse radius | 5.00ms | 28.32ms | 206.62ms |
| Q7 zipcode address | 6.27ms | 25.68ms | 455.22ms |
| Q7 zipcode point | 4.88ms | 28.03ms | 276.14ms |
| Q8 no-result reverse | 4.90ms | 26.52ms | 230.42ms |
| Q8 no-result road | 4.76ms | 27.55ms | 222.18ms |
| Q11 국가지점번호 reverse | 5.16ms | 30.64ms | 167.53ms |

관찰:

- 동시성 1에서는 Q4 통합 search가 가장 느렸지만 p95 `62.12ms`로 ADR-031 DB 목표 `150ms` 안에 있다.
- 동시성 16까지는 모든 query군이 목표 안에 들어왔다.
- 동시성 64에서는 client wall time 기준 Q1/Q2/Q3/Q4/Q5/Q7/Q8 tail이 크게 오른다. 이 run은 기본 pool 최대 15개 connection을 사용하므로 결과에는 DB 실행시간뿐 아니라 pool 대기와 Python scheduling이 섞여 있다.

### Trial 002 — pool-size 64 비교

pool 대기와 DB contention을 분리하기 위해 같은 `corpus.json`을 재사용하고 동시성 64만 `--pool-size 64 --max-overflow 0`으로 다시 실행했다.

| query군 | p95 c64 기본 pool | p95 c64 pool 64 | 해석 |
|---------|------------------:|----------------:|------|
| Q1 도로명 exact | 459.16ms | 371.57ms | pool 대기 일부 감소, 여전히 tail 큼 |
| Q2 지번 exact | 339.66ms | 156.76ms | name-key index + 충분한 pool에서 크게 안정 |
| Q3 fuzzy geocode | 353.92ms | 417.46ms | connection 증가가 CPU/search contention을 키움 |
| Q4 통합 search | 421.36ms | 481.22ms | Q3와 같은 패턴, query split 후보 |
| Q5 reverse nearest | 274.55ms | 250.54ms | 소폭 개선 |
| Q6 reverse radius | 206.62ms | 251.50ms | 약간 악화 |
| Q7 zipcode address | 455.22ms | 374.73ms | pool 대기 일부 감소 |
| Q7 zipcode point | 276.14ms | 280.90ms | 거의 동일 |
| Q8 no-result reverse | 230.42ms | 131.61ms | pool 대기 영향이 컸음 |
| Q8 no-result road | 222.18ms | 122.75ms | pool 대기 영향이 컸음 |
| Q11 국가지점번호 reverse | 167.53ms | 156.74ms | 소폭 개선 |

결론:

- 동시성 64 tail은 단일 원인이 아니다. Q2/Q8은 pool 확대로 확실히 좋아졌지만, Q3/Q4는 오히려 악화되어 DB CPU 또는 trigram 후보 경합을 의심해야 한다.
- 운영 API 기본 pool을 무작정 64로 올리는 것은 적절하지 않다. API worker 수, pool 크기, admission control을 함께 잡고, Q3/Q4는 query split/`UNION ALL`/text-search slim MV를 별도 trial로 봐야 한다.
- 후속 T-047/T-057에서는 REST API e2e latency와 `pg_stat_statements`를 활성화한 DB execution aggregate가 필요하다. 현재 harness의 wall time은 end-to-end DB client 관점이라 pool 대기를 포함한다.

## 2026-05-28 Trial 003 — Q4 search exact preflight

Q4 통합 search의 slow plan은 `rn_nrm % query` trigram branch가 수천~수만 후보를 만든 뒤 recheck/count/sort를 수행하는 형태였다. 예를 들어 `선릉로111길`은 `idx_mv_rn_trgm`의 fuzzy branch에서 16,158 후보가 생겼고, 최종 603행만 남았다. `UNION ALL` 단일 SQL 분리와 `exact_count` CTE 방식은 materialization/count 비용 때문에 유지 기준을 만족하지 못했다.

이번 trial은 저장소 경로를 두 단계로 나눴다.

1. 공백 제거 정규화 query로 `rn_nrm = :query_nrm` 또는 `buld_nm_nrm = :query_nrm` exact preflight를 먼저 실행한다.
2. exact 결과가 하나라도 있으면 그 결과 집합만 반환한다. 이때 page별 `total` 의미가 흔들리지 않는다.
3. exact 결과가 전혀 없을 때만 기존 broad trigram search를 실행한다.

이를 위해 fresh MV SQL과 Alembic migration에 다음 btree 인덱스를 추가했다.

| index | build time | size | 목적 |
|-------|-----------:|-----:|------|
| `idx_mv_rn_nrm_exact` | 120.45초 | 389MiB | 도로명 exact preflight |
| `idx_mv_buld_nm_nrm_exact` | 51.90초 | 316MiB | 건물명 exact preflight |

같은 `standard` corpus의 Q4 100건은 모두 exact preflight만으로 page 1을 채웠다(`min_exact_total=13`, `max_exact_total=1,562`). 같은 샘플 `Q4-search-038`(`퇴계로88나길`)의 DB execution은 broad trigram `42.39ms`에서 exact preflight `0.56ms`로 줄었다. after plan은 `idx_mv_rn_nrm_exact`와 `idx_mv_buld_nm_nrm_exact`의 `BitmapOr`만 사용했다.

전후 p95 비교:

| 조건 | before Q4 p95 | after Q4 p95 | 해석 |
|------|--------------:|-------------:|------|
| default pool, c1 | 62.12ms | 12.23ms | 단일 query path는 크게 개선 |
| default pool, c4 | 70.62ms | 22.39ms | exact preflight가 broad trigram을 우회 |
| default pool, c16 | 116.06ms | 52.27ms | ADR-031 DB 목표 안으로 여유 증가 |
| default pool, c64 | 421.36ms | 622.38ms | pool 최대 15개에서 다른 query군 대기와 섞여 악화, 이 값만으로 SQL 효과를 판단하지 않음 |
| pool 64, c64 | 481.22ms | 295.85ms | pool 대기를 줄이면 동시성 tail도 개선 |

관찰:

- Q4 exact road-name search는 `mv_geocode_text_search` 같은 보조 MV 없이도 1차 목표를 만족한다.
- Q3 fuzzy geocode는 이 PR에서 직접 바뀌지 않았다. pool 64 c64에서는 417.46ms → 302.83ms로 좋아졌지만 run 변동과 DB contention 영향이 섞여 있다. Q3 전용 후보 축소는 T-057 region hint 또는 별도 text-search slim MV에서 다시 본다.
- default pool c64는 query 자체보다 connection pool 대기, Python scheduling, 다른 query군의 broad path가 더 크게 보인다. REST e2e benchmark와 admission control/pool sizing은 후속으로 남긴다.

## 2026-05-28 관측성 benchmark 보강

PR #51/#52 후속 액션 중 `pg_stat_statements`와 pool wait/DB execution 분리를 먼저 harness에 반영했다.

반영 내용:

- `benchmark.json` schema version을 2로 올렸다.
- measurement row에 `checkout_ms`와 `execute_ms`를 추가했다. `checkout_ms`는 `engine.connect()` 획득 시간이고, `execute_ms`는 transaction 시작, `SET LOCAL`, SQL 실행, fetch까지 포함한다.
- summary row에 `p95_checkout_ms`, `p95_execute_ms`를 추가했다.
- `pg-stat-statements-before.json`, `pg-stat-statements-after.json`, `pg-stat-statements-delta.json`을 저장한다.
- `--reset-pg-stat-statements` 옵션은 corpus/environment capture 후 실제 측정 전에 `pg_stat_statements_reset()`을 시도한다.
- `docker-compose.yml`은 fresh Docker DB에서 `shared_preload_libraries=pg_stat_statements`, `pg_stat_statements.track=all`, `pg_stat_statements.max=10000`을 사용한다.
- fresh schema와 Alembic `0011_t047_pg_stat_statements`는 `pg_stat_statements` extension을 `x_extension` schema에 만든다.

검증 smoke:

| 항목 | 값 |
|------|----|
| DB | `postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo` |
| corpus | fresh `cases_per_group=1` |
| run | `iterations=1`, `warmup=0`, `concurrency=1`, `explain=0` |
| row count | `mv_geocode_target=6,416,637`, `tl_sppn_makarea=24,204` |
| 결과 | 11개 query군 error 0 |
| artifact | `artifacts/perf/t047-observability-smoke-20260528` |

현재 기존 T-027 DB는 extension이 아직 설치되지 않아 `pg_stat_statements=false`이고, snapshot artifact는 `available=false`, `error=pg_stat_statements extension is not installed`를 기록했다. 이 결과는 harness 실패가 아니라 기존 DB가 새 Docker/PostgreSQL 설정을 아직 받지 않은 상태라는 의미다. 이후 active observability run에서 DB restart와 extension 활성화를 완료했다.

## 2026-05-28 active observability run

`kraddr-geo-t027-db-1` 컨테이너를 새 `shared_preload_libraries=pg_stat_statements` 설정으로 재생성하고, `x_extension.pg_stat_statements` extension을 활성화했다. 기존 T-027 DB는 수동 full-load DB라 `alembic_version` table이 없었다. `alembic upgrade head`를 그대로 실행하면 Alembic 기본 `version_num varchar(32)`에 33자 revision ID `0005_t039_roadaddr_entrance_table`가 들어가지 않아 실패하므로, revision ID를 `0005_t039_roadaddr_entrc`로 줄이고 길이 회귀 테스트를 추가했다. 실측 DB는 이미 스키마 객체가 존재하는 상태라 extension 생성 후 `alembic stamp head`로 현재 상태를 기록했다.

측정 corpus:

| 항목 | 값 |
|------|----|
| corpus | `artifacts/perf/t047-search-exact-split-20260528/corpus.json` |
| SHA-256 | `ef460f8fbddaddfc4a0318009beeac3b9ff093f55b7d14a45aec163eb40e798f` |
| case count | 1,100 |
| row count | `mv_geocode_target=6,416,637`, `tl_sppn_makarea=24,204` |
| artifact | `artifacts/perf/t047-active-observability-20260528` |

기본 pool(`pool_size=10`, `max_overflow=5`)은 `iterations=3`, `warmup=1`, concurrency `1/4/16/64`로 실행했다. 총 measurement는 17,600건이고 error는 0이다. `pg_stat_statements` before/after/delta는 모두 `available=true`였다.

핵심 p95:

| query군 | c1 p95 | c16 p95 | c64 p95 | c64 checkout p95 | c64 execute p95 |
|---------|-------:|--------:|--------:|-----------------:|----------------:|
| Q1 도로명 exact | 6.82ms | 30.62ms | 309.46ms | 281.94ms | 22.42ms |
| Q2 지번 exact | 4.26ms | 24.72ms | 268.38ms | 253.04ms | 18.30ms |
| Q3 fuzzy | 11.56ms | 40.23ms | 367.02ms | 340.12ms | 33.00ms |
| Q4 search | 8.31ms | 35.56ms | 330.80ms | 307.88ms | 28.09ms |
| Q5 reverse nearest | 4.52ms | 24.55ms | 258.52ms | 240.72ms | 16.94ms |
| Q7 zipcode address | 4.38ms | 28.06ms | 331.87ms | 313.08ms | 19.19ms |
| Q8 no-result road | 4.20ms | 22.60ms | 196.80ms | 179.81ms | 16.30ms |

해석:

- 기본 pool c64 tail은 대부분 connection checkout 대기다. Q4 search는 p95 330.80ms 중 checkout p95 307.88ms, execute p95 28.09ms였다.
- c16까지는 checkout p95가 8ms 안팎이고 execute p95도 Q3/Q4만 25~30ms 수준이라, 단일 worker/기본 pool에서 ADR-031 DB p95 목표에 여유가 있다.
- `pg_stat_statements` delta top은 Q3 fuzzy road query가 총 execution 8,529.06ms/1,600 calls로 가장 크고, Q1 road exact 2,872.67ms/1,600 calls, Q4 search exact 1,907.99ms/1,600 calls 순이었다.

pool 64 비교:

| query군 | 기본 pool c64 p95 | pool64 c64 p95 | pool64 checkout p95 | pool64 execute p95 |
|---------|------------------:|---------------:|--------------------:|-------------------:|
| Q1 도로명 exact | 309.46ms | 150.06ms | 28.07ms | 112.98ms |
| Q2 지번 exact | 268.38ms | 98.32ms | 17.32ms | 68.63ms |
| Q3 fuzzy | 367.02ms | 167.87ms | 28.12ms | 128.72ms |
| Q4 search | 330.80ms | 162.50ms | 28.12ms | 128.11ms |
| Q5 reverse nearest | 258.52ms | 90.26ms | 17.68ms | 62.32ms |
| Q7 zipcode address | 331.87ms | 146.93ms | 28.05ms | 113.08ms |
| Q8 no-result road | 196.80ms | 94.78ms | 17.05ms | 67.80ms |

pool 64는 checkout 대기를 크게 줄였지만, c64에서 DB execute p95가 60~129ms로 커졌다. 운영 기본 pool을 단순히 64로 키우는 것보다 API worker 수, admission control, pool size를 함께 잡고 Q3/Q4 후보 폭을 줄이는 것이 다음 순서다.

## 2026-05-28 T-047 인덱스 운영 영향 측정

T-047에서 추가된 exact btree index 3개가 MV refresh/swap, 디스크, 백업 단계에 미치는 영향을 측정했다.

전제:

- DB: `postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo`
- row count: `mv_geocode_target=6,416,637`
- 측정 artifact: `artifacts/perf/t047-operational-impact-20260528`
- 장기 MV 작업은 `KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000`으로 실행했다.
- 첫 `swap` 시도는 기본 statement timeout 5초에 걸려 실패했다. `mv_geocode_target_next`/`mv_geocode_target_old`는 남지 않았고, 기존 live MV row count는 유지됐다.

MV 크기와 인덱스:

| 항목 | 크기 |
|------|-----:|
| DB 전체 | 31.90GiB |
| `mv_geocode_target` total | 4.78GiB |
| `mv_geocode_target` heap | 1.85GiB |
| `mv_geocode_target` indexes | 2.93GiB |
| `idx_mv_jibun_name_exact` | 760.71MiB |
| `idx_mv_rn_nrm_exact` | 388.72MiB |
| `idx_mv_buld_nm_nrm_exact` | 315.96MiB |
| T-047 exact index 3개 합계 | 1.43GiB |

MV refresh/swap:

| 전략 | T-035 기준 | T-047 측정 | temp delta | 비고 |
|------|-----------:|-----------:|-----------:|------|
| `CONCURRENTLY` | 111.64초 | 133.28초 | +11.31GiB / +80 files | 총시간 +21.64초 |
| shadow `swap` | 137.15초 | 352.85초 | +9.63GiB / +42 files | 총시간 +215.70초 |

shadow `swap` phase 중 T-047 exact index 비용:

| phase | 시간 |
|-------|-----:|
| `rebuild.create_next` | 98.67초 |
| `idx_mv_next_jibun_name_exact` | 46.54초 |
| `idx_mv_next_rn_nrm_exact` | 95.44초 |
| `idx_mv_next_buld_nm_nrm_exact` | 38.38초 |
| exact index 3개 합계 | 180.35초 |
| `swap.rename_live_to_old` + `rename_next_to_live` + `drop_old_post` + `rename_indexes` | 0.03초 |
| `swap.analyze_live` | 5.71초 |

해석:

- T-047 exact index 3개는 조회 p95를 크게 낮추지만, shadow `swap` rebuild 시간에는 약 180초의 인덱스 build 비용을 추가한다.
- live rename 구간은 여전히 0.03초 수준이라 lock window 자체는 짧다. 문제는 shadow MV와 인덱스를 만드는 사전 작업 시간이다.
- `CONCURRENTLY`는 총시간 증가가 21.64초로 작지만, 운영 MV를 직접 갱신하고 temp I/O는 11.31GiB로 더 컸다.
- 짧은 점검 창에서 live lock window가 핵심이면 `swap`을 유지하되, 운영자는 rebuild 시간이 5~6분대로 늘어난다는 점을 알아야 한다. 총시간이 더 중요하고 조회 경합이 낮은 idle 시간에는 `CONCURRENTLY`가 여전히 더 짧다.

백업/disk envelope:

| 항목 | 값 |
|------|----:|
| `pg_dump -Fd --jobs=4` wall time | 2분 21.60초 |
| dump directory size | 4.02GiB |
| dump command RSS max | 32,200KiB |
| filesystem output | 8,424,792 blocks |

현재 WSL 환경에는 `zstd` CLI가 없어 T-046의 최종 `tar.zst` archive 단계는 실행하지 못했다. 따라서 이번 PR의 백업 수치는 archive 압축 전 `pg_dump -Fd` dump directory 기준이다. 다음 backup archive 측정 전에는 `zstd` CLI를 설치하거나 backup helper에 검증된 fallback 압축 경로를 추가해야 한다.

## 2026-05-28 T-047 stress corpus benchmark

PR #51/#52 후속 액션 중 `stress` 10,000건 이상 corpus 조건을 충족하기 위해 query군당 1,000건을 생성해 기본 pool에서 재측정했다.

측정 profile:

| 항목 | 값 |
|------|----|
| artifact | `artifacts/perf/t047-stress-20260528` |
| corpus SHA-256 | `2123e09e41f96760b4a8451d98518a87aee6289cc8b238b8a8b2896b51665f23` |
| case count | 11,000 |
| measurement count | 88,000 |
| iterations / warmup | `iterations=1`, `warmup=1` |
| concurrency | `1/4/16/64` |
| pool | `size=10`, `max_overflow=5` |
| error | 0 |
| `pg_stat_statements` | `available=true` |

case 분포:

| query군 | 건수 |
|---------|-----:|
| Q1 도로명 exact | 1,000 |
| Q2 지번 exact | 1,000 |
| Q3 fuzzy geocode | 1,000 |
| Q4 search | 1,000 |
| Q5 reverse nearest | 1,000 |
| Q6 reverse radius | 1,000 |
| Q7 zipcode | 2,000 |
| Q8 no-result | 2,000 |
| Q11 SPPN | 1,000 |

핵심 p95:

| query군 | c1 p95 | c16 p95 | c64 p95 | c64 checkout p95 | c64 execute p95 |
|---------|-------:|--------:|--------:|-----------------:|----------------:|
| Q1 도로명 exact | 8.61ms | 25.43ms | 338.56ms | 317.54ms | 21.26ms |
| Q2 지번 exact | 4.62ms | 24.00ms | 197.35ms | 180.73ms | 19.65ms |
| Q3 fuzzy | 12.94ms | 33.73ms | 335.01ms | 304.91ms | 32.07ms |
| Q4 search | 7.90ms | 28.75ms | 302.21ms | 280.41ms | 27.77ms |
| Q5 reverse nearest | 4.41ms | 23.34ms | 154.29ms | 134.27ms | 16.05ms |
| Q6 reverse radius | 4.40ms | 23.19ms | 157.28ms | 138.89ms | 16.71ms |
| Q7 zipcode address | 4.83ms | 23.30ms | 353.08ms | 334.48ms | 18.47ms |
| Q7 zipcode point | 4.17ms | 22.99ms | 141.27ms | 123.85ms | 16.44ms |
| Q8 no-result road | 4.34ms | 21.21ms | 181.66ms | 164.89ms | 15.74ms |
| Q8 no-result reverse | 4.20ms | 21.08ms | 181.09ms | 161.97ms | 15.73ms |
| Q11 SPPN reverse | 4.51ms | 21.81ms | 187.43ms | 170.85ms | 17.18ms |

`pg_stat_statements` delta top:

| 순위 | calls | total exec | mean exec |
|------|------:|-----------:|----------:|
| Q3 fuzzy road 계열 | 8,000 | 40,910.80ms | 5.11ms |
| Q1 road exact 계열 | 8,000 | 21,453.97ms | 2.68ms |
| Q4 search 계열 | 8,000 | 18,161.25ms | 2.27ms |
| Q7 zipcode address 계열 | 8,000 | 3,733.88ms | 0.47ms |
| Q11 SPPN reverse 계열 | 8,000 | 1,929.07ms | 0.24ms |
| Q5/Q6 reverse nearest/radius 계열 | 24,000 | 1,412.82ms | 0.06ms |

해석:

- stress corpus에서도 c16까지는 모든 query군 p95가 34ms 안쪽이었다. DB execute p95 기준으로는 Q3 27.50ms, Q4 20.74ms라 1차 목표 안에 들어온다.
- c64 p95 초과는 대부분 pool checkout 대기다. 예를 들어 Q3 c64는 p95 335.01ms 중 checkout p95 304.91ms, execute p95 32.07ms였고, Q4 c64는 p95 302.21ms 중 checkout p95 280.41ms, execute p95 27.77ms였다.
- 가장 느린 client sample은 Q7 zipcode address c64 971.86ms였지만, 이 역시 checkout p95가 334.48ms로 지배적이다.
- 다음 튜닝은 단일 SQL index를 추가하기보다 API worker 수, DB pool size, admission control, REST e2e latency를 함께 측정해야 한다.
- Q3 fuzzy는 `pg_stat_statements` 총 execution time이 가장 크므로, T-057 region hint나 `mv_geocode_text_search` 후보로 query scope를 줄이는 실험은 여전히 유효하다.

## 2026-05-28 PR #51/#52 post-merge 리뷰 반영 메모

PR #51/#52 post-merge 리뷰는 conversation comment 1건씩이었고, review와 review thread는 없었다. 상세 매핑은 `docs/postmerge-review-fixups-pr51-pr52.md`에 둔다.

이번 반영에서 보완한 사항:

- Q4 query split 후보는 PR #53 exact preflight로 코드와 benchmark harness에 반영했다.
- corpus 생성 방식과 후보 확정 run profile을 아래 기준으로 명확히 했다.

남은 후속 액션:

| 항목 | 다음 처리 |
|------|-----------|
| `pg_stat_statements` | Docker/PostgreSQL 설정, schema extension, before/after/delta artifact, 활성 DB의 `standard --iterations 3` run을 완료했다. |
| 인덱스 운영 비용 | T-047 exact index 3개 포함 상태에서 MV refresh/swap, `pg_dump -Fd`, 디스크 envelope를 측정했다. `tar.zst` archive는 로컬 `zstd` CLI 부재로 후속에 남긴다. |
| SQL 상수 public module | T-052 v2 API 또는 SQL 재사용 표면 확대 시 `infra.*_repo`의 underscore 상수를 public SQL module로 추출한다. |
| Q3 fuzzy | T-057 region hint 또는 text-search slim MV 후보로 도로명 trgm 후보 폭을 줄인다. |
| stress corpus | 11,000건 corpus와 88,000 measurement로 c1/c4/c16/c64를 측정했다. error 0, c16 p95 34ms 이하, c64 tail은 대부분 checkout 대기였다. |
| pool wait/DB execution 분리 | `checkout_ms`/`execute_ms`를 artifact에 추가했고, active observability run에서 기본 pool c64 tail 대부분이 checkout 대기임을 확인했다. REST e2e 대조는 후속으로 남긴다. |

## 목표

속도는 T-047의 최우선 품질 지표다. 지오코딩 API는 주소 입력에 대한 대화형 응답 경로이므로, 정합성이 맞더라도 p95/p99 latency가 높으면 운영 준비가 끝난 것으로 보지 않는다.

목표:

- 전국 full-load 직후 실제 운영 규모 row count에서 baseline latency를 확보한다.
- 단일 쿼리 성공 여부가 아니라 p50, p90, p95, p99, max, timeout, error rate를 기록한다.
- 쿼리별 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, SETTINGS)`를 저장해 plan과 buffer 사용량을 비교한다.
- 튜닝은 한 번에 하나의 가설만 적용하고, 전후 차이를 수치로 남긴다.
- 인덱스 추가만으로 부족하면 read-only serving 보조 view/materialized view를 적극 도입한다.
- 튜닝 산출물이 적재 시간, MV refresh/swap 시간, 디스크 사용량, daily delta 반영 시간에 미치는 비용도 함께 기록한다.

## 전제 조건

T-047은 T-027 최종 클린 full-load 이후에 수행한다.

필수 전제:

- Docker PostgreSQL/PostGIS에 전국 전체 데이터가 적재되어 있다.
- `mv_geocode_target`이 shadow swap 방식으로 최신화되어 있다.
- `ANALYZE`가 주요 master table, MV, 후보 보조 view/MV에 수행되어 있다.
- `source_set`, row count, PostgreSQL/PostGIS version, git commit, Docker/WSL/디스크 상태가 기록되어 있다.
- 외부 API fallback은 benchmark baseline에서 끈다. 로컬 DB 쿼리 성능을 먼저 고립해 측정한다.
- `pg_stat_statements`를 사용할 수 있으면 benchmark run 시작 전에 reset하고, run 종료 후 statement 통계를 저장한다.

T-027 정합성 결과에 C2/C4/C6/C7 같은 데이터 품질 오류가 남아도 쿼리 성능 측정은 진행할 수 있다. 다만 benchmark report에는 해당 DB의 `severity_max`, 오류 건수, source set을 함께 기록해 나중에 다른 DB 결과와 혼동하지 않는다.

## 벤치마크 대상 쿼리군

다음 쿼리군을 최소 benchmark set으로 둔다.

| 코드 | 쿼리군 | 예시 | 주요 위험 |
|------|--------|------|-----------|
| Q1 | 도로명주소 exact geocode | `서울특별시 강남구 테헤란로 152` | key filter가 느리거나 `OR` 조건으로 seq scan 발생 |
| Q2 | 지번주소 exact geocode | `대구광역시 중구 동인동1가 1-1` | PNU/법정동/산여부 조합 인덱스 미흡 |
| Q3 | 건물명/도로명 fuzzy geocode | 오타, 축약어, 띄어쓰기 변화 | `pg_trgm` 후보 폭증, similarity threshold 오용 |
| Q4 | 통합 search | 도로명, 행정동, 우편번호, 건물명 혼합 | 여러 lookup이 한 SQL에 섞여 plan 불안정 |
| Q5 | reverse nearest | 건물 출입구 근처 `(lon, lat)` | `ST_Transform`/`ST_DWithin` 인덱스 미사용 |
| Q6 | reverse radius | 반경 10m/50m/200m/1km | 후보 수 폭증, distance sort 비용 |
| Q7 | zipcode lookup | 우편번호 → 주소 목록, 주소 → 우편번호 | limit 전 정렬/필터 비용 |
| Q8 | no-result/invalid | 존재하지 않는 주소, 바다 좌표, 한국 밖 좌표 | 실패 경로가 성공 경로보다 느려지는 문제 |
| Q9 | 행정/기초구역 polygon 보조 조회 | reverse 행정구역, 기초구역 | polygon contains/covers 인덱스 미사용 |
| Q10 | batch/concurrency | 같은 corpus를 동시성 4/16/64로 반복 | connection pool, lock, CPU saturation |
| Q11 | 국가지점번호 보조 geocode/reverse | `다바 7363 4856`, 표기 의무지역 polygon 내부 좌표 | `ST_Covers(tl_sppn_makarea.geom, point)` 공간 조인 비용, 주소 후보 없음 경로의 extension-only 응답 |

## 샘플 corpus

벤치마크 corpus는 고정 파일로 저장해 튜닝 전후에 같은 입력을 반복한다. 생성 기준:

- 전국 17개 시도에서 균등 추출한다.
- 서울/경기/대구처럼 밀집도가 높은 지역은 별도 high-density bucket으로 더 많이 뽑는다.
- 도로명주소와 지번주소를 모두 포함한다.
- direct 출입구 좌표, 위치정보요약DB 출입구 좌표, 내비 centroid fallback 좌표를 각각 포함한다.
- 도로명 오타, 띄어쓰기 제거, 건물번호 누락, 건물명 포함 등 fuzzy 입력을 포함한다.
- 존재하지 않는 주소와 한국 밖 좌표 같은 실패 경로를 포함한다.
- 같은 `bd_mgt_sn`에 보조 지번이 여러 개인 case를 포함한다.
- C2/C4/C6/C7 data-quality sample 일부를 포함해 병적이지만 실제로 발생하는 입력도 측정한다.

현재 harness의 fresh corpus 생성은 PostgreSQL `TABLESAMPLE SYSTEM (...) REPEATABLE (47)`을 우선 사용한다. `mv_geocode_target` 표본은 `TABLESAMPLE SYSTEM (0.2) REPEATABLE (47)`, 국가지점번호 표본은 `tl_sppn_makarea TABLESAMPLE SYSTEM (10) REPEATABLE (47)`이다. 표본이 부족하거나 DB가 `TABLESAMPLE` 실행을 거절하면 fallback으로 `ORDER BY bd_mgt_sn LIMIT :limit` 또는 source table의 안정 정렬을 사용한다. 튜닝 전후 비교에서는 fresh sampling보다 저장된 `corpus.json`과 `corpus-summary.json.sha256`을 재사용하는 것을 원칙으로 한다.

최소 규모:

| corpus | 크기 | 용도 |
|--------|-----:|------|
| `smoke` | 50건 | PR 중 빠른 회귀 |
| `standard` | 1,000건 이상 | 기본 전후 비교 |
| `stress` | 10,000건 이상 | candidate 확정 전 반복 측정 |
| `concurrency` | 1,000건 이상 | 동시성 4/16/64 측정 |

corpus row에는 `case_id`, `query_kind`, `input`, `expected_status`, `expected_bd_mgt_sn` 또는 기대 좌표 범위, `sido`, `sig_cd`, `source`, `note`를 둔다.

## 측정 방법

각 benchmark run은 같은 순서로 수행한다.

1. 시스템 상태를 기록한다. CPU, RAM, 디스크 여유, Docker version, PostgreSQL version, PostGIS version, DB size, table/MV row count, git commit, source set을 저장한다.
2. `ANALYZE` 상태를 확인한다. 후보 view/MV 또는 index를 새로 만들었다면 반드시 `ANALYZE` 후 측정한다.
3. `pg_stat_statements`를 reset한다. 사용할 수 없으면 이유를 report에 남긴다.
4. warm-up run을 1회 수행한다. warm-up 결과는 threshold 판정에서 제외하되 별도 저장한다.
5. 단일 동시성 run을 수행한다. 후보 탐색 PR은 `--iterations 1`로 빠르게 돌릴 수 있지만, 후보 확정·회귀 기준선은 각 query case를 최소 3회 반복하거나 `standard` corpus 전체를 3회 이상 반복한다.
6. 동시성 run을 수행한다. concurrency는 4, 16, 64를 기본으로 하고, 로컬 장비가 버티지 못하면 실패 지점과 resource saturation을 기록한다.
7. 각 query군에서 대표 slow sample에 대해 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, SETTINGS)`를 저장한다.
8. 결과를 JSON/CSV/Markdown으로 저장한다.

기본 지표:

- client wall time
- DB execution time
- REST API total time
- p50, p90, p95, p99, max
- timeout count
- error count
- rows returned
- shared hit/read/dirtied/written buffers
- temp read/write bytes
- plan hash
- index scan/bitmap scan/seq scan 여부
- `pg_stat_statements.mean_exec_time`, `calls`, `rows`, `shared_blks_read`, `temp_blks_written`

## 초기 성능 목표

아래 목표는 첫 운영 기준선이다. 실제 하드웨어와 corpus가 확정되면 ADR-031 부록 또는 T-047 결과 문서에서 조정할 수 있다.

| 쿼리군 | DB p95 목표 | REST p95 목표 | 실패 기준 |
|--------|------------:|--------------:|-----------|
| Q1 도로명 exact | 30ms 이하 | 100ms 이하 | p95 100ms 초과 또는 seq scan |
| Q2 지번 exact | 30ms 이하 | 100ms 이하 | p95 100ms 초과 또는 seq scan |
| Q3 fuzzy geocode | 150ms 이하 | 300ms 이하 | p95 500ms 초과 또는 후보 폭증 |
| Q4 통합 search | 150ms 이하 | 300ms 이하 | p95 500ms 초과 |
| Q5 reverse nearest | 50ms 이하 | 150ms 이하 | GiST 미사용 또는 p95 300ms 초과 |
| Q6 reverse radius | 100ms 이하 | 250ms 이하 | radius 200m에서 p95 500ms 초과 |
| Q7 zipcode lookup | 30ms 이하 | 100ms 이하 | p95 100ms 초과 |
| Q8 no-result/invalid | 50ms 이하 | 150ms 이하 | 실패 경로가 성공 경로보다 2배 이상 느림 |

이 목표는 "무조건 달성해야 하는 숫자"라기보다 튜닝 우선순위 게이트다. 초과하면 이유를 설명하고, 보조 view/MV/index 또는 쿼리 분리 실험을 반드시 수행한다.

## 튜닝 루프

T-047 구현 PR에서는 다음 루프를 반복한다.

1. baseline을 측정한다.
2. 가장 느린 query군과 slow sample을 고른다.
3. plan, buffer, temp I/O, row estimate 오차를 분석한다.
4. 하나의 가설만 적용한다.
5. 같은 corpus와 같은 iteration으로 재측정한다.
6. 개선 폭과 부작용을 비교한다.
7. 기준을 만족하면 유지하고, 만족하지 않으면 되돌리거나 후속 후보로 기록한다.

유지 기준:

- p95 또는 p99가 20% 이상 개선되거나
- shared read/temp write가 30% 이상 감소하거나
- timeout/error가 사라지거나
- 동시성 run에서 tail latency가 명확히 줄어야 한다.

부작용 기준:

- full-load 또는 MV refresh 시간이 크게 늘면 반드시 기록한다.
- `mv_geocode_target` row 계약 또는 vworld 호환 응답 구조가 바뀌면 안 된다.
- `x_extension` 밖에 새 응답 필드를 추가하지 않는다.
- `pg_trgm.similarity_threshold` 전역 변경은 금지한다. 필요하면 transaction 단위 `SET LOCAL`만 사용한다.
- 공간 쿼리는 입력 좌표를 한 번만 5179로 변환하고, indexed column에는 `ST_Transform`을 걸지 않는다.

최소 실험 수:

- baseline이 목표를 모두 만족하더라도 대표 query군별 plan 확인과 3개 이상의 안정화 실험을 수행한다.
- 목표를 초과하는 query군이 있으면 최소 10개 이상의 후보 실험을 수행한다.
- 각 실험은 결과가 나쁘더라도 `artifacts/perf/<run_id>/trials/<trial_id>.md`에 남긴다.

## 적극 도입 가능한 대책

### 쿼리 재작성

- exact lookup과 fuzzy lookup을 한 SQL의 `OR` 조건으로 섞지 않고, exact 실패 후 fuzzy를 별도 단계로 실행한다.
- 후보 추출과 최종 응답 정렬을 분리한다. 후보 CTE는 `LIMIT`을 가능한 빨리 적용한다.
- `UNION ALL`로 road/parcel/building-name 후보를 분리해 planner가 각 branch별 index를 고르게 한다.
- reverse는 `ST_DWithin` 후보를 먼저 좁히고, 최종 정렬에서 `ST_Distance`를 사용한다.
- KNN이 유리한 case는 `ORDER BY pt_5179 <-> target_geom LIMIT N` 후보 추출을 실험한다.
- polygon reverse는 `&& ST_Expand(...)` bounding box prefilter와 `ST_Covers`를 함께 실험한다.

### 인덱스

- exact key용 btree composite index와 `INCLUDE` 컬럼을 추가해 heap fetch를 줄인다.
- fuzzy search용 `gin_trgm_ops` index를 query군별로 분리한다.
- `address_type`, `sido_cd`, `sig_cd`, `zip_no`, `pt_source` 같은 자주 쓰는 filter에는 partial index를 검토한다.
- reverse/radius는 5179 geometry GiST index를 우선한다.
- 새 index는 build time, size, refresh/swap 영향, insert/update 영향까지 기록한다.

### 보조 view/materialized view

인덱스와 쿼리 재작성만으로 목표를 만족하지 못하면 read-only serving 보조 객체를 추가할 수 있다. 이는 "source of truth"를 늘리는 것이 아니라 `mv_geocode_target` 또는 master table에서 파생된 가속 구조다.

후보:

| 후보 | 목적 | 기본 아이디어 |
|------|------|---------------|
| `mv_geocode_exact_key` | Q1/Q2 exact geocode 가속 | 도로명/지번 exact key와 응답에 필요한 최소 컬럼만 보관 |
| `mv_geocode_text_search` | Q3/Q4 fuzzy/search 가속 | 정규화된 검색 문자열, token, trgm 전용 컬럼을 분리 |
| `mv_reverse_point_5179` | Q5/Q6 reverse 가속 | `bd_mgt_sn`, `address_type`, `pt_source`, `pt_5179`, 응답 key만 가진 slim point MV |
| `mv_zipcode_lookup` | Q7 zipcode lookup 가속 | `zip_no`, `sido`, `sig`, 도로명/지번 표시용 최소 컬럼 |
| `v_admin_boundary_4326` | 디버그 지도 표시 | polygon 응답 변환 비용을 UI/디버그 경로에서 분리 |
| `mv_sppn_reverse_area` | Q11 국가지점번호 reverse | `tl_sppn_makarea` polygon 후보의 면적/표시명/4326 bbox를 미리 보관해 reverse 보조 경로와 UI overlay 변환 비용을 분리 |

보조 MV 도입 조건:

- 원천 row를 수정하지 않는다.
- refresh/swap 절차와 의존 순서를 문서화한다.
- unique key와 index 이름을 명시한다.
- `EXPLAIN`으로 실제 query path가 바뀐 것을 증명한다.
- semantic parity test를 추가한다. 기존 `mv_geocode_target` 결과와 후보 MV 결과가 같은지 대표 corpus로 비교한다.
- refresh 비용이 과도하면 `serving-ready` 백업 profile과 T-046 restore 후속 절차에도 반영한다.

### PostgreSQL 설정과 운영 옵션

- 짧은 OLTP query에서 JIT가 손해면 benchmark session에서 `SET LOCAL jit = off`를 실험한다.
- query별 sort/hash가 큰 경우 `SET LOCAL work_mem` 실험을 하되, API global 기본값으로 올리지는 않는다.
- `effective_cache_size`, `random_page_cost` 같은 planner 설정은 Docker 개발 DB와 운영 DB 차이가 크므로 결과 문서에만 후보로 남기고, 코드 기본값으로 즉시 고정하지 않는다.
- `pg_prewarm`은 cold-start 운영 요구가 있을 때 별도 실험한다.

## 산출물

실행 산출물은 git에 커밋하지 않고 `artifacts/perf/<run_id>/`에 둔다.

```text
artifacts/perf/<run_id>/
├── environment.json
├── corpus-summary.json
├── baseline.json
├── baseline-summary.md
├── pg-stat-statements-before.json
├── pg-stat-statements-after.json
├── pg-stat-statements-delta.json
├── plans/
│   ├── Q1_road_exact_001.json
│   └── Q5_reverse_nearest_001.json
├── trials/
│   ├── trial-001-index-exact-key.md
│   ├── trial-002-rewrite-union-all.md
│   └── trial-010-slim-reverse-mv.md
└── final-report.md
```

PR에는 전체 artifact를 커밋하지 않고, `final-report.md`의 핵심 표와 결론만 문서로 옮긴다.

최종 report 필수 표:

- query군별 baseline p50/p95/p99
- query군별 최종 p50/p95/p99
- 개선율
- 새 index/view/MV별 size와 build time
- full-load/MV refresh/swap 시간 영향
- 유지한 실험과 폐기한 실험
- 남은 병목과 후속 task

## 관리 UI 후보

T-047 1차 구현은 CLI와 artifact 중심으로 충분하다. 다만 반복 튜닝이 잦아지면 `/admin/performance` 페이지를 추가해 다음을 보여 줄 수 있다.

- benchmark run 목록
- query군별 p50/p95/p99 trend
- slow sample과 plan JSON 링크
- 새 index/view/MV 적용 전후 비교
- threshold 초과 query군 badge

프론트엔드는 여전히 DB에 직접 연결하지 않고 백엔드 REST 또는 정적 artifact metadata만 읽는다.

## PR 진행 순서

T-047은 변경 폭이 커질 수 있으므로 다음 순서로 나누는 것을 권장한다.

1. benchmark harness와 corpus 생성기 문서/코드.
2. 전국 full-load DB baseline 측정 PR.
3. 가장 큰 병목 1~2개에 대한 index/query rewrite PR.
4. 보조 view/MV가 필요한 경우 별도 PR.
5. 최종 benchmark report와 threshold 갱신 PR.

각 PR은 baseline, 변경, 결과, 부작용을 같은 형식으로 기록한다. "빨라졌다"는 주관적 설명만으로는 merge하지 않는다.

## 구현 후 테스트 항목

- unit: corpus row schema validation.
- unit: query benchmark result aggregation(p50/p95/p99) 계산.
- unit: `EXPLAIN` JSON plan hash 추출과 secret redaction.
- integration: 전국 DB 또는 restored full DB에서 `smoke` corpus benchmark.
- integration: representative slow sample `EXPLAIN`이 seq scan 없이 기대 index를 사용하는지 확인.
- integration: 후보 보조 MV가 기존 `mv_geocode_target` 결과와 semantic parity를 유지하는지 확인.
- frontend: `/admin/performance`를 만들 경우 run list, threshold badge, plan viewer rendering.
