# T-123 phase ① 튜닝·최종 검증 평가

T-123은 T-121 전국 라이브데이터 보강 실행과 T-122 성능 벤치를 바탕으로, C11~C17 phase ① prototype의 튜닝 가능성을 점검하고 source별 최종 go/no-go를 확정한다. 이 문서는 phase ① acceptance 기록이다.

## 입력과 산출물

| 항목 | 값 |
|------|----|
| 기준 원천 | `/mnt/f/dev/kor-travel-geo/data/juso` |
| T-122 기준선 | WSL ext4 테스트 미러 `artifacts/perf/t122-phase1-live/` |
| T-123 재측정 | WSL ext4 테스트 미러 `artifacts/perf/t123-phase1-tuned-live/` |
| 보조 A/B | WSL ext4 테스트 미러 `artifacts/perf/t123-c12-noindex-live/` |
| 측정 범위 | runner process RSS와 `/proc/self/io`; PostgreSQL server I/O 제외 |
| 실패 | C11~C17 전체 실패 0건 |

T-122의 `preparation`은 전자지도 ZIP과 C17 7z materialization을 포함한 cold 비용이다. T-123은 T-122의 `materialized/` 디렉터리를 hardlink로 새 출력 디렉터리에 연결해 warm-cache 비용을 분리했다. 따라서 `preparation` 시간은 cold/warm 비교로만 해석하고, case별 시간은 prototype 실행 비용으로 비교한다.

## 튜닝 내용

- `augment_harness`에 staging key btree index와 `ANALYZE` helper를 추가했다.
- C11은 bundle/electronic 출입구 full key와 bundle weak key 반복 조인을 위해 staging index를 생성한다.
- C12는 connection line ↔ road manage key 조인을 위해 staging index를 생성한다. T-122 대비 단순 비교에서는 느렸지만, 같은 실행 세션의 no-index A/B에서는 index 포함이 더 빨랐다.
- C16은 주소DB/건물DB drift 비교에서 반복되는 `bd_mgt_sn`, `bd_mgt_sn+pnu`, natural key, `pnu+road key` staging index를 생성한다.
- 운영 테이블의 persistent index, serving MV, API 응답, source registry 스키마는 변경하지 않았다.

## 성능 비교

| phase | T-122 cold 기준선 | T-123 warm 재측정 | 변화 |
|------|------------------:|------------------:|-----:|
| preparation | 848.988초 | 0.059초 | -848.929초 |
| C11 | 1284.931초 | 1244.657초 | -40.274초 |
| C12 | 270.358초 | 322.643초 | +52.285초 |
| C13 | 307.343초 | 298.915초 | -8.428초 |
| C14 | 378.739초 | 367.429초 | -11.310초 |
| C15 | 17.534초 | 16.126초 | -1.408초 |
| C16 | 624.866초 | 624.698초 | -0.168초 |
| C17 | 229.178초 | 216.364초 | -12.814초 |
| 전체 | 3961.937초 | 3090.891초 | -871.046초 |

C12는 T-122 기준선보다 느렸지만, 같은 코드 시점에서 staging index를 제거한 `t123-c12-noindex-live`는 C12 378.523초였다. 따라서 C12 index는 최종 코드에 유지한다. T-122와 T-123의 C12 차이는 PostgreSQL server cache/동시 부하 상태가 섞였을 가능성이 있어, phase ②에서는 registry runner에서 같은 DB 상태의 paired trial을 다시 둔다.

## 전국 품질 결과

| case | 핵심 결과 | 판정 |
|------|-----------|------|
| C11 | bundle ↔ 전자지도 full key intersection 6,405,305건, left overlap 0.992367, right overlap 0.999943, 거리 p95/max 0.0m | 조건부 serving 후보, 즉시 편입 금지 |
| C12 | road key left overlap 0.999850, connection dangling 37,065건, dangling ratio 0.005790 | 검증 전용 |
| C13 | detail entrance point containment 409,672/424,639, coverage 0.964754 | 검증 전용 |
| C14 | grid/center row count 일치 10,184,741건, formatter parent mismatch 0건, 1km bbox/center mismatch 1,489건 | 검증 전용 |
| C15 | 도로명주소 parse 100%, geocode match ratio 0.976742, p95 194.350m, 100m 초과 14.054% | 검증 전용 |
| C16 | `bd_mgt_sn` 직접 교집합 0건. 건물 natural key overlap은 `tl_spbd_buld_polygon` 0.994684, `tl_juso_text` 0.998793, 지번 `pnu+road key` 0.997444 | 검증 전용 |
| C17 | `bd_mgt_sn+pnu` 직접 교집합 0건. `pnu+road key`는 right overlap 0.999213이나 left overlap 0.215905 | 검증 전용 |

C16/C17의 `bd_mgt_sn` 직접 교집합 0건은 즉시 serving 금지 근거다. 자연키/PNU 기반 overlap은 운영 데이터 drift를 검증하는 데 충분하지만, 해당 원천을 주소 후보 좌표나 parcel 정본으로 승격하는 근거는 아니다.

## 최종 go/no-go

### Serving 후보

- **C11 출입구 source만 조건부 serving 후보로 유지한다.**
- 다만 ADR-051은 T-123에서 `accepted`로 전환하지 않는다.
- 이유는 C11 bundle ↔ 전자지도 full-key 품질은 충분하지만, `mv_geocode_target` 기존 대표점 대비 p95/p99/outlier 영향, C3/C4/C6/C7 악화 여부, T-047/T-214 계열 성능 회귀, feature flag rollback 경로, v1/v2 노출 정책이 아직 같은 gate에서 검증되지 않았기 때문이다. 후속 gate는 `docs/t125-c11-serving-preflight.md`에 고정한다.
- T-119는 ADR-051 accepted와 사용자 승인 전까지 진행하지 않는다.

### 검증 전용

- C12~C17은 모두 phase ② registry/run-validation에 올릴 검증 case로 확정한다.
- `serving_promotion=false`와 `coordinate_load=false` 계약은 유지한다.
- phase ② T-206은 T-123 결과를 seed로 삼아 prototype metric과 registry run-validation metric이 갈라지지 않도록 회귀 테스트를 둔다.

## Acceptance

phase ①은 다음 조건을 만족하므로 완료로 본다.

- C11~C17 전국 실 원천 실행과 재측정이 실패 0건으로 완료됐다.
- Cold materialization 비용과 warm-cache case 실행 비용이 분리됐다.
- Staging index 튜닝이 코드와 테스트로 고정됐다.
- C11만 조건부 serving 후보로 남기고, C12~C17은 검증 전용으로 최종 확정했다.
- ADR-051은 proposed 상태를 유지하며, T-119는 보류한다.
- phase ② T-206 registry 정식화와 T-213 이후 전국 pipeline 검증으로 넘길 입력이 정리됐다.
