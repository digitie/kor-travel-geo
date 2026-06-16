# T-144 성능 우선 v2/API 계약 후보 검증

## 결론

T-144에서는 새 공개 DTO 필드를 추가하지 않는다. 현재 v2 계약 중 성능에 직접 영향을 주는 다음 항목을 accepted profile로 고정한다.

- `include_geometry=false` 기본값 유지
- `response_model_exclude_none=True` 유지
- geocode `limit <= 100`, search `size <= 100` hard cap 유지
- endpoint별 `GeocodeV2Response`/`ReverseV2Response`/`SearchV2Response`는 유지하되, 후보 본문은 `CandidateV2` 공통 schema를 계속 공유
- payload/p99 budget은 benchmark artifact에서 별도 gate로 평가

새 schema version, field slim mode, detail expansion endpoint, pre-shaped response table은 이번 PR에서 구현하지 않는다. 근거가 생기면 T-105(v2 재audit) 또는 T-139(DB 구조 변경 실험)에서 별도 breaking change로 다룬다.

## 후보 평가

| 후보 | 판정 | 근거 |
|------|------|------|
| `include_geometry=false` 기본화 | 채택(이미 구현됨) | geometry는 payload와 추가 DB 조회 비용이 크다. 현재 기본값이 이미 `false`이며, debug UI처럼 필요한 호출만 `true`를 보낸다. |
| geometry endpoint 분리 | 보류 | `include_geometry` opt-in으로 같은 효과를 얻는다. 별도 endpoint는 OpenAPI/typegen/UI 경로를 늘리지만 T-138 병목의 주 원인인 SQL/pool tail을 줄이지 않는다. |
| response field slim mode | 보류 | FastAPI `response_model_exclude_none=True`로 null field는 이미 빠진다. 새 `fields=slim` 같은 모드는 UI/SDK 분기를 늘리고, 현재 payload가 p99 병목이라는 증거가 부족하다. |
| detail expansion endpoint | 보류 | 상세주소 typed 후보와 다중 point 계약이 아직 없다. T-105에서 `candidate_id`/`point_type` 논의와 함께 다룬다. |
| reverse/geocode/search 분리 응답 schema | 부분 채택(현 상태 유지) | top-level response class는 이미 분리되어 있다. 후보 본문을 endpoint별로 쪼개면 type drift가 커지고 dedup/merge helper 재사용성이 떨어진다. |
| pagination/limit hard cap | 채택(이미 구현됨) | `GeocodeV2Input.limit`과 `Page.size`는 모두 `le=100`이다. 이번 PR에서 회귀 테스트로 고정한다. |
| admin summary 전용 endpoint | 보류 | 운영 artifact 요약은 T-222/T-265 Admin 경로가 담당한다. 공개 주소 API 계약 변경으로 다루지 않는다. |
| streaming/progress endpoint 분리 | 보류 | 주소 조회는 단발 read API다. 장기 작업 진행률은 이미 load/backup job SSE 표면에 있다. |
| pre-shaped response table에 맞춘 DTO 재배치 | 보류 | DB 구조 변경 실험(T-139)에서 같은 corpus로 latency/storage/backup 영향을 먼저 비교해야 한다. |

## 선택한 계약

### 기본 응답

기본 geocode 응답은 geometry와 bbox를 싣지 않는다. `include_geometry=true`를 명시한 호출에서만 후보별 geometry enrich가 붙는다.

```json
{
  "status": "OK",
  "input": {
    "query": "서울특별시 동대문구 왕산로 189-4",
    "limit": 10,
    "fallback": "none",
    "include_geometry": false
  },
  "candidates": [
    {
      "confidence": 1.0,
      "match_kind": "road",
      "address": {
        "type": "road",
        "full": "서울특별시 동대문구 왕산로 189-4",
        "road_name": "왕산로"
      },
      "point": {"x": 127.044, "y": 37.58},
      "point_precision": "exact",
      "source": "local",
      "metadata": {}
    }
  ]
}
```

### 상한

- geocode 후보 수: `1 <= limit <= 100`
- search page size: `1 <= size <= 100`
- reverse 반경: 기존 `1 <= radius_m <= 2000`

상한을 늘리는 변경은 T-141/T-164 계열 benchmark와 payload gate를 함께 갱신해야 한다.

## Benchmark gate

`scripts/evaluate_t144_api_contract.py`는 `scripts/benchmark_api_latency.py`의 `api-report.json`을 읽어 summary row별 p99와 평균 응답 크기를 확인한다.

```bash
python scripts/evaluate_t144_api_contract.py \
  --api-report artifacts/perf/t144-rest/api-report.json \
  --p99-budget-ms 500 \
  --avg-response-budget-bytes 65536 \
  --mode enforce \
  --output artifacts/perf/t144-api-contract/contract-report.json
```

기본 budget은 다음과 같다.

- p99: 500ms
- 평균 응답 크기: 64KiB
- error: 0

이 gate는 즉시 CI 필수 조건으로 묶지 않는다. T-141/T-164 nightly 후보와 같은 artifact 계열로 먼저 사용한다.

## Migration note

이번 PR은 wire schema를 바꾸지 않는다. 따라서 OpenAPI/typegen migration은 없다. 다만 아래 항목은 새 계약으로 문서화한다.

- geometry는 기본 응답에 없다.
- null field는 응답에서 빠진다.
- 후보/page 상한은 100이다.
- payload/p99 budget 초과는 contract drift 후보로 본다.

## Golden response test

`tests/unit/test_t144_api_contract.py`는 다음을 고정한다.

- 기본 `GeocodeV2Response.model_dump(exclude_none=True)`에는 후보 `geometry`/`bbox`가 없다.
- `GeocodeV2Input.limit=101`, `SearchV2Input.size=101`은 validation error다.
- v2 라우터는 `response_model_exclude_none=True`를 유지한다.
- benchmark report 평가기가 p99/payload budget 초과를 실패로 판정한다.

## 검증

- Windows focused unit: `tests/unit/test_t144_api_contract.py` 4 passed
- Windows Ruff: `scripts/evaluate_t144_api_contract.py`, `tests/unit/test_t144_api_contract.py` 통과
- WSL ext4 미러: `pytest -q` 959 passed/54 skipped, Ruff, mypy, `lint-imports`, OpenAPI check 통과

## UI 반영 계획

이번 PR은 OpenAPI를 바꾸지 않으므로 `kor-travel-geo-ui` typegen은 필요 없다.

후속에서 실제 DTO field를 바꾸는 경우에는 다음 순서를 따른다.

1. ADR 또는 T-105 문서에서 wire 변경을 먼저 확정한다.
2. backend DTO/route/test를 변경한다.
3. `scripts/export_openapi.py`로 OpenAPI를 갱신한다.
4. `kor-travel-geo-ui`에서 `gen:types`, 관련 Zod/schema mirror, debug/admin 화면을 갱신한다.
5. UI lint/type/test/build와 필요한 Playwright e2e를 실행한다.
