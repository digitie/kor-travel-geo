# T-118 phase 1 go/no-go 종합과 serving 편입 게이트

T-118은 T-111~T-117 prototype 결과를 phase ②(T-206)의 DB case registry 입력으로 고정하고, 보강 원천을 `mv_geocode_target` 대표 좌표 ranking에 편입할 수 있는 조건을 ADR 초안으로 분리한다. 이번 작업은 코드 변경 없이 문서 판정만 수행한다.

## 결론

1. C11~C17은 모두 phase ①에서는 **검증 전용**으로 유지한다.
2. 일반 주소 geocode/reverse의 serving 좌표 편입 후보는 **C11 출입구 원천 계열만 조건부 후보**로 둔다.
3. C11도 바로 편입하지 않고, T-121 전국 실행과 T-122/T-123 성능·정합성 재측정 뒤 ADR-051 승인, feature flag, `pt_source`/`x_extension` 노출 정책 확정이 있을 때만 T-119로 진행한다.
4. C12~C17은 좌표 ranking 원천이 아니므로 T-206 consistency case registry와 운영 검증 리포트로만 승격한다.
5. 전자지도 `TL_SPBD_EQB`는 구조 검증 필수 layer지만 C11~C17 어느 prototype에도 독립 귀속되지 않았다. 현재는 serving 후보가 아니며, T-206 seed에서는 전자지도 구조 검증 evidence로 남기고 필요하면 후속 C18 또는 C13 확장 검증 후보로 분리한다.

## 입력 요약

| case | prototype | 주 원천 | 기준월 예시 | phase ② category/input | 판정 |
|------|-----------|---------|-------------|-------------------------|------|
| C11 | T-111 | `roadaddr_building_shape_bundle` `TL_SPBD_ENTRC`, 전자지도 `TL_SPBD_ENTRC`, `locsum_full`, `roadaddr_entrance_full` | `202605` 중심, 운영 조합은 `202603~202605` 혼합 가능 | `roadaddr_building_shape_bundle`, `electronic_map_full`, `locsum_full`, `roadaddr_entrance_full` | **조건부 serving 후보**, 기본은 검증 전용 |
| C12 | T-112 | `roadaddr_building_shape_bundle` `TL_SPOT_CNTC`, 전자지도 `TL_SPRD_MANAGE` | `202605` 중심 | `roadaddr_building_shape_bundle`, `electronic_map_full` | 검증 전용 |
| C13 | T-113 | `detail_dong_shape_bundle`, `detail_address_db_full` | `202605` 중심 | `detail_dong_shape_bundle`, `detail_address_db_full` | 검증 전용 |
| C14 | T-114 | `national_point_grid_shape`, `national_point_grid_center` | `202405` | `national_point_grid_shape`, `national_point_grid_center`, 선택 `tl_sppn_makarea` | 검증 전용 |
| C15 | T-115 | `civil_service_institution_map` | `202401` | `civil_service_institution_map`, geocoder 결과 | 검증 전용 |
| C16 | T-116 | `address_db_full`, `building_db_full` | `202605` | `address_db_full`, `building_db_full` | 검증 전용 |
| C17 | T-117 | `navi_full` 내부 `match_jibun_*.txt`, `tl_juso_parcel_link` | `202604` | `navi_full.match_jibun`, `tl_juso_parcel_link` | 검증 전용 |
| 전자지도 잔여 | T-118 판정 | `electronic_map_full` `TL_SPBD_EQB` | 전자지도 기준월, 현재 `202604` | `electronic_map_full` 구조 검증 evidence | serving 후보 아님, 후속 검증 후보 |

기준월은 파일명, 내부 member 이름, row-level `source_yyyymm`가 서로 다를 수 있다. T-206의 C11~C17 report schema는 각 group/report payload에 `source_yyyymm`을 필수 evidence로 보존해야 하며, 여러 원천을 비교하는 case는 좌우 원천별 기준월을 함께 기록해야 한다.

## source별 go/no-go

### C11 출입구 원천

판정: **조건부 go 후보**. 단, 현재 PR과 T-118 자체로는 no-go이며 T-119 착수 승인도 아니다.

이유:

- 출입구 point는 일반 주소 대표 좌표 개선과 직접 연결될 수 있는 유일한 C11~C17 계열이다.
- 이미 ADR-039/T-039 계열에서 `tl_locsum_entrc → same-month tl_roadaddr_entrc → tl_navi_buld_centroid` 순서를 쓰며, 기준월이 다른 direct 출입구는 serving에 승격하지 않는 gate가 있다.
- T-111의 bundle/electronic 비교는 full key와 weak key가 섞인다. 특히 운영 테이블 `tl_locsum_entrc`/`tl_roadaddr_entrc`는 `BUL_MAN_NO`/`EQB_MAN_SN`을 보존하지 않아 `sig_cd + ent_man_no` weak key 비교가 포함된다.

T-119로 가려면 다음이 필요하다.

- T-121 전국 실행에서 C11 `source_yyyymm`가 정본 텍스트·도형과 같은 기준월이거나, 혼합 기준월 노이즈를 별도 산출물로 분리할 것
- full key가 가능한 비교와 weak key 비교를 metric/report에서 분리할 것
- 기존 C3/C4/C6/C7 severity가 악화되지 않을 것
- 좌표 ranking 변경은 feature flag 기본 off로 시작할 것
- v1 호환 필드는 유지하고, 세부 원천은 `x_extension` 또는 v2 전용 필드로 노출할 것

### C12 connection line

판정: **검증 전용 no-go**.

`TL_SPOT_CNTC` connection line은 도로 관리선과 건물/출입구 관계를 검증하는 데 유용하지만, 주소 1건의 대표 point를 직접 제공하지 않는다. C8 또는 road-adjacency 해석 보강으로는 가치가 있으나 `mv_geocode_target` 좌표 ranking에는 편입하지 않는다.

### C13 상세주소 동

판정: **검증 전용 no-go**.

상세주소 동 polygon/point는 상세주소 기능과 건물군 내부 overlay에는 가치가 높다. 그러나 일반 도로명주소 geocode의 1주소 1대표 좌표 계약을 바꾸면 cardinality가 달라진다. C13은 `ST_Covers`, 상세주소DB key overlap, 상세주소 기능 후보 검증으로만 둔다.

### C14 국가지점번호 grid/center

판정: **검증 전용 no-go**.

국가지점번호 도형/중심점은 최대 100m prefix grid 검증에 적합하다. 현 `core/sppn.py`의 10m 좌표 계산보다 더 정밀한 좌표 원천이 아니므로 대표 좌표 ranking 개선으로 표시하면 안 된다.

### C15 민원행정기관 POI

판정: **검증 전용 no-go**.

기관 point는 일반 주소 정본이 아니라 POI 원천이다. 주소 문자열을 geocode한 결과와 기관 SHP point의 거리 검증에는 유용하지만, 기관명/기관 point를 일반 주소 후보나 vworld 호환 응답에 섞지 않는다. POI 검색이 필요해지면 별도 `place` 또는 admin/POI API로 설계한다.

### C16 주소DB/건물DB

판정: **검증 전용 no-go**.

주소DB/건물DB는 row/key drift, 기준월 차이, natural key 누락을 찾는 데 쓰고, 현 텍스트 정본(`tl_juso_text`)이나 전자지도 건물 polygon을 대체하지 않는다. 좌표 원천도 아니므로 serving 좌표 ranking에는 편입하지 않는다.

### C17 내비 지번 member

판정: **검증 전용 no-go**.

`match_jibun_*.txt`는 `navi_full` 내부 optional member다. `tl_juso_parcel_link`와의 coverage 검증에는 유용하지만 좌표를 제공하지 않고, 독립 category가 아니라 `navi_full.match_jibun` member flag로 다룬다.

### `TL_SPBD_EQB`

판정: **serving 후보 아님, 후속 검증 후보**.

`TL_SPBD_EQB`는 전자지도 master 11개 layer 중 하나라 archive 구조 검증에서는 필수다. 그러나 현 serving 적재 9개 layer에는 포함되지 않고, C11~C17에서도 독립 prototype으로 다루지 않았다. `EQB_MAN_SN`은 C11/C13 key 문맥에 등장하지만, `TL_SPBD_EQB` polygon 자체는 아직 별도 metric이 없다.

따라서 T-206에서는 다음처럼 처리한다.

- `electronic_map_full` 구조 검증: `TL_SPBD_EQB` 존재와 sidecar 정상성은 필수 evidence로 유지
- C11/C13: `EQB_MAN_SN` key 문맥은 보존하되 `TL_SPBD_EQB` polygon을 묵시적으로 사용했다고 표시하지 않음
- 후속 후보: 상세주소 동 polygon과 전자지도 건물군 polygon의 포함/overlap 검증이 필요하면 C18 또는 C13 확장으로 분리

## phase ② C11~C17 registry seed 입력

| case_code | 이름 | default severity | required inputs | skipped 조건 | 주요 metric |
|-----------|------|------------------|-----------------|--------------|-------------|
| C11 | 출입구 원천 간 거리 검증 | `WARN` | `roadaddr_building_shape_bundle`, `electronic_map_full`, `locsum_full` | bundle 또는 비교 대상이 없으면 해당 pair skip | key overlap, distance p50/p95/max, weak/full key 구분 |
| C12 | 건물 도형 connection line 검증 | `WARN` | `roadaddr_building_shape_bundle`, `electronic_map_full` | bundle 없으면 skip | road key overlap, line distance, dangling ratio |
| C13 | 상세주소 동 containment 검증 | `WARN` | `detail_dong_shape_bundle`, `detail_address_db_full` | 둘 중 하나 없으면 skip | key overlap, `ST_Covers` coverage, address-matched coverage |
| C14 | 국가지점번호 grid/center 검증 | `WARN` | `national_point_grid_shape`, `national_point_grid_center` | 둘 다 없으면 skip | invalid code, bbox/center mismatch, formatter parent mismatch, coverage |
| C15 | 민원행정기관 POI 주소 거리 검증 | `WARN` | `civil_service_institution_map`, active geocoder result | 원천 없으면 skip | parse/geocode missing, distance p50/p95/max, outlier sample |
| C16 | 주소DB/건물DB row·key drift 검증 | `WARN` | `address_db_full`, `building_db_full` | 해당 자료 없으면 skip | distinct key overlap, left/right-only sample, staging row count |
| C17 | 내비 지번 member coverage 검증 | `WARN` | `navi_full.match_jibun`, `tl_juso_parcel_link` | `match_jibun_*` member 없으면 skipped | `bd_mgt_sn+pnu`, `pnu+road key` coverage |

T-206의 회귀 테스트는 "prototype metric == run-validation metric"을 기준으로 삼는다. phase ② registry가 metric 이름을 바꿔야 하면 alias를 두지 말고 seed 문서와 prototype 문서를 함께 갱신한다.

## ADR-051 초안 요약

ADR-051은 별도 `docs/decisions.md` 항목으로 proposed 상태에 둔다. 요지는 다음이다.

- 기본 결정: T-118 이후에도 C11~C17은 검증 전용이며, C11만 조건부 serving 후보로 남긴다.
- 실행 gate: 전국 C11 full run, C3/C4/C6/C7 악화 없음, 기준월 일치, feature flag 기본 off, OpenAPI/v2/UI 영향 검토.
- 임계값 초안: 후보별 key overlap 99.9% 이상, 기존 대표점 대비 p95 10m 이하 또는 개선 근거 명시, p99 30m 이하, 100m 초과 outlier 0.1% 이하, REST/SQL p95 성능 회귀 5% 이하.
- 노출 정책: public `pt_source` 확장은 기본 보류. 기존 `entrance`/`centroid`는 유지하고, 세부 원천은 `x_extension.coord_source_detail` 또는 v2 전용 필드로 시작한다.

이 ADR은 proposed라서 T-119를 자동 승인하지 않는다. T-119는 ADR-051을 accepted로 전환하는 별도 사용자 승인 뒤에만 진행한다.

## 다음 작업

T-118 완료 후 즉시 진행할 Codex 작업은 T-120이다. T-119는 ADR-051이 accepted가 될 때까지 보류한다. T-121은 T-118 산출물을 입력으로 사용할 수 있지만, T-120은 T-207의 공유 검증 모듈 선행 조건이라 phase ② 합류 전에 끝내는 것이 낫다.
