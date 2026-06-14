# T-114 C14 국가지점번호 grid/center 검증 harness

T-114는 국가지점번호 도형 ZIP과 중심점 TXT를 상시 적재하지 않고 streaming으로 읽어 `core/sppn.py`의 parser/formatter와 100km/10km/1km/100m prefix grid 정합성을 검증하는 prototype이다. 이 작업은 **검증·overlay 후보 평가 전용**이며, 10m 국가지점번호 좌표 정확도를 개선하는 원천으로 승격하지 않는다.

## 입력 계약

| 원천 | 구성 | 역할 |
|------|------|------|
| `national_point_grid_shape` | `TL_SPPN_GRID_100KM`, `TL_SPPN_GRID_10KM`, `TL_SPPN_GRID_1KM`, `TL_SPPN_GRID_100M` SHP/DBF | grid prefix별 polygon bbox와 key field를 검증한다. |
| `national_point_grid_center` | `SPPN_*.TXT` | `prefix|x_5179|y_5179` 형식의 중심점 행을 검증한다. |

도형 ZIP의 key field는 다음처럼 resolution과 직접 연결한다.

| layer | key field | resolution | prefix 예 |
|-------|-----------|------------|-----------|
| `TL_SPPN_GRID_100KM` | `SPO_100KM` | 100,000m | `가다` |
| `TL_SPPN_GRID_10KM` | `SPO_10KM` | 10,000m | `나바45` |
| `TL_SPPN_GRID_1KM` | `SPO_1KM` | 1,000m | `나나8181` |
| `TL_SPPN_GRID_100M` | `SPO_100M` | 100m | `가다789668` |

중심점 TXT는 CP949 header 없는 pipe 파일이다. 각 행은 `prefix|x_5179|y_5179` 3컬럼으로 읽는다. prefix 길이는 2/4/6/8자이며 각각 100km/10km/1km/100m grid를 뜻한다.

## 구현

추가 모듈:

- `src/kortravelgeo/loaders/c14_national_point_grid.py`

주요 공개 helper:

- `parse_grid_code()`: 100km~100m prefix를 EPSG:5179 bbox와 center로 해석한다.
- `parent_grid_code_from_point()`: `format_national_point_number_from_5179()` 결과에서 지정 resolution의 parent prefix를 만든다.
- `iter_grid_zip_shape_features()`: ZIP 내부 SHP/DBF를 member 전체 inflate 없이 record 단위로 읽는다.
- `iter_center_rows()`: 중심점 TXT를 CP949 streaming parser로 읽는다.
- `validate_grid_shape_zip()`: layer별 code, bbox, formatter parent prefix를 검증한다.
- `validate_center_zip()`: 중심점 code와 좌표가 prefix 중심점과 일치하는지 검증한다.
- `compare_c14_national_point_grid()`: 도형 row count와 중심점 row count coverage를 resolution별로 비교한다.
- `build_c14_national_point_grid_report()`: 결과를 `AugmentReport`로 감싼다.

도형 검증은 `TL_SPPN_GRID_100M`이 1천만 polygon 규모이므로 공통 ZIP feature iterator를 쓰지 않는다. C14 전용 iterator는 DBF header만 먼저 읽어 row count와 key field를 확인하고, SHP record header/body와 DBF record를 순차적으로 맞춰 `ShapeFeature`를 흘려보낸다. 기본 CI에서는 작은 synthetic ZIP만 검증하고, 실제 ZIP은 `KTG_SLOW_REAL_DATA=1`일 때 일부 행만 sampling한다.

## 측정 항목

### layer validation

각 layer는 다음 값을 낸다.

- `row_count`: DBF header 기준 전체 행 수
- `checked_count`: 실제 검증한 행 수
- `limited`: `row_limit_per_layer` 때문에 일부만 읽었는지 여부
- `invalid_code_count`: prefix 문법 또는 기대 resolution 불일치
- `bbox_mismatch_count`: code에서 계산한 bbox와 SHP bbox 불일치
- `formatter_parent_mismatch_count`: polygon 중심점을 10m 국가지점번호로 format한 뒤 parent prefix가 원래 code와 다른 경우

### center validation

중심점 TXT는 다음 값을 낸다.

- `row_count`, `checked_count`, `limited`
- `count_by_resolution_m`
- `invalid_row_count`
- `center_mismatch_count`
- `formatter_parent_mismatch_count`

### coverage

`measure_count_coverage()`는 resolution별 도형 row count와 중심점 row count를 비교한다. 제한 실행이면 `coverage_count_basis="limited_sample"`로 표시되어 전체 coverage 판정으로 오해하지 않게 한다. 전체 실행에서는 `coverage_count_basis="full_stream"`이다.

## 10m 좌표 개선이 아닌 이유

현재 `core/sppn.py`는 `다사 6925 4045` 같은 10m 국가지점번호를 직접 해석해 해당 10m cell center를 계산한다. C14 도형/중심점 파일은 최대 100m grid prefix까지의 도형과 중심점 확인에 적합하며, 10m cell보다 더 정밀한 좌표를 제공하지 않는다.

따라서 C14 결과는 다음에만 사용한다.

- parser/formatter regression 검증
- 국가지점번호 grid overlay 후보 평가
- C14 consistency case seed
- T-121 전국 실행에서 대용량 streaming 성능·coverage artifact 산출

다음에는 사용하지 않는다.

- `mv_geocode_target` 대표 좌표 ranking 개선
- 10m 국가지점번호 입력 결과 좌표 보정
- v1/v2 API 응답의 자체 좌표 source 승격

`C14NationalPointGridComparison.metrics()`는 이 계약을 `serving_promotion=False`로 고정한다.

## 검증

단위 테스트:

- `tests/unit/test_c14_national_point_grid.py`
  - grid prefix → bbox/center 계산
  - formatter parent prefix round-trip
  - synthetic SHP/DBF ZIP streaming
  - 중심점 TXT parser
  - mismatch sample과 coverage metric
  - `AugmentReport.generated_at`

선택형 실제 데이터 smoke:

- `tests/integration/test_optional_real_c14_national_point_grid.py`
  - `KTG_SLOW_REAL_DATA=1`
  - 실제 `국가지점번호 도형/202405/국가지점번호도형_5월분.zip`
  - 실제 `국가지점번호 중심점/202405/국가지점번호중심점_5월분.zip`
  - 각 layer 3행, 중심점 100행만 sampling해 CI 기본 시간을 늘리지 않는다.

이번 구현은 측정 경로만 추가하므로 OpenAPI, DTO, serving table, UI type 생성물은 변경하지 않는다.
