# 주소 DB 스키마

공간 제공 스키마는 하나의 SQLite 데이터베이스를 중심으로 구성한다. SpatiaLite 확장을 사용할 수 있으면 지오메트리 컬럼과 공간 인덱스를 추가하고, 사용할 수 없는 환경에서도 `x`, `y`, WKT, WKB 컬럼으로 기본 조회가 동작하도록 유지한다.

## `juso_address_points`

모든 주소 좌표 후보를 저장한다.

- `point_id`: 원천 데이터에서 파생한 안정 키
- `source`: 원천 파일 또는 로더 이름
- `source_dataset`: `location_summary`, `navigation_building`, `navigation_road_section_entrance`
- `source_priority`: 중복 후보가 있을 때 낮은 값이 우선
- `coordinate_role`: `entrance`, `building_center` 등 좌표 역할
- `road_name_code`, `underground_yn`, `building_main_no`, `building_sub_no`: 도로명주소 정확 매칭 키
- `legal_dong_code`, `postal_code`: 법정동 코드와 우편번호
- `road_address`, `building_name`: 표시용 주소/건물명
- `x`, `y`, `srid`: 저장 좌표와 좌표계
- `geom_wkt`, `geom_wkb`: 공간 엔진 호환 지오메트리 표현
- `raw_json`: 원천 행 세부 정보

## `juso_boundary_polygons`

지역별 ZIP에 포함된 모든 SHP에서 추출한 행정구역 다각형 레이어를 저장한다.

- `source_system`: 원천 시스템 이름
- `source_file`: 원천 파일 경로 또는 파일명
- `source_layer`: `tl_scco_sig` 같은 원본 SHP 파일명 줄기
- `source_code`, `source_name`: 원천 코드와 이름
- `legal_dong_code`: 연결 가능한 법정동 코드
- `boundary_level`: 시도/시군구/읍면동 등 경계 수준
- `mapping_status`: 매핑 검증 상태
- `geom_wkt`, `geom_wkb`: 지오메트리 표현
- `raw_json`: 원천 속성 전체

## `juso_spatial_metadata`

로더 실행 시각, 원천 이름, 운영 메모 같은 작은 key/value 메타데이터를 저장한다.

## Alembic

`alembic/versions/0001_spatialite_core.py`가 핵심 테이블과 인덱스를 만든다. 지오메트리 컬럼은 런타임 저장소가 SpatiaLite 로드 가능 여부를 확인한 뒤 추가한다.
