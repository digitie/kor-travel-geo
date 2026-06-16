# T-155 psycopg prepared statement·plan cache 튜닝

작성일: 2026-06-16

## 결론

T-155에서는 PostgreSQL 접속의 psycopg server-side prepared statement threshold를
운영 설정과 SQL benchmark artifact에 노출했다.

- 새 설정: `KTG_PG_PREPARE_THRESHOLD` / `Settings.pg_prepare_threshold`
- 기본값: `5` (psycopg 기본값 유지)
- `0`: 첫 실행부터 prepare
- `none`, `off`, `disable`, `disabled`: prepared statement 비활성화

`make_async_engine()`은 `connect_args["prepare_threshold"]`로 이 값을 psycopg
`AsyncConnection.connect()`에 전달한다. `scripts/benchmark_query_performance.py`는
`--prepare-threshold N`과 `--disable-prepared-statements`를 받아 run별 threshold를 바꾸고,
`environment.json`/`summary.md`에 threshold를 기록한다.

## prepared statement 관측

`pg_prepared_statements`는 session-local view다. 여러 connection이 섞이면 어떤 session을
봤는지 애매하므로, T-155 비교 run은 `--pool-size 1 --max-overflow 0 --concurrency 1`로
고정했다. benchmark harness는 run 전후에 다음 파일을 남긴다.

- `prepared-statements-before.json`
- `prepared-statements-after.json`

주의할 점: psycopg는 prepared statement가 있는 session에서 `ROLLBACK` command를 보면
내부 prepared cache를 지운다. 그래서 `pg_stat_statements`/`pg_prepared_statements` 같은
read-only snapshot도 명시적으로 `commit()`한 뒤 connection을 pool에 돌려보내게 했다.

## Live smoke

WSL ext4 테스트 미러에서 같은 17개 hot-query corpus로 비교했다. live DB의
`mv_geocode_text_search`가 T-171 `buld_slno`/`buld_se_cd` 컬럼을 아직 반영하지 않아
Q3 fuzzy geocode 3건은 제외했다. Search broad/fuzzy, exact geocode, reverse, zipcode,
국가지점번호, no-result path는 포함했다.

공통 설정:

- corpus: `artifacts/perf/t155-hot-corpus-no-fuzzy.json`
- iterations/warmup: `12 / 3`
- concurrency: `1`
- pool: `size=1`, `max_overflow=0`
- statement timeout: `5000ms`

| run | threshold | prepared count | errors | p50 | p95 | p99 | max |
|-----|-----------|----------------|--------|-----|-----|-----|-----|
| `t155-prepared-disabled-nofuzzy-r2` | `None` | 0 | 0 | 2.889ms | 5.585ms | 6.561ms | 6.846ms |
| `t155-prepared-threshold1-nofuzzy-r2` | `1` | 17 | 0 | 2.711ms | 5.644ms | 6.376ms | 7.605ms |
| `t155-prepared-threshold5-nofuzzy-r2` | `5` | 13 | 0 | 2.802ms | 5.383ms | 6.485ms | 6.545ms |

`threshold=1`은 prepared count를 가장 많이 만들지만 전체 p95가 기준보다 약간 나빠졌다.
`threshold=5`는 prepared count를 `0 -> 13`으로 늘리고 전체 p95를 `5.585ms -> 5.383ms`로
낮췄다. per-query p95는 17개 중 10개가 개선됐다. 대표 delta:

| sql | disabled p95 | threshold=5 p95 | delta |
|-----|--------------|-----------------|-------|
| `road_exact` | 6.825ms | 6.525ms | -0.300ms |
| `search` | 5.612ms | 5.337ms | -0.275ms |
| `reverse_nearest` | 3.401ms | 3.190ms | -0.211ms |
| `zipcode_point` | 2.856ms | 2.518ms | -0.338ms |
| `reverse_radius` | 3.890ms | 4.699ms | +0.809ms |

`reverse_radius`는 Q6 benchmark 전용 surface라 runtime reverse nearest 기본값을 바꾸는
근거로 보지 않는다. 이번 결과로는 production 기본값을 `1`로 낮출 이유가 없고,
psycopg 기본 `5`를 명시적으로 유지하는 것이 가장 보수적이다.

## 검증

```bash
python -m pytest tests/unit/test_settings.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_query_performance_benchmark.py -q
python -m ruff check src/kortravelgeo/settings.py src/kortravelgeo/infra/engine.py scripts/benchmark_query_performance.py tests/unit/test_settings.py tests/unit/test_infra_engine_pnu_sql.py tests/unit/test_query_performance_benchmark.py
python -m mypy src/kortravelgeo/settings.py src/kortravelgeo/infra/engine.py scripts/benchmark_query_performance.py
```
