# SpatiaLite 및 VWorld 호환 geocoding 계획

이 구현은 SQLite를 기본 DB로 사용하고, 로컬 extension을 로드할 수 있을 때 SpatiaLite를 활성화한다. 같은 테이블에는 일반 `x`, `y`, WKT, WKB 값도 보존하므로 extension을 사용할 수 없는 machine에서도 라이브러리를 사용할 수 있다.

## 데이터 우선순위

1. `location_summary`: 위치정보요약DB의 공식 Juso 출입구 좌표
2. `navigation_building`: 내비게이션용DB의 건물 중심/출입구 좌표
3. `navigation_road_section_entrance`: 도로 구간 출입구 보조 row
4. `juso_boundary_shapes`: 포함 관계와 행정 검증을 위한 구역 polygon
5. `rnaddrkor.sqlite`: 기존 도로명주소 속성과 관련 지번 데이터

## 테이블

- `juso_address_points`: geocoding/reverse geocoding 후보 point
- `juso_boundary_polygons`: 구역 polygon WKT/WKB와 원천 metadata
- `juso_spatial_metadata`: loader metadata와 운영 메모

Point table은 `source_priority`, `coordinate_role`, 도로명주소 key 컬럼, 법정동 코드, 우편번호, 원천 주소 문자열, EPSG:5179 좌표, 원천 JSON을 저장한다.

## Indexing

핵심 조회 index는 다음과 같다.

- 정확한 도로명주소 key lookup: `(road_name_code, underground_yn, building_main_no, building_sub_no)`
- 우편번호 조회: `postal_code`
- bounded nearest-neighbor scan: `(x, y)`
- filtering: `legal_dong_code`, `source_dataset`, `coordinate_role`, `source_priority`
- polygon 검증: boundary source/layer/code 및 법정동 index

SpatiaLite를 사용할 수 있으면 geometry 컬럼과 spatial index를 같은 DB에 추가한다.

## VWorld 호환 표면

`SpatialiteAddressStore.get_coord()` accepts `AddressGeocodeRequest`.
`SpatialiteAddressStore.get_address()` accepts `AddressReverseGeocodeRequest`.
`lookup_postal_code()` accepts `PostalCodeLookupRequest`.

로컬 후보가 없고 VWorld key/domain이 설정되어 있으면 store는 `python-vworld-api`를 호출하고 응답을 같은 후보 DTO로 정규화한다.
