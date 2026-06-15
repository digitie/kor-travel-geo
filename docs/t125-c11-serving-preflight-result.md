# T-125 C11 serving 사전 검증 결과

작성일: 2026-06-15

## 결론

T-125 gate 결과는 **blocked / no-go**다. C11 `도로명주소 건물 도형` 출입구 후보는 `mv_geocode_target` serving ranking에 바로 편입하지 않는다. ADR-051은 `proposed` 상태를 유지하고, T-119는 계속 보류한다.

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

## 검증

```bash
python -m pytest tests/unit/test_t125_c11_serving_preflight.py -q
python -m ruff check scripts/run_t125_c11_serving_preflight.py tests/unit/test_t125_c11_serving_preflight.py
```

WSL ext4 미러에서도 같은 focused pytest/ruff를 통과했다. 전국 실검증 러너는 `scripts/run_t125_c11_serving_preflight.py`이며, 산출물은 `summary.json`, `outliers_over_100m.csv`, `outliers_over_100m.geojson`이다.
