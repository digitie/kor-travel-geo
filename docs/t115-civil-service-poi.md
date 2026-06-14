# T-115 민원행정기관 POI 거리 검증

`민원행정기관전자지도`는 주소 정본이 아니라 기관 POI 원천이다. 따라서 이번 작업은 일반 주소 후보나 `mv_geocode_target`에 기관명/기관 좌표를 섞지 않고, 원천 SHP point와 기존 도로명주소 geocoder 대표점 사이의 거리만 검증하는 prototype으로 제한한다.

## 원천

실데이터 파일은 `data/juso/민원행정기관전자지도_240124.zip`이다.

ZIP 안에는 한 개의 SHP/DBF/SHX/PRJ 세트가 있으며, 일부 ZIP 도구에서는 파일명이 CP949 원문 대신 mojibake로 보일 수 있다. C15 loader는 member 이름에 의존하지 않고 suffix로 단일 SHP/DBF를 찾는다.

DBF 필드는 CP949 한글 field name이다.

| field | 사용 |
|-------|------|
| `유형` | sample context |
| `상세분류` | sample context |
| `시군구코드` | sample context |
| `도로명코드` | sample context |
| `도로명주소` | geocoder lookup 입력 |
| `기관명` | sample context |
| `위치X`, `위치Y` | 원천 좌표 확인용 context |
| `전화번호` | sample context |

SHP geometry는 EPSG:5179 계열 point로 읽는다.

## 구현

새 모듈은 `src/kortravelgeo/loaders/c15_civil_service_poi.py`이다.

1. ZIP 안의 단일 `.shp`/`.dbf`를 읽는다.
2. DBF field name을 `cp949`로 decoding한다.
3. `도로명주소`를 기존 `parse_address()`로 파싱한다.
4. staging table `_ktg_c15_civil_service_poi`에 POI point, 기관 context, 파싱된 도로명주소 key를 COPY한다.
5. `mv_geocode_target`을 batch exact road lookup 조건으로 join한다.
6. `ST_Distance(POI point, geocoder pt_5179)`로 거리 p50/p95/max와 outlier sample을 만든다.

batch SQL은 `GeocodeRepository.lookup_by_road()`의 exact lookup 핵심 조건을 재현한다. 즉 `rn_nrm`, 건물 본번/부번, 지상/지하 구분, 시도/시군구 조건, 출입구 우선 ordering을 사용한다. `pg_trgm` fuzzy fallback은 C15 prototype의 결정적 거리 비교에서 제외한다.

## 산출 metric

`C15CivilServicePoiComparison.metrics()`는 다음 값을 포함한다.

- `address_parse`: 도로명주소 파싱 성공/실패 row 수와 비율
- `geocode_distance_m`: geocoder match/missing/point-missing row 수, 거리 p50/p95/max, outlier 수와 비율
- `sample`: `distance_outlier`, `geocode_missing`, `geocode_point_missing`, `address_parse_failed`
- `serving_promotion=False`

기본 outlier 기준은 `100m`이다. 전국 실측 단계(T-121)에서는 기준월 차이와 기관 POI의 실제 출입구/건물대표점 차이를 함께 해석해야 한다.

## 금지선

- 기관명을 `v2/search` place 후보로 즉시 노출하지 않는다.
- 기관 point를 `mv_geocode_target` 대표 좌표 ranking에 섞지 않는다.
- vworld 호환 v1 응답에 `x_extension` 외 필드를 추가하지 않는다.

기관 검색이 필요해지면 별도 `match_kind="place"` 또는 admin/POI 전용 API로 설계한다.
