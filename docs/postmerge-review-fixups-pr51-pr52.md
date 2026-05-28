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
| PR #51 M1, PR #52 M2 | `pg_stat_statements` 비활성 | T-047 관측성 보강 PR에서 Docker preload 설정, fresh schema/Alembic extension, before/after/delta artifact, reset 옵션을 추가했다. 기존 T-027 DB는 아직 extension 미설치 상태라 다음 run 전에 restart/upgrade가 필요하다. |
| PR #51 M2 | `idx_mv_jibun_name_exact` 운영 영향 미평가 | PR #53에서 Q4 exact index 2개가 추가됐으므로, 다음 운영 영향 측정은 T-047 인덱스 3개를 묶어 MV refresh/swap, backup archive, 디스크 envelope를 재측정한다. |
| PR #51 M3 | benchmark가 underscore SQL 상수 import | 의도적으로 production path와 측정 path를 맞춘 결정은 유지한다. T-052 v2 API 또는 SQL 재사용 표면이 커질 때 public SQL module 추출을 함께 수행한다. |
| PR #51 M4 | small corpus 분산 한계 | PR #52의 1,100건 standard corpus로 1차 해소했다. 후보 확정 run은 `standard` 3회 이상 또는 `stress` 10,000건 이상으로 수행하도록 T-047 문서에 명시했다. |
| PR #51 M5 | corpus deterministic 보장 설명 부족 | T-047 문서에 현재 corpus 생성 방식(`TABLESAMPLE ... REPEATABLE (47)`, fallback `ORDER BY bd_mgt_sn`, 저장 corpus SHA 재사용)을 추가했다. |
| PR #52 M1 | Q3/Q4 c64 p95 초과 | Q4는 PR #53 exact preflight로 개선했다. Q3 fuzzy 후보 축소는 T-057 region hint 또는 text-search slim MV 실험으로 남긴다. |
| PR #52 M3 | `stress` 10,000건 미수행 | T-047 후속 benchmark 항목으로 유지한다. |
| PR #52 M4 | client wall time이 pool wait/DB execution 미분리 | T-047 관측성 보강 PR에서 measurement별 `checkout_ms`/`execute_ms`, summary별 `p95_checkout_ms`/`p95_execute_ms`를 추가했다. 활성 `pg_stat_statements` run과 REST e2e 대조는 후속으로 남긴다. |
| PR #52 M5 | `iterations=1` sample 부족 | 후보 확정 run은 `--iterations 3` 이상으로 수행하도록 T-047 문서에 명시했다. |

## 다음 실행 순서

1. T-047 active observability run: Docker DB restart/upgrade 후 `pg_stat_statements` 활성 상태로 `standard --iterations 3`를 실행한다.
2. T-047 operational impact run: T-047 인덱스 3개 포함 상태에서 MV refresh/swap, backup archive 크기, 디스크 여유 envelope를 측정한다.
3. T-047 stress run: 10,000건 이상 corpus로 c1/c4/c16/c64를 측정한다.
4. Q3 fuzzy 후보 축소: T-057 region hint 또는 `mv_geocode_text_search` 후보와 함께 비교한다.
5. T-052 또는 SQL 재사용 확대 시점에 SQL 상수 public module을 추출한다.

## 검증

T-060 자체는 문서 반영이었다. 후속 T-047 관측성 보강에서는 benchmark artifact schema 2, `pg_stat_statements` snapshot/delta, checkout/execute 분리 측정이 추가됐다.
