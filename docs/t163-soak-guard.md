# T-163 60분 soak resource guard

작성일: 2026-06-16

## 결론

T-163에서는 T-141 SQL/REST 고부하 matrix runner에 60분 soak용 resource guard를
추가했다. `scripts/run_t141_load_matrix.py`는 이제 soak profile 실행 중 runner
process의 RSS, CPU time, `/proc/self/io` delta를 주기적으로 sampling하고, 정해진
budget과 누수 판정식에 따라 `pass/fail`을 artifact로 남긴다.

이번 작업은 guard 구현과 판정식 고정이 목적이다. 현재 세션에서는 T-141 때와 같이
동작 중인 T-213 r3 PostgreSQL/API 서버를 확인할 수 없어 실제 60분 live soak 결론은
남기지 않는다. 저장소 정책상 PostgreSQL/RustFS를 직접 구동하지 않으므로, 운영 또는
검증 세션에서 준비된 `KTG_PG_DSN`과 API server에 붙여 아래 명령을 실행한다.

## 산출물 계약

`matrix-report.json` schema는 `2`로 올렸다. root에 `soak_guard_budget`이 추가되고,
각 `results[]` row에는 soak profile일 때만 `soak_guard`가 포함된다.

각 soak profile artifact directory에는 다음 파일이 추가된다.

| 파일 | 내용 |
|------|------|
| `soak-resource-samples.json` | sample별 `elapsed_seconds`, `process_time_s`, `rss_bytes`, `rss_max_bytes`, `/proc/self/io` 값 |
| `soak-guard.json` | budget, RSS 증가량, CPU/IO delta, 누수 판정, 실패 사유 |

`summary.md`도 `Soak Guard Budget` 절과 결과표의 `soak guard`, `RSS growth`, `leak`,
`CPU s`, `read bytes`, `write bytes` 열을 포함한다.

## 기본 budget

기본값은 개인 서버의 60분 regression guard 기준이다. 실제 장비별 기준선이 쌓이면
명령 인자로 더 좁히거나 넓힌다.

| 항목 | 기본값 | 의미 |
|------|--------|------|
| `--soak-rss-growth-budget-mb` | `256` | soak 마지막 current RSS - 첫 current RSS 허용 증가량 |
| `--soak-rss-leak-floor-mb` | `64` | 지속 증가를 leak으로 분류하는 최소 RSS 증가량 |
| `--soak-cpu-seconds-budget` | `3600` | runner process CPU time 허용량 |
| `--soak-read-bytes-budget-mb` | `2048` | `/proc/self/io` `read_bytes` 허용 delta |
| `--soak-write-bytes-budget-mb` | `2048` | `/proc/self/io` `write_bytes` 허용 delta |
| `--soak-sample-interval-s` | `5` | RSS/CPU/IO sampling 주기 |

측정 범위는 runner process다. PostgreSQL server I/O와 메모리, 외부 REST API worker
process의 CPU/RSS는 포함하지 않는다. REST soak에서 API server 자원은 별도 운영
관측이나 Prometheus snapshot으로 함께 봐야 한다.

## 판정식

Guard 실패 조건은 다음과 같다.

1. benchmark summary error 수가 `0`보다 크다.
2. RSS current sample이 없거나, `rss_final_bytes - rss_start_bytes`가 budget을 넘는다.
3. RSS leak을 관측할 sample이 3개 미만이거나, leak이 감지된다.
4. CPU seconds delta가 없거나 budget을 넘는다.
5. `/proc/self/io` `read_bytes` 또는 `write_bytes` delta가 없거나 budget을 넘는다.

Leak 감지는 current RSS sample을 첫 1/3 구간과 마지막 1/3 구간으로 나누어 계산한다.
마지막 RSS가 첫 RSS보다 `--soak-rss-leak-floor-mb` 이상 커지고, 마지막 1/3 평균도 첫
1/3 평균보다 같은 floor 이상 크면 `leak_detected=true`다. 일시 spike만으로는 leak으로
보지 않지만, `rss_peak_growth_bytes`는 artifact에 남긴다.

## 실행 명령

Plan-only smoke:

```powershell
python scripts/run_t141_load_matrix.py `
  --mode plan --quick `
  --workload actual_mix `
  --run-id t163-plan-smoke `
  --output-dir .tmp/t163-plan-smoke `
  --include-soak --soak-seconds 3600 `
  --soak-guard-mode enforce
```

SQL 60분 soak:

```powershell
python scripts/run_t141_load_matrix.py `
  --mode sql `
  --workload actual_mix `
  --concurrency 64 `
  --corpus F:\dev\geodata\t138-read-heavy-serving-performance\20260616-r1\sql-baseline\corpus.json `
  --run-id t163-sql-soak-actual-mix-20260616 `
  --output-dir F:\dev\geodata\t163-soak-guard\20260616-r1\sql-actual-mix `
  --include-soak --soak-seconds 3600 `
  --pool-size 20 --max-overflow 64 `
  --soak-guard-mode enforce
```

REST 60분 soak:

```powershell
python scripts/run_t141_load_matrix.py `
  --mode rest `
  --base-url http://127.0.0.1:12201 `
  --corpus F:\dev\geodata\t138-read-heavy-serving-performance\20260616-r1\sql-baseline\corpus.json `
  --workload actual_mix `
  --concurrency 64 `
  --run-id t163-rest-soak-actual-mix-20260616 `
  --output-dir F:\dev\geodata\t163-soak-guard\20260616-r1\rest-actual-mix `
  --include-soak --soak-seconds 3600 `
  --admission-limit 64 `
  --server-profile workers=1 `
  --server-profile pool=20/64 `
  --soak-guard-mode enforce
```

`--soak-guard-mode report`는 실패를 artifact에만 기록한다. `enforce`는 모든 artifact를 쓴
뒤 실패 profile을 stderr에 요약하고 exit code `2`로 종료한다.

## 검증

- Windows focused unit: `python -m pytest tests/unit/test_t141_load_matrix.py -q`
- Windows focused Ruff: `python -m ruff check scripts/run_t141_load_matrix.py tests/unit/test_t141_load_matrix.py`
- Plan-only smoke: `python scripts/run_t141_load_matrix.py --mode plan --quick --workload actual_mix --run-id t163-plan-smoke --output-dir .tmp/t163-plan-smoke --include-soak --soak-seconds 3600 --soak-guard-mode enforce`

실제 60분 live soak는 동작 중인 DB/API가 준비된 WSL ext4 테스트 미러에서 수행한다. 이
작업은 DB/RustFS 생명주기를 직접 제어하지 않는다.

## 후속

- T-164는 이 `soak_guard` 결과와 T-141 p99 summary를 함께 사용해
  `scripts/evaluate_t164_p99_regression.py` 기반 baseline/current p99 회귀 gate를
  고정했다.
- 실제 장비별 60분 baseline이 쌓이면 budget 기본값을 별도 문서나 실행 profile로 조정한다.
