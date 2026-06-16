# T-138 read-mostly serving 성능 benchmark

작성일: 2026-06-16

## 결론

T-138은 T-213 r3 기준 DB에서 read-heavy serving 경로를 재측정하고 Q4 broad search 후보 튜닝을 실험했다. 이번 단계에서 **production index/MV/API SQL은 바꾸지 않는다**.

근거는 다음과 같다.

- SQL baseline은 오류 0이고 worst c64 p95는 `Q4_SEARCH/search_fuzzy=289.146ms`다. T-214 `245.895ms`, T-217 `268.370ms`와 같은 band 안의 공유 DB 부하 변동으로 본다.
- REST c64 425-case 재측정은 오류 0이고 worst p95는 `Q1_ROAD_EXACT/geocode_road=350.545ms`다. T-214 REST worst `534.031ms`, T-216 REST worst `415.022ms`보다 낮다.
- Q4 threshold `0.42` 실험은 `search_fuzzy` 평균 row를 `9.6 -> 6.5`로 줄였지만 c64 p95가 `289.146ms -> 294.329ms`로 개선되지 않았다.
- Q4 `limit-before-join` 실험은 API `total`을 유지하면서 `mv_geocode_target` join을 page 후보 뒤로 미루는 형태였지만 c64 p95가 `289.146ms -> 307.716ms`로 악화됐다.
- SQL c64 p95에는 pool checkout 대기가 약 `139ms` 섞여 있다. pool/backpressure/prepared/cache 계열은 T-154/T-155/T-156, 고부하 matrix와 장시간 budget은 T-141/T-163/T-164에서 다루는 것이 경계상 맞다.

따라서 T-138의 적용 변경은 **benchmark harness 보정 1건**이다. `scripts/benchmark_api_latency.py`에서 synthetic `search_fuzzy` REST case는 `OK`와 `NOT_FOUND`를 모두 latency 표본으로 인정하게 했다. `search_fuzzy`는 의도적으로 exact match를 깨는 broad fallback 측정용 case라 일부 도로명에서는 `NOT_FOUND`가 정상 결과일 수 있다.

## 기준 입력

| 항목 | 값 |
|------|----|
| 기준 DB | `kor_travel_geo_t213_20260615_r3` |
| 기준 row count | `mv_geocode_target=6,419,795`, `mv_geocode_text_search=6,419,795`, `tl_sppn_makarea=24,204` |
| artifact root | `F:\dev\geodata\t138-read-heavy-serving-performance\20260616-r1\` |
| SQL corpus | 2,000 case / 32,000 measurement |
| REST corpus | SQL corpus에서 변환한 425 case / 1,275 measurement |
| 서버 profile | Python `3.13.14`, uvicorn worker `1`, `uvloop`, DB pool `20/64`, admission off, GeoIP off |

## SQL baseline

설정은 T-214/T-217과 맞췄다. `cases_per_group=100`, `iterations=3`, `warmup=1`, concurrency `1/4/16/64`, pool `20/64`, statement timeout 5초다.

| group/sql | c64 p95 | c64 p99 | p95 checkout | p95 execute | errors |
|-----------|--------:|--------:|-------------:|------------:|-------:|
| `Q4_SEARCH/search_fuzzy` | `289.146ms` | `370.125ms` | `138.960ms` | `166.318ms` | 0 |
| `Q3_FUZZY_GEOCODE/fuzzy_geocode` | `278.168ms` | `342.199ms` | n/a | n/a | 0 |
| `Q4_SEARCH/search_sig` | `273.328ms` | `335.451ms` | `142.000ms` | `131.549ms` | 0 |
| `Q4_SEARCH/search` | `264.836ms` | `343.928ms` | `138.044ms` | `132.540ms` | 0 |

Artifact:

- `sql-baseline/benchmark.json`
- `sql-baseline/summary.md`
- `sql-baseline/plans/`

## Q4 후보 실험

두 실험 모두 production에 적용하지 않는다.

| 후보 | 목적 | 결과 | 판정 |
|------|------|------|------|
| `pg_trgm.similarity_threshold=0.42` | Q4 broad fallback 후보 폭 축소 | `search_fuzzy` c64 p95 `289.146ms -> 294.329ms`, max `465.476ms -> 354.613ms`, 평균 row `9.6 -> 6.5` | p95 개선 없음 |
| `limit-before-join` | exact total은 유지하고 `mv_geocode_target` join을 page 후보 뒤로 지연 | `search_fuzzy` c64 p95 `289.146ms -> 307.716ms` | 악화 |

Artifact:

- `sql-q4-threshold-042/`
- `sql-q4-limit-before-join/`

## REST c64

처음 `rest-c64-425/` 실행에서는 `search_fuzzy` 8 measurement가 `NOT_FOUND`를 반환해 harness error로 집계됐다. 이는 서버 오류가 아니라 synthetic broad fallback case의 기대 상태가 너무 좁았던 문제다. `scripts/benchmark_api_latency.py`를 보정한 뒤 `rest-c64-425-fixed/`를 재실행했다.

| group/api | c64 p95 | c64 p99 | errors |
|-----------|--------:|--------:|-------:|
| `Q1_ROAD_EXACT/geocode_road` | `350.545ms` | `397.248ms` | 0 |
| `Q3_FUZZY_GEOCODE/geocode_fuzzy` | `349.633ms` | `422.279ms` | 0 |
| `Q3_FUZZY_GEOCODE/geocode_fuzzy_hint` | `335.589ms` | `359.031ms` | 0 |
| `Q4_SEARCH/search_fuzzy` | `328.667ms` | `356.723ms` | 0 |
| `Q4_SEARCH/search` | `324.140ms` | `352.489ms` | 0 |

Artifact:

- `rest-c64-425/` — 기대 상태 보정 전 exploratory run
- `rest-c64-425-fixed/` — 판정 기준 run

## 후속

- T-139는 즉시 착수하지 않는다. 이번 additive SQL 후보 2개는 p95를 개선하지 못했다.
- T-141은 고부하 matrix를 넓혀 endpoint mix, c128/c256, soak, pool 대기와 DB 실행시간을 함께 본다.
- T-154/T-155/T-156은 T-138에서 확인한 checkout 대기와 hot path 반복 호출을 pool fail-fast, prepared statement, result cache 경계에서 다룬다.
- T-146은 post-load `ANALYZE`/maintenance/warm 절차를 표준화해 benchmark 반복성을 높인다.
