# T-129 C11 100m 초과 outlier 분류 및 원인 태깅

작성일: 2026-06-16

## 결론

T-125에서 나온 C11 후보 100m 초과 outlier 14,433건 전체를 자동 태깅했다. 이 태깅은 원인 확정이 아니라 T-130/T-131에서 샘플을 깊게 볼 우선순위 분류다.

| primary tag | 건수 | 해석 |
|-------------|----:|------|
| `candidate_coordinate_error` | 13,000 | 후보점이 건물 polygon 문맥을 벗어나는 경우가 대부분이다. |
| `current_representative_error` | 899 | 후보점이 건물·우편번호·행정구역 문맥 안에 있고 현행 대표점이 centroid인 경우가 많다. |
| `source_month_drift_possible` | 287 | 후보 202604와 텍스트 202605 기준월 차이가 주요 단서인 애매한 경우다. |
| `key_mismatch` | 210 | 다중 후보 또는 natural-key polygon 미매칭이 함께 보인다. |
| `crs_or_source_coordinate_error` | 33 | 경도 약 2도 이동 패턴이다. 통영/창원 등 T-125에서 보인 `128.x` ↔ `130.x` 사례가 여기에 들어간다. |
| `manual_review` | 4 | 자동 규칙만으로는 판정하기 어렵다. |

따라서 C11 blanket 승격은 여전히 no-go다. 다만 899건은 현행 centroid fallback보다 C11 후보가 더 그럴듯한 좁은 정책 후보로 남길 수 있다. 이 후보도 T-130에서 C4/C6/C7 회귀와 함께 확인한 뒤 T-131 guarded policy simulation으로 넘긴다.

## 실행 기준

| 항목 | 값 |
|------|----|
| DB | `kor_travel_geo_t213_20260615_r3` |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| 후보 원천 | `roadaddr_building_shape_bundle` / `TL_SGCO_RNADR_MST` + `TL_SPBD_ENTRC` |
| 후보 기준월 | `202604` |
| 텍스트 정본 기준월 | `202605` |
| 산출물 | `F:\dev\geodata\t129-c11-outlier-triage\20260616-r1\` |

실행은 WSL ext4 테스트 미러 `~/dev/kor-travel-geo-codex-test`에서 했다. 첫 실행은 SHP staging과 candidate table 생성까지 완료한 뒤 SQLAlchemy bind/cast 문법 오류로 중단됐고, 같은 `_ktg_t125_*` 작업 테이블을 재사용해 태깅을 재실행했다. serving object와 active release는 변경하지 않았다. T-130에서 재사용할 수 있도록 `_ktg_t125_*` 작업 테이블은 남겨 두었다.

## 산출물

| 파일 | 내용 |
|------|------|
| `summary.json` | 전체 tag count, 거리 분포, 시도별 count, tag별 대표 샘플 |
| `outlier_tags.csv` | 14,433건 전체 row-level 태깅 |
| `outlier_tags.geojson` | 후보점 기준 지도 검토용 GeoJSON |
| `representative_samples.sql` | 대표 샘플 재현 SQL |

CSV는 header 포함 14,434라인이며, data row는 14,433건이다.

## 태깅 기준

자동 태깅은 다음 신호를 조합한다.

- `ST_Distance(current_pt_5179, candidate_pt_5179) > 100m`
- 현행 대표점과 후보점의 건물 polygon, 우편번호 polygon, 행정구역 polygon containment
- 경도 차이 약 2도와 작은 위도 차이
- `candidate_sig_cd`와 `bd_mgt_sn` 앞 5자리 일치 여부
- `candidates_per_bd > 1`
- natural-key polygon 미매칭
- 후보 기준월 `202604`와 텍스트 기준월 `202605` 차이

모든 14,433건은 `candidate_source_month_differs_from_text` secondary tag를 갖는다. 따라서 기준월 차이는 단독 원인으로 보지 않고, 공간 containment나 key 신호가 약한 경우에만 `source_month_drift_possible` primary tag로 승격했다.

## 주요 분포

거리 분포:

| metric | 값 |
|--------|---:|
| p50 | 129.351m |
| p95 | 324.342m |
| p99 | 818.288m |
| max | 182,892.443m |

현행 `pt_source`별 분포:

| current `pt_source` | 건수 |
|---------------------|----:|
| `centroid` | 14,260 |
| `entrance` | 173 |

주요 secondary tag:

| tag | 건수 |
|-----|----:|
| `candidate_outside_building_polygon` | 13,519 |
| `candidate_inside_zip_polygon` | 14,356 |
| `candidate_inside_emd_polygon` | 14,341 |
| `current_inside_building_polygon` | 13,999 |
| `multiple_candidates_for_bd` | 1,393 |
| `natural_key_polygon_unmatched` | 61 |
| `lon_shift_approx_2deg` | 33 |

시도별 상위 count:

| 시도 | 건수 |
|------|----:|
| 경기도 | 2,746 |
| 경상북도 | 2,035 |
| 충청남도 | 1,777 |
| 전라남도 | 1,564 |
| 경상남도 | 1,506 |
| 충청북도 | 1,443 |
| 전북특별자치도 | 1,146 |
| 강원특별자치도 | 877 |

## 해석

`candidate_coordinate_error` 13,000건은 대부분 후보점이 해당 natural-key 건물 polygon 밖에 있다는 신호로 분류됐다. 반면 같은 row에서 후보점이 우편번호·행정구역 polygon 안에 있는 경우가 많으므로, "다른 지역으로 튄 좌표"만 뜻하지는 않는다. T-130에서 C4 회귀 샘플을 볼 때 건물 polygon natural-key 조인과 후보 출입구 선택 규칙을 함께 확인해야 한다.

`current_representative_error` 899건은 guarded policy 후보로 볼 수 있다. 다만 이 역시 자동 판정일 뿐이며, 현행 centroid가 틀렸다는 확정 근거는 아니다. T-131에서는 이 그룹을 `pt_source='centroid'`, 후보점이 건물·우편번호·행정구역 containment를 통과하는 좁은 정책 후보로만 실험한다.

`crs_or_source_coordinate_error` 33건은 경도 약 2도 이동 패턴이다. 대표 샘플은 통영·창원·김해 등 경남 주소에서 현행점과 후보점 중 하나가 `128.x`, 다른 하나가 `130.x`로 갈라진다. 후보점 또는 현행 fallback 중 어느 쪽이 잘못됐는지는 row별 containment가 엇갈리므로 수동 확인이 필요하다.

## 후속

T-130은 다음 순서로 본다.

1. `candidate_coordinate_error` 중 C4 over500, C6/C7 신규 ERROR와 겹치는 샘플.
2. `key_mismatch` 210건의 natural-key polygon 미매칭과 다중 후보 원인.
3. `current_representative_error` 899건 중 모든 containment를 통과하는 guarded 후보.
4. `crs_or_source_coordinate_error` 33건의 source 좌표 오류 여부.

T-131 guarded simulation에서는 blanket 승격을 배제하고, 위 2~3번에서 살아남은 좁은 후보만 정책으로 실험한다.

## 검증

```bash
python -m pytest tests/unit/test_t129_c11_outlier_triage.py -q
python -m ruff check scripts/run_t129_c11_outlier_triage.py tests/unit/test_t129_c11_outlier_triage.py
```

WSL ext4 테스트 미러에서도 같은 focused pytest/ruff를 통과했다.
