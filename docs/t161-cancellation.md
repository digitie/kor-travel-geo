# T-161 client disconnect·query cancellation 일관성

## 목표

공개 주소 API에서 클라이언트가 연결을 끊었을 때 진행 중인 요청 작업을 계속 유지하지 않는다. 요청 취소는 `asyncio.CancelledError`로 내부 작업에 전파하고, SQLAlchemy async connection context가 정상 정리되어 커넥션이 pool에 반환되는지 검증한다.

## 구현

- `/v1/address/*`, `/v2/*` 경로에 `ClientDisconnectCancellationMiddleware`를 적용한다.
- ASGI `receive` 메시지를 queue로 전달하면서 `http.disconnect`를 감지하면 inner app task를 cancel한다.
- 대용량 admin upload body를 미리 읽지 않도록 disconnect cancel 범위는 공개 주소 API로 제한한다.
- 성능 middleware는 `asyncio.CancelledError`를 잡아 `status_code=499`로 요청 duration을 기록하고, 반드시 같은 예외를 다시 raise한다.
- `KTG_API_PERFORMANCE_LOGGING_ENABLED=true`일 때 취소 요청은 `api_request_cancelled` 로그로 남긴다.

## 관측 지표

새 Prometheus 지표:

- `kor_travel_geo_api_request_cancellations_total{method,route}`
- `kor_travel_geo_db_query_cancellations_total{operation,query_fingerprint}`

기존 DB query 지표에도 `status="cancelled"` label을 허용한다. SQLAlchemy `handle_error`에서 `asyncio.CancelledError` 또는 PostgreSQL `QueryCanceled` 중 "user request" cancel만 취소로 분류한다. Statement timeout은 취소가 아니라 기존 `error`로 남긴다.

## 검증

- 단위 테스트는 ASGI `http.disconnect` 메시지를 직접 넣어 `/v1/address/slow` handler가 취소되고, 응답을 보내지 않으며, API cancel counter와 `499` request metric이 노출되는지 검증한다.
- 메트릭 단위 테스트는 API cancel counter, DB query cancel counter, `asyncio.CancelledError` 분류를 고정한다.
- 선택형 통합 테스트 `tests/integration/test_query_cancellation.py`는 `KTG_TEST_PG_DSN`이 있을 때만 실행한다. Pool size 1 엔진에서 `SELECT pg_sleep(10)`이 active 상태가 된 뒤 task를 cancel하고, `pg_stat_activity`에 orphan `pg_sleep`이 남지 않으며 같은 pool에서 `SELECT 1`을 다시 실행할 수 있는지 확인한다.

## 남은 범위

- DB 단절·복구·IO 지연 chaos/fault injection은 T-159에서 별도로 검증한다.
- 장시간 soak에서 취소와 부하가 섞였을 때의 RSS/IO budget은 T-163/T-164의 고부하 gate에서 다룬다.
