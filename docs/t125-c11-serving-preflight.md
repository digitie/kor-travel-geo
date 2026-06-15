# T-125 C11 serving 편입 승인용 사전 검증

T-125는 C11 출입구 후보를 `mv_geocode_target` 대표 좌표 ranking에 편입해도 되는지 판단하기 위한 **승인 전 검증 gate**다. 이 문서는 T-119 구현 계획서가 아니며, 아래 증거가 모두 채워지기 전에는 ADR-051을 `accepted`로 전환하거나 T-119를 구현하지 않는다.

## 범위

- 대상: C11 출입구 계열 후보 중 `mv_geocode_target` 대표 좌표를 바꿀 수 있는 source.
- 기준: 현재 active serving DB의 기존 `mv_geocode_target` 결과와 C11 후보 적용 결과를 같은 기준월·같은 query corpus·같은 consistency case 정의로 비교한다.
- 산출물 위치: `artifacts/t125-c11-serving-preflight/<YYYYMMDDTHHMMSSZ>/`.
- 문서 산출물: 최종 요약은 이 문서의 후속 절 또는 별도 `docs/t125-c11-serving-preflight-result.md`에 남기고, `docs/tasks.md`, `docs/resume.md`, ADR-051을 함께 갱신한다.

## 착수 전 고정할 기준선

다음 기준선을 먼저 JSON 또는 Markdown으로 기록한다.

| 항목 | 필수 기록 |
|------|-----------|
| DB/release 기준 | `serving_release_id`, `dataset_snapshot_id`, source match set, `mv_geocode_target` row count |
| C11 후보 기준 | source group, source month, full key/weak key 구분, 후보 row count |
| 정합성 기준 | 현재 C3/C4/C6/C7 report id, case definition version, severity, ERROR/WARN count |
| 성능 기준 | T-047 또는 T-214 SQL/REST benchmark corpus, p50/p95/p99, timeout/error count |
| API 기준 | v1/v2 OpenAPI diff 대상 SHA, `pt_source` enum, `x_extension` 정책 |

## 필수 검증

### 1. 기존 대표점 대비 impact

기존 `mv_geocode_target` 대표점과 C11 후보 적용 대표점을 `bd_mgt_sn` 또는 serving row key 단위로 1:1 비교한다.

필수 metric:

- 비교 대상 row count, current-only, candidate-only, matched count.
- 거리 delta p50/p95/p99/max.
- 10m/30m/100m 초과 count와 ratio.
- 100m 초과 outlier sample CSV와 지도 검토 가능한 GeoJSON.
- 기존 `pt_source`별 영향 분포(`entrance`, `centroid`).
- 개선/악화 sample을 분리한 수동 판정 표.

통과 기준 초안:

- p95 10m 이하.
- p99 30m 이하.
- 100m 초과 outlier 0.1% 이하.
- outlier가 원천 오류, 기준월 차이, weak key 충돌 중 무엇인지 분류되어야 한다.

### 2. C3/C4/C6/C7 회귀

C11 후보 적용 전후로 같은 case definition과 같은 sample policy를 사용해 C3/C4/C6/C7을 다시 실행한다.

필수 metric:

- case별 baseline severity, candidate severity.
- case별 ERROR/WARN count delta.
- 새로 생긴 ERROR sample과 사라진 ERROR sample.
- 기존 알려진 원천 품질 ERROR와 신규 ranking 회귀를 분리한 설명.

통과 기준:

- C3/C4/C6/C7의 `severity_max`가 악화되지 않는다.
- ERROR count가 증가하지 않는다.
- ERROR count가 같더라도 새 outlier가 생기면 원인을 설명하고 사용자 승인을 다시 받아야 한다.

### 3. 성능 회귀

T-047/T-214 계열 SQL/REST corpus를 baseline과 candidate에 같은 조건으로 실행한다.

필수 metric:

- SQL benchmark p50/p95/p99, max, timeout/error count.
- REST benchmark p50/p95/p99, max, HTTP error count.
- `mv_refresh` 또는 rebuild refresh 구간의 wall time과 lock 영향.
- 주요 query군의 `EXPLAIN ANALYZE BUFFERS` 차이.

통과 기준:

- 핵심 SQL/REST p95 회귀가 5%를 넘지 않는다.
- timeout/error count가 증가하지 않는다.
- `mv_geocode_target` row count와 주요 index 사용 계획이 설명 없이 바뀌지 않는다.

### 4. feature flag와 rollback

C11 ranking 편입은 feature flag 기본 off로만 들어갈 수 있다.

필수 확인:

- flag off 상태에서 기존 ranking과 동일한 `mv_geocode_target`이 생성되는지 확인한다.
- flag on 상태에서만 C11 후보가 ranking에 참여하는지 확인한다.
- rollback 절차는 `flag off + mv_refresh` 또는 동등한 hot-swap 절차로 문서화하고 실제 리허설한다.
- rollback 후 row count, 대표점 hash 또는 sample hash가 baseline과 일치하는지 기록한다.
- flag 이름, 설정 위치, 기본값, 운영 변경 절차를 문서화한다.

통과 기준:

- flag 기본값은 off다.
- flag off rollback이 재현 가능해야 한다.
- rollback이 source registry, active release, API 응답 계약을 깨지 않아야 한다.

### 5. v1/v2 노출 정책

v1은 vworld 호환을 유지한다. 새 세부 출처는 `x_extension` 또는 v2 전용 필드로만 노출한다.

필수 확인:

- 기존 public `pt_source` 값(`entrance`, `centroid`)은 유지한다.
- `pt_source` enum 확장이 필요하면 ADR-051을 별도 갱신하고 OpenAPI, UI generated type, v1/v2 API 문서를 함께 갱신한다.
- v1 응답에는 `x_extension` 외 자체 top-level 필드를 추가하지 않는다.
- v2에는 세부 출처 필드 이름, enum, nullable 정책, migration note를 문서화한다.
- v1 golden snapshot 또는 대표 응답 diff로 wire 호환성을 확인한다.

통과 기준:

- v1 소비자가 새 C11 편입을 모르는 상태에서도 기존 필드를 그대로 읽을 수 있어야 한다.
- 세부 출처가 필요하면 `x_extension.coord_source_detail` 또는 v2 전용 필드로 시작한다.

## 승인 조건

T-125 완료 판정은 다음 조건을 모두 만족해야 한다.

- 위 5개 필수 검증의 artifact가 모두 존재한다.
- 실패 또는 보류 항목이 있으면 C11은 검증 전용 후보로 유지한다.
- 모든 통과 기준을 만족하면 ADR-051 `accepted` 전환 제안 PR을 별도로 만들고 사용자 승인을 요청한다.
- 사용자 승인 전까지 T-119 구현 브랜치를 만들지 않는다.

## T-119 착수 금지선

다음 중 하나라도 빠져 있으면 T-119는 착수하지 않는다.

- 기존 `mv_geocode_target` 대표점 대비 impact.
- C3/C4/C6/C7 회귀 비교.
- T-047/T-214 계열 성능 회귀 비교.
- feature flag off/on 및 rollback 리허설.
- v1/v2 노출 정책과 OpenAPI/UI 영향 검토.
- ADR-051 `accepted` 전환.
- 사용자 명시 승인.
