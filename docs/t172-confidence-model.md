# T-172 confidence 산정 결정성·교정 중앙 모델

작성일: 2026-06-16

## 결론

T-172에서는 v1/v2 후보 confidence 산정을 `src/kortravelgeo/core/confidence.py`로 모았다.
기존에는 geocode centroid cap, 국가지점번호 confidence, reverse distance score, external fallback
confidence가 각각 호출부에 상수로 흩어져 있었다. 이제 공개 응답에 들어가는 confidence 값은
다음 helper를 거친다.

- `geocode_lookup_confidence()`: local 도로명/지번 후보 confidence를 0~1로 clamp하고,
  `pt_source="centroid"`이면 `0.82`로 cap을 둔다.
- `sppn_geocode_confidence()` / `sppn_reverse_confidence()`: 국가지점번호 10m grid cell
  후보를 `0.72`로 고정한다.
- `reverse_distance_confidence()`: `1 - distance_m / radius_m` 선형식으로 산정하고 0~1로
  clamp한다. 거리가 멀수록 confidence가 단조 감소한다.
- `external_geocode_confidence()`: VWorld fallback은 `0.70`, Juso fallback은 `0.65`다.
- `search_confidence()` / `geometry_confidence()`: SQL score를 0~1로 clamp하고,
  geometry 보조 후보의 score가 없으면 `0.90`을 사용한다.

SPPN reverse 후보는 기존 `1.0`에서 `0.72`로 낮췄다. 국가지점번호는 10m cell 중심 좌표라
exact 주소 대표점과 같은 의미의 확정 match가 아니기 때문이다. 후보 순서나 v1/v2 schema는
변경하지 않았다.

## 검증

- `tests/unit/test_confidence.py`가 clamp, centroid cap, reverse distance 단조성,
  match family 기준값 순서를 고정한다.
- `tests/unit/test_v2_api.py`가 reverse SPPN 후보 confidence를 중앙 상수로 확인한다.
- `tests/unit/test_external_api.py`가 VWorld/Juso fallback confidence를 확인한다.
- T-140 corpus의 `T140-GEO-SPPN-001`은 `candidates[0].confidence = 0.72`를 golden field로
  고정한다.

## 영향

OpenAPI schema 변경은 없다. 값 의미만 정리한 변경이므로 frontend typegen은 필요하지 않다.
다만 SPPN reverse v2 후보의 confidence 값은 `1.0`에서 `0.72`로 바뀐다.
