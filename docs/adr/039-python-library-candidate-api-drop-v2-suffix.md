# ADR-039: Python 라이브러리는 후보 목록 API만 공개하고 `_v2` 접미사를 제거한다

- 상태: accepted
- 날짜: 2026-05-29
- 결정자: 사용자 요청, codex

## 컨텍스트

ADR-038은 REST 표면을 `/v1/*`와 `/v2/*`로 분리하면서 Python 라이브러리에도 `geocode_v2`, `reverse_v2`, `search_v2`를 추가했다. 그러나 사용자 요청에 따라 Python API에서는 v1-style 메서드를 삭제하고 v2 계약만 남기되, 메서드명에서 `v2` 글자를 제거해야 한다. REST v1은 기존 HTTP 소비자와 vworld 호환 계약 때문에 유지해야 하지만, Python 라이브러리 사용자는 새 후보 목록 schema를 기본으로 보게 하는 편이 단순하다.

## 결정

1. REST API 표면은 그대로 유지한다. `/v1/*`는 vworld 호환, `/v2/*`는 후보 목록 응답이다.
2. `AsyncAddressClient`의 공개 주소 조회 메서드는 `geocode()`, `reverse()`, `search()`만 둔다.
3. 공개 `geocode()`, `reverse()`, `search()`는 각각 `GeocodeV2Response`, `ReverseV2Response`, `SearchV2Response`를 반환한다.
4. `geocode_v2()`, `reverse_v2()`, `search_v2()`, `reverse_geocode()`는 공개 Python API에서 제거한다.
5. REST v1 라우터는 `AsyncAddressClient`의 private v1 adapter(`_geocode_v1`, `_reverse_geocode_v1`, `_search_v1`)를 호출한다. 이 adapter는 REST v1 호환을 위한 내부 구현 세부사항이며 문서화된 Python API가 아니다.
6. `geocode_many()`는 여러 query를 받아 `tuple[GeocodeV2Response, ...]`를 반환한다.
7. `fallback="api"`는 기존 vworld/juso fallback 결과를 내부 v1 DTO로 받은 뒤 후보 목록 응답으로 투영한다. Kakao/Naver/Google live 호출을 추가하지 않는다.

## 근거

- Python 라이브러리 사용자는 v1/v2 이름 선택보다 하나의 안정된 최신 계약을 기대한다.
- REST path의 versioning은 HTTP 계약에는 필요하지만, Python method 접미사로 중복 노출하면 API 표면이 불필요하게 넓어진다.
- vworld 호환 응답이 필요한 기존 소비자는 REST `/v1/*`를 그대로 사용할 수 있다.

## 결과

- `AsyncAddressClient.geocode()`, `reverse()`, `search()`가 후보 목록 응답의 표준 Python API가 된다.
- REST v1 회귀는 내부 어댑터 호출로 격리한다.
- 문서의 Python 예시는 접미사 없는 메서드로 갱신한다.

## 남은 위험

- 기존 Python 사용자가 vworld 호환 `GeocodeResponse`/`ReverseResponse`를 직접 기대했다면 호환성 깨짐이다. 현재 master는 아직 1.0 안정 릴리스 전이므로 전환 비용을 감수한다.
- 내부 v1 어댑터를 테스트하지 않으면 REST v1 회귀를 놓칠 수 있으므로 v1 라우터 테스트와 OpenAPI drift 검사를 계속 유지한다.
