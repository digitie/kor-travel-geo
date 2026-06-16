# T-146 적재 후 읽기 최적화 maintenance pipeline

## 목적

적재 완료 뒤 쓰기 빈도가 낮고 조회가 대부분인 운영 전제를 기준으로, serving 경로를 빠르게 만들기 위한 후처리 순서를 표준화한다. 이 작업은 새 DB object나 OpenAPI 계약을 만들지 않고, 기존 `refresh_mv()`/`ops.table_stats_snapshots`/benchmark artifact 표면을 묶어 재현 가능한 report를 남긴다.

## 구현 범위

- `src/kortravelgeo/loaders/postload_maintenance.py`
  - `build_postload_maintenance_plan()`은 표준 단계와 자동/수동 경계를 반환한다.
  - `collect_postload_object_stats()`는 `pg_class`, `pg_stat_user_tables`, `pg_index`, `pg_total_relation_size()`로 source/MV/index 상태를 읽는다.
  - `build_postload_maintenance_warnings()`는 index budget 초과, invalid index, analyze 누락, dead tuple ratio를 경고로 분리한다.
  - `run_postload_maintenance()`는 기본 `plan` 모드에서는 read-only catalog report만 만들고, `execute_safe` 모드에서만 선택된 자동 단계를 실행한다.
- `scripts/run_t146_postload_maintenance.py`
  - 기본 실행은 plan-only다.
  - `--mode execute-safe`는 `resolve_text_geometry_links()`와 `refresh_mv(strategy=...)`를 실행한다.
  - `--vacuum-analyze`를 함께 줬을 때만 source relation에 `VACUUM (ANALYZE)`를 실행한다.
  - `--register-artifact --output <path>`를 주면 T-265의 `benchmark` ops artifact로 report를 등록한다.
- `tests/unit/test_t146_postload_maintenance.py`
  - 자동/수동 단계 분리, warning 판정, catalog query 표면, artifact 등록 연결을 고정한다.

## 표준 순서

1. `catalog.before`: relation/index 크기, dead tuple, analyze timestamp, invalid index를 catalog에서 읽는다.
2. `source.vacuum_analyze`: 대량 COPY/UPSERT 뒤 source table에 `VACUUM (ANALYZE)`를 실행한다. 기본 plan에서는 실행하지 않고, `execute-safe --vacuum-analyze`에서만 수행한다.
3. `links.resolve`: `resolve_text_geometry_links(statement_timeout_ms=1800000)`로 serving key를 해소한다.
4. `serving.refresh`: `refresh_mv(strategy="swap" | "concurrent")`로 `mv_geocode_target`, `mv_geocode_text_search`, `region_radius_parts`를 같은 세대로 갱신한다. 성공 후 `ANALYZE`와 `geo_cache` 무효화는 기존 `refresh_mv()`가 담당한다.
5. `stats.capture`: `ops.table_stats_snapshots`에 후처리 후 relation 상태를 저장한다.
6. `budget.check`: index footprint, invalid index, analyze 누락, dead tuple ratio를 report warning으로 남긴다.

## 수동 경계

- `REINDEX INDEX CONCURRENTLY <index_name>`은 invalid index 또는 명확한 index bloat 증거가 있을 때만 운영자가 선택한다. high IO와 start/end lock이 있으므로 T-146 자동 실행에 넣지 않는다.
- `CLUSTER`는 live relation에 강한 잠금을 요구한다. 물리 정렬이 필요하면 raw `CLUSTER`보다 shadow rebuild 또는 `pg_repack`류 절차를 별도 작업으로 쪼갠다.
- `pg_prewarm`과 hot-query warm 자동화는 T-162 범위다. T-146은 maintenance 직후 runtime warm이 필요하다는 runbook 경계만 남긴다.

## 실행 예시

```bash
python scripts/run_t146_postload_maintenance.py \
  --mode plan \
  --strategy swap \
  --output artifacts/perf/t146-postload-maintenance-plan/report.json
```

```bash
python scripts/run_t146_postload_maintenance.py \
  --mode execute-safe \
  --strategy swap \
  --vacuum-analyze \
  --output artifacts/perf/t146-postload-maintenance-r1/report.json \
  --register-artifact
```

`execute-safe`도 PostgreSQL/RustFS를 직접 구동하지 않는다. 현재 `KTG_PG_DSN`이 가리키는 이미 동작 중인 DB에 접속해 작업한다.

## 측정과 해석

- WSL ext4 테스트 미러 plan smoke는 `artifacts/perf/t146-postload-maintenance-plan/report.json`에 보존했다. 2026-06-16T08:39Z 기준 75개 object를 catalog에서 읽었고, relation bytes는 27,936,006,144, index bytes는 12,183,379,968이었다. Warning은 비어 있는 `postal_bulk_delivery`/`postal_pobox`의 `missing_analyze` 2건뿐이었다.
- rebuild 시간과 lock window는 기존 `scripts/benchmark_mv_refresh.py`로 계속 측정한다. T-035 전국 DB 기준 `CONCURRENTLY`는 1분 49.64초, shadow swap은 2분 16.28초였고 rename/index rename 구간은 약 0.016초였다.
- T-047 exact index 추가 후 envelope에서는 `CONCURRENTLY` refresh가 133.28초, shadow swap이 352.85초까지 늘었다. 새 보조 index/MV를 도입하면 같은 report에 index size와 refresh 시간을 함께 남긴다.
- T-146 report의 `warning`은 운영 판단 보조다. `index_budget_exceeded`나 `dead_tuple_ratio_high`가 있어도 자동으로 구조 변경을 수행하지 않는다.
- rollback은 relation-level DDL undo가 아니라 백업/복원 또는 serving DB hot-swap rollback에 의존한다. 따라서 full-load 뒤 T-146 `execute-safe`를 실행하기 전 serving-ready backup 또는 restore rollback 경로가 준비되어 있어야 한다.

## T-162와의 경계

T-146은 적재 직후 DB object 상태를 정리하고 report를 남기는 작업이다. 재기동·swap 직후 cold p99 spike를 낮추는 `pg_prewarm`, hot-query replay, API worker warm은 T-162에서 자동화한다.
