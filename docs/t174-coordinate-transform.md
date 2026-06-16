# T-174 좌표계 왕복 정밀도 검증·변환 경로 통일

2026-06-16에 완료했다.

## 목표

EPSG:5179와 EPSG:4326 사이의 point 변환을 여러 repository가 각각 보유하지 않게 하고, PostGIS 기준 왕복 오차가 운영 허용치 안에 있음을 검증한다. 외부 인터페이스의 좌표 순서는 계속 `(lon, lat)`다.

## 구현

- `src/kortravelgeo/infra/coordinates.py`를 추가해 PostGIS 기반 point projection helper를 단일 진입점으로 둔다.
- `srid_from_crs()`는 기존 `dto.common.normalize_crs()`를 재사용해 `epsg-4326`, `EPSG5179` 같은 입력도 같은 방식으로 SRID로 변환한다.
- `project_point_to_5179(engine, point, crs=...)`는 입력 CRS의 point를 EPSG:5179로 변환한다.
- `project_point_5179_to_4326(engine, point)`는 EPSG:5179 point를 EPSG:4326 `(lon, lat)`로 변환한다.
- `GeocodeRepository.project_sppn_point_4326()`와 `ReverseRepository.project_reverse_point_5179()`는 자체 SQL을 갖지 않고 shared helper만 호출한다.
- Reverse 조회 SQL의 inline CTE는 기존처럼 query 안에서 한 번만 입력점을 EPSG:5179로 변환한다. 공간 index를 쓰는 serving SQL의 성능 특성은 바꾸지 않는다.

## 정밀도 기준

`ROUNDTRIP_MAX_ERROR_M = 0.001`을 기준으로 둔다. 이는 EPSG:5179 → EPSG:4326 → EPSG:5179 왕복 후 x/y 각각 1mm 이하 오차를 허용한다. 실제 검증은 PostGIS가 있는 `KTG_TEST_PG_DSN` 환경에서 opt-in integration test로 수행한다.

## 검증

- `tests/unit/test_infra_repo_sql.py`가 shared projection SQL과 repo method delegation을 고정한다.
- `tests/integration/test_coordinate_projection_roundtrip.py`가 서울·부산·제주·국가지점번호 회귀 샘플의 EPSG:5179 → EPSG:4326 → EPSG:5179 왕복 오차를 검증한다. `KTG_TEST_PG_DSN`이 없으면 skip한다.
- Windows focused run: `python -m pytest tests/unit/test_infra_repo_sql.py tests/integration/test_coordinate_projection_roundtrip.py -q`는 28 passed, 1 skipped다.
- WSL ext4 미러에서 backend `pytest` 856 passed/52 skipped, Ruff, mypy, import-linter, OpenAPI check를 통과했다.

## 범위 밖

Serving SQL 안에서 성능상 한 번만 수행하는 `ST_Transform` CTE는 이번 작업에서 분리하지 않는다. 해당 변환은 query plan과 공간 index 사용 방식에 묶여 있으므로 T-142/T-143 최적화 작업에서 별도로 다룬다.
