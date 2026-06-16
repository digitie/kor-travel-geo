# T-143 geocode/search query plan 안정화

작성일: 2026-06-16

## 결론

T-143에서는 `/v2/search` address/road 경로의 exact preflight를 OR 기반 단일 scan에서
입력 유형별 branch로 분리했다. 기존 `_SEARCH_EXACT_SQL`은 `mv_geocode_target`에서
다음 세 조건을 하나의 OR로 묶었다.

- `rn_nrm = :query_nrm`
- `buld_nm_nrm = :query_nrm`
- `sigungu_buld_nm_nrm = :query_nrm`

이제 exact preflight는 `exact_keys AS MATERIALIZED` CTE 안에서 세 branch를
`UNION ALL`로 실행한다. 각 branch는 같은 region hint filter를 갖고, 기존 exact index와
partial index 조건을 그대로 타도록 `buld_nm_nrm IS NOT NULL`,
`sigungu_buld_nm_nrm IS NOT NULL` 조건을 branch 안에 둔다. 중복 `bd_mgt_sn`은
`DISTINCT ON (bd_mgt_sn)`으로 제거하고, 동률은 다음 우선순위로 고정한다.

1. 도로명 exact(`rn_nrm`)
2. 건물명 exact(`buld_nm_nrm`)
3. 시군구 건물명 exact(`sigungu_buld_nm_nrm`)
4. `bd_mgt_sn`

exact path의 score는 모두 `1.0`으로 고정했다. exact 여부를 이미 equality 조건이
보장하므로 이 경로에서는 `similarity()`와 `GREATEST()`를 계산하지 않는다. broad trigram
fallback은 exact 결과가 없을 때만 실행한다.

## 정규화

search broad fallback도 SQL 내부 `regexp_replace(:query, '\s+', '', 'g')` 대신 Python에서
정규화한 `:query_nrm` bind를 받게 했다. `_normalize_search_query()`는 T-165와 같은
`normalize_spaces()` + `compact()` 경로를 사용하므로 전각 숫자, 전각 대시, 쉼표류
구분자, 숫자 사이 하이픈 공백을 repository와 benchmark가 같은 방식으로 접는다.

`scripts/benchmark_query_performance.py`는 기존 저장 corpus가 `query_nrm`을 갖고 있지
않아도 실행 직전에 `_search_sql_params()`로 값을 합성한다. 따라서 기존 T-141/T-138
benchmark corpus JSON은 그대로 재사용할 수 있다.

## 변경하지 않은 범위

- 새 DB object, migration, index는 추가하지 않았다.
- `mv_geocode_target`과 `mv_geocode_text_search` 정의는 그대로 둔다.
- `pg_trgm.similarity_threshold`는 기존처럼 transaction-local `SET LOCAL`만 사용한다.
- v1/v2 REST 응답 계약, OpenAPI, 프론트엔드 typegen은 바뀌지 않는다.
- broad fuzzy fallback 자체의 recall 축소, token table, generated column, statistics target
  조정은 이번 PR에서 적용하지 않았다. T-143의 1차 목표는 plan 변동이 큰 exact
  preflight OR를 제거하고 benchmark harness가 같은 정규화 bind를 쓰게 하는 것이다.

## 회귀 테스트

단위 테스트는 다음을 고정한다.

- `_SEARCH_EXACT_SQL`이 `exact_keys AS MATERIALIZED`와 `UNION ALL` branch를 사용한다.
- exact SQL이 `mv_geocode_text_search`를 건드리지 않고, OR 기반 exact 조건과
  `GREATEST()` 계산을 쓰지 않는다.
- broad search SQL은 `SELECT CAST(:query_nrm AS text) AS query_nrm`을 사용한다.
- `_normalize_search_query()`가 전각 숫자/대시 입력을 ASCII 형태로 접는다.
- benchmark runner는 legacy corpus params에서 `query_nrm`을 합성한다.

## Live EXPLAIN 재측정

실제 DB가 준비된 환경에서는 같은 branch에서 다음처럼 재측정한다. 이 저장소는
PostgreSQL/RustFS를 직접 구동하지 않으므로 `KTG_PG_DSN`은 이미 실행 중인 T-213/T-214
기준 DB를 가리켜야 한다.

```bash
python scripts/benchmark_query_performance.py \
  --run-id t143-search-plan \
  --output-dir artifacts/perf/t143-search-plan \
  --cases-per-group 5 \
  --iterations 3 \
  --warmup 1 \
  --concurrency 1 \
  --concurrency 16 \
  --concurrency 64 \
  --explain-slowest-per-group 2
```

산출물에서 확인할 항목은 다음이다.

- Q4 search exact case가 `_SEARCH_EXACT_SQL` plan으로 EXPLAIN되는지
- exact path가 세 branch의 exact index path를 타는지
- exact miss case가 `_SEARCH_SQL` broad fallback으로만 내려가는지
- Q4 p95/p99와 error가 T-138/T-141 baseline보다 악화되지 않는지

## 검증

이번 코드 변경은 Windows focused 검증과 WSL ext4 전체 검증으로 확인한다.

```bash
python -m pytest tests/unit/test_infra_repo_sql.py tests/unit/test_query_performance_benchmark.py -q
python -m ruff check .
python -m mypy src/kortravelgeo
lint-imports
python scripts/export_openapi.py --check
```

WSL ext4 미러에서 T-213 계열 DB를 대상으로 Q4 search 전용 smoke도 실행했다.

- artifact: `artifacts/perf/t143-search-plan-q4-smoke/` (WSL 테스트 미러, git ignore)
- 대상 row count: `mv_geocode_target=6,416,637`,
  `mv_geocode_text_search=6,416,637`, `tl_sppn_makarea=24,204`
- Q4 samples: `search`, `search_sig`, `search_fuzzy` 각 1건, error 0
- p95: `search=6.756ms`, `search_sig=5.926ms`, `search_fuzzy=5.923ms`
- EXPLAIN:
  - `search`, `search_sig`: `exact_keys` CTE, `mv_geocode_target`,
    `idx_mv_rn_nrm_exact`, `idx_mv_buld_nm_nrm_exact`,
    `idx_mv_sigungu_buld_nm_nrm_exact`
  - `search_fuzzy`: `scored` CTE, `mv_geocode_text_search`,
    `idx_mv_text_search_*_trgm`

처음 전체 smoke는 현재 live DB의 helper MV가 아직 T-171 컬럼(`buld_slno`)을 갖지 않아
Q3 fuzzy geocode만 오류가 났다. T-143 확인 범위는 Q4 search plan이므로 생성 corpus에서
Q4 case만 분리해 위 smoke를 다시 실행했다.
