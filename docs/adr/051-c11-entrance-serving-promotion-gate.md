# ADR-051: 보강 출입구 source의 serving 좌표 ranking 편입은 별도 gate로 제한한다

- 상태: proposed (T-137 최종 gate 후 accepted 전환 거절, C11은 validation-only로 고정)
- 날짜: 2026-06-14
- 결정자: codex

## 컨텍스트

T-111~T-117은 C11~C17 보강 검증 prototype을 만들었다. 이 중 일반 도로명주소 geocode/reverse 대표 좌표를 직접 개선할 가능성이 있는 source는 C11 출입구 계열뿐이다. 그러나 기존 `mv_geocode_target`은 1주소 1행과 `pt_source ∈ {entrance, centroid}` 계약을 갖고, v1은 vworld 호환 응답을 유지해야 한다. T-039 direct entrance도 기준월이 맞는 경우에만 fallback 후보가 되도록 이미 제한돼 있다.

## 결정

C11~C17은 기본적으로 검증 전용으로 유지한다. C11 출입구 계열만 조건부 serving 편입 후보로 두며, 다음 gate를 모두 통과하고 본 ADR이 accepted로 전환된 뒤에만 T-119에서 `mv_geocode_target` ranking 변경을 구현한다.

1. 전국 C11 실행 결과 source별 `source_yyyymm`가 정본 텍스트·도형과 일치하거나, 혼합 기준월 노이즈가 별도 artifact로 분리되어야 한다.
2. candidate source의 key overlap은 full key 기준 99.9% 이상이어야 한다. weak key(`sig_cd + ent_man_no`)만 가능한 비교는 단독 승격 근거로 쓰지 않는다.
3. 기존 대표점 대비 거리 p95는 10m 이하, p99는 30m 이하, 100m 초과 outlier는 0.1% 이하를 초안 임계값으로 둔다. T-121/T-123 전국 실측에서 더 엄격한 값으로 조정할 수 있다.
4. C3/C4/C6/C7 severity와 ERROR count가 baseline보다 악화되면 편입하지 않는다.
5. REST/SQL benchmark p95 회귀가 5%를 넘으면 편입하지 않는다.
6. feature flag는 기본 off다. 운영자가 명시적으로 켠 환경에서만 새 ranking을 사용하고, rollback은 flag off + MV refresh로 가능해야 한다.
7. public `pt_source` enum 확장은 기본 보류한다. v1 호환을 위해 기존 `entrance`/`centroid`는 유지하고, 세부 출처는 우선 `x_extension.coord_source_detail` 또는 v2 전용 필드로 노출한다. `pt_source` 값 확장이 필요하면 OpenAPI, 프론트엔드 타입, v1/v2 문서를 함께 갱신한다.

## 근거

- C12~C17은 좌표 원천이 아니거나 일반 주소 대표 좌표와 의미가 다르다. validation/report로는 가치가 있지만 serving ranking에 섞으면 `mv_geocode_target` 계약이 흐려진다.
- C11도 full key 비교와 weak key 비교가 섞인다. weak key는 전국 중복 위험을 먼저 정량화해야 한다.
- 기준월 차이가 있는 좌표를 ranking에 넣으면 실제 정확도 개선과 월차 노이즈를 분리하기 어렵다.
- v1 응답은 vworld 호환이 핵심이다. 새 `pt_source` 값을 성급히 추가하면 기존 소비자와 UI 타입에 영향을 준다.

## 결과(긍정)

- 보강 검증과 serving 변경의 경계가 명확해진다.
- T-206은 C11~C17을 registry seed로 정식화하되, T-119 없이도 phase ②를 진행할 수 있다.
- T-119가 진행되더라도 feature flag와 rollback 경로를 전제로 하므로 운영 위험을 줄인다.

## 결과(부정)

- C11이 실제로 좋은 좌표 원천이어도 T-121~T-123 전국 측정과 ADR 승인 전까지 serving 개선은 지연된다.
- `x_extension.coord_source_detail` 또는 v2 전용 세부 출처 필드가 필요해지면 DTO/OpenAPI/UI 변경이 별도 PR 범위로 생긴다.

## T-123 평가

T-123 전국 재측정에서 C11 bundle `TL_SPBD_ENTRC`와 전자지도 `TL_SPBD_ENTRC`는 full key 기준 intersection 6,405,305건, left overlap 0.992367, right overlap 0.999943, 거리 p95/max 0.0m를 기록했다. 이 결과는 C11을 계속 조건부 serving 후보로 둘 만큼 강하지만, 본 ADR을 accepted로 전환하기에는 아직 부족하다.

부족한 증거는 다음과 같다.

1. 기존 `mv_geocode_target` 대표점 대비 p95/p99/outlier 영향이 같은 harness에서 아직 측정되지 않았다.
2. C3/C4/C6/C7 severity와 ERROR count가 C11 scoring 편입 뒤 악화되지 않는지 검증하지 않았다.
3. 운영 테이블과의 weak key(`sig_cd + ent_man_no`) 비교는 전국 outlier와 key namespace 위험이 있어 단독 승격 근거로 쓰지 않는다.
4. Feature flag, rollback, v1/v2 노출 정책은 구현 전 설계만 존재한다.

따라서 T-123 acceptance는 C11을 "조건부 serving 후보"로 유지하되, T-119 구현 승인은 보류한다고 결론 내렸다. C12~C17은 검증 전용으로 최종 확정한다.

## T-125 사전 검증 gate

T-119 착수 전에는 `docs/t125-c11-serving-preflight.md`의 체크리스트를 모두 채워야 한다. 특히 다음 5개 증거가 하나라도 없으면 본 ADR을 `accepted`로 전환하지 않는다.

1. 기존 `mv_geocode_target` 대표점 대비 C11 후보 impact: 거리 p50/p95/p99/max, 100m 초과 outlier, sample CSV/GeoJSON.
2. C3/C4/C6/C7 회귀: 같은 case definition 기준 baseline/candidate severity와 ERROR/WARN count delta.
3. 성능 회귀: T-047/T-214 계열 SQL/REST p95, timeout/error count, 주요 query plan 차이.
4. feature flag rollback: 기본 off, flag on/off MV 생성 차이, `flag off + mv_refresh` 또는 동등한 rollback 리허설.
5. v1/v2 노출 정책: v1 `pt_source` 호환 유지, 세부 출처는 `x_extension` 또는 v2 전용 필드, OpenAPI/UI type 영향 검토.

이 gate가 모두 통과해도 T-119는 자동 착수하지 않는다. ADR-051 `accepted` 전환 PR과 사용자 명시 승인을 별도로 받아야 한다.

## T-125 평가

2026-06-15 T-125 사전 검증에서 C11 후보를 실제 T-213 r3 serving DB 기준으로 staging 비교했다. 후보는 `TL_SGCO_RNADR_MST.ADR_MNG_NO`와 `TL_SPBD_ENTRC`를 결합해 대표 출입구를 만든 뒤 기존 `mv_geocode_target` 대표점과 비교했다.

결론은 **blocked / no-go**다. C3 대표 출입구 결측은 3,513,854건에서 15,786건으로 크게 줄지만, 기존 대표점 대비 거리 p95 `22.801m`, p99 `54.283m`, 100m 초과 `14,433`건으로 ADR-051 초안 임계값을 넘었다. 또한 C4 over500은 16건에서 68건, C6 ERROR는 803건에서 3,635건, C7 ERROR는 6,815건에서 9,896건으로 증가했다. SQL/REST 후보 경로 benchmark와 feature flag rollback 리허설도 T-119 구현 전에는 실행할 수 없다.

따라서 ADR-051은 계속 `proposed`로 유지하고, T-119는 착수하지 않는다. 상세 artifact는 `F:\dev\geodata\t125-c11-serving-preflight\20260615-r2\`, 요약 문서는 `docs/t125-c11-serving-preflight-result.md`에 둔다.

## T-137 최종 gate

2026-06-16 T-137은 T-129~T-134와 Admin UI 반영 T-220/T-221을 묶어 ADR-051을 재판정했다. 결론은 **validation-only 고정 / active serving no-go**다.

- T-129는 T-125의 100m 초과 outlier 14,433건 중 `candidate_coordinate_error=13,000`건을 확인했다.
- T-130은 C6/C7 증가가 기존 baseline 출입구 결측 row를 C11 후보로 새로 평가하면서 대량 표면화된다는 점을 확인했다.
- T-131/T-132의 guarded 정책 `centroid_c4_50_c6_c7_move_500`은 candidate C4/C6/C7 오류 0건을 재현했지만, 100m 초과 이동 `10,099`건과 기준월 차이를 남겼다.
- T-133 shadow serving은 rollback과 cleanup은 통과했지만 SQL max p95 회귀 `83.087%`, REST max p95 회귀 `132.447%`로 성능 gate를 실패했다.
- T-134/ADR-055는 좌표 출처 계약만 확정했고, T-220/T-221은 C11 no-go를 Admin UI에 `promotion_blocked_no_go`로 표시하는 방향으로 반영했다.

따라서 본 ADR은 `accepted`로 전환하지 않는다. T-119는 새 같은 기준월 원천, correctness 무회귀, SQL/REST p95 회귀 5% 이하, rollback, ADR-055 구현 계획, 사용자 명시 승인이 모두 다시 갖춰질 때만 재논의한다. 상세는 `docs/t137-c11-final-gate.md`에 둔다.

## 후속

- (done) T-121/T-123 전국 C11~C17 실행에서 본 ADR 임계값을 일부 평가했다.
- (done) T-123 최종 검증에서 ADR-051은 accepted로 전환하지 않는다. C11은 조건부 serving 후보로 유지하고 C12~C17은 검증 전용으로 둔다.
- (done) T-125는 기존 대표점 대비 impact와 C3/C4/C6/C7 회귀를 artifact로 채웠고, gate는 blocked/no-go로 판정했다.
- (done) T-137은 T-129~T-134와 T-220/T-221을 종합해 C11을 validation-only로 고정하고 ADR-051 accepted 전환을 거절했다.
- (blocked) T-119는 새 증거, ADR-051 accepted 전환, 사용자 명시 승인 뒤에만 재논의한다.
