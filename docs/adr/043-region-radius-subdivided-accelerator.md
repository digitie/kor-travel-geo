# ADR-043: 행정구역 반경조회는 subdivided serving accelerator를 사용한다

- 상태: accepted
- 날짜: 2026-06-02
- 결정자: 사용자 요청, codex

## 컨텍스트

`/v2/regions/within-radius`는 POI 주변 시도·시군구·읍면동을 반환한다. 초기 구현은 `tl_scco_ctprvn`, `tl_scco_sig`, `tl_scco_emd`를 레벨별로 각각 조회했고, 매 쿼리마다 입력 좌표를 EPSG:5179로 변환했다. 전국 행정구역 row 수는 작지만 일부 polygon이 크고 복잡해 반경이 커질수록 `ST_DWithin` tail latency가 커졌다. 사용자는 1~5번 튜닝안을 모두 실제 테스트와 함께 진행하라고 지시했다.

## 결정

행정구역 원본 테이블은 그대로 유지하되, `/v2/regions/within-radius` 전용 serving accelerator인 `region_radius_parts`를 둔다.

1. `region_radius_parts`는 `sido`/`sigungu`/`emd` polygon을 `ST_Subdivide(geom, 256)`으로 쪼갠 조각 테이블이다.
2. API 쿼리는 하나의 SQL에서 입력점을 한 번만 EPSG:5179로 변환한다.
3. 반경 후보는 `region_radius_parts.geom` GiST 인덱스와 `ST_DWithin`으로 찾는다.
4. `contains` 관계는 원본 `tl_scco_ctprvn`/`tl_scco_sig`/`tl_scco_emd`에서 `ST_Covers`로 코드 기준 계산한다.
5. 시군구 후보는 반경 안의 시도 후보 parent code로, 읍면동 후보는 반경 안의 시군구 후보 parent code로 좁힌다.
6. `region_radius_parts`는 `alembic upgrade head`, `load shp`, `load shp-all`, `load all-sidos`, `refresh mv` 경로에서 다시 채운다.

## 근거

- 큰 행정구역 polygon을 작은 조각으로 나누면 boundary overlap 반경조회가 더 작은 bounding box 후보로 평가된다.
- 원본 geometry를 변환하지 않고 입력점만 변환하므로 GiST 인덱스 사용 방향을 유지한다.
- contains 판정을 accelerator 조각이 아니라 원본 polygon에서 계산해야 중심점 포함 의미가 안정적이다.
- parent code 계층 필터는 읍면동 전체 후보를 바로 뒤지는 것보다 안전하게 후보 폭을 줄인다.

## 결과

- 새 테이블과 GiST/parent index를 schema와 migration에 추가한다.
- `GeometryRepository.regions_within_radius()`는 레벨별 3회 query loop 대신 단일 SQL을 실행한다.
- 선택형 실제 PostgreSQL 테스트는 accelerator 결과가 원본 `tl_scco_*` 직접 `ST_DWithin` 결과와 같은지 비교한다.

## 남은 위험

- SHP 원천만 갱신하고 `region_radius_parts`를 다시 채우지 않으면 반경조회 결과가 오래될 수 있다. 표준 CLI/API 적재 경로는 refresh를 수행하지만, 운영자가 psql에서 원본 테이블만 직접 수정하는 경로는 금지한다.
- `ST_Subdivide` 조각 수와 vertex 수 `256`은 현재 전국 DB 기준의 1차값이다. 더 큰 반경/동시성에서 추가 측정이 필요하면 조각 크기를 재실측한다.
