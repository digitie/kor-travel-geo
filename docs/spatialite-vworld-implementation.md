# SpatiaLite 및 VWorld 호환 지오코딩 계획

이 구현은 SQLite를 기본 DB로 사용하고, 로컬 확장을 로드할 수 있을 때 SpatiaLite를 활성화한다. 같은 테이블에는 일반 `x`, `y`, WKT, WKB 값도 보존하므로 확장을 사용할 수 없는 환경에서도 라이브러리를 사용할 수 있다.

## 데이터 우선순위

1. `location_summary`: 위치정보요약DB의 공식 Juso 출입구 좌표
2. `navigation_building`: 내비게이션용DB의 건물 중심/출입구 좌표
3. `navigation_road_section_entrance`: 도로 구간 출입구 보조 행
4. `juso_boundary_shapes`: 포함 관계와 행정 검증을 위한 구역 다각형
5. `rnaddrkor.sqlite`: 기존 도로명주소 속성과 관련 지번 데이터

## 테이블

- `juso_address_points`: 지오코딩/역지오코딩 후보 포인트
- `juso_boundary_polygons`: 구역 다각형 WKT/WKB와 원천 메타데이터
- `juso_spatial_metadata`: 로더 메타데이터와 운영 메모

포인트 테이블은 `source_priority`, `coordinate_role`, 도로명주소 key 컬럼, 법정동 코드, 우편번호, 원천 주소 문자열, EPSG:5179 좌표, 원천 JSON을 저장한다.

## 인덱싱

핵심 조회 인덱스는 다음과 같다.

- 정확한 도로명주소 key 조회: `(road_name_code, underground_yn, building_main_no, building_sub_no)`
- 우편번호 조회: `postal_code`
- 범위 제한 최근접 후보 검색: `(x, y)`
- 필터링: `legal_dong_code`, `source_dataset`, `coordinate_role`, `source_priority`
- 다각형 검증: 경계 원천/레이어/코드 및 법정동 인덱스

SpatiaLite를 사용할 수 있으면 지오메트리 컬럼과 공간 인덱스를 같은 DB에 추가한다.

## VWorld 호환 표면

`SpatialiteAddressStore.get_coord()`는 `AddressGeocodeRequest`를 받는다.
`SpatialiteAddressStore.get_address()`는 `AddressReverseGeocodeRequest`를 받는다.
`lookup_postal_code()`는 `PostalCodeLookupRequest`를 받는다.

로컬 후보가 없고 VWorld 키/도메인이 설정되어 있으면 저장소는 `python-vworld-api`를 호출하고 응답을 같은 후보 DTO로 정규화한다.
