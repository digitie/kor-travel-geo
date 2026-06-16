# T-154 async DB pool checkout timeout/fail-fast

2026-06-16에 완료했다.

## 목표

T-047/T-141 고부하 측정에서 드러난 checkout 대기를 무한 tail로 방치하지 않는다. SQLAlchemy async engine의 pool 크기와 checkout timeout을 명시 설정하고, 풀 포화 시 API가 구조화된 503으로 빠르게 실패하게 한다.

## 구현

- `Settings.pg_pool_timeout_ms`를 추가했다. 기본값은 `1000`ms다.
- `infra.engine.make_async_engine()`가 `pool_size`, `max_overflow`, `pool_timeout`, `pool_pre_ping`, `pool_recycle`을 모두 명시한다.
- SQLAlchemy pool checkout `TimeoutError`는 FastAPI exception handler에서 `DatabaseError(E0500, HTTP 503)`로 변환한다.
- REST v1 VWorld 호환 경로(`/v1/address/geocode`, `/v1/address/reverse`)는 기존 VWorld error shape를 유지하며, pool timeout은 `SYSTEM_ERROR`로 노출된다.
- `/metrics`에 `kor_travel_geo_pg_pool_checkout_timeouts_total{method,route}` counter를 추가했다.
- `/v1/readyz` pool detail에 `timeout_ms`를 추가해 현재 process의 checkout 상한을 운영자가 확인할 수 있게 했다.
- `KTG_TEST_PG_DSN`이 있을 때만 실행되는 opt-in 통합 테스트가 `pool_size=1`, `max_overflow=0`, `pg_pool_timeout_ms=50` 조건에서 두 번째 checkout이 빠르게 실패하는지 검증한다.

## 오류 코드 결정

풀 포화는 DB 인프라 가용성 문제이므로 HTTP 503 + `E0500`으로 반환한다. `E0409`는 T-059 이후 advisory lock 기반 동시 실행 충돌 전용으로 유지한다. 이렇게 해야 운영자가 "같은 운영 작업이 이미 실행 중"인 상황과 "DB connection pool이 고갈됨"을 구분할 수 있다.

## 운영 의미

기본 상한 1초는 c64 tail의 긴 checkout 대기를 끊기 위한 1차 가드다. 정상 부하에서 timeout이 반복되면 먼저 `KTG_API_MAX_CONCURRENCY`로 `/v1/address/*`/`/v2/*` admission을 낮추고, DB가 감당 가능한 범위에서만 `KTG_PG_POOL_SIZE`/`KTG_PG_MAX_OVERFLOW`를 조정한다. 무조건 pool을 키우는 것은 PostgreSQL 동시 실행 경합을 키울 수 있으므로 T-145에서 endpoint-level backpressure와 overload envelope를 이어서 정리한다.

## 검증

- `tests/unit/test_infra_engine_pnu_sql.py`: engine 생성 인자가 `pool_timeout`, `pool_pre_ping`을 포함하는지 검증한다.
- `tests/unit/test_api_responses.py`: SQLAlchemy pool timeout이 일반 API와 VWorld 호환 API에서 구조화 응답으로 변환되는지 검증한다.
- `tests/unit/test_metrics.py`: pool checkout timeout counter가 Prometheus body에 노출되는지 검증한다.
- `tests/unit/test_health_readiness.py`: readiness pool detail에 `timeout_ms`가 포함되는지 검증한다.
- `tests/integration/test_pool_timeout_failfast.py`: `KTG_TEST_PG_DSN` opt-in 환경에서 실제 pool 포화 checkout timeout을 검증한다.

## 후속

- T-145: endpoint별 concurrency cap, overload error envelope, retry 금지 구간, timeout storm/worker recovery 검증.
- T-161: client disconnect 시 DB query cancellation과 connection 반환 관측.
- T-159: DB 단절·복구·IO 지연 fault injection.
