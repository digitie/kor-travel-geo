# T-047: 전국 적재 후 쿼리 성능 벤치마크와 튜닝 설계

## 범위

본 문서는 전국 전체 데이터가 적재된 PostgreSQL + PostGIS DB를 대상으로 지오코딩/역지오코딩/검색 쿼리 속도를 반복 측정하고, 병목이 확인되면 인덱스, 쿼리 재작성, 보조 view 또는 materialized view까지 적극 도입하는 성능 튜닝 계획이다.

이번 문서는 구현 전 설계만 다룬다. 코드는 작성하지 않는다. 실제 full-load, benchmark, migration, UI 구현은 후속 T-047 구현 PR에서 수행한다.

## 목표

속도는 T-047의 최우선 품질 지표다. 지오코딩 API는 주소 입력에 대한 대화형 응답 경로이므로, 정합성이 맞더라도 p95/p99 latency가 높으면 운영 준비가 끝난 것으로 보지 않는다.

목표:

- 전국 full-load 직후 실제 운영 규모 row count에서 baseline latency를 확보한다.
- 단일 쿼리 성공 여부가 아니라 p50, p90, p95, p99, max, timeout, error rate를 기록한다.
- 쿼리별 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, SETTINGS)`를 저장해 plan과 buffer 사용량을 비교한다.
- 튜닝은 한 번에 하나의 가설만 적용하고, 전후 차이를 수치로 남긴다.
- 인덱스 추가만으로 부족하면 read-only serving 보조 view/materialized view를 적극 도입한다.
- 튜닝 산출물이 적재 시간, MV refresh/swap 시간, 디스크 사용량, daily delta 반영 시간에 미치는 비용도 함께 기록한다.

## 전제 조건

T-047은 T-027 최종 클린 full-load 이후에 수행한다.

필수 전제:

- Docker PostgreSQL/PostGIS에 전국 전체 데이터가 적재되어 있다.
- `mv_geocode_target`이 shadow swap 방식으로 최신화되어 있다.
- `ANALYZE`가 주요 master table, MV, 후보 보조 view/MV에 수행되어 있다.
- `source_set`, row count, PostgreSQL/PostGIS version, git commit, Docker/WSL/디스크 상태가 기록되어 있다.
- 외부 API fallback은 benchmark baseline에서 끈다. 로컬 DB 쿼리 성능을 먼저 고립해 측정한다.
- `pg_stat_statements`를 사용할 수 있으면 benchmark run 시작 전에 reset하고, run 종료 후 statement 통계를 저장한다.

T-027 정합성 결과에 C2/C4/C6/C7 같은 데이터 품질 오류가 남아도 쿼리 성능 측정은 진행할 수 있다. 다만 benchmark report에는 해당 DB의 `severity_max`, 오류 건수, source set을 함께 기록해 나중에 다른 DB 결과와 혼동하지 않는다.

## 벤치마크 대상 쿼리군

다음 쿼리군을 최소 benchmark set으로 둔다.

| 코드 | 쿼리군 | 예시 | 주요 위험 |
|------|--------|------|-----------|
| Q1 | 도로명주소 exact geocode | `서울특별시 강남구 테헤란로 152` | key filter가 느리거나 `OR` 조건으로 seq scan 발생 |
| Q2 | 지번주소 exact geocode | `대구광역시 중구 동인동1가 1-1` | PNU/법정동/산여부 조합 인덱스 미흡 |
| Q3 | 건물명/도로명 fuzzy geocode | 오타, 축약어, 띄어쓰기 변화 | `pg_trgm` 후보 폭증, similarity threshold 오용 |
| Q4 | 통합 search | 도로명, 행정동, 우편번호, 건물명 혼합 | 여러 lookup이 한 SQL에 섞여 plan 불안정 |
| Q5 | reverse nearest | 건물 출입구 근처 `(lon, lat)` | `ST_Transform`/`ST_DWithin` 인덱스 미사용 |
| Q6 | reverse radius | 반경 10m/50m/200m/1km | 후보 수 폭증, distance sort 비용 |
| Q7 | zipcode lookup | 우편번호 → 주소 목록, 주소 → 우편번호 | limit 전 정렬/필터 비용 |
| Q8 | no-result/invalid | 존재하지 않는 주소, 바다 좌표, 한국 밖 좌표 | 실패 경로가 성공 경로보다 느려지는 문제 |
| Q9 | 행정/기초구역 polygon 보조 조회 | reverse 행정구역, 기초구역 | polygon contains/covers 인덱스 미사용 |
| Q10 | batch/concurrency | 같은 corpus를 동시성 4/16/64로 반복 | connection pool, lock, CPU saturation |

T-042 `TL_SPPN_MAKAREA`가 구현된 뒤에는 국가지점번호 보조 geocode/reverse query를 Q11로 추가한다.

## 샘플 corpus

벤치마크 corpus는 고정 파일로 저장해 튜닝 전후에 같은 입력을 반복한다. 생성 기준:

- 전국 17개 시도에서 균등 추출한다.
- 서울/경기/대구처럼 밀집도가 높은 지역은 별도 high-density bucket으로 더 많이 뽑는다.
- 도로명주소와 지번주소를 모두 포함한다.
- direct 출입구 좌표, 위치정보요약DB 출입구 좌표, 내비 centroid fallback 좌표를 각각 포함한다.
- 도로명 오타, 띄어쓰기 제거, 건물번호 누락, 건물명 포함 등 fuzzy 입력을 포함한다.
- 존재하지 않는 주소와 한국 밖 좌표 같은 실패 경로를 포함한다.
- 같은 `bd_mgt_sn`에 보조 지번이 여러 개인 case를 포함한다.
- C2/C4/C6/C7 data-quality sample 일부를 포함해 병적이지만 실제로 발생하는 입력도 측정한다.

최소 규모:

| corpus | 크기 | 용도 |
|--------|-----:|------|
| `smoke` | 50건 | PR 중 빠른 회귀 |
| `standard` | 1,000건 이상 | 기본 전후 비교 |
| `stress` | 10,000건 이상 | candidate 확정 전 반복 측정 |
| `concurrency` | 1,000건 이상 | 동시성 4/16/64 측정 |

corpus row에는 `case_id`, `query_kind`, `input`, `expected_status`, `expected_bd_mgt_sn` 또는 기대 좌표 범위, `sido`, `sig_cd`, `source`, `note`를 둔다.

## 측정 방법

각 benchmark run은 같은 순서로 수행한다.

1. 시스템 상태를 기록한다. CPU, RAM, 디스크 여유, Docker version, PostgreSQL version, PostGIS version, DB size, table/MV row count, git commit, source set을 저장한다.
2. `ANALYZE` 상태를 확인한다. 후보 view/MV 또는 index를 새로 만들었다면 반드시 `ANALYZE` 후 측정한다.
3. `pg_stat_statements`를 reset한다. 사용할 수 없으면 이유를 report에 남긴다.
4. warm-up run을 1회 수행한다. warm-up 결과는 threshold 판정에서 제외하되 별도 저장한다.
5. 단일 동시성 run을 수행한다. 각 query case는 최소 30회 반복하거나, `standard` corpus 전체를 3회 이상 반복한다.
6. 동시성 run을 수행한다. concurrency는 4, 16, 64를 기본으로 하고, 로컬 장비가 버티지 못하면 실패 지점과 resource saturation을 기록한다.
7. 각 query군에서 대표 slow sample에 대해 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, SETTINGS)`를 저장한다.
8. 결과를 JSON/CSV/Markdown으로 저장한다.

기본 지표:

- client wall time
- DB execution time
- REST API total time
- p50, p90, p95, p99, max
- timeout count
- error count
- rows returned
- shared hit/read/dirtied/written buffers
- temp read/write bytes
- plan hash
- index scan/bitmap scan/seq scan 여부
- `pg_stat_statements.mean_exec_time`, `calls`, `rows`, `shared_blks_read`, `temp_blks_written`

## 초기 성능 목표

아래 목표는 첫 운영 기준선이다. 실제 하드웨어와 corpus가 확정되면 ADR-031 부록 또는 T-047 결과 문서에서 조정할 수 있다.

| 쿼리군 | DB p95 목표 | REST p95 목표 | 실패 기준 |
|--------|------------:|--------------:|-----------|
| Q1 도로명 exact | 30ms 이하 | 100ms 이하 | p95 100ms 초과 또는 seq scan |
| Q2 지번 exact | 30ms 이하 | 100ms 이하 | p95 100ms 초과 또는 seq scan |
| Q3 fuzzy geocode | 150ms 이하 | 300ms 이하 | p95 500ms 초과 또는 후보 폭증 |
| Q4 통합 search | 150ms 이하 | 300ms 이하 | p95 500ms 초과 |
| Q5 reverse nearest | 50ms 이하 | 150ms 이하 | GiST 미사용 또는 p95 300ms 초과 |
| Q6 reverse radius | 100ms 이하 | 250ms 이하 | radius 200m에서 p95 500ms 초과 |
| Q7 zipcode lookup | 30ms 이하 | 100ms 이하 | p95 100ms 초과 |
| Q8 no-result/invalid | 50ms 이하 | 150ms 이하 | 실패 경로가 성공 경로보다 2배 이상 느림 |

이 목표는 "무조건 달성해야 하는 숫자"라기보다 튜닝 우선순위 게이트다. 초과하면 이유를 설명하고, 보조 view/MV/index 또는 쿼리 분리 실험을 반드시 수행한다.

## 튜닝 루프

T-047 구현 PR에서는 다음 루프를 반복한다.

1. baseline을 측정한다.
2. 가장 느린 query군과 slow sample을 고른다.
3. plan, buffer, temp I/O, row estimate 오차를 분석한다.
4. 하나의 가설만 적용한다.
5. 같은 corpus와 같은 iteration으로 재측정한다.
6. 개선 폭과 부작용을 비교한다.
7. 기준을 만족하면 유지하고, 만족하지 않으면 되돌리거나 후속 후보로 기록한다.

유지 기준:

- p95 또는 p99가 20% 이상 개선되거나
- shared read/temp write가 30% 이상 감소하거나
- timeout/error가 사라지거나
- 동시성 run에서 tail latency가 명확히 줄어야 한다.

부작용 기준:

- full-load 또는 MV refresh 시간이 크게 늘면 반드시 기록한다.
- `mv_geocode_target` row 계약 또는 vworld 호환 응답 구조가 바뀌면 안 된다.
- `x_extension` 밖에 새 응답 필드를 추가하지 않는다.
- `pg_trgm.similarity_threshold` 전역 변경은 금지한다. 필요하면 transaction 단위 `SET LOCAL`만 사용한다.
- 공간 쿼리는 입력 좌표를 한 번만 5179로 변환하고, indexed column에는 `ST_Transform`을 걸지 않는다.

최소 실험 수:

- baseline이 목표를 모두 만족하더라도 대표 query군별 plan 확인과 3개 이상의 안정화 실험을 수행한다.
- 목표를 초과하는 query군이 있으면 최소 10개 이상의 후보 실험을 수행한다.
- 각 실험은 결과가 나쁘더라도 `artifacts/perf/<run_id>/trials/<trial_id>.md`에 남긴다.

## 적극 도입 가능한 대책

### 쿼리 재작성

- exact lookup과 fuzzy lookup을 한 SQL의 `OR` 조건으로 섞지 않고, exact 실패 후 fuzzy를 별도 단계로 실행한다.
- 후보 추출과 최종 응답 정렬을 분리한다. 후보 CTE는 `LIMIT`을 가능한 빨리 적용한다.
- `UNION ALL`로 road/parcel/building-name 후보를 분리해 planner가 각 branch별 index를 고르게 한다.
- reverse는 `ST_DWithin` 후보를 먼저 좁히고, 최종 정렬에서 `ST_Distance`를 사용한다.
- KNN이 유리한 case는 `ORDER BY pt_5179 <-> target_geom LIMIT N` 후보 추출을 실험한다.
- polygon reverse는 `&& ST_Expand(...)` bounding box prefilter와 `ST_Covers`를 함께 실험한다.

### 인덱스

- exact key용 btree composite index와 `INCLUDE` 컬럼을 추가해 heap fetch를 줄인다.
- fuzzy search용 `gin_trgm_ops` index를 query군별로 분리한다.
- `address_type`, `sido_cd`, `sig_cd`, `zip_no`, `pt_source` 같은 자주 쓰는 filter에는 partial index를 검토한다.
- reverse/radius는 5179 geometry GiST index를 우선한다.
- 새 index는 build time, size, refresh/swap 영향, insert/update 영향까지 기록한다.

### 보조 view/materialized view

인덱스와 쿼리 재작성만으로 목표를 만족하지 못하면 read-only serving 보조 객체를 추가할 수 있다. 이는 "source of truth"를 늘리는 것이 아니라 `mv_geocode_target` 또는 master table에서 파생된 가속 구조다.

후보:

| 후보 | 목적 | 기본 아이디어 |
|------|------|---------------|
| `mv_geocode_exact_key` | Q1/Q2 exact geocode 가속 | 도로명/지번 exact key와 응답에 필요한 최소 컬럼만 보관 |
| `mv_geocode_text_search` | Q3/Q4 fuzzy/search 가속 | 정규화된 검색 문자열, token, trgm 전용 컬럼을 분리 |
| `mv_reverse_point_5179` | Q5/Q6 reverse 가속 | `bd_mgt_sn`, `address_type`, `pt_source`, `pt_5179`, 응답 key만 가진 slim point MV |
| `mv_zipcode_lookup` | Q7 zipcode lookup 가속 | `zip_no`, `sido`, `sig`, 도로명/지번 표시용 최소 컬럼 |
| `v_admin_boundary_4326` | 디버그 지도 표시 | polygon 응답 변환 비용을 UI/디버그 경로에서 분리 |
| `mv_sppn_reverse_area` | T-042 이후 국가지점번호 reverse | `TL_SPPN_MAKAREA` polygon 후보를 reverse 보조 경로로 분리 |

보조 MV 도입 조건:

- 원천 row를 수정하지 않는다.
- refresh/swap 절차와 의존 순서를 문서화한다.
- unique key와 index 이름을 명시한다.
- `EXPLAIN`으로 실제 query path가 바뀐 것을 증명한다.
- semantic parity test를 추가한다. 기존 `mv_geocode_target` 결과와 후보 MV 결과가 같은지 대표 corpus로 비교한다.
- refresh 비용이 과도하면 `serving-ready` 백업 profile과 T-046 restore 후속 절차에도 반영한다.

### PostgreSQL 설정과 운영 옵션

- 짧은 OLTP query에서 JIT가 손해면 benchmark session에서 `SET LOCAL jit = off`를 실험한다.
- query별 sort/hash가 큰 경우 `SET LOCAL work_mem` 실험을 하되, API global 기본값으로 올리지는 않는다.
- `effective_cache_size`, `random_page_cost` 같은 planner 설정은 Docker 개발 DB와 운영 DB 차이가 크므로 결과 문서에만 후보로 남기고, 코드 기본값으로 즉시 고정하지 않는다.
- `pg_prewarm`은 cold-start 운영 요구가 있을 때 별도 실험한다.

## 산출물

실행 산출물은 git에 커밋하지 않고 `artifacts/perf/<run_id>/`에 둔다.

```text
artifacts/perf/<run_id>/
├── environment.json
├── corpus-summary.json
├── baseline.json
├── baseline-summary.md
├── pg-stat-statements-before.json
├── pg-stat-statements-after.json
├── plans/
│   ├── Q1_road_exact_001.json
│   └── Q5_reverse_nearest_001.json
├── trials/
│   ├── trial-001-index-exact-key.md
│   ├── trial-002-rewrite-union-all.md
│   └── trial-010-slim-reverse-mv.md
└── final-report.md
```

PR에는 전체 artifact를 커밋하지 않고, `final-report.md`의 핵심 표와 결론만 문서로 옮긴다.

최종 report 필수 표:

- query군별 baseline p50/p95/p99
- query군별 최종 p50/p95/p99
- 개선율
- 새 index/view/MV별 size와 build time
- full-load/MV refresh/swap 시간 영향
- 유지한 실험과 폐기한 실험
- 남은 병목과 후속 task

## 관리 UI 후보

T-047 1차 구현은 CLI와 artifact 중심으로 충분하다. 다만 반복 튜닝이 잦아지면 `/admin/performance` 페이지를 추가해 다음을 보여 줄 수 있다.

- benchmark run 목록
- query군별 p50/p95/p99 trend
- slow sample과 plan JSON 링크
- 새 index/view/MV 적용 전후 비교
- threshold 초과 query군 badge

프론트엔드는 여전히 DB에 직접 연결하지 않고 백엔드 REST 또는 정적 artifact metadata만 읽는다.

## PR 진행 순서

T-047은 변경 폭이 커질 수 있으므로 다음 순서로 나누는 것을 권장한다.

1. benchmark harness와 corpus 생성기 문서/코드.
2. 전국 full-load DB baseline 측정 PR.
3. 가장 큰 병목 1~2개에 대한 index/query rewrite PR.
4. 보조 view/MV가 필요한 경우 별도 PR.
5. 최종 benchmark report와 threshold 갱신 PR.

각 PR은 baseline, 변경, 결과, 부작용을 같은 형식으로 기록한다. "빨라졌다"는 주관적 설명만으로는 merge하지 않는다.

## 구현 후 테스트 항목

- unit: corpus row schema validation.
- unit: query benchmark result aggregation(p50/p95/p99) 계산.
- unit: `EXPLAIN` JSON plan hash 추출과 secret redaction.
- integration: 전국 DB 또는 restored full DB에서 `smoke` corpus benchmark.
- integration: representative slow sample `EXPLAIN`이 seq scan 없이 기대 index를 사용하는지 확인.
- integration: 후보 보조 MV가 기존 `mv_geocode_target` 결과와 semantic parity를 유지하는지 확인.
- frontend: `/admin/performance`를 만들 경우 run list, threshold badge, plan viewer rendering.
