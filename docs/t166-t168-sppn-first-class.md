# T-166~T-168 국가지점번호 계산 좌표 노출

날짜: 2026-06-16  
담당: Agent A / Codex

## 요약

국가지점번호 좌표를 `TL_SPPN_MAKAREA` polygon 포함 여부에서 분리했다. 이제 국가지점번호 문자열 자체가 유효하고 한국 SPPN 지원 envelope 안에 있으면, `core.sppn` 계산식으로 만든 EPSG:5179 10m cell 중심을 PostGIS로 EPSG:4326에 투영해 geocode 결과로 반환한다. `TL_SPPN_MAKAREA`는 좌표 생성 gate가 아니라 `x_extension.sppn_makarea` 문맥 enrich로만 사용한다.

reverse geocode도 입력 좌표를 EPSG:5179로 투영한 뒤 formatter로 국가지점번호를 계산해 `ReverseResponse.x_extension.national_point_number`에 노출한다. 해당 좌표가 표기 의무지역 polygon 안에 있으면 기존처럼 `x_extension.sppn_makarea`와 v2 `match_kind="sppn"` 후보 metadata에 구역 문맥을 붙인다. polygon 문맥이 없어도 v2 reverse는 국가지점번호 후보를 하나 반환한다.

## 구현

- `core.sppn`
  - 한국 SPPN 지원 envelope를 추가했다.
  - parser와 formatter 모두 envelope 밖 좌표/코드는 거절한다.
- `core.geocoder`
  - `lookup_sppn_area()`가 `None`이어도 `project_sppn_point_4326()`으로 계산 좌표를 반환한다.
  - `sppn_makarea`는 area가 있을 때만 채운다.
- `core.reverse_geocoder`
  - `project_reverse_point_5179()` + `format_national_point_number_from_5179()`를 배선했다.
  - `ReverseExtension.national_point_number`를 추가했다.
- `core.v2`
  - reverse의 SPPN 후보 metadata에 `national_point_number`를 넣는다.
  - makarea가 없는 좌표도 `match_kind="sppn"`, `point_precision="approximate"` 후보로 노출한다.
- `infra.geocode_repo` / `infra.reverse_repo`
  - 추가 데이터 테이블 없이 PostGIS `ST_Transform`으로 계산점 투영만 수행한다.
  - 공간 술어에서 indexed geometry 컬럼을 변환하지 않는 기존 원칙은 유지한다.

## 검증

- `tests/unit/test_sppn_core.py`
  - 한국 envelope 밖 code 거절
  - makarea 없는 forward geocode OK
  - makarea 없는 reverse에서 `national_point_number` 반환
- `tests/unit/test_v2_api.py`
  - makarea 후보 metadata의 `national_point_number`
  - makarea 없는 reverse SPPN 후보
- `tests/unit/test_infra_repo_sql.py`
  - SPPN 투영 SQL이 입력점만 변환하고 indexed geometry 컬럼 변환을 추가하지 않음

## 남은 사항

- `point_precision="grid_cell"` 같은 더 정직한 enum은 T-169에서 v2 enum 정리와 함께 처리한다.
- 한국 envelope는 행정 경계 polygon 판정이 아니라 명백한 바다/국경 밖 grid code 차단용 보수적 bounding gate다. 더 정밀한 국경/해상 경계 판정은 별도 원천과 정책 결정이 필요하다.
