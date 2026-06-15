# T-214 phase ② 성능평가·벤치

작성일: 2026-06-15
담당: Codex(Agent A)

## 기준 입력

T-214는 기본 개발 DB를 쓰지 않고 `docs/t213-data-preservation.md`의 전용 T-213 기준 데이터를 사용했다.

| 항목 | 값 |
|------|----|
| PostgreSQL DB | `kor_travel_geo_t213_20260615_r3` |
| RustFS bucket/prefix | `kor-travel-geo` / `kor-travel-geo/t213/20260615-rerun3` |
| T-213 artifact | `F:\dev\geodata\t213-baseline\20260615-rerun3\` |
| T-214 artifact | `F:\dev\geodata\t214-benchmark\20260615-r3\` |
| source match set | `a0c2d514-a91d-44c4-bdb6-0bc4771ae61a` |
| serving release | `54e17e80-312e-46da-a58f-d8b10be37c85` |
| dataset snapshot | `1b354560-52bc-4ec6-8760-55fed63d9e98` |

> artifact는 repo 밖 NTFS 공용 영역(`F:\dev\geodata`, Git 비커밋)에 보존한다. 상세 보존 정책: `docs/t213-data-preservation.md`.

Preflight에서 `current_database()`, active serving release, dataset snapshot, 핵심 row count가 T-213 summary와 일치함을 확인했다.

| relation | rows |
|----------|-----:|
| `mv_geocode_target` | 6,419,795 |
| `mv_geocode_text_search` | 6,419,795 |
| `tl_sppn_makarea` | 24,204 |

## 실행 범위

| 범위 | 하네스/근거 | artifact |
|------|-------------|----------|
| full load / rebuild-db | T-213 r3 실제 full-load batch 로그 | `F:\dev\geodata\t213-baseline\20260615-rerun3\t213-live-summary.json` |
| SQL geocode/reverse/search | `scripts/benchmark_query_performance.py` | `query-standard\` |
| REST API geocode/reverse/search | `scripts/benchmark_api_latency.py` | `rest-api\` |
| MV refresh/swap | `scripts/benchmark_mv_refresh.py` | `mv-refresh\` |
| deep rehash / multipart streaming | `scripts/benchmark_source_registry_perf.py` | `source-registry-synthetic\` |
| RustFS reconciliation quick/deep | `AsyncAddressClient.run_source_reconcile()` | `reconcile\` |

## full load / rebuild-db

T-213 r3 재실행은 실제 source registry → match set → rebuild-db → consistency → MV refresh 경로다. 총 실행 시간은 6,175.539초이고, full-load batch 자체는 2,917.935초였다.

| job kind | seconds |
|----------|--------:|
| `juso_text_load` | 215.762 |
| `locsum_load` | 141.609 |
| `navi_load` | 309.324 |
| `shp_polygons_load` | 1,253.827 |
| `roadaddr_entrance_load` | 220.781 |
| `sppn_makarea_load` | 33.306 |
| `consistency_check` | 261.840 |
| `mv_refresh` | 481.223 |
| `full_load_batch` | 2,917.935 |

## SQL benchmark

설정: `cases_per_group=100`, `iterations=3`, `warmup=1`, concurrency `1/4/16/64`, pool `size=20`, `max_overflow=64`, statement timeout 5초. 전체 summary 80개에서 오류는 0건이다.

| concurrency | worst p95 | group / sql |
|-------------|----------:|-------------|
| 1 | 14.838ms | `Q3_FUZZY_GEOCODE` / `fuzzy_geocode_wide` |
| 4 | 18.023ms | `Q3_FUZZY_GEOCODE` / `fuzzy_geocode` |
| 16 | 35.153ms | `Q3_FUZZY_GEOCODE` / `fuzzy_geocode` |
| 64 | 245.895ms | `Q4_SEARCH` / `search_fuzzy` |

Q3/Q4 fuzzy/search 계열이 c64 tail의 주 후보다. artifact에는 slow sample별 `EXPLAIN` JSON과 `pg_stat_statements` delta가 포함된다.

## REST API benchmark

설정: SQL corpus에서 REST case 425개를 변환했고, `iterations=2`, `warmup=1`, concurrency `1/4/16/64`, timeout 15초로 측정했다. 오류는 0건이다.

| concurrency | worst p95 | group / API |
|-------------|----------:|-------------|
| 1 | 10.066ms | `Q4_SEARCH` / `search_fuzzy` |
| 4 | 15.162ms | `Q4_SEARCH` / `search_fuzzy` |
| 16 | 58.168ms | `Q5_REVERSE_NEAREST` / `reverse_reverse_nearest` |
| 64 | 534.031ms | `Q4_SEARCH` / `search_fuzzy` |

c64에서는 REST 서버/DB pool 대기와 Q4 search fuzzy tail이 함께 보인다. T-215에서 admission/pool 설정과 Q4/Q3 tail을 재측정 후보로 둔다.

## MV refresh/swap

| strategy | total seconds | rows after | text-search rows after |
|----------|--------------:|-----------:|-----------------------:|
| `concurrent` | 126.414 | 6,419,795 | 6,419,795 |
| `swap` rerun | 340.128 | 6,419,795 | 6,419,795 |

첫 `swap` 측정은 실제 swap 이후 `ANALYZE mv_geocode_target` 단계에서 DB 세션의 5초 statement timeout에 걸렸다. relation은 `mv_geocode_target`, `mv_geocode_text_search`만 남고 row count도 기준값과 일치했다. `ANALYZE`를 statement timeout 없이 수동 보정했으며 7.001초가 걸렸다. 최종 비교값은 statement timeout을 30분으로 올린 `swap-rerun.json`을 기준으로 한다. 실패 분류와 복구 내역은 `mv-refresh\swap-timeout-note.json`에 둔다.

## Source registry / RustFS

기기 비종속 synthetic 하네스는 1MiB chunk streaming 계약을 재확인했다.

| 항목 | 입력 | elapsed | throughput | peak traced memory |
|------|------|--------:|-----------:|-------------------:|
| deep rehash | 8개 × 64MiB | 0.457s | 1,119.6MiB/s | 2.01MiB |
| multipart read | 512MiB | 0.166s | 3,084.9MiB/s | 2.01MiB |

실제 T-213 RustFS prefix reconcile 결과는 다음과 같다.

| mode | elapsed | scanned objects | DB files | rehashed | skipped rehash | mismatch |
|------|--------:|----------------:|---------:|---------:|---------------:|---------:|
| `quick` | 11.374s | 56 | 54 | 54 | 0 | 2 |
| `deep` | 9.952s | 56 | 54 | 54 | 0 | 2 |

두 mismatch는 모두 `object_missing_db` warning이다. 등록 DB row가 없는 object가 prefix에 2개 남아 있고, 등록된 DB file의 object missing은 0건이다. 이 두 object는 T-213 기준 load를 막지는 않지만, T-215 또는 운영 정리 단계에서 typed confirmation 기반 hard-delete 후보로 분리한다.

## 결론

T-214 범위의 full-load, SQL/REST, MV refresh/swap, source registry synthetic perf, RustFS quick/deep reconcile 측정은 완료됐다. T-215는 이 결과를 기준으로 Q3/Q4 c64 tail, REST pool/admission, MV swap timeout 설정, reconcile warning 2건 정리 여부, geocode/reverse 정확도·v1/v2 회귀·C1~C17 최종 acceptance를 다룬다. N150/Odroid 실측은 하드웨어가 준비되면 T-063으로 연결한다.
