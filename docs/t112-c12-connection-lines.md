# T-112 C12 건물 도형 connection line 검증 prototype

T-112는 `도로명주소 건물 도형` bundle의 `TL_SPOT_CNTC` polyline을 전자지도 도로 관리선 `TL_SPRD_MANAGE`와 비교하는 prototype이다. 이 작업은 **측정 전용**이며 serving 좌표, `mv_geocode_target`, C8 운영 SQL을 바꾸지 않는다.

## 구현 범위

- `src/kortravelgeo/loaders/c12_connection_lines.py`
  - bundle `TL_SPOT_CNTC` staging spec
  - 전자지도 `TL_SPRD_MANAGE` staging spec
  - road key overlap (`RDS_SIG_CD + RDS_MAN_NO` ↔ `SIG_CD + RDS_MAN_NO`)
  - key join 기반 line-to-line `ST_Distance` p50/p95/max
  - dangling connection 측정
  - `AugmentReport`로 감쌀 수 있는 `build_c12_connection_report()` 제공
- `tests/unit/test_c12_connection_lines.py`
  - staging spec, join key, road adjacency SQL, metric payload, missing source skip 검증
- `tests/integration/test_optional_real_postgres_c12_connection_lines.py`
  - `KTG_SLOW_REAL_DATA=1`과 `KTG_TEST_PG_DSN`이 모두 있을 때만 세종 실제 bundle/electronic line을 staging해 smoke 검증

## 비교 기준

| 항목 | 기준 |
|------|------|
| connection 원천 | `도로명주소 건물 도형` bundle `TL_SPOT_CNTC` |
| road 원천 | 도로명주소 전자지도 `TL_SPRD_MANAGE` |
| key join | `TL_SPOT_CNTC.RDS_SIG_CD = TL_SPRD_MANAGE.SIG_CD` + `RDS_MAN_NO` |
| distance | `ST_Distance(connection.geom, road.geom)` |
| 기본 tolerance | 1m |
| dangling | road key가 없거나, key는 있지만 road geometry가 없거나, distance가 tolerance를 초과한 connection |

T-040에서 이미 확인한 connection ↔ bundle entrance 참조 overlap도 metric에 포함한다. 이 값은 `SIG_CD + ENT_MAN_NO` 기준이며, road adjacency와는 별도 해석이다.

기본 1m tolerance는 line-to-line geometry가 같은 도로 관리선에 거의 붙어 있는지 보는 smoke 기준이다. 실제 전국 판정에서는 T-121/T-123 artifact와 함께 5m/10m 민감도를 별도로 비교해야 하며, 1m 초과가 곧 serving 오류를 뜻하지는 않는다.

## metric 형태

`C12ConnectionComparison.metrics()`는 다음 정보를 포함한다.

- `staging_rows`
  - bundle `TL_SPOT_CNTC` row 수
  - electronic `TL_SPRD_MANAGE` row 수
- `connection_entrance_ref_overlap`
  - T-040 DBF key set 기반 connection ↔ bundle entrance 참조 overlap
- `road_key_overlap`
  - staging table 기준 road key overlap
- `road_distance_m`
  - road key가 match된 connection과 road line의 거리 분포
- `road_adjacency`
  - `total_connections`
  - `road_key_matched`
  - `road_key_missing`
  - `road_geometry_missing`
  - `within_tolerance`
  - `over_tolerance`
  - `dangling`
  - `dangling_ratio`
  - matched line distance p50/p95/max
- `serving_promotion=False`

`sample()`은 dangling connection sample만 `sample_kind='road_dangling'`으로 평탄화한다.

## 비범위

- 운영 C8 SQL을 변경하지 않는다.
- `tl_sprd_manage`, `tl_sprd_intrvl`, `tl_sprd_rw` 스키마를 변경하지 않는다.
- connection line을 serving 좌표나 geometry overlay API에 편입하지 않는다.
- `ops.source_*` registry와 phase ② C12 registry seed는 T-206에서 다룬다.

## 후속 작업 메모

- T-118은 C12 결과를 C11/C13~C17과 함께 종합해 connection line을 "검증 전용 / serving 편입 후보" 중 어디에 둘지 ADR 게이트에 기록한다.
- T-121 전국 실행에서는 tolerance별 민감도(예: 1m, 5m, 10m)를 artifact로 남기면 C8 해석에 도움이 된다.
