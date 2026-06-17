# ADR-059: T-144 성능 우선 API 계약은 기존 v2 기본값과 상한을 고정하고 큰 breaking change는 근거가 생길 때 분리한다

- 상태: accepted
- 날짜: 2026-06-16
- 결정자: codex
- 관련: T-144, T-105, T-138, T-139, T-141, T-164, T-170, ADR-056, ADR-057

## 컨텍스트

T-144는 배포 전이라는 전제를 반영해 성능과 안정성에 유리한 API 계약 변경 후보를 검토했다.
후보에는 geometry 기본 제외, field slim mode, detail expansion endpoint, endpoint별 응답 schema 분리,
pagination/limit hard cap, streaming/progress 분리, pre-shaped response table에 맞춘 DTO 재배치가 있었다.

이미 T-138/T-141 계열 측정에서 주요 tail은 SQL/pool/read path 영향이 컸고, v2 계약에는
`include_geometry=false`, `response_model_exclude_none=True`, `limit`/`size` 상한 100이 이미 들어 있다.
따라서 근거 없이 새 wire mode를 늘리면 latency보다 typegen/UI/SDK 분기 비용이 먼저 커질 수 있다.

## 결정

1. T-144는 새 공개 DTO field, 새 endpoint, schema version bump를 만들지 않는다.
2. v2 geocode의 `include_geometry=false` 기본값을 성능 기준 계약으로 고정한다.
3. v2 라우터의 `response_model_exclude_none=True`를 payload slim 기본 계약으로 고정한다.
4. `GeocodeV2Input.limit <= 100`과 `SearchV2Input.size <= 100`을 hard cap으로 유지한다.
5. geocode/reverse/search top-level response class는 분리된 현 상태를 유지하되, 후보 본문은 `CandidateV2` 공통 schema를 계속 공유한다.
6. payload와 p99 budget은 `scripts/evaluate_t144_api_contract.py`로 benchmark artifact에서 판정한다.
7. geometry endpoint 분리, field slim mode, detail expansion endpoint, pre-shaped DTO/table 재배치는 T-105 또는 T-139에서 근거가 생길 때 별도 breaking change로 다룬다.

## 근거

- Geometry payload는 크고 추가 조회를 유발할 수 있으므로 기본 제외가 맞다. 필요한 debug/UI 호출만 opt-in한다.
- Null field 제외는 이미 FastAPI response model 설정으로 적용되어 있다. 별도 `fields=slim` mode는 클라이언트 분기만 늘릴 가능성이 높다.
- 후보 공통 schema는 T-170 dedup/merge helper와 맞물려 있다. endpoint별 후보 schema로 쪼개면 type drift와 변환 중복이 늘어난다.
- 상한 100은 high-concurrency matrix에서 caller 폭주를 막는 단순하고 방어적인 계약이다.
- Pre-shaped response table은 DB 구조·저장공간·backup/restore 영향이 있으므로 T-139의 같은 corpus 비교 없이 API 계약으로 먼저 끌어올리지 않는다.

## 결과

- OpenAPI와 frontend typegen drift는 없다.
- T-144는 문서·ADR·단위 테스트·benchmark 평가 script로 현재 성능 우선 계약을 고정한다.
- 향후 payload/p99 budget 초과가 반복되면 `scripts/evaluate_t144_api_contract.py` artifact를 근거로 T-105/T-139 후속 변경을 연다.

## 후속

- T-105 v2 재audit에서 error model, `candidate_id`, `point_type`, geometry/detail expansion 정책을 계속 검토한다. → ADR-060에서 차원별 컨벤션으로 정리.
- T-139 DB 구조 변경 실험이 필요해지면 pre-shaped response table 후보를 현재 계약과 같은 corpus로 비교한다.
- UI에서 geometry opt-in을 쓰는 화면은 request body에 `include_geometry=true`를 명시한다. 기본 호출은 geometry 없는 후보 응답을 전제로 둔다.
