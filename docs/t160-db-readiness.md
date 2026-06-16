# T-160 DB readiness/degradation 신호

2026-06-16에 완료했다.

## 목표

`/v1/healthz`는 프로세스 liveness로 유지하고, DB와 SQLAlchemy pool 상태를 반영하는 별도 readiness 표면을 둔다. 운영자는 DB 단절, API 시작 미완료, pool 포화, pool 고부하를 같은 응답 구조로 구분할 수 있어야 한다.

## 구현

- `GET /v1/healthz`: 기존처럼 DB를 건드리지 않고 `{"status":"ok"}`만 반환한다.
- `GET /v1/readyz`: `ReadinessResponse` DTO로 `status`, `ready`, `degraded`, `components.database`, `components.pool`을 반환한다.
- `api_readiness_timeout_ms`: readiness DB probe timeout 설정이다. 기본값은 `1000`ms다.
- DB probe는 `SELECT current_database(), current_setting('server_version')`만 실행하고, 성공 시 database component를 `ok`로 표시한다.
- DB probe timeout 또는 예외는 HTTP 503, `ready=false`, `degraded=true`, database `status="unavailable"`로 반환한다.
- `app.state.client.engine`이 아직 없으면 HTTP 503, `reason="client_not_started"`를 반환한다.
- pool component는 `size`, `checked_in`, `checked_out`, `overflow`, `capacity`, `utilization`을 보고한다.
- pool이 capacity까지 checked-out이고 checked-in이 없으면 DB checkout을 새로 시도하지 않고 HTTP 503, pool `status="saturated"`, database `status="skipped"`를 반환한다.
- pool utilization이 `0.8` 이상이면 HTTP 200, `ready=true`, `degraded=true`, pool `status="degraded"`로 반환한다.

## 응답 의미

| 조건 | HTTP | `ready` | `degraded` | 설명 |
|------|------|---------|------------|------|
| DB probe 성공, pool 정상 | 200 | `true` | `false` | 트래픽 수신 가능 |
| DB probe 성공, pool utilization 0.8 이상 | 200 | `true` | `true` | 트래픽 수신은 가능하지만 운영 경고 |
| pool 포화 | 503 | `false` | `true` | 새 DB checkout을 만들지 않고 fail-fast |
| DB 단절/timeout | 503 | `false` | `true` | DB 의존 요청 수신 불가 |
| API client 미시작 | 503 | `false` | `true` | startup 미완료 또는 lifespan 문제 |

## 검증

- `tests/unit/test_health_readiness.py`에서 liveness, 정상 readiness, DB 실패, pool 포화 fail-fast, pool 고부하 degradation을 검증한다.
- `tests/unit/test_api_app_contract.py`가 `/v1/readyz` OpenAPI 경로를 고정한다.
- `tests/unit/test_settings.py`가 `api_readiness_timeout_ms=1000` 기본값을 고정한다.
- OpenAPI와 `kor-travel-geo-ui` 생성 타입을 갱신했다.
- WSL ext4 미러에서 backend `pytest`, Ruff, mypy, import-linter, OpenAPI check와 UI lint/type-check/test/build를 통과했다. React Doctor는 `errorCount=0`, 기존 경고 16건이다.

## 후속

T-154에서 engine pool timeout/fail-fast를 더 좁히고, T-145에서 overload error envelope와 endpoint-level backpressure를 정리한다. T-159에서는 실제 DB 단절·복구·IO 지연 주입으로 readiness 신호와 API 회복성을 재검증한다.
