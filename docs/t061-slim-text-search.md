# T-061 Q3 fuzzy slim text-search 구조

## 상태

- 상태: 구현 및 실측 완료
- 대상 브랜치: `codex/t061-slim-text-search`
- 기준 DB: Docker PostGIS `kor_travel_geo`, `mv_geocode_target=6,416,637`
- 기준 corpus: `artifacts/perf/t057-region-hint-standard-20260528/corpus.json`

## 목표와 판단

T-057의 `sig_cd`/`bjd_cd` hint는 Q3 fuzzy tail을 낮췄지만, `mv_geocode_target`의 넓은 row를 그대로 trigram recheck 대상으로 읽는 구조는 남아 있었다. T-061에서는 source of truth를 늘리지 않고 `mv_geocode_target`에서 재생성 가능한 read-only helper MV `mv_geocode_text_search`를 추가했다.

핵심 판단은 다음과 같다.

- Q3 fuzzy geocode는 helper MV를 사용한다.
- Q4 search의 exact preflight는 기존 `mv_geocode_target` exact index가 충분히 빠르므로 유지한다.
- Q4 broad trigram fallback만 helper MV를 사용한다.
- helper MV는 target MV와 같은 세대로 swap되어야 하므로, shadow swap에서 `mv_geocode_target_next`와 `mv_geocode_text_search_next`를 함께 만들고 같은 rename window에서 교체한다.

운영자는 `mv_geocode_target`만 psql에서 직접 `REFRESH MATERIALIZED VIEW` 하지 않는다. `mv_geocode_text_search`는 target에서 파생되는 helper라 target만 단독 refresh하면 Q3/Q4 후보가 이전 세대에 머물 수 있다. 평시에는 `ktgctl refresh mv` 또는 `/v1/admin/maintenance/refresh-mv`, 풀로드 후에는 `ktgctl refresh mv --swap` 같은 orchestration 경로만 사용한다.

## 구현

`mv_geocode_text_search` 컬럼은 조회 후보 추출에 필요한 최소값으로 제한했다.

| 컬럼 | 용도 |
|------|------|
| `bd_mgt_sn` | 최종 `mv_geocode_target` join key |
| `sido_cd`, `sig_cd`, `bjd_cd` | region hint filter |
| `si_nm`, `sgg_nm` | 기존 parser 지역명 filter 보존 |
| `rn_nrm`, `buld_nm_nrm` | trigram/exact text 후보 |
| `sigungu_buld_nm_nrm` | T-065 내비게이션용DB `시군구용건물명` 검색 후보 |
| `buld_mnnm`, `buld_slno`, `buld_se_cd` | 도로명 fuzzy의 건물번호 filter(T-171 이후 exact 조회와 같은 본번·부번·지하구분 계약 유지) |
| `pt_source` | 기존 fuzzy 정렬의 entrance 우선순위 보존 |

인덱스는 최종 채택본 기준 6개다.

| index | 용도 |
|-------|------|
| `idx_mv_text_search_pk` | `REFRESH CONCURRENTLY`와 target join |
| `idx_mv_text_search_sig_buld` | 5자리 `sig_cd` hint + 건물번호 |
| `idx_mv_text_search_sido_buld` | 2자리 시도 prefix hint + 건물번호 |
| `idx_mv_text_search_bjd_prefix_buld` | 8/10자리 `bjd_cd` hint + 건물번호 |
| `idx_mv_text_search_rn_trgm` | 도로명 fuzzy |
| `idx_mv_text_search_buld_nm_trgm` | 건물명 broad search fallback |
| `idx_mv_text_search_sigungu_buld_nm_trgm` | T-065 `시군구용건물명` broad search fallback |

초기안에는 helper exact index와 `buld_mnnm` 단독 index도 포함했지만, Q4 exact는 기존 target index를 유지하기로 하면서 제거했다. 이 조정으로 helper rebuild 시간이 `235.22초`에서 `82.77초`로 줄고, helper total size가 `3.4GiB`에서 `2.4GiB`로 줄었다.

T-065에서는 helper 컬럼과 인덱스가 하나 늘었다. 202604 전국 DB 기준 helper row count는 `6,416,642`, heap `904MB`, indexes `1,582MB`, total `2,486MB`이고, 새 `idx_mv_text_search_sigungu_buld_nm_trgm`은 약 `10MB`였다. 상세 전후 recall/latency는 `docs/t065-navi-building-name-search.md`에 둔다.

T-171에서는 helper에 `buld_slno`와 `buld_se_cd`를 추가하고 region+건물번호 btree 인덱스에 두 컬럼을 포함했다. 이 변경은 도로명 오타 보정 중에도 부번이 다른 후보가 1순위로 올라오는 것을 막기 위한 ranking 결정성 보강이다. 별도 live size/latency 실측은 T-143 plan 안정화 작업에서 다시 측정한다.

## 성능 결과

같은 T-057 corpus를 사용했다. 변경 전은 `t061-before-main-20260528`, 변경 후 채택본은 `t061-after-text-search-slim-20260528`이다. 표의 `execute`는 DB 실행 p95이고, c64 전체 latency는 pool checkout 대기가 섞인다.

| query | conc | before p95 | after p95 | before execute p95 | after execute p95 | 판단 |
|-------|-----:|-----------:|----------:|-------------------:|------------------:|------|
| Q3 fuzzy | 1 | 14.48ms | 10.43ms | 13.66ms | 9.77ms | 개선 |
| Q3 fuzzy | 16 | 38.19ms | 36.41ms | 30.37ms | 27.83ms | 개선 |
| Q3 fuzzy | 64 | 359.25ms | 227.57ms | 30.78ms | 31.69ms | tail 개선, 실행은 유사 |
| Q3 fuzzy + `sig_cd` | 1 | 10.77ms | 6.80ms | 10.08ms | 6.09ms | 개선 |
| Q3 fuzzy + `sig_cd` | 16 | 37.11ms | 29.57ms | 28.77ms | 22.03ms | 개선 |
| Q3 fuzzy + `sig_cd` | 64 | 193.36ms | 182.27ms | 28.62ms | 24.61ms | 소폭 개선 |
| Q3 fuzzy wide | 1 | 10.41ms | 10.56ms | 9.67ms | 9.86ms | 동등 |
| Q3 fuzzy wide | 16 | 41.26ms | 32.27ms | 33.51ms | 26.42ms | 개선 |
| Q3 fuzzy wide | 64 | 255.36ms | 200.69ms | 26.26ms | 28.42ms | tail 개선 |
| Q4 exact search | 64 | 230.39ms | 177.14ms | 22.21ms | 23.06ms | exact 경로 유지, 실행 동등 |
| Q4 exact search + `sig_cd` | 64 | 210.12ms | 268.28ms | 22.23ms | 23.58ms | checkout 변동, 실행 동등 |

Q4 broad fallback은 새 corpus `t061-after-generated-search-fuzzy-20260528`에서 확인했다.

| query | conc | p95 | execute p95 | error |
|-------|-----:|----:|------------:|------:|
| Q4 `search_fuzzy` | 1 | 9.87ms | 9.14ms | 0 |
| Q4 `search_fuzzy` | 16 | 40.13ms | 31.27ms | 0 |
| Q4 `search_fuzzy` | 64 | 364.94ms | 31.59ms | 0 |

Q4 fallback의 c64 p95는 checkout 대기가 크지만 DB execute p95는 31.59ms라, 현재 병목은 SQL 후보 추출보다 pool/admission 쪽에 가깝다.

## 운영 비용

실제 DB에서 채택 DDL을 재빌드했다.

| 항목 | 값 |
|------|---:|
| helper row count | 6,416,637 |
| helper heap | 854MiB |
| helper indexes | 1,572MiB |
| helper total | 2,426MiB |
| helper-only rebuild | 82.77초 |

shadow swap benchmark artifact는 `artifacts/perf/t061-mv-swap-20260528.json`이다.

| 항목 | 값 |
|------|---:|
| total_seconds | 497.54초 |
| target create_next | 148.08초 |
| target index build 합계 | 약 255.12초 |
| text-search create_next | 14.33초 |
| text-search index build 합계 | 약 71.04초 |
| rename/drop/index rename lock window | 약 1.06초 |
| analyze | 5.27초 |
| temp 증가 | 57 files / 11.67GiB |

T-047 exact index 포함 shadow swap 기준 `352.85초`와 비교하면 helper 포함 swap은 약 `+144.69초`다. 조회 p95 개선은 있지만 helper index 6개가 refresh/swap과 backup envelope를 늘리므로, 운영에서는 shadow swap을 기본으로 유지하고 refresh window를 명확히 잡아야 한다.

T-055 N150/Odroid sizing에서는 helper MV total `2,426MiB`, swap 중 임시 파일 증가 `11.67GiB`, GIN index build의 `maintenance_work_mem`/temp disk 사용량을 별도 항목으로 기록한다.

## 검증

- 단위: `tests/unit/test_infra_repo_sql.py`, `tests/unit/test_postload_mv.py`, `tests/unit/test_mv_refresh_benchmark.py`, `tests/unit/test_backup_restore.py`, `tests/unit/test_alembic_migrations.py`
- 실제 DB semantic parity: `KTG_TEST_PG_DSN=... pytest tests/integration/test_optional_real_postgres_text_search.py -q`
- 실제 DB migration/rebuild: 0013 migration 적용, helper rebuild 2회, shadow swap benchmark 1회
- benchmark artifacts:
  - `artifacts/perf/t061-before-main-20260528`
  - `artifacts/perf/t061-after-text-search-slim-20260528`
  - `artifacts/perf/t061-after-generated-search-fuzzy-20260528`
  - `artifacts/perf/t061-mv-swap-20260528.json`

## 후속

- c64 tail은 여전히 pool checkout 대기가 크다. T-050 이후 `/admin/performance`에서 checkout/execute 분리 표시를 추가할 때 T-061 artifact도 함께 노출한다.
- `mv_geocode_text_search`는 serving-ready backup profile에는 포함하고, materialized view 제외 옵션에서는 `mv_geocode_target`과 함께 data를 제외한다.
- 마지막 T-027 클린 적재에서는 helper MV까지 빈 DB에서 재생성되는지 다시 확인한다.
