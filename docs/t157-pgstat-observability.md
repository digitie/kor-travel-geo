# T-157 pg_stat_statements 상시 수집·노출

T-157은 일회성 benchmark artifact에만 있던 `pg_stat_statements` 관측을 운영 스키마와 Admin/Prometheus 표면으로 끌어올린 작업이다. 목적은 API 재기동 뒤에도 최신 top-N slow query 관측치를 유지하고, overload/fail-fast 후속 작업에서 같은 기준으로 DB 실행 시간을 확인하는 것이다.

## 구현 범위

- `ops.pg_stat_statements_snapshots`를 추가한다.
  - fresh schema: `src/kortravelgeo/infra/sql.py`, `sql/ddl/001_schema.sql`
  - upgrade: `alembic/versions/0019_t157_pg_stat_snapshots.py`
  - 인덱스: `captured_at DESC, rank`, `query_fingerprint, captured_at DESC`
- `AdminRepository.capture_pg_stat_statement_snapshots()`가 `x_extension.pg_stat_statements`에서 현재 DB의 top-N query를 읽어 snapshot row로 저장한다.
- `AsyncAddressClient`와 `/v1/admin/ops/pg-stat-statements`, `/v1/admin/ops/pg-stat-statements/capture`를 추가한다.
- API lifespan scheduler가 기본 5분마다 capture를 수행한다. 수동 capture와 scheduler는 PostgreSQL advisory transaction lock으로 중복 실행을 막는다.
- `/metrics`는 최신 persisted snapshot을 읽어 Prometheus gauge로 노출한다.
- `/admin/ops`는 최신 top-N query를 조회하고 수동 capture를 실행할 수 있다.

## 노출 원칙

`pg_stat_statements.query` 원문은 Prometheus label에 절대 넣지 않는다. Prometheus label은 `rank`, `operation`, `query_fingerprint`만 사용한다. Admin API에는 운영자가 원인을 파악할 수 있도록 `query_preview`를 제공하지만, 문자열 literal과 숫자는 `?`로 마스킹하고 500자로 자른다.

`query_fingerprint`는 기존 DB query metrics의 `sql_fingerprint()`를 재사용한다. 따라서 runtime SQL histogram과 persisted top-N snapshot을 같은 저카디널리티 식별자로 교차 확인할 수 있다.

## 설정

| 설정 | 기본값 | 의미 |
|------|--------|------|
| `KTG_OPS_PG_STAT_STATEMENTS_CAPTURE_INTERVAL_MINUTES` | `5` | API lifespan scheduler 주기. `0`이면 비활성 |
| `KTG_OPS_PG_STAT_STATEMENTS_CAPTURE_LIMIT` | `20` | 한 번에 저장할 top-N query 수 |
| `KTG_OPS_PG_STAT_STATEMENTS_CAPTURE_ON_STARTUP` | `true` | API 시작 직후 1회 capture 여부 |
| `KTG_OPS_PG_STAT_STATEMENTS_RETENTION_DAYS` | `7` | capture transaction 안에서 이 기간보다 오래된 `ops.pg_stat_statements_snapshots` row를 정리 |

## Prometheus metric

| metric | labels |
|--------|--------|
| `kor_travel_geo_pg_stat_statements_total_exec_time_ms` | `rank`, `operation`, `query_fingerprint` |
| `kor_travel_geo_pg_stat_statements_calls` | `rank`, `operation`, `query_fingerprint` |
| `kor_travel_geo_pg_stat_statements_mean_exec_time_ms` | `rank`, `operation`, `query_fingerprint` |
| `kor_travel_geo_pg_stat_statements_max_exec_time_ms` | `rank`, `operation`, `query_fingerprint` |

## 주의

`pg_stat_statements`는 extension이 생성되어 있어도 PostgreSQL 서버가 `shared_preload_libraries=pg_stat_statements`로 떠 있어야 정상 집계된다. 이 저장소는 PostgreSQL을 직접 구동·재시작하지 않으므로 서버 설정 변경은 외부 운영 환경에서 처리한다. capture 실패는 scheduler 로그에 남고 API 프로세스는 계속 동작한다.

## 검증

- WSL ext4 테스트 미러: `python -m pytest -q` 849 passed, 51 skipped.
- WSL ext4 테스트 미러: `ruff check .`, `mypy src/kortravelgeo`, `lint-imports` 통과.
- OpenAPI drift: `python scripts/export_openapi.py --check` 통과.
- WSL ext4 테스트 미러 UI: `npm run lint`, `npm run type-check`, `npm run test`, `npm run build` 통과.
- React Doctor: `npx react-doctor@latest . --offline --verbose --json`은 `errorCount=0`으로 통과했다. 기존 source-files/backups 영역 warning 16건은 이번 T-157 변경 파일 밖의 구조 경고라 별도 후속 정리 대상으로 남긴다.
