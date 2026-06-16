# T-141 SQL/REST 고부하 benchmark matrix

작성일: 2026-06-16

## 결론

T-141에서는 기존 T-047/T-138 단발 SQL/REST benchmark를 운영형 matrix로 묶는
`scripts/run_t141_load_matrix.py`를 추가했다. 이번 PR의 산출물은 **matrix runner와
재현 가능한 plan artifact**이며, 실제 고부하 성능 결론은 아직 내리지 않는다.

실제 T-213 r3 PostgreSQL에 연결해 SQL smoke를 시도했지만 현재 Windows 환경에서
`127.0.0.1:5432`가 listen 중이 아니었다(`Test-NetConnection` 실패). 이 저장소는
PostgreSQL/RustFS를 직접 구동하지 않는 정책이므로 DB를 시작하지 않고 중단했다.
따라서 이번 문서는 live 수치가 아니라 **실행 가능한 측정 표면**과 **blocked 이유**를
기록한다.

## 추가한 runner

`scripts/run_t141_load_matrix.py`는 다음 역할을 한다.

- T-047/T-138 SQL corpus를 재사용하거나 DB에서 새 corpus를 생성한다.
- workload를 `actual_mix`, `worst_case_mix`, `adversarial_fuzzy`,
  `reverse_polygon_heavy`로 나눈다.
- SQL profile은 기존 `benchmark_query_performance.py`를 호출해 p50/p95/p99/max,
  error, pool checkout, DB execute, `pg_stat_statements` before/after/delta를 남긴다.
- REST profile은 기존 `benchmark_api_latency.py`를 호출하고, `actual_mix`와
  `worst_case_mix`에는 lightweight admin summary endpoint(`/v1/admin/cache/metrics`,
  `/v1/admin/tables`)를 함께 넣을 수 있다.
- phase를 `steady`, `burst`, `recovery`, `soak`로 구분하고, concurrency
  `1/4/16/64/128/256`, pool, statement timeout, admission limit metadata를 plan에 남긴다.
- runner process 기준 CPU/RSS/`/proc/self/io` snapshot을 profile 전후에 기록한다.
- T-163 이후 soak profile은 `soak-resource-samples.json`과 `soak-guard.json`을
  추가로 남기고, RSS/CPU/IO budget과 누수 판정 결과를 `matrix-report.json`
  schema `2`의 `soak_guard`에 기록한다.

Windows 직접 실행에서 psycopg async가 기본 `ProactorEventLoop`를 거부하는 문제도
runner 내부에서 `SelectorEventLoop`를 사용하도록 보강했다.

## Workload 정의

| workload | 목적 |
|----------|------|
| `actual_mix` | 도로명/지번 exact, fuzzy, search, reverse, zipcode, no-result, admin summary를 운영 비율에 가깝게 섞는다. |
| `worst_case_mix` | T-047/T-138에서 tail 후보였던 fuzzy/search/reverse-radius 경로를 집중 측정한다. |
| `adversarial_fuzzy` | broad trigram, synthetic no-result, fuzzy 실패 경계로 p99 안정성을 본다. |
| `reverse_polygon_heavy` | reverse nearest/radius, zipcode point, SPPN reverse 중심으로 공간 조회 tail을 본다. |

## Artifact

| 항목 | 경로 | 내용 |
|------|------|------|
| quick plan | `F:\dev\geodata\t141-load-matrix\20260616-r1\plan\` | PR 검증용 c1/c4 plan-only artifact |
| full plan | `F:\dev\geodata\t141-load-matrix\20260616-r1\full-plan\` | 기본 64개 SQL/REST profile matrix plan |
| live smoke 시도 | `F:\dev\geodata\t141-load-matrix\20260616-r1\sql-live-smoke\` | DB 연결 전 실패. `selected-corpus.json`까지만 생성 |

Full plan은 SQL/REST 각각 4개 workload에 대해 steady c1/c4/c16/c64,
burst c128/c256, recovery c16, soak c64를 만든다. `--include-soak
--soak-seconds 1800` 기준 총 64개 profile이다.

## 재현 명령

Plan-only:

```powershell
python scripts/run_t141_load_matrix.py `
  --mode plan `
  --run-id t141-load-matrix-full-plan-20260616 `
  --output-dir F:\dev\geodata\t141-load-matrix\20260616-r1\full-plan `
  --include-soak --soak-seconds 1800 `
  --pool-size 20 --max-overflow 64 --admission-limit 64
```

60분 soak guard를 nightly/수동 gate처럼 fail-fast하려면 T-163 기준으로
`--soak-seconds 3600 --soak-guard-mode enforce`를 함께 사용한다. 기본 budget은
RSS 증가 `256MiB`, leak floor `64MiB`, CPU `3600s`, read/write 각각 `2GiB`다.
상세 판정식과 운영 명령은 `docs/t163-soak-guard.md`를 본다.

SQL live smoke(외부 DB가 떠 있을 때만):

```powershell
python scripts/run_t141_load_matrix.py `
  --mode sql --quick `
  --workload actual_mix `
  --concurrency 1 `
  --corpus F:\dev\geodata\t138-read-heavy-serving-performance\20260616-r1\sql-baseline\corpus.json `
  --max-cases-per-sql 1 `
  --run-id t141-sql-live-smoke-20260616 `
  --output-dir F:\dev\geodata\t141-load-matrix\20260616-r1\sql-live-smoke
```

REST high-load run은 API 서버를 별도로 띄운 뒤 `--mode rest --base-url
http://127.0.0.1:<port>`를 사용한다. 서버 profile은 `--server-profile
workers=... --server-profile pool=... --admission-limit ...`로 artifact에 기록한다.

## 현재 blocker

- `127.0.0.1:5432` TCP 연결이 실패한다.
- T-140 live corpus 실행 때는 WSL `.env` credential도 T-213 PostgreSQL 인증과 맞지 않았다.
- 저장소 정책상 PostgreSQL/RustFS를 직접 구동·재시작하지 않으므로, 올바른
  `KTG_PG_DSN`과 동작 중인 T-213 r3 DB가 준비된 세션에서만 live matrix를 실행한다.

## 후속 사용

- T-142/T-143은 이 runner의 `worst_case_mix`, `adversarial_fuzzy`,
  `reverse_polygon_heavy` plan을 사용해 후보 변경 전후를 같은 corpus로 비교한다.
- T-145/T-154는 burst c128/c256과 admission/pool metadata를 사용해 fail-fast와
  checkout timeout 정책을 비교한다.
- T-163은 `--include-soak --soak-seconds 3600 --soak-guard-mode enforce`로
  RSS/IO/CPU budget과 leak guard를 고정했다.
- T-164는 같은 matrix 결과 위에 p99 회귀 gate를 추가한다.
