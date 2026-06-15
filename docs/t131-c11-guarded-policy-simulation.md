# T-131 C11 guarded candidate policy 설계·오프라인 simulation

작성일: 2026-06-16

## 결론

T-129/T-130 결과를 바탕으로 C11 후보를 blanket 승격하지 않고, 좁은 guarded policy로만 오프라인 simulation했다. C11 blanket은 계속 no-go다.

가장 실험 가치가 있는 후속 후보는 `centroid_c4_50_c6_c7_move_500`이다.

- 기존 대표점이 `centroid`인 row만 C11 후보로 대체한다.
- 후보점의 건물 polygon 최근접 거리가 50m 이하여야 한다.
- 후보점이 우편번호 polygon과 행정구역 polygon 안에 있어야 한다.
- 기존 대표점 대비 이동거리는 500m 이하로 제한한다.

이 정책은 C3 결측 후보 3,482,270건을 채우면서 candidate C4/C6/C7 오류를 모두 0으로 유지했다. p99 이동거리는 64.981m이고, 최대 이동거리는 495.345m다. 다만 100m 초과 이동이 10,099건 남아 있으므로 active serving promotion은 여전히 금지하고, T-132 반복 검증 harness와 T-133 shadow serving에서만 후속 평가한다.

## 실행 기준

| 항목 | 값 |
|------|----|
| DB | `kor_travel_geo_t213_20260615_r3` |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| 후보 원천 | `roadaddr_building_shape_bundle` / `TL_SGCO_RNADR_MST` + `TL_SPBD_ENTRC` |
| 후보 기준월 | `202604` |
| 텍스트 정본 기준월 | `202605` |
| 산출물 | `F:\dev\geodata\t131-c11-guarded-policy-simulation\20260616-r1\` |

T-129/T-130에서 남겨 둔 `_ktg_t125_*` 후보 테이블을 재사용했다. 새 feature table `_ktg_t131_c11_policy_features`만 만들었고, serving object와 active release는 변경하지 않았다. T-132에서 재사용할 수 있도록 작업 테이블은 남겨 두었다.

첫 실행은 bind parameter가 있는 다중 SQL 문을 psycopg prepared statement로 보내 실패했다. 이후 feature table 생성 경로를 `DROP TABLE`, `CREATE TABLE AS`, `CREATE INDEX`, `ANALYZE` 네 문장으로 분리해 재실행했다.

## 산출물

| 파일 | 내용 |
|------|------|
| `summary.json` | baseline count, 정책별 coverage·오류·movement 통계 |
| `policy_summary.csv` | 정책별 요약 표 |
| `reproduce_t131_policy_summary.sql` | feature table과 정책 요약 재현 SQL |

## Baseline

| metric | 값 |
|--------|---:|
| C11 후보 row | 6,404,009 |
| 후보 집합 내 baseline C3 unresolved | 3,498,081 |
| 후보 집합 내 baseline C4 over500 | 16 |
| 후보 집합 내 baseline C6 error | 803 |
| 후보 집합 내 baseline C7 error | 6,815 |
| 같은 기준월 후보 | 0 |

`same_text_month_only` 정책은 0건이다. 이번 후보는 `202604`, 텍스트 정본은 `202605`라 기준월이 맞지 않는다. 따라서 같은 기준월 gate는 현재 원천 조합에서는 정책으로 쓸 수 없다.

## 정책별 결과

| policy | 후보 사용 | C3 채움 | candidate C4/C6/C7 오류 | p95 | p99 | max | >100m | >500m |
|--------|---------:|--------:|--------------------------|----:|----:|----:|------:|------:|
| `blanket_c11` | 6,404,009 | 3,498,081 | 68 / 3,635 / 9,896 | 22.801m | 54.283m | 182,892.443m | 14,433 | 330 |
| `c4_50_c6_c7_ok` | 6,362,917 | 3,482,434 | 0 / 0 / 0 | 22.516m | 51.213m | 182,251.491m | 10,415 | 166 |
| `centroid_c4_100_c6_c7_ok` | 3,489,603 | 3,489,603 | 0 / 0 / 0 | 31.670m | 69.797m | 182,251.491m | 12,871 | 202 |
| `centroid_c4_50_c6_c7_ok` | 3,482,434 | 3,482,434 | 0 / 0 / 0 | 30.970m | 65.107m | 182,251.491m | 10,263 | 164 |
| `centroid_c4_50_c6_c7_single_candidate` | 3,469,753 | 3,469,753 | 0 / 0 / 0 | 30.680m | 63.913m | 182,251.491m | 9,224 | 143 |
| `centroid_c4_50_c6_c7_move_500` | 3,482,270 | 3,482,270 | 0 / 0 / 0 | 30.956m | 64.981m | 495.345m | 10,099 | 0 |
| `same_text_month_only` | 0 | 0 | 0 / 0 / 0 | 없음 | 없음 | 없음 | 0 | 0 |

## 해석

`c4_50_c6_c7_ok`는 거의 모든 C11 후보를 살리면서 C4/C6/C7 candidate 오류를 0으로 만들지만, 현행 `entrance` row까지 바꾸므로 C11을 "centroid fallback 보정"으로만 쓰자는 안전 원칙에 맞지 않는다. 또한 500m 초과 이동이 166건 남는다.

`centroid_c4_50_c6_c7_ok`는 C11을 기존 centroid fallback row에만 적용하므로 정책 의도가 더 분명하다. candidate C4/C6/C7 오류는 0건이지만, 500m 초과 이동 164건과 최대 182km outlier가 남는다.

`centroid_c4_50_c6_c7_single_candidate`는 다중 후보를 배제해 100m 초과 이동을 1,039건 줄이지만, 여전히 500m 초과 143건과 최대 182km outlier가 남는다. coverage는 12,681건 줄어든다.

`centroid_c4_50_c6_c7_move_500`은 coverage 손실이 164건뿐인데 500m 초과 outlier를 모두 제거한다. C4/C6/C7 오류 0건도 유지한다. 따라서 T-132 반복 검증의 1차 정책 후보로 둔다.

## 후속

T-132에서는 `centroid_c4_50_c6_c7_move_500`을 기본 후보로 삼고, threshold를 flag로 바꿔 반복 실행할 수 있어야 한다.

1. `pt_source='centroid'`
2. `candidate_c4_dist_m <= 50`
3. `candidate_c6_ok AND candidate_c7_ok`
4. `movement_m <= 500`

추가로 `movement_m <= 100`, `candidates_per_bd = 1`, 같은 기준월 원천이 준비됐을 때의 `same_text_month` gate를 비교 대상으로 남긴다. T-133 shadow serving은 T-132가 같은 결과를 재현한 뒤에만 진행한다.

## 검증

```bash
python -m pytest tests/unit/test_t131_c11_guarded_policy_simulation.py -q
python -m ruff check scripts/run_t131_c11_guarded_policy_simulation.py tests/unit/test_t131_c11_guarded_policy_simulation.py
python -m mypy scripts/run_t131_c11_guarded_policy_simulation.py
```

WSL ext4 테스트 미러에서도 같은 focused pytest/ruff/mypy를 통과했다. 실제 simulation은 WSL ext4 테스트 미러에서 587.920초 동안 실행됐다.
