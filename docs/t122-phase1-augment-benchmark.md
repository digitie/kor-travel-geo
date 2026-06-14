# T-122 phase ① 보강 성능평가·벤치

T-122는 T-121에서 전국 실 원천으로 실행한 C11~C17 보강 검증 harness의 실행 비용을 case별로 분리 측정한다. 목적은 phase ① 최종 검증(T-123)에서 튜닝 후보를 고르기 위한 기준선을 만드는 것이다.

## 실행 환경

- 실행 위치: WSL ext4 테스트 미러 `~/dev/kor-travel-geo-codex-test`
- Git source of truth: `F:\dev\kor-travel-geo-codex`
- 입력 원천: `data/juso` symlink → `/mnt/f/dev/kor-travel-geo/data/juso`
- DB: `.env`의 `KTG_PG_DSN`이 가리키는 기존 PostGIS DB
- 산출물: `artifacts/perf/t122-phase1-live/`
- run_id: `t122-phase1-live-20260614`
- Git commit: `0882c42bf59f97f7cb8df33e21e2d97bfa04d951`
- artifact 기준 실행 시각: `2026-06-14T15:16:25Z` ~ `2026-06-14T16:22:27Z`

실행 명령:

```bash
KTG_SLOW_REAL_DATA=1 TMPDIR=/tmp TMP=/tmp TEMP=/tmp \
  .venv/bin/python scripts/benchmark_phase1_augment_performance.py \
  --output-dir artifacts/perf/t122-phase1-live \
  --run-id t122-phase1-live-20260614 \
  --materialize-navi-7z \
  --pg-statement-timeout-ms 3600000 \
  --sample-interval-s 1 \
  --git-repo F:/dev/kor-travel-geo-codex
```

## 측정 범위

`scripts/benchmark_phase1_augment_performance.py`는 T-121 runner의 source plan과 case 실행 함수를 재사용한다. `preparation` 단계에서 전자지도 ZIP과 C17 `match_jibun_*.txt` materialization 비용을 먼저 측정하고, C11~C17 case는 그 뒤 순차 실행해 각각 별도 `ResourceUsage`를 기록한다.

측정값은 runner process 기준이다.

- RSS: `/proc/self/status`의 `VmRSS`를 1초 간격으로 sampling한 peak
- I/O: `/proc/self/io`의 `rchar`, `read_bytes`, `wchar`, `write_bytes` delta
- child I/O: 사용 가능한 경우 `resource.RUSAGE_CHILDREN`의 block I/O delta를 JSON에 기록
- 제외: PostgreSQL server process의 buffer/cache/디스크 I/O와 DB 내부 메모리

따라서 C11~C17의 `write_bytes=0`은 DB staging/COPY가 없었다는 뜻이 아니라, runner process가 로컬 파일로 쓴 바이트가 없었다는 뜻이다. DB 서버의 write I/O는 이 artifact에 포함되지 않는다.

## 전국 실행 결과

총 실행시간은 3961.937초다. 준비 단계에서 materialized cache는 약 17GiB까지 생성됐다.

| phase | task | used | failed | seconds | peak RSS | rchar | read bytes | wchar | write bytes |
|-------|------|-----:|-------:|--------:|---------:|------:|-----------:|------:|------------:|
| preparation | source-plan | n/a | n/a | 848.988 | 97.9 MiB | 4.6 GiB | 4.6 GiB | 16.0 GiB | 16.0 GiB |
| C11 | T-111 | 17 | 0 | 1284.931 | 2.0 GiB | 4.1 GiB | 8.0 GiB | 0 B | 0 B |
| C12 | T-112 | 17 | 0 | 270.358 | 2.2 GiB | 4.9 GiB | 3.6 GiB | 0 B | 0 B |
| C13 | T-113 | 17 | 0 | 307.343 | 1.0 GiB | 650.0 MiB | 649.6 MiB | 0 B | 0 B |
| C14 | T-114 | 1 | 0 | 378.739 | 763.0 MiB | 1.4 GiB | 1.4 GiB | 0 B | 0 B |
| C15 | T-115 | 1 | 0 | 17.534 | 758.0 MiB | 1.9 MiB | 1.9 MiB | 0 B | 0 B |
| C16 | T-116 | 1 | 0 | 624.866 | 756.2 MiB | 314.0 MiB | 313.8 MiB | 0 B | 0 B |
| C17 | T-117 | 1 | 0 | 229.178 | 747.9 MiB | 1.2 GiB | 1.1 GiB | 0 B | 0 B |

전체 case는 실패 0건으로 끝났다. C11~C13은 17개 시도 모두 `used=17`, C14~C17은 전국 단일 묶음 `used=1`이다.

## 관찰

- `preparation`은 848.988초와 16.0GiB local write로 가장 큰 로컬 I/O 비용을 만든다. T-123에서는 materialized cache 재사용 여부를 명시하고, cache warm/cold를 분리해 재측정하는 것이 좋다.
- C11은 case 실행시간 1284.931초로 가장 오래 걸린다. T-121의 1394.216초보다 약간 낮지만 여전히 phase ①의 주 병목이다.
- C12는 270.358초지만 peak RSS가 2.2GiB로 가장 높다. connection line staging과 road line distance 계산 구간의 메모리 사용을 T-123에서 우선 확인할 후보로 둔다.
- C14는 DB를 쓰지 않는 streaming 검증인데도 378.739초와 1.4GiB read를 기록했다. 100m grid streaming iterator는 현재 구조로도 전국 실행 가능하지만, T-123에서 chunk 단위 보고와 ZIP member 선택 비용을 더 볼 수 있다.
- C15는 17.534초로 비용이 작아 별도 튜닝 우선순위가 낮다.
- C16은 624.866초로 텍스트 parser/COPY와 key drift SQL 비용이 섞여 있다. T-123에서 parser chunk 크기와 staging index 생성 위치를 점검할 후보로 둔다.
- C17은 preparation에서 7z materialization 비용을 대부분 지불하고, case 본체는 229.178초다. phase ② registry에서는 materialization cache lifecycle이 성능과 운영 UX에 직접 영향을 준다.

## 산출물 구조

```text
artifacts/perf/t122-phase1-live/
  benchmark.json
  summary.md
  run.log
  reports/
    c11-t-111.json
    c12-t-112.json
    c13-t-113.json
    c14-t-114.json
    c15-t-115.json
    c16-t-116.json
    c17-t-117.json
  materialized/
    electronic_map_202604/
    navi_match_jibun_202604/
```

`benchmark.json`은 각 phase의 raw byte delta, child block I/O delta, source path 목록을 포함한다. `reports/*.json`은 T-121과 같은 `AugmentReport` 원문이다.

## 다음 작업

T-123에서는 이 기준선을 바탕으로 튜닝과 최종 검증 평가를 수행한다. 우선 후보는 다음 순서다.

1. materialization cache warm/cold 분리와 재사용 정책 명시
2. C11/C12 SHP staging peak RSS와 distance SQL 비용 확인
3. C16 parser/COPY chunk 및 staging index 위치 점검
4. 튜닝 후 같은 benchmark script로 재측정
