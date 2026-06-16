# T-137 C11 후속 종합 gate 및 ADR-051 재판정

작성일: 2026-06-16

## 결론

C11 `도로명주소 건물 도형` 출입구 후보는 **active serving 좌표 ranking에 편입하지 않는다**. T-137 최종 판정은 **validation-only 고정**이다.

ADR-051은 `accepted`로 전환하지 않는다. T-119는 착수하지 않으며, 사용자 명시 승인 전까지 계속 보류한다. 이후 C11을 다시 논의하려면 기존 T-125/T-133과 다른 새 증거가 필요하다.

핵심 이유는 다음과 같다.

| gate | 결과 | 판정 |
|------|------|------|
| T-125 blanket C11 | p95 `22.801m`, p99 `54.283m`, 100m 초과 `14,433`건, C4/C6/C7 악화 | 실패 |
| T-129 outlier triage | 100m 초과 14,433건 중 `candidate_coordinate_error=13,000` | blanket no-go 유지 |
| T-130 회귀 원인 | C6/C7 증가는 baseline 출입구 결측 row가 후보로 새로 평가되며 대량 표면화 | 강한 guard 필요 |
| T-131 guarded simulation | `centroid_c4_50_c6_c7_move_500`은 C4/C6/C7 오류 0, 100m 초과 이동 `10,099`건 | 후보만 유지 |
| T-132 반복 검증 | 같은 후보 3,482,270건 재현, hard block 0, `serving_promotion_allowed=false` | 승격 금지 |
| T-133 shadow serving | rollback/cleanup 통과, SQL max p95 회귀 `83.087%`, REST max p95 회귀 `132.447%` | 성능 gate 실패 |
| T-134 노출 계약 | `pt_source` enum 확장 금지, 세부 출처는 `coord_source_detail` | 구현 보류 |
| T-220/T-221 Admin UI | C11은 `promotion_blocked_no_go`로 구분해 운영자 오해를 줄임 | UI 반영 완료 |

## 판정

### 1. Blanket C11은 no-go

T-125는 C11 후보를 기존 `mv_geocode_target` 대표점과 직접 비교했다. C3 대표 출입구 결측은 3,513,854건에서 15,786건으로 줄었지만, 거리 impact와 consistency 회귀가 ADR-051 초안 gate를 넘었다.

- 100m 초과 이동: `14,433`건
- C4 over500: `16 → 68`
- C6 ERROR: `803 → 3,635`
- C7 ERROR: `6,815 → 9,896`

T-129/T-130은 이 결과가 단순한 측정 잡음이 아님을 확인했다. 특히 `candidate_coordinate_error`가 13,000건이고, C6/C7은 기존 baseline 출입구가 없던 row가 C11 후보로 새로 평가되면서 대량 오류가 표면화된다.

### 2. Guarded policy도 active go가 아니다

T-131/T-132의 `centroid_c4_50_c6_c7_move_500` 정책은 의미 있는 검증 후보다. 이 정책은 기존 `pt_source='centroid'` row 3,482,270건만 C11 후보로 바꾸고, C4/C6/C7 candidate 오류 0건과 500m 초과 이동 0건을 재현했다.

그러나 active serving 승격에는 부족하다.

- 100m 초과 이동이 `10,099`건 남는다.
- 후보 기준월은 `202604`, 텍스트 정본은 `202605`로 같은 기준월 gate를 통과하지 못한다.
- T-133 shadow serving에서 SQL/REST p95 성능 회귀가 5% budget을 크게 초과했다.

따라서 guarded policy는 **검증·분석 후보**로만 보존하고, active serving 후보로 승인하지 않는다.

### 3. API 계약은 고정하되 구현하지 않는다

T-134/ADR-055는 C11이 나중에 다시 논의될 경우를 대비해 좌표 출처 노출 계약을 확정했다.

- `pt_source`는 coarse enum `entrance`/`centroid`만 유지한다.
- 세부 원천은 `coord_source_detail`로 분리한다.
- v1은 자체 필드를 `response.x_extension` 아래에만 둔다.
- v1 reverse는 후보별 C11 detail을 새로 노출하지 않는다.
- v2는 후보 metadata를 사용하고, stable field 승격은 T-105/T-169로 미룬다.

T-137 결론이 no-go이므로 이번 단계에서는 DTO, OpenAPI, typegen, UI field 구현을 하지 않는다.

### 4. Admin UI는 no-go 오해를 줄이는 방향으로 반영됐다

T-220 감사는 `/admin/source-files`가 optional source의 실제 serving 활용도를 오해시킬 수 있음을 확인했다. T-221은 `serving_usage` 분류를 카탈로그/API/UI에 추가하고, C11을 `promotion_blocked_no_go`로 표시하게 했다.

이 반영은 C11을 serving에 올린다는 뜻이 아니다. 운영자가 "등록됨"과 "active serving 활용 중"을 구분하도록 하는 안전 표면이다.

## ADR-051 재판정

ADR-051은 **accepted로 전환하지 않는다**. 상태는 `proposed`로 남기되, T-137 평가 결과에 따라 현재 C11 경로는 validation-only로 고정한다.

T-119는 다음 조건이 모두 새로 충족될 때만 재논의한다.

1. 같은 기준월 또는 기준월 차이를 제거한 C11 원천 조합이 준비된다.
2. T-125와 같은 blanket/guarded correctness gate에서 C3 개선이 C4/C6/C7 악화 없이 유지된다.
3. T-133과 같은 shadow 또는 동등한 serving rehearsal에서 SQL/REST p95 회귀가 5% 이하이고 오류가 0건이다.
4. rollback/cleanup이 public serving identity를 보존한다.
5. ADR-055 계약에 맞춘 `coord_source_detail` 구현, OpenAPI/typegen/test 계획이 포함된다.
6. ADR-051 accepted 전환 PR과 사용자 명시 승인이 별도로 있다.

이 조건이 없으면 C11은 source registry/run-validation, outlier 분석, Admin UI no-go 표시용 evidence로만 유지한다.

## 후속

- T-119는 계속 보류한다.
- T-138/T-140/T-141 이후 read-heavy 성능·golden corpus·고부하 benchmark 작업을 진행한다.
- T-127은 optional source 구조 validator 강화로 완료했다.
- T-105/T-169는 v2 `point_precision`과 후보 metadata 정직화를 별도 API 재audit 범위에서 다룬다.
