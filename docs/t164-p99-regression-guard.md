# T-164 p99 regression guard

작성일: 2026-06-16

## 결론

T-164에서는 T-141 matrix artifact를 baseline/current로 비교하는 p99 회귀 gate를
추가했다. `scripts/evaluate_t164_p99_regression.py`는 두 `matrix-report.json`의
같은 `profile_id`를 비교하고, current p99가 허용 임계를 넘거나 error가 있거나 T-163
soak guard가 실패하면 `p99-guard.json`과 `summary.md`를 남긴 뒤 exit code `2`로
종료할 수 있다.

이 작업은 실제 live 60분 실행이 아니라 **artifact 비교 gate**를 고정한다. Live SQL/REST
matrix는 동작 중인 DB/API가 있는 WSL ext4 테스트 미러에서 T-141/T-163 명령으로 만들고,
이 스크립트는 생성된 baseline/current artifact를 CI/nightly 단계에서 비교한다.

## 비교 기준

기본 임계값은 다음과 같다.

| 항목 | 기본값 | 의미 |
|------|--------|------|
| `--max-p99-regression-ratio` | `0.20` | baseline p99 대비 20% 초과 회귀를 실패로 본다. |
| `--absolute-tolerance-ms` | `25` | 작은 baseline의 noise를 피하기 위한 최소 허용 delta다. |
| error budget | `0` | 기본적으로 current row의 `errors > 0`이면 실패한다. |
| soak guard | 필수 | `phase="soak"` row는 T-163 `soak_guard.passed=true`가 아니면 실패한다. |

허용 p99는 `max(baseline_p99 * (1 + ratio), baseline_p99 + absolute_tolerance_ms)`다.
예를 들어 baseline p99가 `100ms`이면 기본 허용값은 `125ms`이고, baseline p99가
`300ms`이면 기본 허용값은 `360ms`다.

## 대상 profile

비교 key는 `profile_id`다. Current report에 포함된 profile이 baseline report에 없으면
`baseline_profile_missing` 실패로 처리한다. 기본은 current report의 모든 결과 row를
비교하지만, T-164 nightly 후보는 입력분포 변화에 민감한 workload를 우선 필터링한다.

권장 필터:

- `--workload adversarial_fuzzy`
- `--workload worst_case_mix`
- `--workload reverse_polygon_heavy`

필요하면 `--target sql`, `--target rest`, `--phase steady`, `--phase burst`,
`--phase recovery`, `--phase soak`를 반복 지정해 scope를 좁힌다.

## 산출물

출력 디렉터리에는 다음 파일을 남긴다.

| 파일 | 내용 |
|------|------|
| `p99-guard.json` | threshold, filter, 비교 row별 baseline/current p99, delta, ratio, 실패 사유 |
| `summary.md` | 사람이 읽는 비교표 |

`--mode report`는 산출물만 쓰고 종료한다. 기본 `--mode enforce`는 실패 row가 있으면
stderr에 `p99 guard failed: <profile_id>: <reason>`을 출력하고 exit code `2`로 종료한다.

## 실행 예시

```powershell
python scripts/evaluate_t164_p99_regression.py `
  --baseline-report F:\dev\geodata\t141-load-matrix\baseline\matrix-report.json `
  --current-report F:\dev\geodata\t141-load-matrix\candidate\matrix-report.json `
  --output-dir F:\dev\geodata\t164-p99-guard\20260616-r1 `
  --workload adversarial_fuzzy `
  --workload worst_case_mix `
  --workload reverse_polygon_heavy `
  --max-p99-regression-ratio 0.20 `
  --absolute-tolerance-ms 25 `
  --mode enforce
```

Soak row의 resource guard를 별도 단계에서 이미 판정하고 p99만 보고 싶다면
`--allow-missing-soak-guard`를 사용할 수 있다. 기본 gate에서는 쓰지 않는다.

## 검증

- Windows focused unit: `python -m pytest tests/unit/test_t164_p99_guard.py -q`
- Windows focused Ruff: `python -m ruff check scripts/evaluate_t164_p99_regression.py tests/unit/test_t164_p99_guard.py`
- Windows focused mypy: `python -m mypy scripts/evaluate_t164_p99_regression.py`

## 후속

- T-171부터는 T-140 corpus의 ranking/confidence/negative/hint/reverse boundary case를
  실제 정확도 gate로 넓힌다.
- 실제 nightly를 붙일 때는 T-141/T-163 실행 job이 `matrix-report.json`을 먼저 만들고,
  이 T-164 evaluator를 다음 step에서 실행한다.
