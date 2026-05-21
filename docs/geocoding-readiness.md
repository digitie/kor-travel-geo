# Geocoding 준비 상태

현재 구현은 Juso ZIP/TXT 데이터셋을 `juso_address_points`에 적재하면 로컬 geocoding과 reverse geocoding을 수행할 수 있는 상태다.

## 강한 입력 데이터

- 위치정보요약DB: 출입구 수준 좌표를 제공하므로 가장 가치가 높다.
- 내비게이션용DB: 건물 중심 좌표와 navigation 스타일 matching fallback에 유용하다.
- 구역의 도형: 포함 관계 검사, 법정동 검증, 누락 gap report에 유용하다.
- 도로명주소/관련지번 SQLite: 주소 문자열과 관련 지번 보강에 유용하다.

## 알려진 빈틈

- SpatiaLite extension 사용 가능 여부는 machine마다 다르다. 일반 index 컬럼만으로도 store는 동작하지만 polygon spatial predicate는 extension 또는 Shapely 평가가 필요하다.
- 일부 district SHP layer는 직접 법정동 polygon이 아니라 행정/서비스 구역일 수 있으므로 교차 검증 전까지 `mapping_status`는 `unverified`로 둔다.
- 도로명 fuzzy search에는 공백, 건물 alias, 과거 주소 형식을 다루는 normalization layer가 더 필요하다.
- Live VWorld fallback은 API credential이 필요하고 production에서는 rate limit을 적용해야 한다.

## 검증 checklist

- 전체 위치정보요약DB를 적재하고 row count를 확인한다.
- 최소 한 지역의 내비게이션용DB 파일을 적재하고 도로명주소 key 공유 여부를 비교한다.
- 17개 지역 구역의 도형 ZIP을 모두 적재하고 지역별 7개 layer를 확인한다.
- 도로명 key, 우편번호, nearest-neighbor 후보 query에 대해 `EXPLAIN QUERY PLAN`을 실행한다.
- `python-krmois-api` sample 주소를 로컬 geocoding/reverse geocoding 결과와 비교한다.
