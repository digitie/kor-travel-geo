# ADR-031: 전국 적재 후 쿼리 성능은 반복 벤치마크로 gate하고 보조 view/MV 도입을 허용한다

- 상태: accepted (T-047 1차 harness와 지번 exact 튜닝 완료)
- 날짜: 2026-05-26
- 결정자: 사용자 요청, codex

## 컨텍스트

T-033~T-035는 full-load, SHP 적재, MV refresh/swap 성능을 다뤘다. 그러나 운영 사용자가 직접 체감하는 지표는 적재 시간이 아니라 지오코딩, 역지오코딩, 통합 검색의 응답 latency다. 전국 전체 데이터가 적재된 뒤에는 row count, 데이터 분포, 도시 밀도, fuzzy 후보 수, 공간 index 선택성이 작은 샘플과 다르므로 실제 운영 규모에서 다시 측정해야 한다.

정합성이 맞아도 p95/p99 latency가 높으면 운영 준비가 끝난 것이 아니다. 특히 주소 검색은 대화형 UI와 API 호출 경로에서 반복 실행되므로 tail latency와 timeout이 중요하다.

## 결정

T-047에서는 전국 full-load 직후 query benchmark를 별도 품질 gate로 둔다. 최소 query군은 도로명 exact, 지번 exact, fuzzy geocode, 통합 search, reverse nearest, reverse radius, zipcode lookup, no-result/invalid 경로다. 각 query군은 p50, p90, p95, p99, max, timeout, error rate, buffer 사용량, plan hash를 기록한다.

성능 목표를 초과하는 query군은 인덱스 추가, SQL 재작성, query split, `UNION ALL` 분기, KNN 후보 추출, 5179 공간 index 사용 보강을 먼저 실험한다. 이것만으로 부족하면 `mv_geocode_target` 또는 master table에서 파생된 read-only 보조 view/materialized view를 적극 도입할 수 있다.

허용되는 보조 객체 예:

- `mv_geocode_exact_key`: 도로명/지번 exact lookup 전용 slim MV
- `mv_geocode_text_search`: fuzzy/search 전용 정규화 text/trgm MV
- `mv_reverse_point_5179`: reverse/radius 전용 point-only slim MV
- `mv_zipcode_lookup`: zipcode lookup 전용 MV
- `v_admin_boundary_4326`: 디버그/지도 표시용 polygon 변환 view
- `mv_sppn_reverse_area`: T-042 이후 국가지점번호 표기 의무지역 reverse 보조 MV

## 제약

- 보조 view/MV는 source of truth가 아니다. master table 또는 `mv_geocode_target`에서 재생성 가능한 read-only serving accelerator여야 한다.
- API 응답 구조와 vworld 호환 계약은 바꾸지 않는다. 자체 확장은 계속 `x_extension` 안에만 둔다.
- `pg_trgm.similarity_threshold` 전역 변경은 금지한다. 필요하면 transaction 단위 `SET LOCAL`만 사용한다.
- 공간 쿼리는 입력 좌표를 한 번만 5179로 변환하고, indexed geometry column에는 `ST_Transform`을 걸지 않는다.
- 보조 MV를 도입하면 refresh/swap 순서, index build time, disk size, `ANALYZE`, T-046 backup/restore 영향까지 함께 기록한다.
- 튜닝 PR은 "변경 전/후 p95/p99, plan, buffer, 부작용" 표 없이는 merge하지 않는다.

## 측정 기준

초기 목표는 다음과 같다. 실제 하드웨어와 corpus가 확정되면 T-047 결과 문서에서 조정할 수 있다.

| 쿼리군 | DB p95 목표 | REST p95 목표 |
|--------|------------:|--------------:|
| 도로명 exact geocode | 30ms 이하 | 100ms 이하 |
| 지번 exact geocode | 30ms 이하 | 100ms 이하 |
| fuzzy geocode | 150ms 이하 | 300ms 이하 |
| 통합 search | 150ms 이하 | 300ms 이하 |
| reverse nearest | 50ms 이하 | 150ms 이하 |
| reverse radius | 100ms 이하 | 250ms 이하 |
| zipcode lookup | 30ms 이하 | 100ms 이하 |
| no-result/invalid | 50ms 이하 | 150ms 이하 |

목표를 초과하면 최소 10개 이상의 후보 실험을 수행하고, 각 실험은 결과가 실패해도 artifact와 report에 남긴다.

## 결과

- 운영 latency가 감각이 아니라 수치와 plan으로 관리된다.
- 추가 view/MV/index를 도입해도 source of truth와 응답 계약을 지킬 수 있다.
- 성능 개선이 적재/refresh/backup 비용을 얼마나 늘리는지 함께 판단할 수 있다.
- T-027 최종 클린 로드 이후 T-047 benchmark가 운영 준비의 다음 gate가 된다.

## 후속

- (done) T-047 1차 PR에서 benchmark harness, corpus JSON, summary/report artifact schema를 구현했다.
- (done) T-027 최종 full-load DB에서 smoke와 small concurrency baseline을 측정하고 `idx_mv_jibun_name_exact`를 추가했다.
- (open) 목표 초과 query군은 trial별로 index/query/view/MV 후보를 실험한다.
- (open) 최종 채택한 보조 object는 `docs/architecture/data-model.md`와 Alembic migration에 반영한다.
