# ADR-058: confidence 산정은 중앙 모델로 고정하고 SPPN grid 후보는 exact 주소보다 낮게 둔다

- 상태: accepted
- 날짜: 2026-06-16
- 결정자: codex
- 관련: T-172, T-140, T-166, T-168, T-169, T-171, ADR-038, ADR-055, ADR-056

## 컨텍스트

v2 후보 schema는 `confidence`를 public field로 갖지만, 실제 산정은 여러 위치에 흩어져 있었다.
geocode는 `pt_source="centroid"`일 때만 호출부에서 `0.82` cap을 적용했고, 국가지점번호 forward
geocode는 `0.72`, reverse SPPN 후보는 `1.0`, VWorld/Juso fallback은 각각 `0.70`/`0.65`,
reverse 주소 후보는 `1 - distance / radius`를 직접 계산했다. 이 구조는 새 후보 유형을 추가할
때 점수 의미가 쉽게 엇갈린다.

## 결정

1. 공개 confidence 산정 helper를 `kortravelgeo.core.confidence`에 둔다.
2. local exact 주소 후보의 기본 confidence는 `1.0`이고, `pt_source="centroid"` 후보는 `0.82`
   cap을 적용한다.
3. 국가지점번호 10m grid cell 후보는 geocode/reverse 모두 `0.72`로 둔다.
4. external fallback은 VWorld `0.70`, Juso `0.65`로 둔다.
5. reverse 주소 후보는 `1 - distance_m / radius_m` 선형식과 0~1 clamp를 유지한다.
6. search/geometry producer의 SQL score는 public candidate 변환 시 0~1로 clamp한다.
7. wire schema, enum, 후보 정렬 순서는 바꾸지 않는다.

## 근거

- SPPN은 10m cell 중심 계산 좌표이므로 `point_precision="grid_cell"`과 일관되게 exact 주소
  대표점보다 낮은 confidence가 맞다.
- Centroid 후보 cap은 `pt_source` coarse enum의 의미를 보존하면서 좌표 정밀도 차이를 표현한다.
- external fallback 점수는 provider 응답을 그대로 local DB exact 후보와 같은 신뢰도로 보지
  않겠다는 기존 정책을 유지한다.
- 중앙 helper는 새 후보 유형 추가 시 confidence 단조성 테스트를 한 곳에 모을 수 있다.

## 결과

- SPPN reverse v2 후보 confidence가 `1.0`에서 `0.72`로 바뀐다.
- T-140 `T140-GEO-SPPN-001`은 `confidence=0.72`를 golden으로 고정한다.
- OpenAPI/typegen 변경은 없다.

## 후속

- T-105 v2 재audit에서 `candidate_id`, `point_type`, confidence 설명 문구를 함께 재검토한다.
- T-173/T-176에서 negative·reverse boundary case를 추가할 때 distance confidence 경계값도
  필요하면 golden으로 좁힌다.
