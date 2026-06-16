# optional 원천 사용·미사용 최종 판정

작성일: 2026-06-15

상태: **accepted**

관련: PR #193, PR #194, T-118, T-123, T-125, T-216, ADR-026, ADR-027, ADR-051, ADR-054

## 목적

이 문서는 `F:\dev\geodata\juso\unused`에 보존한 optional 원천과 현행 full-load 원천을 놓고, 어떤 데이터를 serving에 승격하고 어떤 데이터는 검증·보조·미사용으로 남길지 최종 판정한다.

PR #193은 clean-slate v2 가정에서 optional 데이터셋이 상세주소와 무주소 정확도를 실제로 높일 수 있는지 비판적으로 검토했고, PR #194는 그 결론을 한눈 요약 표로 보강했다. 두 PR은 2026-06-15 21:39 KST / 21:46 KST에 각각 `main`에 머지됐고, GitHub conversation comment, review, review thread는 모두 0건이었다. 따라서 반영 대상은 PR comment가 아니라 두 PR의 문서 본문 의견이다.

본 문서는 그 의견에 T-125 C11 serving preflight 결과를 더해 다음을 확정한다.

- **국가지점번호 좌표는 활용한다.** 단, 좌표는 grid 파일을 적재해서 얻는 것이 아니라 `core.sppn` 계산식으로 만든다.
- `도로명주소 건물 도형`의 출입구점은 대표 좌표 승격 후보였지만, T-125에서 no-go이므로 현행 serving ranking에는 승격하지 않는다.
- `상세주소DB`와 `건물군 내 상세주소 동 도형`은 상세주소 기능 원천으로는 쓴다. 일반 주소 대표 좌표를 더 정확하게 만드는 원천으로 쓰지는 않는다.
- `주소DB`, `건물DB`, `민원행정기관전자지도`, `국가지점번호 도형/중심점`은 현행 기본 주소 좌표 원천으로 쓰지 않고 검증·별도 기능 후보로 둔다.

## 판정 등급

| 등급 | 의미 |
|------|------|
| 기본 서빙 유지 | 현재 full-load 또는 선택 loader가 이미 serving DB를 만드는 정본/보조 원천이다. |
| 서빙 기능 승격 | 현재 또는 후속 v2에서 사용자 기능으로 노출한다. 대표 좌표 MV에 섞는다는 뜻은 아니다. |
| 조건부 승격 | 기준월, feature flag, 회귀 gate 같은 조건을 통과할 때만 좌표 ranking에 반영한다. |
| 검증 전용 | source registry, run-validation, 품질 리포트, UI overlay, 회귀 fixture에 쓴다. 일반 주소 좌표 후보로 쓰지 않는다. |
| 서빙 미사용 | 최신 serving DB를 만드는 입력으로 쓰지 않는다. 삭제한다는 뜻은 아니며 보존·회귀 용도는 남길 수 있다. |

## 최종 분류표

| 원천/구성 | 최종 판정 | 사용 위치 | 핵심 근거 | 금지선 |
|-----------|-----------|-----------|-----------|--------|
| `도로명주소 한글_전체분` `rnaddrkor_*.txt` | 기본 서빙 유지 | `tl_juso_text` | 도로명주소 텍스트 정본, `bd_mgt_sn` 중심 정체성 | 다른 텍스트 DB로 조용히 대체 금지 |
| `도로명주소 한글_전체분` `jibun_rnaddrkor_*.txt` | 기본 서빙 유지 | `tl_juso_parcel_link` | 건물-지번 1:N 관계 정본 | `tl_juso_text.pnu` 덮어쓰기 금지 |
| `위치정보요약DB` | 기본 서빙 유지 | `tl_locsum_entrc`, 대표 출입구 1순위 | 현재 `mv_geocode_target`의 주 출입구 좌표 원천 | `bd_mgt_sn` 직접 존재로 가정 금지 |
| `내비게이션용DB` `match_build_*.txt` | 기본 서빙 유지 | `tl_navi_buld_centroid`, 검색 보강 | 출입구 없는 건물의 centroid fallback, `시군구용건물명` 검색 보강 | 출입구보다 높은 대표점 우선순위 금지 |
| `내비게이션용DB` `match_rs_entrc.txt` | 기본 서빙 유지 | `tl_navi_entrc` | 내비 진입점 보조, 검증·분석 문맥 | 일반 대표 좌표로 직접 승격 금지 |
| 도로명주소 전자지도 9개 layer | 기본 서빙 유지 | 행정/기초구역/도로/건물 도형 테이블 | geometry, reverse, consistency, `include_geometry`의 핵심 원천 | 미사용 layer를 묵시 적재 금지 |
| `도로명주소 출입구 정보` | 조건부 승격 | `tl_roadaddr_entrc`, same-month fallback | `bd_mgt_sn + EPSG:5179` direct 출입구. 기준월이 텍스트 정본과 맞을 때만 후보 | 기준월 불일치 상태에서 대표 좌표 승격 금지 |
| **국가지점번호 문자열 좌표** | **서빙 기능 승격** | v2 forward/reverse 무주소 좌표 | `parse_national_point_number()`가 EPSG:5179 10m cell 중심을 계산한다. 데이터 적재 없이 좌표 활용 가능 | T-166~T-168에서 `TL_SPPN_MAKAREA` gate를 제거하고 reverse code 방출을 구현. `point_precision="grid_cell"` 같은 enum 정리는 T-169에서 처리 |
| `TL_SPPN_MAKAREA` | 기본 서빙 유지 | 국가지점번호 표기 의무지역 context | 이미 `tl_sppn_makarea`로 적재·조회. 좌표가 아니라 zone context | 정밀 좌표나 국가지점번호판 point 목록처럼 사용 금지 |
| `도로명주소 건물 도형` `TL_SPBD_ENTRC` | 검증 전용, 대표 좌표 승격 보류 | C11 run-validation, outlier 분석 | T-123 원천 간 일치는 좋았지만 T-125에서 대표점 impact p95 `22.801m`, p99 `54.283m`, 100m 초과 `14,433`건, C4/C6/C7 악화 | 현행 `mv_geocode_target` ranking에 blanket 승격 금지 |
| `도로명주소 건물 도형` `TL_SGCO_RNADR_MST` | 검증 전용, geometry 후보 | 주소 polygon 분석, v2 geometry 후보 | `ADR_MNG_NO` 기반 주소 polygon으로 전자지도 `TL_SPBD_BULD`와 의미가 다름 | `tl_spbd_buld_polygon` 대체 금지 |
| `도로명주소 건물 도형` `TL_SPOT_CNTC` | 검증 전용 | C12 connection line 검증 | 출입구-도로 연결선으로 C8/road-adjacency 설명에 유용 | 대표 point 원천으로 사용 금지 |
| `상세주소DB` | 별도 기능 승격 후보 | v2 `match_kind="detail"` 상세주소 열거 | 동/층/호 텍스트 3.2M행. 좌표 컬럼은 없음 | 일반 주소 좌표 정확도 개선 원천으로 광고 금지 |
| `건물군 내 상세주소 동 도형` `TL_SGCO_RNADR_DONG` | 별도 기능 승격 후보 | 상세주소 동 polygon, UI overlay | 상세주소 동 단위 polygon으로 상세주소 기능에는 가치 있음 | 전체 건물 polygon 정본 대체 금지 |
| `건물군 내 상세주소 동 도형` `TL_SPBD_ENTRC_DONG` | 별도 기능 승격 후보 | 상세주소 동 출입구 앵커 | 전국 424,639점, C13 containment 96.48% | 호별 door-level 좌표처럼 표시 금지 |
| `국가지점번호 도형` | 검증 전용 | C14 parser/formatter 검증, grid overlay 후보 | 제공 최저 해상도는 100m라 현 10m 계산 좌표보다 거칠다 | 10m 좌표 정확도 개선용 serving table 적재 금지 |
| `국가지점번호 중심점` | 검증 전용 | 100m 이하 prefix 중심점 검증 | 100m prefix center는 formatter 회귀 검증에 유용 | 10m 국가지점번호 좌표 원천으로 사용 금지 |
| `민원행정기관전자지도` | 검증 전용, 별도 POI 후보 | C15, 후속 `match_kind="poi"` 후보 | 행정기관 POI다. T-123 기준 p95 `194.350m`, 100m 초과 `14.054%`, 기준월 `202401` | 일반 주소 대표 좌표 대체 금지 |
| `주소DB` | 검증 전용 | C16 row/key drift, 기준월 비교 | 좌표 원천이 아니라 텍스트/속성 snapshot | `도로명주소 한글_전체분` 정본 대체 금지 |
| `건물DB` | 검증 전용 | C16 building key drift, 속성 비교 | 좌표 원천이 아니라 건물 속성/키 snapshot | 좌표 후보로 직접 사용 금지 |
| `내비게이션용DB` `match_jibun_*.txt` | 검증 전용 | C17 parcel-link coverage | 지번 link coverage 검증에는 유용하나 좌표 없음 | 독립 source category나 좌표 원천으로 승격 금지 |
| 과거 snapshot | 서빙 미사용 | regression, 일변동·복원 검증 | 최신 serving 정본이 아님 | 최신 serving source set 대체 금지 |

## 왜 일부 데이터는 쓰지 않는가

### `도로명주소 건물 도형`

이 원천은 “안 쓴다”가 아니라 **구성별로 다르게 쓴다**.

- `TL_SPBD_ENTRC` 출입구점: 대표 좌표 승격은 보류한다. T-125가 실제 T-213 r3 serving DB에서 기존 대표점과 비교한 결과, C3 결측은 줄었지만 C4 over500 `16 → 68`, C6 ERROR `803 → 3,635`, C7 ERROR `6,815 → 9,896`으로 악화됐다.
- `TL_SGCO_RNADR_MST` polygon: 주소 polygon 분석과 v2 geometry 후보로는 남긴다. 다만 전자지도 `TL_SPBD_BULD`와 의미가 달라 기존 건물 polygon 정본을 대체하지 않는다.
- `TL_SPOT_CNTC`: connection line 검증용이다. 대표 좌표가 아니다.

따라서 현 결론은 **C11 출입구 blanket 승격 no-go, 검증·outlier 분석은 계속 사용**이다. 나중에 재검토하려면 T-125의 14,433개 100m 초과 outlier와 C4/C6/C7 악화 원인을 먼저 분류해야 한다.

### `건물군 내 상세주소 동 도형`과 `상세주소DB`

이 두 원천은 상세주소 기능에는 쓴다. 다만 일반 주소 좌표를 더 정확하게 만드는 만능 원천은 아니다.

- `상세주소DB`는 동/층/호 문자열을 제공하지만 좌표 컬럼이 없다.
- `TL_SGCO_RNADR_DONG`은 상세주소 동 polygon이고, `TL_SPBD_ENTRC_DONG`은 동 출입구 point다.
- 호별 좌표는 어떤 optional 원천에도 없다.
- 동 출입구점은 전국 424,639점으로 전체 건물/주소 수에 비해 제한적이다.

따라서 v2에서는 `match_kind="detail"` 같은 typed candidate로 노출할 수 있지만, `point_precision`은 `approximate` 또는 `centroid` 계열로 정직하게 내려야 한다. “호별 door-level 좌표”라고 설명하면 안 된다.

### `주소DB`와 `건물DB`

둘 다 이름만 보면 정본처럼 보이지만, 이 프로젝트의 현행 정본은 `도로명주소 한글_전체분`, `위치정보요약DB`, `내비게이션용DB`, 전자지도 조합이다.

- `주소DB`는 도로명주소/부가정보/지번/도로명코드 텍스트 snapshot이다.
- `건물DB`는 건물 속성/지번/도로명코드 snapshot이다.
- 둘 다 좌표를 제공하지 않는다.
- C16에서 `bd_mgt_sn` 직접 교집합은 0건으로 관찰됐고, 자연키 기반 drift 검증에 더 적합하다.

따라서 이 둘은 row count, key drift, 기준월 차이, 누락 원인 분석에 쓴다. 대표 좌표나 건물 polygon 정본으로 대체하지 않는다.

### `민원행정기관전자지도`

이 원천은 행정기관 POI다. 행정기관명 검색이나 별도 place 기능에는 쓸 수 있지만, 일반 도로명주소의 좌표를 대체하면 안 된다.

T-123 기준으로 기관 주소를 현 geocoder와 맞춘 뒤 POI point와 비교하면 p95가 `194.350m`, 100m 초과 비율이 `14.054%`였다. 이 숫자는 POI 자체가 틀렸다는 단정이 아니라, POI점과 주소 대표점이 같은 의미의 좌표가 아니라는 증거다. 그래서 결론은 **주소 좌표 대체 금지, 별도 POI 후보로 격리**다.

### `국가지점번호 도형`과 `국가지점번호 중심점`

국가지점번호는 **좌표를 활용한다**. 다만 활용하는 좌표 원천은 도형/중심점 파일이 아니라 문자열 계산식이다.

- 현 parser는 한글 2자 + 숫자 8자리 국가지점번호를 EPSG:5179 10m cell 중심으로 계산한다.
- `국가지점번호 도형`과 `국가지점번호 중심점`은 100m prefix까지의 grid/center를 제공한다.
- 100m 원천을 10m 입력 좌표의 정밀도 개선에 쓰면 오히려 더 거칠어진다.

따라서 후속 v2에서는 makarea gate를 “좌표 suppress”가 아니라 “zone context enrich”로 낮추고, reverse에서 formatter를 first-class로 배선하는 방향이 맞다. C14 grid/center는 parser/formatter 회귀 검증과 지도 overlay 후보로 남긴다.

## 현행 기본 서빙 입력

현재 T-213/T-214/T-125 기준 serving DB를 재구성하는 핵심 입력은 다음이다.

| 역할 | 원천 | 테이블 |
|------|------|--------|
| 주소 텍스트 정본 | `202605_도로명주소 한글_전체분.zip` | `tl_juso_text` |
| 건물-지번 1:N | `jibun_rnaddrkor_*.txt` | `tl_juso_parcel_link` |
| 대표 출입구 1순위 | `202604_위치정보요약DB_전체분.zip` | `tl_locsum_entrc` |
| centroid fallback/검색 보강 | `202604_내비게이션용DB_전체분.7z` | `tl_navi_buld_centroid`, `tl_navi_entrc` |
| 행정·도로·건물 geometry | `도로명주소 전자지도\202604\<시도>.zip` | `tl_scco_*`, `tl_kodis_bas`, `tl_sprd_*`, `tl_spbd_buld_polygon` |
| 선택 direct 출입구 | `도로명주소 출입구 정보\202604\<시도>.zip` | `tl_roadaddr_entrc` |
| 국가지점번호 zone context | `구역의도형\202603\<시도>.zip` `TL_SPPN_MAKAREA` | `tl_sppn_makarea` |

`roadaddr_entrance`는 DB에 적재할 수 있지만 `source_yyyymm`이 텍스트 정본 기준월 집합과 맞을 때만 대표 좌표 fallback 후보가 된다. `tl_sppn_makarea`는 국가지점번호 좌표를 만드는 원천이 아니라 context 원천이다.

## 후속 작업

1. T-169 v2 enum 정리에서 국가지점번호 `point_precision="grid_cell"` 또는 동등한 정밀도 표기를 설계한다. Forward makarea gate 분리와 reverse formatter 노출은 T-166~T-168에서 구현됐다.
2. 상세주소 기능을 구현할 때는 `상세주소DB + 상세주소 동 도형`을 별도 `match_kind="detail"` 흐름으로 설계하고, 호별 좌표가 없다는 한계를 API 문서에 명시한다.
3. C11을 다시 검토하려면 T-125 outlier 14,433건과 C4/C6/C7 악화 샘플을 먼저 분류한 뒤, 좁은 조건의 후보 교체 정책을 새 gate로 다시 제안한다.
4. T-127에서 optional source 구조 validator를 강화해 `warning`과 `failed`의 의미를 category별로 좁힌다.
