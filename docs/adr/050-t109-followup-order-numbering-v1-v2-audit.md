# ADR-050: T-109 후속은 데이터 원천 보강 검증을 먼저, 적재/백업 구현을 다음에 한다 (T-numbering·v1/v2 audit 포함)

- 상태: accepted
- 날짜: 2026-06-14
- 결정자: 사용자 요청, claude

## 컨텍스트

T-109(PR #131) 백업 원천 업로드·매칭·검증 설계가 여러 차례 리뷰를 거쳐 수렴했다. 이제 후속 구현을 어떤 순서·번호 체계로 잘게 나눠 진행할지, 그리고 v1/v2 REST API 재점검을 백로그 어디에 둘지 확정한다.

## 결정

1. **작업 순서**: ① 데이터 원천 보강·테스트 검증을 **먼저**, ② 데이터 적재/백업 기능(T-109 설계) 구현·검증을 **다음에** 한다.
2. **번호 체계**: 원천 보강은 `T-110`부터 1씩, 적재/백업은 `T-200`부터 1씩 올린다. 중간에 추가되는 작업은 각각 `T-1xx`/`T-2xx` 번호로 채운다.
3. **T-105 = v2 API 재audit**: 기존 호환성보다 **확장성·일관성·유지보수성** 기준으로 v2를 재audit한 뒤 반영한다(v1 vworld 호환은 불변).
4. **T-106 = v1 vworld 100% 호환**: v1 geocoding/reverse가 vworld와 100% 호환인지 재점검·검증하고 코드에 반영한다. 단 현 ADR-038은 v1을 'vworld-style 키 + 자체 `x_extension`'으로 정의하므로, T-106 착수 시 **호환 수준(키 호환 vs wire 100%)을 먼저 ADR로 확정**(ADR-038 보정 여부 포함)한다.
5. **T-105·T-106은 우선순위 최하위**(ID는 110보다 낮지만 순위는 phase ①·② 뒤).
6. phase ① prototype은 `ops.source_*` registry에 **의존하지 않고** 로컬 디스크 경로로 독립 수행한다(역의존 금지). C11~C17 검증은 phase ①에서 prototype으로 만들고, phase ②(T-206)에서 `ops.consistency_case_definitions` registry로 정식화하며 "prototype metric == run-validation metric" 회귀로 두 정의가 갈라지지 않게 한다.
7. 보강 자료의 serving 좌표 ranking 편입(T-119)은 **별도 ADR 게이트(T-118 산출) 승인 후에만** 진행한다. 그 전(T-111~T-118)은 측정·검증·결정만 하고 `mv_geocode_target`을 바꾸지 않는다.
8. **T-109(PR #131)는 ②의 설계 문서**이며, 구현은 T-200대(T-200~T-215)로 분할한다. 각 phase 끝에는 전국 라이브데이터 실행/로딩 → 성능평가·벤치 → 튜닝·최종 검증 평가를 둔다(phase ① T-121~T-123, phase ② T-213~T-215).

## 근거

- 어떤 보강 source가 실제로 정확도/coverage를 높이는지 먼저 정량화해야 phase ②의 C11+ 케이스·match set category·serving 편입 범위가 확정된다. 가치 없는 source에 업로드/match-set 기계를 만드는 낭비를 막는다.
- phase ①은 기존 loader + `compare_*` 스크립트로 현행 full-load 파이프라인 위에서 독립 수행 가능해, phase ②의 무거운 registry/UI를 기다릴 필요가 없다.
- v1은 vworld 호환 소비자 보존이 존재 이유(ADR-038)라 응답 변경 위험이 크고 '재점검' 성격이므로 최하위. v2는 1.0 전이라 일관성 정리에 적기이나 핵심 기능 변화가 아니라 최하위.

## 결과(긍정)

- 구현자가 순서·번호·우선순위를 명확히 따를 수 있고, phase 분리로 헛작업을 막는다.
- C11+ prototype→registry 분리, epost phase①검증/phase②fetch UI 분리 같은 cross-cutting 경계가 task 단위로 고정된다.

## 결과(부정)

- phase ① prototype 일부 측정 로직이 phase ② registry 정식화에서 재구현될 수 있으나, 기존 `compare_*`/`building_shape_bundle`/`extra_shape_layers` 재사용으로 비용은 낮다.

## 후속

- (resolved, ADR-053) T-106 호환 수준은 REST v1 geocode/reverse의 VWorld HTTP envelope/key/대소문자 호환으로 확정했다. 자체 보강 정보는 `x_extension`에 유지한다.
- (open) 보강 자료 serving 편입 ADR(T-118 산출물).
- (open) 영역 간 단일 `openapi.json`/`api.gen.ts` 동시 변경 충돌을 막는 머지 순서·재생성 규칙.
