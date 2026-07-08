# 백업/복원 오케스트레이션 검토 의견

> 본 문서는 리뷰용 의견 정리다. 아직 ADR이나 확정 아키텍처 결정이 아니다.
> 리뷰 후 별도 요청이 있을 때 ADR, 아키텍처 문서, 구현 task로 반영한다.

## 질문

backup/restore 구조를 Airflow 또는 Dagster 같은 오케스트레이터 기반으로 바꾸는 것이 좋은가?

구체적인 운영 기대는 다음이다.

- restore는 파일 업로드 또는 기존 artifact 선택 후 ETL 백그라운드 작업으로 실행한다.
- backup은 명령 또는 스케줄로 시작하고, 완료 후 다운로드 가능한 artifact를 만든다.
- 정기 백업, backup verify, restore drill, 외부 복사, 실패 알림을 스케줄로 다루고 싶다.
- 외부 dependency 추가 비용은 판단에서 제외하고, 안정성·유지보수성만 본다.

## 요약 의견

안정성·유지보수성 관점에서는 외부 오케스트레이터 도입 가치가 있다. 단, **상태 정본을
오케스트레이터로 옮기는 방식은 비추천**이다.

권장 방향은 다음이다.

- Airflow보다는 Dagster가 더 적합하다.
- Dagster는 실행기, 스케줄러, 관측 sidecar로 둔다.
- `load_jobs`, `ops.artifacts`, `ops.audit_events`, `ops.serving_releases`는 계속 정본으로 둔다.
- Admin UI/API는 사용자 진입점, 권한 판단, download token, typed confirmation, audit 기록을 계속 소유한다.
- Dagster는 schedule, retry, alert, restore drill, asset lineage 관측을 맡는다.

즉 “Dagster로 전면 이전”이 아니라 “기존 운영 계약을 유지한 Dagster sidecar 연동”이 가장 안정적이다.

## 현재 보존해야 할 계약

| 계약 | 현재 정본 | 유지 이유 |
|------|-----------|-----------|
| 작업 상태 | `load_jobs` | UI/API/SSE/CLI가 이미 `queued/running/done/failed/cancelled`, progress, stage, log tail을 본다 |
| 백업 artifact | `ops.artifacts` | archive 경로, checksum, retention, download token, callback 상태를 보유 |
| 감사 | `ops.audit_events` | UI/API/CLI/운영 작업의 compliance 기록 |
| 데이터셋 릴리스 | `ops.dataset_snapshots`, `ops.serving_releases` | restore, MV swap, rollback lineage를 설명 |
| 백업 실행 | `run_backup_job()` | path allowlist, `.part` rename, checksum, manifest, callback HMAC, secret redaction |
| 복원 실행 | `run_restore_job()` | 새 빈 DB guard, archive 검증, version guard, target cleanup, smoke/reconcile |
| hot-swap | ADR-036 경로 | maintenance window, typed confirmation, same-cluster rename, post-swap smoke, rollback |
| 정기 백업 due 판정 | `/v1/admin/backups/scheduled/run-due` | 중복 enqueue 방지, `BACKUP_SCHEDULE` advisory lock, retention class |

외부 오케스트레이터가 이 정본을 직접 대체하면 상태 머신이 둘로 갈라진다. 유지보수성은 좋아지지 않고,
실패 복구와 UI 설명이 어려워진다.

## Airflow와 Dagster 비교

Airflow는 DAG와 task 중심 오케스트레이션에 강하다. scheduler, Dag processor, API server, metadata
database를 중심으로 task dependency와 executor를 관리한다. 여러 시스템을 task 단위로 묶고 조직
표준 Airflow가 이미 있을 때는 좋은 선택이다.

Dagster는 asset, materialization, job, schedule, sensor 중심 모델이 강하다. `kor-travel-geo`의 운영
대상은 단순 task보다 지속 산출물이다.

- 원천 묶음: `source_set`
- 적재 결과: master table, geometry table, helper MV
- 조회면: `mv_geocode_target`, `mv_geocode_text_search`
- 운영 이력: `ops.dataset_snapshots`, `ops.serving_releases`
- 백업 결과: `db_backup` artifact

따라서 단독 운영 개선 목적이라면 Dagster가 더 자연스럽다. Airflow를 선택할 조건은 다음처럼 좁다.

- 이미 운영 표준 Airflow가 있고 새로운 오케스트레이터를 늘리지 않는 것이 더 안정적인 경우
- `kor-travel-geo` 외 여러 시스템의 작업을 같은 DAG에서 통합 관리해야 하는 경우
- task 중심 실행 이력만 필요하고 asset lineage는 중요하지 않은 경우

그 외에는 Dagster를 우선한다.

참고 문서:

- Apache Airflow Architecture Overview: <https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/overview.html>
- Dagster Assets: <https://docs.dagster.io/guides/build/assets>
- Dagster Asset Jobs: <https://docs.dagster.io/guides/build/jobs/asset-jobs>
- Dagster Schedules: <https://docs.dagster.io/guides/automate/schedules>
- Dagster Sensors: <https://docs.dagster.io/guides/automate/sensors>

## 목표 아키텍처

```
Admin UI
  │
  │ POST /v1/admin/backups
  │ POST /v1/admin/restores
  │ POST /v1/admin/backups/scheduled/run-due
  ▼
FastAPI Admin API
  │
  ├─ load_jobs              ← 실행 상태 정본
  ├─ ops.artifacts          ← 백업/복원 산출물 정본
  ├─ ops.audit_events       ← 감사 정본
  └─ ops.serving_releases   ← serving lineage 정본
        ▲
        │ observe / trigger
        │
Dagster sidecar
  ├─ schedules              ← 정기 백업, restore drill
  ├─ jobs                   ← verify/copy/alert, 운영 graph
  ├─ sensors                ← artifact/source-set/job 상태 감지
  └─ assets                 ← source set, MV, backup artifact, release 관측
```

Dagster는 기본적으로 Admin API를 호출한다. DB에 직접 쓰는 것은 피하고, 필요하면 read-only 조회만 허용한다.
특히 다음 작업은 반드시 기존 API/서비스 경로를 사용한다.

- 백업 생성
- 복원 생성
- job cancel
- backup verify
- artifact copy/delete
- restore hot-swap plan/execute
- maintenance window 생성/종료
- audit 기록

## 상태 모델

### `load_jobs`는 실행 정본이다

Dagster run은 외부 오케스트레이션의 실행 이력이다. UI와 API가 보여 주는 실제 작업 상태는 계속
`load_jobs`다.

필요한 경우 다음 메타데이터를 `load_jobs.payload` 또는 별도 컬럼으로 추가할 수 있다.

| 필드 | 용도 |
|------|------|
| `executor` | `api_in_process`, `dagster` 같은 실행 주체 구분 |
| `orchestrator` | `dagster` 또는 `airflow` |
| `orchestrator_run_id` | Dagster run id 또는 Airflow dag run id |
| `orchestrator_step_key` | 외부 step 식별자 |
| `lease_expires_at` | worker heartbeat 만료 판정 |

실제 worker 대체 전에는 `payload.x_orchestration`처럼 비정규화 metadata로 시작해도 충분하다. 다만
Dagster가 실제 장기 작업 실행자가 되면 컬럼화가 낫다.

### startup recovery 변경이 필요하다

현재 `JobQueue.recover_startup()`은 `state='running'` 작업을 process restart로 끊긴 작업으로 보고
`failed` 처리한다. Dagster worker가 작업을 실행 중인데 FastAPI만 재시작된 경우에는 이 가정이 틀린다.

Dagster-backed worker를 도입할 때는 다음 규칙이 필요하다.

- `executor='api_in_process'`인 running job: 기존처럼 API startup에서 `failed` 처리.
- `executor='dagster'`인 running job: `orchestrator_run_id`와 heartbeat/lease를 확인.
- Dagster run이 살아 있고 lease가 유효하면 `running` 유지.
- Dagster run이 terminal인데 `load_jobs`가 미반영이면 reconciler가 `done/failed/cancelled`로 수렴.
- lease가 만료되고 Dagster run도 찾을 수 없으면 `failed` 처리.

## 권장 단계

### 1단계: scheduled backup thin wrapper

가장 작은 도입은 기존 scheduled backup due-check를 Dagster schedule로 호출하는 것이다.

흐름:

1. Dagster schedule이 주기적으로 실행된다.
2. `POST /v1/admin/backups/scheduled/run-due`를 호출한다.
3. 응답이 `enqueued=false`이면 Dagster run은 skip/success로 끝난다.
4. 응답이 `enqueued=true`이면 `job_id`를 기록한다.
5. `/v1/admin/jobs/{job_id}` 또는 `/events`를 terminal state까지 관찰한다.
6. 완료 후 artifact id, archive sha256, display name, size를 Dagster materialization metadata로 기록한다.

이 단계에서는 기존 `JobQueue`가 실제 백업을 실행한다. Dagster는 cron 대체와 관측만 담당한다.

장점:

- `load_jobs`와 `ops.artifacts` 계약 변경 없음.
- 중복 enqueue 방지는 기존 `BACKUP_SCHEDULE` advisory lock에 맡김.
- 실패 알림과 실행 이력만 Dagster에서 얻을 수 있음.

### 2단계: backup verify, copy, restore drill graph

정기 백업 후 다음 작업을 Dagster job으로 연결한다.

```
run_due_backup
  └─ wait_backup_done
       ├─ verify_backup
       ├─ copy_backup_to_allowed_target
       ├─ restore_drill_to_throwaway_db
       └─ notify_result
```

각 step은 직접 파일/DB를 조작하지 않고 기존 API 또는 CLI 계약을 호출한다.

| Dagster step | 호출할 내부 계약 |
|--------------|------------------|
| `run_due_backup` | `POST /v1/admin/backups/scheduled/run-due` |
| `wait_backup_done` | `/v1/admin/jobs/{job_id}` 또는 `/events` |
| `verify_backup` | backup verify API/CLI |
| `copy_backup_to_allowed_target` | backup copy API |
| `restore_drill_to_throwaway_db` | `ktgctl backup restore-drill` 또는 후속 API |
| `notify_result` | 외부 알림. 민감값 제외 |

restore drill은 운영 DB를 바꾸지 않는다. throwaway DB를 만들고 복원한 뒤 reconcile/smoke를 실행하고
항상 정리한다.

### 3단계: asset graph 관측

Dagster asset으로 다음을 표현한다.

| Dagster asset | 내부 정본 |
|---------------|-----------|
| `source_set:<hash>` | `load_jobs.source_set`, `load_manifest.source_set` |
| `master_tables` | Postgres row count snapshot |
| `mv_geocode_target` | MV row count, refresh job id |
| `dataset_snapshot` | `ops.dataset_snapshots` |
| `serving_release` | `ops.serving_releases` |
| `db_backup_artifact` | `ops.artifacts(artifact_type='db_backup')` |
| `restore_drill_result` | restore drill JSON artifact |

Dagster metadata에는 정본 값을 복제하지 않고 식별자와 요약만 둔다.

- `job_id`
- `artifact_id`
- `snapshot_id`
- `serving_release_id`
- row count summary
- checksum prefix
- redacted storage URI

### 4단계: Dagster-backed worker

실제 장기 실행을 FastAPI in-process queue에서 Dagster worker로 옮기는 단계다. 이 단계는 별도 ADR과
마이그레이션이 필요하다.

필요한 변경:

- `load_jobs`에 `executor`, `orchestrator`, `orchestrator_run_id`, `lease_expires_at` 추가 검토
- `JobQueue.enqueue()`는 상태 row를 만들고 Dagster run을 launch하는 adapter로 변경
- `JobQueue.recover_startup()`은 executor별 recovery로 분리
- cancel endpoint는 Dagster run cancel과 `cancel_event` 등가 처리를 연결
- Dagster worker는 `run_backup_job`, `run_restore_job`, loader handler를 실행하되 기존 progress callback으로
  `load_jobs`를 갱신
- advisory lock은 기존 `cross_process_lock` helper를 계속 사용
- retry는 step 전체 자동 retry보다 내부 idempotency와 artifact `.part` cleanup을 우선

이 단계 전까지는 Dagster가 직접 `pg_dump`/`pg_restore`를 실행하지 않는 편이 안전하다.

## 작업별 권장 경계

### Backup

권장:

- Dagster가 `/v1/admin/backups` 또는 `/backups/scheduled/run-due`를 호출한다.
- 실제 `run_backup_job()`은 기존 서비스 경로에서 실행된다.
- 완료 artifact는 `ops.artifacts`에 기록되고 기존 download endpoint로 받는다.

비권장:

- Dagster op가 직접 `pg_dump`를 호출한다.
- Dagster가 `ops.artifacts` row를 직접 만든다.
- Dagster가 allowlist 밖 경로를 쓰거나 download token을 자체 발급한다.

### Restore

권장:

- UI/API가 upload set 또는 backup artifact를 등록한다.
- Dagster는 `POST /v1/admin/restores`를 호출하거나, 추후 Dagster-backed worker로 `run_restore_job()`을
  실행하더라도 `load_jobs` progress와 `ops.artifacts`를 갱신한다.
- 기본 restore는 새 빈 DB 대상이다.

비권장:

- Dagster가 임의 DB에 직접 `pg_restore`를 수행한다.
- restore 실패 cleanup을 Dagster task cleanup만으로 처리한다.
- `replace_current`를 schedule로 자동 실행한다.

### Hot-swap

Hot-swap은 자동 schedule 대상이 아니다. 반드시 수동 승인 흐름이어야 한다.

1. restore가 새 DB에 완료된다.
2. `hot-swap-plan`으로 current/restore DB, previous alias, typed confirmation을 확인한다.
3. active `restore` maintenance window를 만든다.
4. typed confirmation을 제출한다.
5. 기존 API/CLI 경로가 `ALTER DATABASE ... RENAME`과 post-swap smoke, rollback lineage를 기록한다.

Dagster는 이 흐름을 관찰하거나 수동 job 버튼으로 감쌀 수 있지만, confirmation 판단과 실행은 기존
API에 맡긴다.

### Full-load / MV refresh

`full_load_batch`는 외부 DAG에서 child task로 다시 쪼개지 않는다.

권장:

- Dagster가 `POST /v1/admin/loads`로 `full_load_batch` 하나를 enqueue한다.
- 기존 batch DAG가 source child, consistency gate, `mv_refresh(strategy='swap')` successor를 처리한다.
- Dagster는 root `load_batch_id`를 관찰한다.

비권장:

- Dagster가 `juso_text_load`, `locsum_load`, `navi_load`, `shp_polygons_load`를 독립 task로 병렬 실행한다.
- Dagster가 consistency report 없이 MV swap을 호출한다.

## 실패 처리

### Retry

대형 backup/restore는 blind retry에 취약하다. 실패 원인에 따라 retry 정책을 분리한다.

| 실패 | 자동 retry |
|------|------------|
| Admin API transient 502/503 | 가능. enqueue 전 단계만 |
| `/run-due` lock conflict | retry 불필요. 성공 skip으로 처리 가능 |
| disk space preflight 실패 | 금지. 공간 확보 필요 |
| checksum mismatch | 금지. artifact 손상 |
| `pg_restore` 중 schema/version mismatch | 금지. 운영자 판단 필요 |
| external copy transient | 제한 retry 가능 |
| 알림 webhook 실패 | retry 가능. 본 작업 성공 여부와 분리 |

Dagster retry는 같은 `job_id`를 재사용하는 방식이 아니라, 내부 API의 idempotent endpoint 또는 새로운
작업 생성 규칙을 따라야 한다.

### Cancel

취소 정본은 `load_jobs` cancel endpoint다.

- UI 취소: 기존 `/jobs/{job_id}/cancel`.
- Dagster run 취소: 같은 cancel endpoint를 호출하고, terminal state를 확인한다.
- cancel endpoint만 호출하고 Dagster run을 그대로 두거나, Dagster run만 취소하고 내부 job을 그대로 두는
상태를 만들면 안 된다.

### Reconcile

Dagster run과 `load_jobs`가 불일치할 수 있다. 주기적 reconciler가 필요하다.

| Dagster run | `load_jobs` | 처리 |
|-------------|-------------|------|
| success | running | artifact/release 정본 확인 후 done 수렴 |
| failed | running | error message 반영 후 failed 수렴 |
| cancelled | running | cancelled 수렴 |
| running 없음 | running + lease 만료 | failed 수렴 |
| running | failed | Dagster run cancel 또는 orphan 표시 |

## 보안과 권한

오케스트레이터에는 가능한 한 DB superuser DSN을 주지 않는다. 1~3단계에서는 Admin API service account만
사용한다.

원칙:

- secret은 Dagster code, run config, event log에 평문으로 남기지 않는다.
- callback secret, admin proxy secret, DB DSN은 기존 애플리케이션 설정 또는 별도 secret backend에 둔다.
- Dagster metadata에는 storage URI를 redaction하거나 allowlist root 기준 상대 경로만 남긴다.
- destructive restore, hot-swap, delete는 기존 maintenance window와 typed confirmation을 요구한다.
- Dagster UI의 재시도/취소 권한은 운영자 권한으로 본다. 일반 사용자용 Admin UI를 대체하지 않는다.

## 구현 체크리스트

리뷰 후 실제 반영한다면 다음 순서가 적절하다.

1. 이 의견을 ADR 후보로 승격할지 결정한다.
2. `KtgAdminApiResource`를 별도 orchestration package 또는 외부 repo에 둔다.
3. 첫 job은 `scheduled_backup_job` 하나로 시작한다.
4. `run-due` 응답과 `job_id` polling, terminal state 판정을 구현한다.
5. 완료 artifact metadata를 Dagster materialization으로 기록한다.
6. 실패 알림은 민감값 없이 `job_id`, `stage`, `error_code`, artifact id만 포함한다.
7. restore drill job을 추가하되 live serving DB를 바꾸지 않는다.
8. Dagster-backed worker 전환은 별도 ADR과 DB migration 전에는 하지 않는다.

## 결론

안정성·유지보수성 관점에서 외부 dependency 비용을 제외하면 Dagster 도입 가치는 있다. 하지만 안정성은
오케스트레이터 자체가 아니라 상태 정본을 하나로 유지하는 데서 나온다. 따라서 `load_jobs`와
`ops.artifacts`를 계속 정본으로 두고, Dagster는 schedule, orchestration, lineage 관측을 담당하는
sidecar로 도입한다.

현재 단계에서 문서에 반영할 결정은 아니다. 리뷰 후 확정되면 ADR과 아키텍처 문서에 다음을 반영한다.

- Dagster sidecar 연동 원칙
- `load_jobs`/`ops.artifacts` 정본 유지
- Airflow는 조직 표준이 있을 때의 대안으로 제한
- Dagster-backed worker 전환 시 필요한 별도 ADR/마이그레이션 조건
