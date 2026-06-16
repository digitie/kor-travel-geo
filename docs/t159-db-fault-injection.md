# T-159 DB 단절·복구·IO 지연 장애 주입

## 목적

DB 단절, 복구, 느린 DB probe 상황에서 API가 crash 없이 안정적으로 저하되는지 검증한다.

합격 기준은 다음이다.

- DB 단절 중 공개 API 요청은 HTTP 503 + `E0500`으로 빠르게 실패한다.
- VWorld 호환 경로(`/v1/address/geocode`, `/v1/address/reverse`)는 기존 `SYSTEM_ERROR` envelope를 유지한다.
- `/v1/readyz`는 단절 또는 timeout을 `ready=false`, `degraded=true`, HTTP 503으로 노출한다.
- DB가 다시 정상화되면 같은 프로세스에서 `/v1/readyz`와 공개 API가 자동으로 200으로 회복된다.
- 응답 payload에 SQL 문장, 파라미터, DSN, secret 값이 노출되지 않는다.

## 구현

`api/responses.py`는 SQLAlchemy pool checkout timeout 외에 `DBAPIError` 계열을 별도 처리한다. 공개 응답은 고정 메시지 `database operation failed`와 운영 힌트만 포함하며, 내부 예외 문자열이나 SQL 원문은 반환하지 않는다.

Prometheus에는 API 레벨 DB 드라이버 오류 counter를 추가했다.

```text
kor_travel_geo_api_db_errors_total{method,route,error_type}
```

기존 지표와 역할은 다음처럼 나뉜다.

| 지표 | 의미 |
|------|------|
| `kor_travel_geo_pg_pool_checkout_timeouts_total` | SQLAlchemy pool checkout timeout |
| `kor_travel_geo_api_db_errors_total` | 공개 API까지 올라온 DB 드라이버/연결 오류 |
| `kor_travel_geo_db_queries_total{status="error"}` | SQLAlchemy query 계측에서 잡은 DB 실행 오류 |
| `kor_travel_geo_db_query_cancellations_total` | client disconnect 또는 PostgreSQL user cancel로 취소된 query |

`/v1/readyz`는 T-160에서 만든 구조를 유지한다. DB probe가 `KTG_API_READINESS_TIMEOUT_MS` 안에 끝나지 않으면 `components.database.error_type="TimeoutError"`와 HTTP 503을 반환한다. Pool 포화는 새 DB checkout 없이 `database.status="skipped"`로 fail-fast한다.

## 재현 스크립트

`scripts/run_t159_db_fault_injection.py`는 실제 PostgreSQL/RustFS를 시작·중지·재시작하지 않는다. FastAPI 앱과 가짜 engine을 ASGI in-process로 띄운 뒤 `ok → down → slow → ok` 순서로 상태를 바꾸며 같은 exception handler, readiness router, VWorld error envelope를 검증한다.

```bash
python scripts/run_t159_db_fault_injection.py \
  --run-id t159-local \
  --output-dir artifacts/chaos/t159-local
```

산출물은 다음이다.

- `fault-report.json`: schema version, 환경, 각 check의 HTTP status/latency/pass 여부
- `summary.md`: 사람이 읽는 요약표

기본 check는 다음 순서로 실행된다.

| check | 기대 |
|-------|------|
| `baseline-readyz` | 정상 DB, `/v1/readyz` 200 |
| `disconnect-readyz` | DB 단절, `/v1/readyz` 503 fast-fail |
| `disconnect-public-api` | DB 단절, `/v1/address/geocode` 503 fast-fail |
| `slow-io-readyz` | 느린 DB probe, readiness timeout 503 fast-fail |
| `recovered-readyz` | 복구 후 `/v1/readyz` 200 |
| `recovered-public-api` | 복구 후 공개 API 200 |

## 검증

단위 테스트는 다음을 고정한다.

- `tests/unit/test_api_responses.py`: `OperationalError`가 일반 경로와 VWorld 경로에서 HTTP 503으로 구조화된다. SQL/파라미터 원문은 응답에 노출되지 않는다.
- `tests/unit/test_health_readiness.py`: 느린 DB probe가 readiness timeout으로 빠르게 끊기고, 같은 engine이 정상화되면 다음 요청이 200으로 회복된다.
- `tests/unit/test_metrics.py`: `kor_travel_geo_api_db_errors_total` 지표가 노출된다.

작업 중 확인한 focused 실행:

```bash
python -m pytest tests/unit/test_api_responses.py tests/unit/test_health_readiness.py tests/unit/test_metrics.py -q
python scripts/run_t159_db_fault_injection.py --run-id t159-focused --output-dir .tmp/t159-focused
python -m ruff check src/kortravelgeo/api/responses.py src/kortravelgeo/infra/metrics.py tests/unit/test_api_responses.py tests/unit/test_health_readiness.py tests/unit/test_metrics.py scripts/run_t159_db_fault_injection.py
```

## 범위 밖

이 작업은 PostgreSQL 프로세스나 네트워크를 실제로 끊지 않는다. 저장소 정책상 PostgreSQL/RustFS 생명주기는 이 저장소가 직접 제어하지 않기 때문이다. 실제 운영망에서 DB 네트워크 차단, 장애 복구 시간, 드라이버 재연결 tail을 측정하는 장시간 실험은 별도 환경에서 T-163/T-164 soak·회귀 gate와 함께 수행한다.
