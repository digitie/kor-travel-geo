# T-177H 벤치마크 수용 보고서

## 목적

T-177G 전국 장기 실행 file-driven full-load e2e로 구축한 PostgreSQL/PostGIS DB가 서빙
용도로 계속 사용할 수 있는지 SQL/REST 벤치마크로 최종 확인한다. 이 문서는 T-047 계열
벤치마크 hook, p95/p99, 오류 건수, 느린 실행 계획, `pg_stat_statements` snapshot 산출물을
T-177 파일 기반 full-load e2e의 최종 수용 근거로 묶는다.

## 실행 전 게이트

- PR #387(T-197 REST 벤치마크 client disconnect cancellation 오탐 수정)을 먼저 머지했다.
- `codex/t177h-benchmark-acceptance` 브랜치를 `origin/main`
  `2a3bee2b3db5675e39066abb31029feaa5b66573` 위로 리베이스했다.
- 다음 문서를 다시 읽고 prod/dev 정의를 확인했다.
  - `README.md`
  - `SKILL.md`
  - `docs/runbooks/agent-workflow.md`
  - `docs/runbooks/agent-failure-patterns.md`
  - `docs/architecture/architecture.md`
  - `docs/resume.md`
  - `docs/adr/README.md`
  - `docs/tasks.md`
  - `docs/ports.md`
  - `docs/dev-environment.md`
  - `docs/t177-file-driven-full-load-e2e-plan.md`
  - `.env.dev.example`
  - `.env.prod.example`
  - `kor-travel-geo-ui/.env.local.example`

이번 벤치마크는 prod 공식 도메인이나 `.env.prod`가 아니라 로컬 dev 정의를 따른다. API는
`127.0.0.1:12501`, PostgreSQL은 이미 동작 중인 `127.0.0.1:5432`의 T-177G DB에 접속했다.
저장소 절차에 따라 PostgreSQL/RustFS 생명주기는 조작하지 않았고, 벤치마크용 API
프로세스만 WSL ext4 테스트 미러에서 띄웠다가 종료했다.

## 대상 DB

| 항목 | 값 |
| --- | --- |
| DB | `kor_travel_geo_t177g_codex_20260618133300` |
| PostgreSQL | `127.0.0.1:5432` |
| DB 크기 | `35 GB` (`37,309,190,627` bytes) |
| active `serving_release_id` | `d29594b5-f033-45c2-839e-71b1b0100a61` |
| active `dataset_snapshot_id` | `d9020c84-79e7-400c-b2e3-fc39baa44885` |
| release kind | `manual_rebuild` |
| activated/created | `2026-06-18T06:37:22.081851Z` |

주요 row count:

| relation | row count |
| --- | ---: |
| `mv_geocode_target` | 6,419,795 |
| `mv_geocode_text_search` | 6,419,795 |
| `tl_juso_text` | 6,419,795 |
| `tl_sppn_makarea` | 24,204 |
| `tl_locsum_entrc` | 6,405,091 |
| `tl_roadaddr_entrc` | 6,404,697 |
| `tl_juso_parcel_link` | 1,771,043 |
| `tl_spbd_buld_polygon` | 10,687,732 |
| `tl_navi_buld_centroid` | 10,687,317 |
| `tl_navi_entrc` | 12,830 |

원천 기준월은 `database_manifest_inference`로 복원된 snapshot 기준이며, `mixed_yyyymm=true`다.
종류별 기준월은 `shp=202604`, `juso=202605`, `navi=202604`, `locsum=202604`,
`parcel_link=202605`, `sppn_makarea=202603`, `roadaddr_entrance=202605`다.

## SQL 벤치마크

산출물:

`/home/digitie/dev/kor-travel-geo-codex-test/artifacts/perf/t177h-sql-20260619T182225Z`

실행 프로파일:

- 실행기: `scripts/benchmark_query_performance.py`
- `--cases-per-group 100`
- `--iterations 2`
- `--warmup 1`
- 동시성: `1`, `16`, `64`
- `--statement-timeout-ms 10000`
- 풀: `--pool-size 64 --max-overflow 0`
- 느린 실행 계획: `--explain-slowest-per-group 1`
- `pg_stat_statements`: reset 후 상위 100개 snapshot

결과:

- 총 measurement: 18,000
- 오류 건수: 0
- corpus/plan/stat 산출물 생성 완료

최악 p95:

| concurrency | group / case | p95 | p99 |
| ---: | --- | ---: | ---: |
| 1 | `Q5_REVERSE_NEAREST / reverse_nearest_sig` | 16.046 ms | 17.621 ms |
| 16 | `Q3_FUZZY_GEOCODE / fuzzy_geocode` | 36.747 ms | 42.526 ms |
| 64 | `Q4_SEARCH / search_fuzzy` | 146.225 ms | 155.640 ms |

## REST 벤치마크

산출물:

`/home/digitie/dev/kor-travel-geo-codex-test/artifacts/perf/t177h-rest-20260619T182653Z`

실행 프로파일:

- 실행기: `scripts/benchmark_api_latency.py`
- base URL: `http://127.0.0.1:12501`
- corpus: SQL 벤치마크의 `corpus.json`
- `--iterations 2`
- `--warmup 1`
- 동시성: `1`, `4`, `16`, `64`
- timeout: `15s`
- Prometheus before/after capture
- API 서버: `uvicorn_workers=1`, `uvicorn_loop=uvloop`
- DB 풀: `KTG_PG_POOL_SIZE=20`, `KTG_PG_MAX_OVERFLOW=64`
- admission: disabled
- geoip gate: off
- env: dev

벤치마크 전후 `/v1/readyz`와 `/metrics` snapshot을 남겼고, API 로그는 정상 200 응답과
정상 shutdown만 기록했다. 벤치마크 뒤 `12501` listen이 남아 있지 않음을 확인했다.

결과:

- REST case count: 1,800
- 총 measurement: 21,600
- 오류 건수: 0
- corpus SHA-256: `83f6a293dbd972e989157586278b70d8e8a68a19b55e83e85f946b4c596cdb48`

최악 p95:

| concurrency | group / case | p95 | p99 |
| ---: | --- | ---: | ---: |
| 1 | `Q3_FUZZY_GEOCODE / geocode_fuzzy` | 17.283 ms | 21.504 ms |
| 4 | `Q8_NO_RESULT / geocode_no_result_road` | 26.233 ms | 33.728 ms |
| 16 | `Q8_NO_RESULT / geocode_no_result_road` | 110.722 ms | 123.116 ms |
| 64 | `Q8_NO_RESULT / geocode_no_result_road` | 406.511 ms | 427.224 ms |

concurrency 64의 주요 p95:

| case | p95 |
| --- | ---: |
| `search` | 393.380 ms |
| `search_fuzzy` | 359.380 ms |
| `geocode_fuzzy` | 317.810 ms |
| `geocode_fuzzy_hint` | 313.320 ms |
| `geocode_road_hint` | 282.870 ms |
| `search_hint` | 282.330 ms |
| `reverse_sppn_reverse` | 274.230 ms |
| `zipcode_address` | 264.150 ms |

가장 느린 단일 sample은 `geocode_fuzzy_hint` concurrency 64의 max 1,105.610 ms였지만,
해당 case p99는 461.760 ms였고 error는 없었다.

## 판정

T-177H는 통과로 판정한다.

- SQL 벤치마크는 18,000 measurement, error 0이다.
- REST 벤치마크는 21,600 measurement, error 0이다.
- T-197 전 재현됐던 REST client disconnect/`CancelledError` 오탐은 최종 REST 실행에서
  재발하지 않았다.
- SQL/REST p95는 T-177G 전국 DB의 현재 read-optimized serving 구조에서 허용 가능한 범위에
  있으며, T-177 파일 기반 full-load e2e의 최종 성능 acceptance 차단 요인은 없다.

이 판정은 file-driven full-load로 구축한 전국 DB의 서빙 성능 acceptance다. 원천 기준월 혼합은
snapshot metadata에 기록된 기존 데이터 특성으로 남아 있으며, 이 문서에서 별도의 데이터 품질
수정 작업으로 취급하지 않는다.

## 남은 후속

- T-177A~T-177H는 모두 완료했다.
- 낮은 우선순위 선택 후속은 T-219 잔여 L만 남아 있다.
- 외부 장비가 필요한 T-063 N150/Odroid 실측은 하드웨어 준비 전까지 보류다.
