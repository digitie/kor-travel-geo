# T-126 phase ② 수용 후속

작성일: 2026-06-15
담당: Codex(Agent A)

## 배경

T-215는 phase ② 최종 검증 평가를 수행했지만 두 가지를 수용 완료로 닫지 않았다.

| 잔여 항목 | T-215 상태 | T-126 처리 방향 |
|-----------|------------|-----------------|
| REST c64 tail | pool `20/64`에서도 worst p95 `3631.900ms`로 T-214 기준 `534.031ms`보다 크게 악화 | 실행 환경을 artifact에 남기고 Python/uvicorn/pool/admission/metrics 영향을 분리 재측정 |
| C11~C17 optional run-validation | 현 serving match set에 보강 원천이 없어 7건 모두 `skipped` | optional source를 포함한 별도 `custom` match set을 만들고 RustFS verifier가 켜진 run-validation 실행 |

N150/Odroid 실제 장비 throughput은 이 작업 범위가 아니며 계속 T-063으로 남긴다.

## 이번 반영

1. `scripts/benchmark_api_latency.py`의 artifact schema를 `2`로 올리고 REST 서버 실행 조건을 `--server-profile KEY=VALUE`로 기록하게 했다. `--capture-prometheus`를 주면 `/metrics` raw 응답을 benchmark 전후 `prometheus-before.txt`, `prometheus-after.txt`로 저장한다.
2. `scripts/run_t126_acceptance_followup.py`를 추가했다. 이 runner는 optional 검증 원천을 RustFS/source registry에 등록하고, 현재 active 또는 지정한 base source match set에 optional 항목을 더한 `custom` match set을 만든 뒤 `run_consistency_validation()`을 실행한다. rebuild/promote는 하지 않는다.
3. C17 registry 입력을 `navi_full.match_jibun` 독립 category에서 `navi_full` category + `member_flag="navi_full.match_jibun"`로 정정했다. `tl_juso_parcel_link`는 업로드 원천이 아니라 active serving DB table이므로 `requires_active_table` metadata로만 남긴다.
4. run-validation 응답의 `validation_inputs.*.source_file_group_id`가 present/ok 입력에도 실제 group id를 싣도록 보정했다. 이전에는 실패 quarantine id만 채워 정상 입력이 `null`로 보일 수 있었다.
5. admin API 주석과 loader bridge 문구를 현재 구현에 맞췄다. `POST /v1/admin/source-match-sets/{id}/run-validation`은 현재 source archive presence/integrity gate만 실행하며, C11~C17 prototype `.metrics()`는 registry metric drift guard로 유지한다.

## Optional source plan

runner가 찾는 optional 원천은 `F:\dev\geodata\juso\unused\` 아래 보존된 파일을 기준으로 한다.

| category | 기준월 | 파일 수 | 경로 |
|----------|--------|--------:|------|
| `roadaddr_building_shape_bundle` | `202604` | 17 | `unused/도로명주소 건물 도형/202604/건물도형_전체분_<시도>.zip` |
| `detail_dong_shape_bundle` | `202604` | 17 | `unused/건물군 내 상세주소 동 도형/202604/건물군내동도형_전체분_<시도>.zip` |
| `detail_address_db_full` | `202604` | 1 | `unused/202604_상세주소DB_전체분.zip` |
| `national_point_grid_shape` | `202405` | 1 | `unused/국가지점번호도형_5월분.zip` |
| `national_point_grid_center` | `202405` | 1 | `unused/국가지점번호중심점_5월분.zip` |
| `civil_service_institution_map` | `202401` | 1 | `unused/민원행정기관전자지도_240124.zip` |
| `address_db_full` | `202605` | 1 | `unused/202605_주소DB_전체분.zip` |
| `building_db_full` | `202605` | 1 | `unused/202605_건물DB_전체분.zip` |

WSL ext4 테스트 미러에서 plan 모드를 실행해 8개 category, 40개 archive 경로가 모두 존재함을 확인했다.

```bash
python scripts/run_t126_acceptance_followup.py \
  --data-root data/juso \
  --output-dir artifacts/t126-followup-plan
```

실제 실행은 RustFS 설정과 대상 DB를 명시한 뒤 수행한다.

```bash
export KTG_PG_DSN='postgresql+psycopg://.../kor_travel_geo_t213_20260615_r3'
export KTG_RUSTFS_ENABLED=true
export KTG_RUSTFS_ENDPOINT_URL='http://127.0.0.1:12101'
export KTG_RUSTFS_BUCKET='kor-travel-geo'
export KTG_RUSTFS_PREFIX='kor-travel-geo/t126/<run-id>'
export KTG_RUSTFS_ACCESS_KEY='<secret>'
export KTG_RUSTFS_SECRET_KEY='<secret>'

python scripts/run_t126_acceptance_followup.py \
  --data-root data/juso \
  --output-dir artifacts/t126-followup-<run-id> \
  --execute
```

`--execute`는 다음 artifact를 남긴다.

| 파일 | 내용 |
|------|------|
| `source-plan.json` | optional source category와 입력 파일 목록 |
| `registered-optional-groups.json` | 재사용 또는 신규 등록한 source group id와 group hash |
| `c11-c17-run-validation.json` | `run_consistency_validation()` 결과 |
| `summary.json` | base/custom source match set, runnable/skipped/failed count |

## REST c64 재측정 기준

T-126 REST acceptance는 T-214와 같은 corpus 계열을 기준으로 판단한다.

| 항목 | 기준 |
|------|------|
| 기준 artifact | `F:\dev\geodata\t214-benchmark\20260615-r3\rest-api\` |
| 기준 corpus hash | T-214/T-215 공통 `3e832d...` |
| 기준 case count | 425 REST case |
| 기준 결과 | error 0, c64 worst p95 `534.031ms` |
| 수용 조건 | error 0, 같은 corpus와 c64에서 worst p95가 T-214 기준 `534.031ms` 이하 |
| noise band | `534.031ms` 초과 `600ms` 이하는 baseline-compatible 후보로만 기록하고, 최종 수용은 반복 측정 또는 원인 설명이 필요 |

재측정 명령은 실행 환경을 반드시 `--server-profile`에 남긴다.

```bash
python scripts/benchmark_api_latency.py \
  --base-url http://127.0.0.1:<api-port> \
  --corpus <t214-or-t215-corpus.json> \
  --output-dir artifacts/perf/t126-rest-<profile> \
  --iterations 2 \
  --warmup 1 \
  --concurrency 64 \
  --timeout-s 15 \
  --server-profile python=3.13.14 \
  --server-profile uvicorn_workers=1 \
  --server-profile uvicorn_loop=uvloop \
  --server-profile pg_pool=20/64 \
  --server-profile admission=disabled \
  --capture-prometheus
```

Python 3.14 재측정, uvicorn worker 수, DB pool/admission 조합은 같은 corpus hash와 case count로만 비교한다. `/metrics` snapshot은 API request duration, DB pool gauge, DB query duration이 REST c64 tail과 같이 움직이는지 확인하는 보조 증거다.

## 현재 실행 한계

이번 세션의 `.env`, 프로세스 환경, `data/rustfs/config.json`에는 RustFS 접속 설정이 없었다. 또한 `http://127.0.0.1:12501`, `:12514`, `:12518`의 API health endpoint가 모두 응답하지 않아 REST live benchmark도 실행하지 않았다.

따라서 이번 T-126 반영은 다음을 완료한 상태다.

- C11~C17 optional source run-validation을 재현 가능한 runner와 plan artifact로 준비
- C17 source category 모델 오류와 run-validation 응답 group id 누락 수정
- REST benchmark artifact에 서버 프로필과 Prometheus snapshot을 남길 수 있게 보강
- REST 수용 기준을 T-214 c64 worst p95 `534.031ms` 기준으로 재정의

남은 live acceptance는 `KTG_RUSTFS_*`와 API 서버가 준비된 세션에서 위 명령으로 실행한다.

## 검증

WSL ext4 테스트 미러 `~/dev/kor-travel-geo-codex-test`에서 확인했다.

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest \
  tests/unit/test_t206_consistency_registry.py \
  tests/unit/test_api_latency_benchmark.py -q

.venv/bin/python -m ruff check \
  scripts/benchmark_api_latency.py \
  scripts/run_t126_acceptance_followup.py \
  src/kortravelgeo/core/consistency_run_validation.py \
  src/kortravelgeo/infra/consistency_run_validation_service.py \
  src/kortravelgeo/core/consistency_registry_seed.py \
  src/kortravelgeo/api/routers/admin.py \
  src/kortravelgeo/loaders/consistency_run_validation.py \
  tests/unit/test_t206_consistency_registry.py \
  tests/unit/test_api_latency_benchmark.py

.venv/bin/python -m mypy src/kortravelgeo \
  scripts/benchmark_api_latency.py \
  scripts/run_t126_acceptance_followup.py

.venv/bin/lint-imports
```

결과는 focused unit `24 passed`, ruff 통과, mypy 통과, import-linter `Layered architecture KEPT`다.
