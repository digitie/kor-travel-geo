# T-035 MV refresh/swap 벤치마크

본 문서는 `mv_geocode_target` 갱신 전략 두 가지를 같은 실제 전국 DB에서 비교한 기록이다. 목적은 단순 총시간 비교가 아니라, 풀로드 직후 운영 점검 창을 잡을 때 어떤 구간이 조회와 경합하는지 판단할 수 있도록 phase별 시간과 임시 파일 I/O를 남기는 것이다.

## 범위

비교 대상:

1. `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target`
2. shadow MV build + index build + 짧은 rename swap

사용 데이터:

- DB: `kraddr_geo_t033`
- 출처: T-033 전국 full-load 결과
- `mv_geocode_target`: 6,416,637행
- MV total size: 약 3.35GiB
- DB size: 약 26GB

T-035는 새 full-load를 다시 수행하지 않는다. 동일 DB에서 MV 갱신 전략만 반복 실행해 비교했다.

## 실행 환경

| 항목 | 값 |
|------|----|
| 실행일 | 2026-05-26 |
| 작업 브랜치 | `codex/t035-mv-refresh-benchmark` |
| OS | WSL2 Linux `6.6.87.2-microsoft-standard-WSL2` |
| CPU | AMD Ryzen 7 7840HS, 16 logical cores |
| 메모리 | 29GiB total, 실행 시 available 약 27GiB |
| ext4 여유 공간 | `/dev/sdd` 1007G 중 759G available |
| NTFS 데이터 공간 | `/mnt/f` 932G 중 267G available |
| Docker DB | `kraddr-geo-t027-db-1`, `postgis/postgis:16-3.5`, host port `15432` |
| benchmark artifact | `artifacts/t035-mv-refresh-20260526_045339/` (git ignore) |

## 재현 스크립트

이번 PR에서 `scripts/benchmark_mv_refresh.py`를 추가했다. 이 스크립트는 `KRADDR_GEO_PG_DSN`이 가리키는 DB에서 전략별 refresh를 실행하고 JSON으로 다음 값을 출력한다.

- 실행 전략과 시작/종료 시간
- phase별 시간
- `mv_geocode_target` row count, heap/index/total size
- `pg_stat_database.temp_files`, `temp_bytes`
- 운영 MV index 이름과 크기
- JSON `schema_version`
- trial 번호, cache warm hint, note, benchmark 전후 active session 수, wait event snapshot

실행 예:

```bash
ARTIFACT_DIR=artifacts/t035-mv-refresh-20260526_045339

/usr/bin/time -v env \
  KRADDR_GEO_PG_DSN='postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t033' \
  KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000 \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/python scripts/benchmark_mv_refresh.py \
    --strategy concurrent \
    --trial-index 1 \
    --cache-warm-hint repeated-same-db \
    --note "idle Docker DB; no intentional concurrent API traffic" \
    --output "$ARTIFACT_DIR/concurrent.json" \
  2>&1 | tee "$ARTIFACT_DIR/concurrent.time.log"

/usr/bin/time -v env \
  KRADDR_GEO_PG_DSN='postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t033' \
  KRADDR_GEO_PG_STATEMENT_TIMEOUT_MS=1800000 \
  TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/python scripts/benchmark_mv_refresh.py \
    --strategy swap \
    --trial-index 1 \
    --cache-warm-hint repeated-same-db \
    --note "idle Docker DB; no intentional concurrent API traffic" \
    --output "$ARTIFACT_DIR/swap-split-analyze.json" \
  2>&1 | tee "$ARTIFACT_DIR/swap-split-analyze.time.log"
```

## 결과 요약

| 전략 | `/usr/bin/time` wall clock | 스크립트 phase 합계 | temp files 증가 | temp bytes 증가 | MV row count |
|------|----------------------------:|--------------------:|----------------:|----------------:|-------------:|
| `CONCURRENTLY` | 1분 49.64초 | 111.64초 | +91 | +12,309,605,099 bytes | 6,416,637 |
| `swap` | 2분 16.28초 | 137.15초 | +44 | +9,150,995,144 bytes | 6,416,637 |

이번 idle Docker DB에서는 `CONCURRENTLY`가 총시간 기준 약 26.6초 빨랐다. 그러나 `CONCURRENTLY`는 운영 MV를 직접 refresh하면서 약 12.31GB의 temp I/O를 만들었고, 실행 중 `pg_stat_activity`에서 `wait_event_type=IO`, `wait_event=BufFileWrite`가 관측됐다. 반대로 `swap`은 총시간은 더 길지만, 조회가 물고 있는 운영 MV를 그대로 둔 채 `mv_geocode_target_next`를 만든 뒤 rename 구간만 짧게 가져간다.

## `CONCURRENTLY` 세부

최종 측정 파일: `concurrent.json`, `concurrent.time.log`

| Phase | 시간 |
|-------|-----:|
| `refresh_concurrently` | 106.68초 |
| `analyze` | 4.96초 |

관찰:

- 실행 중 `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_geocode_target` backend가 `BufFileWrite` I/O wait를 보였다.
- temp 누적값은 `temp_files` 398 → 489, `temp_bytes` 55,741,339,227 → 68,050,944,326으로 증가했다.
- MV heap/index size는 refresh 전후 동일했다. 이는 원천 데이터가 변하지 않은 상태에서 재계산했기 때문이다.
- 단발 측정 기준으로는 운영 조회를 계속 허용하면서 가장 짧은 총시간을 보였다.

## `swap` 세부

최종 측정 파일: `swap-split-analyze.json`, `swap-split-analyze.time.log`

| Phase | 시간 |
|-------|-----:|
| `rebuild.create_next` | 68.79초 |
| `rebuild.index.idx_mv_next_geocode_target_next_pk` | 12.20초 |
| `rebuild.index.idx_mv_next_road` | 6.37초 |
| `rebuild.index.idx_mv_next_jibun` | 6.56초 |
| `rebuild.index.idx_mv_next_rn_trgm` | 11.01초 |
| `rebuild.index.idx_mv_next_buld_nm_trgm` | 5.79초 |
| `rebuild.index.idx_mv_next_geom5179` | 9.27초 |
| `rebuild.index.idx_mv_next_geom4326` | 9.42초 |
| `rebuild.index.idx_mv_next_pt_source` | 2.19초 |
| `swap.drop_old_pre` | 0.0005초 |
| `swap.rename_live_to_old` | 0.0007초 |
| `swap.rename_next_to_live` | 0.0008초 |
| `swap.drop_old_post` | 0.0021초 |
| `swap.rename_indexes` | 0.0124초 |
| `swap.analyze_live` | 4.89초 |

관찰:

- shadow MV 생성 자체가 약 68.79초로 가장 크다.
- index build 합계는 약 63.29초다. 그중 PK 12.20초, `rn_trgm` 11.01초, GiST 두 개가 각각 약 9.3~9.4초로 컸다.
- temp 누적값은 `temp_files` 577 → 621, `temp_bytes` 86,352,934,614 → 95,503,929,758로 증가했다.
- `mv_geocode_target_next`와 `mv_geocode_target_old`는 최종적으로 남지 않았다.
- 운영 index 이름은 `idx_mv_*`로 정상 정규화됐다.

## 이번 PR의 코드 개선

첫 granular 측정에서 기존 `shadow_swap_mv()`가 rename/drop/index rename 이후 `ANALYZE mv_geocode_target`까지 같은 transaction 안에서 실행하는 것을 확인했다. `ANALYZE` 자체는 약 4.86초였고, 이 시간이 swap transaction에 남아 있으면 rename으로 잡은 lock을 불필요하게 오래 유지할 수 있다.

이번 PR은 `shadow_swap_mv()`를 다음처럼 바꿨다.

1. transaction A: `lock_timeout`, old drop, live → old rename, next → live rename, old drop, index rename
2. transaction B: `SET LOCAL lock_timeout = '2s'` 후 `ANALYZE mv_geocode_target`

최종 측정 기준 lock-sensitive rename/index rename 구간은 다음 합계로 약 **0.016초**다.

```text
swap.drop_old_pre
swap.rename_live_to_old
swap.rename_next_to_live
swap.drop_old_post
swap.rename_indexes
```

`swap.analyze_live` 4.89초는 별도 transaction으로 분리되어, rename swap의 ACCESS EXCLUSIVE lock window와 분리된다.

T-036 후속 리뷰 반영으로 `scripts/benchmark_mv_refresh.py` 출력 JSON은 `schema_version=2`와 `metadata`를 포함한다. `metadata.concurrent_sessions_before/after`는 같은 DB의 idle이 아닌 다른 session 수를 기록하고, `metadata.wait_events_before/after`는 `pg_stat_activity`의 wait event snapshot을 남긴다. 단, wait event는 benchmark 시작/종료 snapshot이므로 실행 중 순간적으로 보인 `BufFileWrite` 같은 이벤트를 완전한 time series로 보존하지는 않는다.

## 운영 판단

| 상황 | 권장 |
|------|------|
| 평시 소량 변동분, 운영 조회 경합이 낮고 짧은 총시간이 우선 | `REFRESH MATERIALIZED VIEW CONCURRENTLY` |
| 분기/월간 대규모 풀로드 직후, 운영 MV를 최대한 오래 안정적으로 유지해야 함 | `--swap` |
| 점검 창이 아주 짧고 temp I/O 여유가 충분한 야간 | 두 전략 모두 가능하지만 `CONCURRENTLY`가 이번 idle DB에서는 더 짧았음 |
| API latency가 중요한 시간대 | `swap`을 선호. rebuild/index build는 shadow MV에서 일어나고 rename 구간만 짧음 |

T-033의 full-load 직후 `refresh mv --swap`은 약 2분 28초였다. T-035의 최종 `swap` 단독 벤치마크는 2분 16.28초로 비슷한 범위다. 차이는 DB cache 상태, 직전 refresh 반복, temp 파일 상태에 따른 변동으로 본다.

## 검증

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py -q
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check scripts/benchmark_mv_refresh.py tests/unit/test_mv_refresh_benchmark.py tests/unit/test_postload_mv.py src/kraddr/geo/loaders/postload.py
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m mypy scripts/benchmark_mv_refresh.py src/kraddr/geo/loaders/postload.py
```

최종 PR 검증에서는 전체 테스트와 import-linter도 함께 실행한다.

## 후속

- T-036: `maplibre-vworld-js` upstream main 동기화.
- T-028: 완료. 일변동 ZIP 로더는 실제 `20260401`/`20260404` daily ZIP과 synthetic fixture로 검증했다.
- T-027: 모든 후속 작업이 끝난 뒤 DB를 삭제하고 처음부터 다시 full-load + MV refresh + smoke + consistency를 검증한다.
