# PR #51/#52 post-merge 리뷰 반영

## 상태

- 확인일: 2026-05-28
- 대상:
  - PR #51 `T-047 query benchmark harness and tuning`
  - PR #52 `T-047 standard benchmark pool comparison`
- 확인 표면:
  - `gh pr view 51/52 --json comments,reviews,latestReviews`
  - GraphQL `reviewThreads` fetch
- 결과:
  - PR #51: conversation comment 1건, review 0건, review thread 0건
  - PR #52: conversation comment 1건, review 0건, review thread 0건

두 PR 모두 post-merge conversation review만 있었고 unresolved inline thread는 없었다. 코멘트는 대부분 T-047 후속 측정 보강이다. Q4 search 병목은 PR #53에서 exact preflight로 먼저 반영했고, 나머지는 아래 후속 액션으로 정리한다.

## 반영 매핑

| 출처 | 항목 | 처리 |
|------|------|------|
| PR #51 M1, PR #52 M2 | `pg_stat_statements` 비활성 | T-047 관측성 보강 PR에서 Docker preload 설정, fresh schema/Alembic extension, before/after/delta artifact, reset 옵션을 추가했다. 이어서 실제 T-027 DB를 preload 상태로 재시작하고 `standard --iterations 3` active run을 완료했다. |
| PR #51 M2 | `idx_mv_jibun_name_exact` 운영 영향 미평가 | T-047 인덱스 3개를 묶어 MV refresh/swap, `pg_dump -Fd`, 디스크 envelope를 재측정했다. `CONCURRENTLY` refresh는 133.28초, shadow `swap`은 352.85초였고 exact index 3개 build phase 합계는 180.35초였다. `tar.zst` archive는 로컬 `zstd` CLI 부재로 후속에 남겼다. |
| PR #51 M3 | benchmark가 underscore SQL 상수 import | 의도적으로 production path와 측정 path를 맞춘 결정은 유지한다. T-052 v2 API 또는 SQL 재사용 표면이 커질 때 public SQL module 추출을 함께 수행한다. |
| PR #51 M4 | small corpus 분산 한계 | PR #52의 1,100건 standard corpus로 1차 해소했다. 후보 확정 run은 `standard` 3회 이상 또는 `stress` 10,000건 이상으로 수행하도록 T-047 문서에 명시했다. |
| PR #51 M5 | corpus deterministic 보장 설명 부족 | T-047 문서에 현재 corpus 생성 방식(`TABLESAMPLE ... REPEATABLE (47)`, fallback `ORDER BY bd_mgt_sn`, 저장 corpus SHA 재사용)을 추가했다. |
| PR #52 M1 | Q3/Q4 c64 p95 초과 | Q4는 PR #53 exact preflight로 개선했다. Q3 fuzzy 후보 축소는 T-057 region hint 또는 text-search slim MV 실험으로 남긴다. |
| PR #52 M3 | `stress` 10,000건 미수행 | 11,000건 corpus SHA `2123e09...`와 88,000 measurement로 기본 pool `c1/c4/c16/c64`를 측정했다. error 0, c16 p95 34ms 이하였고, c64 tail은 대부분 checkout 대기였다. |
| PR #52 M4 | client wall time이 pool wait/DB execution 미분리 | T-047 관측성 보강 PR에서 measurement별 `checkout_ms`/`execute_ms`, summary별 `p95_checkout_ms`/`p95_execute_ms`를 추가했다. active/stress run에서 기본 pool c64 tail 대부분이 checkout 대기임을 확인했고, REST e2e run으로 HTTP/JSON/FastAPI overhead를 대조했다. |
| PR #52 M5 | `iterations=1` sample 부족 | 후보 확정 run은 `--iterations 3` 이상으로 수행하도록 T-047 문서에 명시했다. |

## 다음 실행 순서

1. API worker 수, DB pool size, admission control grid를 REST e2e로 비교한다. pool64 단일 process는 Q3 fuzzy만 개선하고 다수 경로를 악화시켰으므로, 기본 pool 상향이 아니라 worker/admission 조합으로 다시 좁힌다.
2. Q3 fuzzy 후보 축소: T-057 region hint 또는 `mv_geocode_text_search` 후보와 함께 SQL/REST 전후를 비교한다.
3. backup archive 압축 단계: 로컬 `zstd` CLI 설치 또는 backup helper fallback 압축 경로 검증 뒤 `tar.zst` 크기와 wall time을 재측정한다.
4. T-052 또는 SQL 재사용 확대 시점에 SQL 상수 public module을 추출한다.

## 검증

T-060 자체는 문서 반영이었다. 후속 T-047 관측성 보강에서는 benchmark artifact schema 2, `pg_stat_statements` snapshot/delta, checkout/execute 분리 측정이 추가됐다. 이어서 T-047 operational impact run에서 exact index 3개 포함 MV refresh/swap, `pg_dump -Fd`, 디스크 envelope를 측정했고, stress run에서 11,000건 corpus c1/c4/c16/c64를 측정했다. REST API e2e run도 추가해 HTTP/JSON/FastAPI overhead를 대조했다. 마지막으로 REST pool64 단일 process 비교를 수행했고, Q3 fuzzy 외 다수 경로가 악화되어 운영 기본 pool 단순 상향은 보류했다.
