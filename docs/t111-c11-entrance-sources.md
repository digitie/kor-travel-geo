# T-111 C11 출입구 원천 간 거리 검증 prototype

T-111은 `도로명주소 건물 도형` bundle의 `TL_SPBD_ENTRC` point를 PostGIS staging에 올려 기존 출입구 원천과의 key overlap 및 거리 분포를 측정하는 prototype이다. 이 작업은 **측정 전용**이며 serving 좌표 ranking, `mv_geocode_target`, API 응답 구조를 바꾸지 않는다.

## 구현 범위

- `src/kortravelgeo/loaders/augment_harness.py`
  - staging/운영 테이블 간 key overlap 측정을 위한 `KeyOverlapMeasurement`, `key_overlap_sql()`, `measure_key_overlap()` 추가
- `src/kortravelgeo/loaders/c11_entrance_sources.py`
  - `TL_SPBD_ENTRC` staging spec (`SIG_CD`, `BUL_MAN_NO`, `ENT_MAN_NO`, `EQB_MAN_SN`, `geom`)
  - bundle ZIP `TL_SPBD_ENTRC`와 전자지도 `TL_SPBD_ENTRC` staging COPY
  - 세 비교쌍의 key overlap 및 `ST_Distance` 분포 측정
  - `AugmentReport`로 감쌀 수 있는 `build_c11_entrance_report()` 제공
- `tests/unit/test_c11_entrance_sources.py`
  - staging spec이 `building_shape_bundle.py`의 `ENTRANCE_KEY_FIELDS`를 재사용하는지 검증
  - full key / weak key metric 구조와 `serving_promotion=False` 계약 검증
  - 시도별 source group discovery와 missing source skip 검증
- `tests/integration/test_optional_real_postgres_c11_entrance_sources.py`
  - `KTG_SLOW_REAL_DATA=1`과 `KTG_TEST_PG_DSN`이 모두 있을 때만 세종 실제 bundle/electronic 출입구를 staging해 smoke 검증

## 비교쌍과 key 계약

| 비교쌍 | join key | 비고 |
|--------|----------|------|
| bundle `TL_SPBD_ENTRC` ↔ 전자지도 `TL_SPBD_ENTRC` | `SIG_CD`, `BUL_MAN_NO`, `ENT_MAN_NO`, `EQB_MAN_SN` | `ENTRANCE_KEY_FIELDS` full key |
| bundle `TL_SPBD_ENTRC` ↔ `tl_locsum_entrc` | `sig_cd`, `ent_man_no` | 운영 테이블이 `BUL_MAN_NO`/`EQB_MAN_SN`을 보존하지 않아 weak key |
| bundle `TL_SPBD_ENTRC` ↔ `tl_roadaddr_entrc` | `sig_cd`, `ent_man_no` | `ent_man_no`가 NULL일 수 있고 full key가 없어 weak key |

`weak_sig_ent_key` 결과는 동일 시군구 안에서 `ent_man_no`가 충분히 안정적이라는 가정 위의 측정이다. 따라서 C11 report는 이 비교쌍을 full key 판정과 같은 의미로 해석하지 않도록 `key_contract`와 `note`에 제약을 남긴다.

## metric 형태

`C11EntranceComparison.metrics()`는 다음 정보를 포함한다.

- `staging_rows`
  - bundle/electronic `TL_SPBD_ENTRC` staging row 수
- `dbf_exact_key_overlap`
  - 기존 T-040 DBF key set 기반 full key overlap
- `comparisons`
  - 비교쌍별 `key_overlap`
  - 비교쌍별 `distance_m.samples`, `p50_m`, `p95_m`, `max_m`
  - 비교쌍별 `key_contract`, `join_keys`, `note`
- `serving_promotion=False`

`sample()`은 각 비교쌍의 거리 상위 sample을 `comparison`, `key_contract`와 함께 평탄화한다. T-121 전국 실행에서는 이 payload를 case별 artifact로 저장하면 된다.

## 비범위

- 출입구 좌표를 serving 후보로 승격하지 않는다.
- `pt_source`나 v1/v2 응답 필드를 확장하지 않는다.
- `tl_locsum_entrc` 또는 `tl_roadaddr_entrc` 스키마를 변경하지 않는다.
- `ops.source_*` registry와 phase ② C11 registry seed는 T-206에서 다룬다.

## 후속 작업 메모

- T-112는 같은 staging/COPY 기반 위에서 `TL_SPOT_CNTC` polyline과 전자지도 도로 layer 인접성을 측정한다.
- T-118은 T-111 결과를 다른 C12~C17 결과와 함께 종합해 "검증 전용 / serving 편입 후보" 판정을 ADR 게이트로 정리한다.
- T-121 전국 실행 전에는 `weak_sig_ent_key`의 중복 위험을 metric 해석 문서에 다시 명시해야 한다.
