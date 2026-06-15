# T-130 C11 C4/C6/C7 회귀 샘플 원인 분석

작성일: 2026-06-16

## 결론

T-125에서 악화된 C4/C6/C7을 row-level로 baseline serving 출입구와 C11 후보점 기준으로 비교했다. C11 blanket 승격은 계속 no-go다.

핵심은 다음이다.

- C4 over500 68건 중 52건은 후보점에서 새로 생긴 회귀이고, 16건은 기존 baseline도 이미 500m 초과인 shared error다.
- C6 candidate error 3,635건 중 2,834건은 후보점 때문에 새로 표면화된 회귀이고, 그중 2,827건은 기존 baseline 출입구가 없어 C6 평가 대상이 아니던 row다.
- C7 candidate error 9,896건 중 3,087건은 후보점 때문에 새로 표면화된 회귀이고, 그중 3,077건은 기존 baseline 출입구가 없어 C7 평가 대상이 아니던 row다.
- C6/C7의 shared error는 후보점과 baseline점이 거의 같은 좌표인 경우가 많아 C11 고유 회귀라기보다 기존 원천 품질 오류다.

즉 C11 후보는 C3 결측을 크게 줄이지만, 결측 row를 새 좌표로 채우는 순간 C6/C7 품질 게이트에 새 오류를 대량으로 올린다. 이 상태에서는 guarded policy가 있더라도 C6/C7 containment를 통과한 후보만 남기는 강한 필터가 필요하다.

## 실행 기준

| 항목 | 값 |
|------|----|
| DB | `kor_travel_geo_t213_20260615_r3` |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| 후보 원천 | `roadaddr_building_shape_bundle` / `TL_SGCO_RNADR_MST` + `TL_SPBD_ENTRC` |
| 후보 기준월 | `202604` |
| 텍스트 정본 기준월 | `202605` |
| 산출물 | `F:\dev\geodata\t130-c11-regression-root-cause\20260616-r1\` |

T-129에서 남겨 둔 `_ktg_t125_*` 작업 테이블을 재사용했다. serving object와 active release는 변경하지 않았다. T-131에서 후보 정책 simulation을 바로 할 수 있도록 작업 테이블은 계속 남겨 두었다.

## 산출물

| 파일 | 내용 |
|------|------|
| `summary.json` | case별 row count, regression kind, root-cause tag, 대표 샘플 |
| `c4_regression_rows.csv` / `.geojson` | C4 후보 또는 baseline 500m 초과 68건 |
| `c6_regression_rows.csv` / `.geojson` | C6 후보 또는 baseline 우편번호 polygon 오류 3,637건 |
| `c7_regression_rows.csv` / `.geojson` | C7 후보 또는 baseline 행정구역 polygon 오류 9,902건 |
| `reproduce_t130_regression_samples.sql` | 재현 SQL |

## C4 분석

| 분류 | 건수 |
|------|----:|
| candidate regression | 52 |
| shared error | 16 |

Root-cause tag:

| tag | 건수 |
|-----|----:|
| `candidate_far_from_building` | 48 |
| `multiple_candidates_candidate_far_from_building` | 4 |
| `both_points_far_from_building` | 16 |

C4 candidate regression 52건은 대부분 T-129의 경도 약 2도 shift 또는 후보점-건물 polygon 불일치와 겹친다. Shared 16건은 기존 baseline C4 over500과 같은 성격이라 C11 후보만의 신규 회귀로 보지 않는다.

## C6 분석

| 분류 | 건수 |
|------|----:|
| candidate regression | 2,834 |
| shared error | 801 |
| candidate improves baseline | 2 |

Root-cause tag:

| tag | 건수 |
|-----|----:|
| `candidate_error_without_baseline_entrance` | 2,827 |
| `candidate_outside_zip_polygon_baseline_ok` | 7 |
| `shared_outside_zip_polygon` | 801 |
| `baseline_outside_zip_polygon_candidate_ok` | 2 |

대부분의 C6 증가분은 기존 baseline 출입구가 없던 row가 C11 후보로 채워지면서 우편번호 polygon 밖으로 판정된 것이다. baseline이 정상인데 후보만 새로 틀린 순수 회귀는 7건이다.

## C7 분석

| 분류 | 건수 |
|------|----:|
| candidate regression | 3,087 |
| shared error | 6,809 |
| candidate improves baseline | 6 |

Root-cause tag:

| tag | 건수 |
|-----|----:|
| `candidate_error_without_baseline_entrance` | 3,077 |
| `candidate_outside_emd_polygon_baseline_ok` | 10 |
| `shared_outside_emd_polygon` | 6,809 |
| `baseline_outside_emd_polygon_candidate_ok` | 6 |

C7도 C6과 같은 구조다. 순수 후보 회귀는 10건이지만, baseline 출입구 결측을 후보로 채우면서 행정구역 polygon 밖으로 잡힌 row가 3,077건이다. shared 6,809건은 기존 consistency baseline의 known data-quality 오류와 거의 같은 집합이다.

## T-131 정책 시사점

T-131 guarded policy에서는 다음 필터를 최소 조건으로 둔다.

1. C6/C7 candidate reason이 `ok`인 후보만 사용한다.
2. C4 candidate distance가 500m를 넘는 후보는 제외한다. 더 보수적으로는 50m 또는 100m threshold도 simulation한다.
3. 기존 baseline 출입구가 없는 row를 채우는 정책은 C3 개선 효과가 크지만, C6/C7 오류를 새로 노출하므로 별도 budget을 둔다.
4. `multiple_candidates_candidate_far_from_building` 4건과 T-129 `key_mismatch` 그룹은 후보 대표점 선택 규칙을 바꾸기 전까지 제외한다.
5. `shared_error`는 C11 후보 문제가 아니라 기존 원천 품질 오류로 분리해 C11 정책 평가에서 별도 bucket으로 둔다.

## 검증

```bash
python -m pytest tests/unit/test_t130_c11_regression_root_cause.py -q
python -m ruff check scripts/run_t130_c11_regression_root_cause.py tests/unit/test_t130_c11_regression_root_cause.py
python -m mypy scripts/run_t130_c11_regression_root_cause.py
```

WSL ext4 테스트 미러에서도 같은 focused pytest/ruff/mypy를 통과했다.
