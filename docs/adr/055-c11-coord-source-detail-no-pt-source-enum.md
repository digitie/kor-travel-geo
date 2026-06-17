# ADR-055: C11 좌표 세부 출처는 `coord_source_detail`로 노출하고 `pt_source` enum은 확장하지 않는다

- 상태: accepted
- 날짜: 2026-06-16
- 결정자: codex
- 관련: T-134, T-119, T-125, T-132, T-133, T-137, T-105, T-169, T-219, ADR-003, ADR-051, ADR-053, ADR-054

## 컨텍스트

T-125는 C11 `도로명주소 건물 도형` 출입구 후보를 현행 대표 좌표와 비교했고, C3 결측은 줄었지만 p95/p99 이동, 100m 초과 outlier, C4/C6/C7 회귀가 gate를 넘어서 no-go로 판정했다. T-132 guarded 정책은 correctness hard block이 없었지만 100m 초과 이동 warning이 남았고, T-133 shadow serving 리허설은 rollback은 통과했지만 SQL/REST p95 성능 gate가 실패했다.

그럼에도 C11은 당시 T-137/T-119에서 다시 논의될 수 있었으므로, active serving 구현 전에 좌표 출처 노출 계약을 확정해야 했다. 특히 `pt_source`에 `c11_bundle_guarded` 같은 새 값을 넣을지, v1 VWorld 호환 표면을 어떻게 유지할지, v2 후보 metadata로 분리할지를 정해야 했다. 이후 T-137은 C11을 validation-only로 고정하고 active serving 승격을 금지했다.

## 결정

1. `pt_source`는 coarse enum으로 유지한다. 허용 값은 `entrance`, `centroid`뿐이다. C11, 위치정보요약DB, direct 출입구, 내비 centroid 같은 세부 원천명을 `pt_source` 값으로 추가하지 않는다.
2. 세부 좌표 출처는 `coord_source_detail` 문자열로 표현한다. C11 guarded 후보는 `coord_source_detail="c11_bundle_guarded"`를 사용한다.
3. v1 REST 응답에는 최상위나 `result` 내부 자체 필드를 추가하지 않는다. 필요 시 `response.x_extension.pt_source`와 `response.x_extension.coord_source_detail`만 사용한다.
4. v1 reverse는 후보가 여러 개라 top-level `x_extension.coord_source_detail` 하나로 안정 표현할 수 없다. 후보별 좌표 출처가 필요한 사용자는 v2 reverse를 사용한다.
5. v2는 `CandidateV2.point_precision`으로 큰 정밀도 계층을 표현하고, 세부 출처는 `CandidateV2.metadata.pt_source`와 `CandidateV2.metadata.coord_source_detail`에 둔다. 안정 public field 승격과 enum 확장은 T-105/T-169에서 별도 결정한다.
6. T-134는 문서와 테스트 계획만 확정한다. 현재 `GeocodeExtension`에는 `pt_source`/`coord_source_detail` field가 없으므로 OpenAPI/typegen/code 변경은 하지 않는다.

## 근거

- `pt_source`는 hot path ranking과 confidence 산정에 쓰이는 coarse field다. 세부 원천명을 섞으면 `ORDER BY CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END` 같은 기존 쿼리 의미가 흐려진다.
- v1은 VWorld 호환 surface다. 자체 정보는 ADR-003/ADR-053에 따라 `x_extension`으로 격리해야 한다.
- v2는 candidate schema라 후보별 metadata를 자연스럽게 담을 수 있다. 다만 metadata field를 바로 first-class schema로 승격하면 T-105 v2 재audit과 T-169 enum 정직화 범위를 선점하게 된다.
- T-133은 no-go라 즉시 API field를 추가할 필요가 없다. 계약만 먼저 고정해 후속 구현 PR의 scope를 줄이는 편이 안전하다.

## 결과(긍정)

- v1 호환 surface를 유지하면서 C11 세부 출처를 설명할 수 있다.
- `pt_source` enum 확장으로 인한 query/order/UI/typegen 회귀를 피한다.
- T-105/T-169에서 v2 field 승격을 더 넓은 API 정리와 함께 다룰 수 있다.

## 결과(부정)

- C11 세부 출처를 안정 typed field로 즉시 노출하지 않는다. v2 사용자는 당분간 `metadata.coord_source_detail`을 읽어야 한다.
- v1 reverse에는 후보별 C11 세부 출처를 제공하지 않는다.
- 나중에 `GeocodeExtension` field를 추가하면 OpenAPI와 UI typegen 갱신이 필요하다.

## 후속

- (done) T-134에서 세부 계약과 테스트 계획을 `docs/t134-c11-coordinate-source-contract.md`에 정리한다.
- (done) T-137은 C11 최종 gate와 ADR-051 상태를 재판정했고, C11을 validation-only로 고정했다.
- (blocked) T-119가 새 증거와 사용자 승인으로 재개되면 구현 PR에서 `coord_source_detail` 산출, v1 geocode `x_extension`, v2 metadata/point_precision 매핑, OpenAPI/typegen/tests를 함께 반영한다.
- (open) T-105/T-169에서 v2 `point_precision` enum과 candidate source field 승격 여부를 재검토한다.
