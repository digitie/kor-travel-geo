# T-158 slow-query·overload 구조화 로깅과 표본 persist

## 목적

T-157은 `pg_stat_statements` top-N을 주기적으로 저장하지만, "어떤 API endpoint에서 어떤 느린 쿼리가 발생했는지"와 overload 순간의 요청 맥락은 별도로 남기지 않았다. T-158은 과다 로깅을 피하면서 느린 API 요청, admission overload, 느린 DB 쿼리 표본을 구조화 로그와 `ops` 표본 테이블에 남긴다.

## 구현

- 새 설정은 기본 비활성이다.
  - `KTG_OPS_SLOW_SAMPLES_ENABLED=false`
  - `KTG_OPS_SLOW_QUERY_MS=250`
  - `KTG_OPS_SLOW_SAMPLE_RATE=1.0`
  - `KTG_OPS_SLOW_SAMPLE_MIN_INTERVAL_MS=1000`
  - `KTG_OPS_SLOW_SAMPLE_QUEUE_SIZE=1000`
  - `KTG_OPS_SLOW_SAMPLE_FLUSH_INTERVAL_MS=1000`
  - `KTG_OPS_SLOW_SAMPLE_FLUSH_BATCH_SIZE=50`
  - `KTG_OPS_SLOW_QUERY_EXPLAIN_ENABLED=false`
  - `KTG_OPS_SLOW_QUERY_EXPLAIN_TIMEOUT_MS=3000`
- `infra.slow_observability`가 process-local queue, sample-rate, per-key 최소 간격, 민감정보 마스킹을 담당한다.
- Fresh schema는 `src/kortravelgeo/infra/sql.py`, `sql/ddl/001_schema.sql`, `sql/indexes.sql`에 반영하고 기존 DB upgrade는 `alembic/versions/0021_t158_slow_observability.py`로 처리한다.
- API middleware는 느린 요청 표본을 `sample_type="api_request"`로, admission timeout은 `sample_type="overload"`로 큐에 넣는다.
- SQLAlchemy query metric hook은 `KTG_OPS_SLOW_SAMPLES_ENABLED=true`일 때만 slow query callback을 설치한다.
- DB 표본은 `sample_type="db_query"`이며 `method`, `route`, `operation`, `query_fingerprint`, literal 마스킹 `query_preview`, `context.status`를 포함한다.
- `KTG_OPS_SLOW_QUERY_EXPLAIN_ENABLED=true`이면 flush task가 `SELECT`/`WITH` 쿼리에 한해 `EXPLAIN (FORMAT JSON)`을 별도 timeout 안에서 실행하고 `plan` JSONB에 저장한다. `ANALYZE`는 사용하지 않는다.

## 저장소

`ops.slow_observability_samples`는 append형 운영 관측 테이블이다. 원문 SQL, 파라미터, 주소 문자열은 저장하지 않는다.

주요 컬럼:

- `sample_type`: `api_request` / `db_query` / `overload`
- `method`, `route`, `status_code`
- `elapsed_ms`, `threshold_ms`, `sample_rate`
- `operation`, `query_fingerprint`, `query_preview`
- `plan`: 선택적 `EXPLAIN (FORMAT JSON)` 결과 또는 skip/error 사유
- `context`: source, status, scope, executemany 같은 보조 맥락

인덱스:

- `captured_at DESC, sample_type`
- `route, captured_at DESC`
- `query_fingerprint, captured_at DESC`

## 운영 메모

- 기본값은 비활성이라 정상 요청 경로에는 추가 DB write가 없다.
- 활성화해도 표본은 메모리 queue에 먼저 들어가고 API lifespan background task가 batch insert한다.
- queue가 가득 차면 새 표본을 버리고 `dropped_slow_sample_count()`에 누적한다. 운영에서는 sample rate나 최소 간격을 낮춰 조정한다.
- `EXPLAIN`은 planning 비용이 있으므로 먼저 `KTG_OPS_SLOW_QUERY_EXPLAIN_ENABLED=false`로 표본만 모은 뒤, 문제 fingerprint가 좁혀질 때 켠다.

## 검증

- `tests/unit/test_t158_slow_observability.py`
- `tests/unit/test_api_app_contract.py::test_performance_monitoring_enqueues_slow_request_sample`
- `tests/unit/test_api_admission_control.py::test_admission_timeout_enqueues_overload_sample`
- `tests/unit/test_ops_metadata.py`
- `tests/unit/test_alembic_migrations.py::test_t158_slow_observability_migration_adds_sample_table`
