# ADR-054: optional 원천은 역할별로 승격하고 국가지점번호 좌표는 계산값을 사용한다

- 상태: accepted
- 날짜: 2026-06-15
- 결정자: 사용자 요청, codex
- 관련: PR #193, PR #194, T-118, T-123, T-125, T-216, ADR-026, ADR-027, ADR-051

## 컨텍스트

PR #193은 clean-slate v2 가정에서 optional 데이터셋이 상세주소와 무주소 정확도를 실제로 높일 수 있는지 검토했고, PR #194는 데이터셋별 요약 표를 추가했다. 두 PR 모두 GitHub conversation comment, review, review thread가 0건이므로 반영 대상은 PR comment가 아니라 문서 본문 의견이다.

이후 T-125는 `도로명주소 건물 도형` C11 출입구 후보를 실제 T-213 r3 serving DB에서 기존 `mv_geocode_target` 대표점과 비교했다. C3 결측은 줄었지만 p95/p99/outlier와 C4/C6/C7 회귀가 ADR-051 gate를 넘어서 C11 blanket 승격은 no-go로 판정됐다.

## 결정

optional 원천은 하나의 "쓰거나 버리는" 집합이 아니라 역할별로 분리한다. 최종 source-of-truth 문서는 `docs/optional-source-usage-decision.md`다.

1. **국가지점번호 좌표는 활용한다.** 좌표는 `국가지점번호 도형/중심점` 파일 적재가 아니라 `core.sppn`의 EPSG:5179 10m cell 계산값으로 만든다. `TL_SPPN_MAKAREA`는 좌표 원천이 아니라 표기 의무지역 context로 유지한다.
2. `도로명주소 건물 도형`의 `TL_SPBD_ENTRC`는 현행 대표 좌표 ranking에 blanket 승격하지 않는다. T-125 no-go 결과를 우선하고, 검증·outlier 분석 원천으로 유지한다.
3. `도로명주소 건물 도형`의 `TL_SGCO_RNADR_MST`와 `TL_SPOT_CNTC`는 geometry/connection 검증 원천으로 둔다. 기존 전자지도 `TL_SPBD_BULD`나 대표 point를 대체하지 않는다.
4. `상세주소DB`와 `건물군 내 상세주소 동 도형`은 상세주소 기능 후보로 승격할 수 있다. 단, 호별 좌표가 없으므로 일반 주소 대표 좌표 정확도 개선 원천으로 표시하지 않는다.
5. `주소DB`, `건물DB`, `내비게이션용DB match_jibun`, `민원행정기관전자지도`, `국가지점번호 도형/중심점`은 기본 주소 좌표 원천이 아니라 검증·overlay·별도 feature 후보로 둔다.
6. 과거 snapshot은 최신 serving source set 입력으로 쓰지 않고 회귀·복원·일변동 검증용으로만 보존한다.

## 근거

- 좌표가 없는 원천(`상세주소DB`, `주소DB`, `건물DB`)은 대표 좌표 정확도를 직접 높일 수 없다.
- 의미가 다른 좌표(`민원행정기관전자지도` POI)는 주소 대표점과 같은 좌표로 취급하면 안 된다.
- 국가지점번호는 문자열 자체가 좌표를 결정하므로 grid 파일보다 계산식이 더 정밀하다. 100m grid/center 원천은 10m 좌표 개선이 아니라 parser/formatter 검증에 맞다.
- C11은 유일한 대표점급 optional 후보였지만, T-125에서 p95 `22.801m`, p99 `54.283m`, 100m 초과 `14,433`건과 C4/C6/C7 악화가 확인됐다.
- 1:N 후보를 단일 flat MV로 펼치면 ADR-007의 `bd_mgt_sn` unique, `REFRESH CONCURRENTLY`, search dedup/pagination 이득이 깨진다. 별도 typed candidate/보조 테이블로 분리해야 한다.

## 결과

- `docs/optional-source-usage-decision.md`가 optional 원천 사용/미사용 최종 판정 문서가 된다.
- `docs/source-data-accuracy-review.md`는 배경 검토 문서로 남기고, 최신 판단은 ADR-054와 최종 판정 문서를 우선한다.
- ADR-051은 계속 `proposed`이고 T-119는 보류한다.
- T-105 v2 재audit에서는 국가지점번호 makarea gate 분리, reverse formatter first-class 노출, 상세주소 typed candidate 설계를 후속으로 다룬다.
