# v2 API 공통 규약

v2(자체 통합 candidate, ADR-039)의 endpoint 공통 규약이다. 각 endpoint 상세는 `geocode.md`,
`reverse.md`, `search.md`, `regions-within-radius.md`를, 차원별 audit/목표는 `conventions.md`를,
결정·우선순위는 ADR-060을 본다. v1 vworld 호환(ADR-038)은 별개 표면이며 이 규약과 무관하다.

## 메서드 · trace (ADR-060 §7)

- **v2는 모두 `POST`** 다. 다중 surface(`query`/`road_address`/…), `bbox`, region hint 같은
  구조화 입력을 body로 받기 때문이다. GET은 지원하지 않는다(v1 vworld는 GET).
- **`query_id`** 가 공식 trace 키다. 성공 응답 header(`status`/`query_id`/`input`)에 담기며,
  요청별로 새로 발급한다. v1의 `ServiceMeta`(vworld 호환)와 분리한다.

## 응답 envelope (ADR-060 §1)

- 후보 endpoint(geocode/reverse/search)는 공통 header `{status, query_id, input}` 위에
  `candidates`(+ search는 `total`)를 둔다.
- `regions/within-radius`는 현재 이 공통 header 없이 `center`/`radius_km`/레벨별 배열만 반환한다.
  공통 header로 올리는 것은 **breaking이라 v2 배포 직전 묶음으로 연기**(ADR-060 §1, 우선순위 ③).

## 페이지네이션 (ADR-060 §3)

| 분류 | endpoint | 방식 |
|------|----------|------|
| ranked-candidate | `geocode` | `limit`(≤100)로 상위 N 후보. `page`/`total` 없음 — 정렬된 best-match는 페이징 대상이 아니다. |
| ranked-candidate | `reverse` | `page`/`total`/`limit` 모두 없음. `radius_m`로 검색 반경만 제어하고 후보는 거리순으로 반환한다. |
| collection | `search` | `page`/`size`(≤100) + `total`. |
| 공간 그룹 | `regions/within-radius` | 레벨별(`sido`/`sigungu`/`emd`) 배열. 공간 조회는 페이징하지 않는다. |

## 좌표 · 반경 단위 (ADR-060 §6)

- 외부 입력 좌표는 `lon`/`lat`(reverse·regions), bbox는 `min_lon`/`min_lat`/`max_lon`/`max_lat`.
- **반경은 단위 suffix를 항상 드러낸다**: `radius_m`(미터, reverse) · `radius_km`(킬로미터, regions).
  점-수준 조회는 미터, 지역-수준 조회는 km가 자연스러우므로 단위 통일 대신 suffix 규약을 쓴다.
- 후보 출력 좌표는 현재 `point: {x, y}`(x=lon, y=lat)다. `{lon, lat}` 노출은 **breaking이라
  v2 배포 직전 묶음으로 연기**(ADR-060 §6, 우선순위 ④).

## geometry opt-in (ADR-060 §5, ADR-059)

- candidate를 반환하는 모든 endpoint(geocode/reverse/search)가 `include_geometry`(기본 `false`)를
  대칭으로 받는다. `bbox`(EPSG:4326 비교 범위)는 geocode/search 입력에만 둔다(reverse는 이미 점+radius).
  **현재 `bbox`는 입력/응답 schema 보존용 echo이고, 엄격한 공간 필터는 후속**이다(`geocode.md`/`search.md`).
- geometry는 후보가 도형 조회 key를 가질 때 채워진다(`region`→region polygon, 건물 key 있는
  `road`/`parcel`→building polygon). key가 없으면 DTO에서는 `None`이고, v2 라우터는
  `response_model_exclude_none=True`라 **REST 응답에서는 `geometry`/`bbox` 필드가 생략**된다(`null` 아님).
  상세는 각 endpoint 문서.

## 변경 정책

- v2는 미배포 candidate라 breaking이 가능하나, 각 변경은 backend DTO + frontend typegen
  (`api.gen.ts`/`schemas.gen.ts`)을 동반하고 OpenAPI drift 0을 유지한다(ADR-059).
- breaking 묶음(enum 정직화 §2 · envelope/error 통일 §1/§4 · 좌표 lon/lat §6)은
  v2 배포 직전 한 번에 적용해 typegen/UI 분기 비용을 최소화한다(ADR-060 §9).
