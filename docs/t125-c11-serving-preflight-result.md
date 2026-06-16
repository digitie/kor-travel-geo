# T-125 C11 serving 사전 검증 결과

작성일: 2026-06-15

## 결론

T-125 gate 결과는 **blocked / no-go**다. C11 `도로명주소 건물 도형` 출입구 후보는 `mv_geocode_target` serving ranking에 바로 편입하지 않는다. ADR-051은 `proposed` 상태를 유지하고, T-119는 계속 보류한다.

T-137 최종 종합 gate에서도 이 결론은 바뀌지 않았다. T-131/T-132 guarded policy는 반복 가능한 검증 후보를 만들었지만, 100m 초과 이동 `10,099`건과 T-133 SQL/REST p95 성능 회귀 때문에 active serving 승격은 금지한다. C11은 validation-only로 고정한다.

주요 차단 사유:

- 기존 대표점 대비 거리 impact가 ADR-051 초안 임계값을 넘었다. p95 `22.801m`, p99 `54.283m`, 100m 초과 `14,433`건이다.
- C3 대표 출입구 결측은 크게 줄지만, C4/C6/C7 ERROR가 증가했다.
- SQL/REST p95 후보 경로 benchmark와 feature flag off/on rollback 리허설은 T-119 구현 전에는 실행할 수 없어 gate를 만족하지 못한다.

## 실행 기준

| 항목 | 값 |
|------|----|
| DB | `kor_travel_geo_t213_20260615_r3` |
| active serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |
| source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| 후보 원천 | `roadaddr_building_shape_bundle` / `TL_SGCO_RNADR_MST` + `TL_SPBD_ENTRC` |
| 후보 기준월 | `202604` |
| 실행 미러 | `/home/digitie/dev/kor-travel-geo-codex-t125-test` |
| 보존 artifact | `F:\dev\geodata\t125-c11-serving-preflight\20260615-r2\` |

검증은 운영 serving object를 변경하지 않고 `_ktg_t125_*` 작업 테이블로만 수행했다. 완료 후 작업 테이블은 삭제했고, 확인 결과 `_ktg_t125_%` relation은 0개다.

## Coverage

| metric | 값 |
|--------|---:|
| bundle address rows | 6,406,445 |
| bundle entrance rows | 6,454,571 |
| candidate raw rows | 6,454,564 |
| candidate distinct `bd_mgt_sn` | 6,406,165 |
| current `mv_geocode_target` rows | 6,419,795 |
| matched current/candidate rows | 6,404,009 |
| current only rows | 15,786 |
| candidate only rows | 2,156 |

`TL_SGCO_RNADR_MST`에는 `BD_MGT_SN`이 없으므로 26자리 `ADR_MNG_NO`를 후보 `bd_mgt_sn`으로 사용했다. `tl_juso_text`와는 대부분 맞지만, 전자지도 polygon과는 직접 `bd_mgt_sn`으로 조인하지 않고 natural key를 써야 한다.

## Namespace 위험

| metric | 값 |
|--------|---:|
| weak key count (`sig_cd + ent_man_no`) | 6,454,562 |
| duplicate weak key | 2 |
| weak key to multiple `bd_mgt_sn` | 2 |
| multiple candidate를 가진 `bd_mgt_sn` | 34,861 |
| max candidates per `bd_mgt_sn` | 95 |

weak key namespace 자체는 전국 기준 낮은 위험으로 보인다. 단, serving 편입 판단은 weak key가 아니라 `ADR_MNG_NO`/natural key와 정합성 회귀를 함께 봐야 한다.

## 대표점 Impact

| metric | 값 |
|--------|---:|
| matched point rows | 6,404,009 |
| p50 | 2.348m |
| p95 | 22.801m |
| p99 | 54.283m |
| max | 182,892.443m |
| 10m 초과 | 1,180,674 |
| 30m 초과 | 194,495 |
| 100m 초과 | 14,433 |

`pt_source`별 영향:

| current `pt_source` | rows | p95 | p99 | 100m 초과 |
|---------------------|-----:|----:|----:|----------:|
| `centroid` | 3,498,081 | 31.840m | 71.008m | 14,260 |
| `entrance` | 2,905,928 | 0.000001m 미만 | 0.000001m 미만 | 173 |

상위 outlier에는 경남 일부 주소에서 경도 약 2도 차이가 나는 좌표가 포함됐다. 예: 통영/창원 주소에서 현재점과 후보점이 `128.x` ↔ `130.x`로 갈라진다. 이는 후보 좌표 원천 오류, 후보 관리번호 대응 오류, 또는 현행 fallback centroid 오류를 분리해 수동 판정해야 한다.

## C3/C4/C6/C7 회귀

| case | baseline | candidate | 판정 |
|------|---------:|----------:|------|
| C3 대표 출입구 결측 | 3,513,854 WARN | 15,786 WARN | 개선 |
| C4 출입구-건물 polygon 거리 | 3,416 ERROR / over500 16 | over500 68 ERROR, polygon unmatched 18,453 | 악화 |
| C6 우편번호 polygon 외부 | 803 ERROR | 3,635 ERROR | 악화 |
| C7 행정구역 polygon 외부 | 6,815 ERROR | 9,896 ERROR | 악화 |

C4 후보 측정은 `ADR_MNG_NO` 직접 조인이 아니라 `rncode_full + buld_se_cd + buld_mnnm + buld_slno` natural key로 전자지도 polygon을 찾았다. 후보 C4 p95는 `8.091m`, p99는 `21.237m`지만, 500m 초과가 68건이라 gate를 통과하지 못한다.

## 성능·Rollback·노출 정책

성능 baseline은 T-214/T-217 SQL, T-216 REST 수용 결과로 확보되어 있다. 하지만 T-119의 flag-controlled serving query path 또는 shadow MV가 아직 없으므로, 후보 on/off SQL/REST p95 회귀는 T-125에서 실행할 수 없다.

T-119가 재검토된다면 최소 조건은 다음이다.

- feature flag 기본 off.
- flag off에서 기존 `mv_geocode_target` hash/표본이 동일.
- flag on 후보 경로에서 SQL/REST p95 회귀 5% 이하.
- rollback은 `flag off + mv_refresh` 또는 동등한 hot-swap으로 리허설.
- v1 `pt_source` 값은 기존 `entrance`/`centroid`를 유지하고, 세부 출처는 `x_extension.coord_source_detail` 또는 v2 전용 필드로만 노출.

## 후속 Action Task

T-125 결과에 따른 후속 작업은 `docs/tasks.md`의 T-129~T-134·T-137(+ Admin UI 반영 T-220/T-221)로 분리했다.

| Task | 목적 |
|------|------|
| T-129 | 100m 초과 outlier 14,433건을 원인별로 태깅한다. |
| T-130 | C4/C6/C7 회귀 샘플의 polygon/key/좌표 원인을 분석한다. |
| T-131 | blanket 승격 대신 guarded candidate policy를 설계하고 오프라인 simulation한다. |
| T-132 | T-125 preflight harness를 policy 반복 검증용으로 확장한다. |
| T-133 | shadow serving path에서 성능 회귀와 rollback을 리허설한다. |
| T-134 | v1/v2 좌표 출처 노출 계약을 확정한다. |
| T-220 (과거 T-135) | 실제 활용 파일과 Admin UI 표시가 일치하는지 감사한다. |
| T-221 (과거 T-136) | T-125 이후 적재·검증·승격 보류 상태를 Admin UI에 반영한다. |
| T-137 | 후속 산출물을 종합해 ADR-051과 T-119 진행 여부를 재판정했고, C11을 validation-only로 고정했다. |

별도 read-heavy 성능 최적화는 T-138, additive 튜닝으로 부족할 때의 DB 구조 변경 실험 DB 비교는 T-139에서 진행한다. 배포 전 안정화·고성능 geocoder/Admin UI 보강은 T-140~T-153 병행 트랙에서 다룬다.

T-137 완료 후 T-119는 착수하지 않는다. 새 같은 기준월 C11 원천, correctness 무회귀, SQL/REST p95 회귀 5% 이하, rollback 리허설, ADR-055 구현 계획, 사용자 명시 승인이 모두 다시 갖춰질 때만 재논의한다.

## 검증

```bash
python -m pytest tests/unit/test_t125_c11_serving_preflight.py -q
python -m ruff check scripts/run_t125_c11_serving_preflight.py tests/unit/test_t125_c11_serving_preflight.py
```

WSL ext4 미러에서도 같은 focused pytest/ruff를 통과했다. 전국 실검증 러너는 `scripts/run_t125_c11_serving_preflight.py`이며, 산출물은 `summary.json`, `outliers_over_100m.csv`, `outliers_over_100m.geojson`이다.
