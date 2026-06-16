# T-145 운영 backpressure·fail-fast 보강

## 범위

T-145는 T-141 고부하 matrix 이후 API가 포화 상태에서 오래 대기하다 무너지는 대신, process 내부에서 예측 가능하게 제한하고 관측할 수 있게 만드는 작업이다. DB pool checkout timeout은 T-154에서, DB readiness는 T-160에서 이미 닫았으므로 이번 범위는 HTTP admission control, overload envelope, Prometheus 지표, readiness degradation 신호로 좁혔다.

이번 PR은 client disconnect/query cancellation(T-161), DB 단절·복구 fault injection(T-159), 60분 soak budget(T-163), slow query 표본 persist(T-158)는 구현하지 않는다. 해당 작업들은 각 전용 task에서 실제 부하/장애 주입과 함께 검증한다.

## 설정

기존 `KTG_API_MAX_CONCURRENCY`는 그대로 process별 전역 공개 주소 API cap으로 유지한다. 여기에 endpoint scope별 cap을 추가했다.

| 설정 | 적용 scope | 경로 |
|------|------------|------|
| `KTG_API_MAX_CONCURRENCY` | `address` | `/v1/address/*`, `/v2/*` 전체 |
| `KTG_API_GEOCODE_MAX_CONCURRENCY` | `geocode` | `/v1/address/geocode`, `/v2/geocode` |
| `KTG_API_REVERSE_MAX_CONCURRENCY` | `reverse` | `/v1/address/reverse`, `/v2/reverse` |
| `KTG_API_SEARCH_MAX_CONCURRENCY` | `search` | `/v1/address/search`, `/v2/search` |
| `KTG_API_ZIPCODE_MAX_CONCURRENCY` | `zipcode` | `/v1/address/zipcode` |
| `KTG_API_POBOX_MAX_CONCURRENCY` | `pobox` | `/v1/address/pobox` |
| `KTG_API_REGIONS_MAX_CONCURRENCY` | `regions` | `/v2/regions/within-radius` |

모든 값은 unset이면 비활성이다. 전역 cap과 endpoint cap을 함께 설정하면 요청은 endpoint scope를 먼저 얻고, 이어서 전역 `address` scope를 얻는다. 이 순서는 특정 endpoint가 포화됐을 때 전역 slot을 오래 잡지 않게 하기 위한 것이다.

Admission 대기 시간은 기존 `KTG_API_ADMISSION_TIMEOUT_MS`를 사용한다. 여러 scope를 얻어야 하는 요청도 하나의 deadline 안에서 처리하며, deadline을 넘으면 이미 얻은 slot을 모두 반납하고 overload 응답을 반환한다.

## Overload 응답

Admission timeout은 `RateLimitError(E0200, HTTP 429)`로 변환한다. 비 VWorld 경로는 기존 구조화 오류 envelope를 사용하고, `/v1/address/geocode`·`/v1/address/reverse`는 VWorld 호환 오류 코드 `OVER_REQUEST_LIMIT`를 유지한다.

응답 header는 다음을 포함한다.

- `Retry-After: 1`
- `Cache-Control: no-store`

서버 내부에서 같은 요청을 자동 재시도하지 않는다. 호출자는 overload 응답을 명시 실패로 처리하고, 외부 rate limiter나 caller concurrency를 낮추는 방향으로 대응해야 한다.

## 지표

`/metrics`에 다음 Prometheus 지표를 추가했다.

| 지표 | type | label | 의미 |
|------|------|-------|------|
| `kor_travel_geo_api_admission_wait_seconds` | histogram | `method`, `route`, `scope`, `outcome` | admission slot 대기 시간. `outcome`은 `accepted` 또는 `rejected` |
| `kor_travel_geo_api_admission_rejections_total` | counter | `method`, `route`, `scope` | admission timeout으로 거절한 요청 수 |
| `kor_travel_geo_api_admission_in_progress` | gauge | `scope` | 현재 process에서 admission slot을 점유한 요청 수 |

기존 API request duration, slow request, DB pool gauge, pool checkout timeout counter와 함께 보면 "요청 폭주 → admission 대기/거절 → DB pool 포화" 흐름을 분리해서 볼 수 있다.

## Readiness 신호

`/v1/readyz`는 admission 설정이 활성화된 경우 `components.admission`을 추가한다.

```json
{
  "status": "degraded",
  "ready": true,
  "degraded": true,
  "components": {
    "admission": {
      "status": "saturated",
      "detail": {
        "timeout_ms": 30000,
        "max_utilization": 1.0,
        "scopes": [
          {
            "scope": "geocode",
            "limit": 1,
            "in_use": 1,
            "available": 0,
            "utilization": 1.0
          }
        ]
      }
    }
  }
}
```

Admission saturation은 DB 단절과 달리 process가 아직 요청을 처리할 수 있는 상태이므로 readiness HTTP status는 200을 유지하고 `ready=true`, `degraded=true`로 표시한다. DB 단절·pool 포화는 T-160/T-154 정책대로 503을 유지한다.

## 검증

Windows focused run:

```powershell
python -m pytest tests/unit/test_api_admission_control.py tests/unit/test_health_readiness.py tests/unit/test_metrics.py tests/unit/test_settings.py -q
python -m pytest tests/unit/test_geoip_gate.py tests/unit/test_api_app_contract.py -q
python -m ruff check src/kortravelgeo/api/app.py src/kortravelgeo/api/admission.py src/kortravelgeo/api/routers/healthz.py src/kortravelgeo/infra/metrics.py src/kortravelgeo/settings.py tests/unit/test_api_admission_control.py tests/unit/test_health_readiness.py tests/unit/test_metrics.py tests/unit/test_settings.py
python -m mypy src/kortravelgeo/api/admission.py src/kortravelgeo/api/routers/healthz.py src/kortravelgeo/infra/metrics.py src/kortravelgeo/settings.py
```

Windows 전체 mypy는 현재 로컬 환경에 GDAL `osgeo` import/stub이 없어 기존 loader 파일에서 실패했다. 공식 전체 gate는 WSL ext4 테스트 미러에서 확인했다.

WSL ext4 test mirror:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy src/kortravelgeo
lint-imports
python scripts/export_openapi.py --check --output openapi.json
```

결과는 `pytest` 863 passed/53 skipped, Ruff 통과, mypy 통과, import-linter `Layered architecture KEPT`, OpenAPI drift 0이다.
