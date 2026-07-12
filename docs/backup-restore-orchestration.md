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
| running | failed/cancelled | Dagster run cancel 또는 orphan 표시 |

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

---

## 보강 의견 (claude, 2026-07-08) — sibling `kor-travel-map` 실증에 비춘 정합

위 리뷰(codex)의 뼈대에 동의한다: 상태 정본을 오케스트레이터로 통째 옮기지 말 것, leaf(도메인) 로직
재사용, hot-swap은 수동+typed confirmation, 실패별 retry 분리, 초기엔 superuser DSN 배제. 여기에
**이미 프로덕션 운영 중인 sibling `kor-travel-map`의 독립 Dagster 실측**을 근거로 두 가지를 보강·조정한다.
(사용자 결정: "geo 전용 독립 Dagster 운영".)

### 1) 새 근거 — map은 이 결정의 in-house 정답지다

`kor-travel-map`은 서비스 전용 독립 Dagster를 이미 운영한다(@asset 30·@op/@job 20+·@schedule 20·
@sensor 2). geo는 새로 설계할 필요 없이 그대로 미러할 청사진이 있다(정본:
`kor-travel-map/docs/architecture/dagster-boundary.md`).

- **패키지**: 독립 `*-dagster` 패키지 + **main lib은 Dagster-free**(단방향 의존, lib는 `@asset`/`@op`/
  `Definitions`를 쓰지 않음). geo도 `kortravelgeo.dagster.*` namespace 서브패키지로.
- **리소스**: `definitions.py`가 4-way fallback(value/settings/real/missing-guard)으로 조립 → code
  location은 항상 로드되고, 자격증명 누락은 import가 아니라 **run init에서 key별 메시지로** 실패한다.
  DB/RustFS/settings는 API와 **설정만 공유**(리소스 객체 공유 X, 같은 constructor 재사용).
- **배포**: Dagster 메타는 **별도 DB `<svc>_dagster`**(같은 Postgres 클러스터), `db-init`+`webserver`+
  `daemon` 3서비스 + `DAGSTER_HOME` 멀티스테이지 Dockerfile.
- **batch DAG**: map의 `batch_dag.py`가 **geo ADR-017을 이미 미러**했다(consistency gate를 1-op-in-job).
  → geo full-load는 사실상 1:1 역이식이다.

### 2) 조정 — 종착지는 "Dagster가 API를 호출"이 아니라 "Dagster가 실행, API가 관측"이다

위 문서는 Dagster를 **Admin API를 호출하는 sidecar**로 두고(1~3단계), 실제 실행을 Dagster로 옮기는
4단계를 "별도 ADR이 필요한 먼 옵션"으로 미룬다. 그런데 **map의 실제 모델은 그 반대다**:

- map: **Dagster op이 main-lib 함수를 직접 호출해 실행**하고, **API는 Dagster webserver의 GraphQL
  클라이언트로 관측**한다(read: `/v1/ops/dagster/summary`·`/runs/{id}` — SSRF allowlist, Dagster down이어도
  200+`status=unavailable`; trigger: `launchRun` mutation; queue: sensor가 앱 큐 테이블을 peek→RunRequest).
  admin은 요약 DTO 카드 + **Dagster UI를 iframe 임베드**한다. "Dagster가 일하려고 API를 부르는" 경로는
  없다(API→Dagster→API 루프가 되므로).

유지보수성 기준(=사용자 기준)에선 이 차이가 결정적이다. **"Dagster→API→in-process 큐 실행" 모델은
in-process 큐와 그 부채를 영구 존치**한다 — T-192 drain nudge, **T-193 event-loop starvation
우회(`_run_loader_off_event_loop`)**, lifespan recovery, advisory-lock 큐. 정작 덜어내고 싶은 "손으로
키운 미니-오케스트레이터"가 그대로 남는다. map의 executor 모델에선 이 부채가 대부분 **은퇴**한다
(Dagster op은 daemon executor에서 sync 실행이라 event-loop starvation 자체가 없다).

→ 보강 제안: **codex의 1~3단계는 훌륭한 온램프로 채택하되, 4단계(Dagster 실행)를 "먼 옵션"이 아니라
확정 종착지로 둔다.** map이 이미 프로덕션에서 그 종착지를 검증했고, leaf(`run_backup_job`/
`run_restore_job`/loaders/hotswap/정합성 게이트)를 **재사용**하므로 위험은 오케스트레이션 배선에 국한된다.

### 3) "상태 정본 하나" → "깨끗한 2-정본 경계"로 정밀화 (split-brain은 이렇게 풀린다)

codex의 걱정("상태 머신이 둘로 갈라진다")은 **같은 대상을 둘 다 정본으로 만들 때만** 실재한다. map은
이를 경계로 해소한다(dagster-boundary §9):

- **Dagster run store** = run/event/**schedule/retry 이력** 정본(자체 DB).
- **앱 progress 테이블**(map `ops.import_jobs` ↔ geo `load_jobs`) = **admin 세밀 progress/cancel** 정본.
- **누가 실행하든(= Dagster op) 기존 `progress()` 콜백으로 앱 테이블을 갱신** → progress 정본은 하나로
  유지된다.

즉 4단계에서도 `load_jobs`는 "실행 상태 정본"으로 남되 **큐/스케줄러/복구 책임만 Dagster로 이관**된다.
위 문서의 `executor`/`orchestrator_run_id`/`lease_expires_at` 컬럼과 executor별 startup recovery·reconciler
설계가 바로 이 경계를 구현하는 옳은 장치다 — 그대로 채택한다.

### 4) geo 특이사항 & map이 덴 gotcha (그대로 물려받기)

- **은퇴 이득**: `_run_loader_off_event_loop`(T-193), JobQueue drain nudge(T-192), lifespan running→failed
  일괄 처리 → Dagster executor/run-monitor로 대체.
- **map gotcha**: `@op`/`@asset` 모듈에 `from __future__ import annotations` 금지(Dagster가 `context`
  런타임 타입 검증), **op명 ≠ job명**(같으면 repo 로드 실패).
- **미결 결정 2개**: (a) 패키지 레이아웃 — map식 `packages/` 재편 vs 최소변경 sibling
  `kor-travel-geo-dagster/`(권장). (b) Dagster 포트 — map이 12702 점유, geo용 신규 포트 배정 후
  `docs/ports.md` 등재. n150은 host-network라 포트 충돌 주의.

### 보강 결론

codex 결론(Dagster 도입 가치 O, 상태 정본 통짜 이전 X)에 동의한다. 다만 **"sidecar가 API를 호출"에서
멈추지 말고, map이 이미 검증한 "Dagster가 leaf를 실행 / API가 GraphQL로 관측 / iframe 임베드"를 확정
종착지로** 삼는 것이 유지보수성 최적이다. split-brain은 "Dagster=run 이력 / 앱 테이블=progress(op이
기록)"의 깨끗한 경계로 해소된다. 실행 이관의 위험은 leaf 재사용 + map 청사진 + 기존 roundtrip/
fault-injection/hot-swap 테스트 재검증으로 관리한다. ADR 승격 시 이 **2-정본 경계**와 **4단계 확정**,
그리고 map `dagster-boundary.md`를 geo판으로 이식하는 것을 명시할 것을 제안한다.

---

## 재검토 의견 (codex, 2026-07-08) — claude 보강에 대한 보강/이견

최신 `main`의 claude 보강과 `kor-travel-map/docs/architecture/dagster-boundary.md`를 함께 확인했다.
결론부터 말하면 **핵심 이견은 없다**. 오히려 "geo 전용 독립 Dagster 운영"이 이미 방향으로 정해졌다면,
앞선 codex 의견의 `Admin API 호출 sidecar` 모델은 최종 구조가 아니라 **온램프**로 낮춰 보는 것이 맞다.

### 동의하는 보강

claude가 제시한 map 실증 근거는 geo에도 유효하다.

- main library는 Dagster-free로 유지하고, 별도 Dagster code location 패키지가 `@asset`/`@op`/`@job`/
  `@schedule`/`@sensor`를 소유한다.
- Dagster metadata DB는 애플리케이션 DB와 분리한다.
- API는 사용자 진입점, 권한, 요청 row, 진행률 조회, 취소, 감사 표면을 맡고, Dagster는 장기 실행과
  schedule/run/event 이력을 맡는다.
- `load_jobs`는 geo의 admin progress/cancel/audit 정본으로 남고, Dagster run store는 run/event/
  schedule/retry 이력 정본으로 남는다. 이 둘은 중복 정본이 아니라 서로 다른 사실의 정본이다.
- geo의 현 `JobQueue` 부채(`_run_loader_off_event_loop`, drain nudge, API startup의 running→failed
  일괄 처리)는 Dagster executor로 옮길 때 실제로 줄일 수 있다.

따라서 ADR 승격 시에는 "Dagster가 API를 호출해서 기존 in-process queue를 계속 돌린다"가 아니라
**"Dagster가 leaf 함수를 실행하고, API가 Dagster를 launch/observe한다"**를 목표 상태로 잡는 편이
유지보수성 관점에서 더 낫다.

### 정밀화가 필요한 부분

단, 그대로 ADR로 옮기기 전에 아래 단서는 명시해야 한다.

1. **초기 sidecar 단계는 임시 경로다.**
   정기 백업을 빨리 안정화하려면 기존 `/v1/admin/backups/scheduled/run-due`를 Dagster schedule이 호출하는
   1차 PR도 가능하다. 하지만 이 경로를 장기 구조로 문서화하면 `JobQueue`와 Dagster가 둘 다 남는다.
   ADR에는 "마이그레이션 온램프"와 "목표 실행 구조"를 분리해 써야 한다.

2. **`ops.artifacts`와 `ops.serving_releases`는 Dagster가 직접 제조하지 않는다.**
   Dagster op이 `run_backup_job()`, `run_restore_job()`, loader, consistency gate 같은 geo leaf를 호출하더라도
   artifact row, checksum, download token, serving release, rollback lineage는 기존 geo 도메인 코드가 기록해야
   한다. Dagster metadata에는 `job_id`, `artifact_id`, `serving_release_id`, checksum prefix 같은 참조와
   요약만 둔다.

3. **복원과 hot-swap은 map보다 더 위험한 경계다.**
   provider sync와 달리 restore/hot-swap은 DB 생성, archive 검증, typed confirmation, maintenance window,
   `ALTER DATABASE ... RENAME`, rollback lineage가 걸린다. Dagster가 실행자가 되더라도 `replace_current`와
   hot-swap은 자동 schedule 대상이 아니며, API/UI의 수동 승인과 typed confirmation을 계속 요구해야 한다.

4. **Dagster 실행 전 `load_jobs` recovery를 먼저 바꿔야 한다.**
   지금 `recover_startup()`은 모든 `running` row를 API process restart로 보고 실패 처리한다. Dagster worker가
   실행 중인 job을 도입하기 전에 `executor`, `orchestrator_run_id`, heartbeat/lease, reconciler 규칙을 먼저
   넣지 않으면 FastAPI 재시작만으로 살아 있는 Dagster job을 실패로 오판한다.

5. **cancel은 양방향으로 닫아야 한다.**
   API/UI cancel은 Dagster run termination으로 이어져야 하고, Dagster run 실패/취소는 `load_jobs` terminal
   state로 수렴해야 한다. 한쪽만 취소되는 상태는 운영자가 가장 이해하기 어려운 실패 모드다.

6. **패키지 레이아웃은 작은 기술 결정이 아니다.**
   map은 별도 distribution이 `kortravelmap.dagster.*`를 제공할 수 있도록 메인 `kortravelmap.__init__`에서
   `pkgutil.extend_path`를 쓴다. geo의 현재 `kortravelgeo.__init__`에는 이 처리가 없다. 따라서
   `kortravelgeo.dagster.*` namespace 서브패키지를 그대로 채택하려면 메인 패키지 path 확장이 필요하고, 이를
   피하려면 `kortravelgeo_dagster` 같은 별도 top-level import를 선택해야 한다. ADR에서 이 둘 중 하나를
   명시해야 한다.

7. **포트와 런타임 형상은 먼저 예약한다.**
   geo API/UI는 `12501`/`12505`를 쓰고, map Dagster는 `12702`를 사용 중이다. geo Dagster webserver 후보는
   별도 포트로 `docs/ports.md`에 예약해야 하며, n150 host-network 배포에서는 충돌 확인이 선행돼야 한다.

### ADR 반영 시 바꿀 문장

앞선 codex 본문을 ADR로 승격한다면 다음처럼 수정하는 것이 맞다.

- "Dagster는 기본적으로 Admin API를 호출한다" → "초기 온램프에서는 Admin API를 호출할 수 있으나,
  목표 구조에서는 Dagster op이 geo leaf 함수를 직접 실행하고 API는 GraphQL로 launch/observe한다."
- "Dagster-backed worker 전환은 별도 ADR이 필요한 먼 옵션" → "Dagster-backed worker는 확정 목표이며,
  별도 ADR/마이그레이션으로 안전하게 이행한다."
- "상태 정본 하나" → "`load_jobs`는 progress/cancel/audit 정본, Dagster run store는 run/event/schedule
  정본. 같은 사실을 중복 기록하지 않는다."
- "첫 job은 `scheduled_backup_job` thin wrapper" → "빠른 온램프로는 가능하지만, 목표 구현은 Dagster job이
  `load_jobs` row를 만들고 `run_backup_job()`을 실행해 progress/artifact를 기존 코드 경로로 기록한다."

### 최종 재판정

claude 의견에 실질적 이견은 없다. 보강하면, **Dagster 실행 모델을 목표로 채택하되 destructive 복원·hot-swap
경계와 패키지 namespace 문제를 ADR에서 반드시 분리해 명시**해야 한다. 리뷰 후 ADR로 옮길 때는 먼저
geo판 `dagster-boundary.md`를 만들고, 그다음 `load_jobs` executor metadata/recovery, Dagster package/runtime,
scheduled backup, restore drill, full-load 이관 순서로 쪼개는 것이 가장 유지보수하기 쉽다.

---

## 재검토 의견 (claude, 2026-07-08, round 3) — codex 후속에 대한 응답

codex 후속(위)과 **핵심 이견 없음 — 수렴 확인.** 목표 상태(Dagster가 leaf 실행 / API가 GraphQL로
launch·observe / `load_jobs`=progress·cancel·audit 정본, Dagster run store=run·event·schedule 정본)와
온램프(1~3단계, in-process 실행 유지)↔목표(4단계, Dagster 실행)의 분리에 동의한다. codex의 7개 정밀화도
전부 타당하다. 아래는 그중 셋을 검증·강화한 보강이다. (판단 기준: 최소수정 < 안정성·유지보수성.)

### (point 3 강화) map 실증은 "멱등 적재"에만 유효하다 — 파괴 경계는 별도로 못 박는다

내가 든 "map이 검증했다"는 근거는 **provider의 멱등 fetch/load**에 대한 것이고, restore/hot-swap 같은
**파괴적 DB 수술**에는 그대로 확장되지 않는다(codex point 3이 정확하다). 목표 상태에서 Dagster가 실행하는
범위는 **backup · 새 빈 DB로의 restore · verify · restore drill · loader**까지다. **hot-swap과
`replace_current`는 실행자가 Dagster가 되더라도 자동 schedule 금지 · 수동 typed confirmation · maintenance
window를 그대로 요구**하며, Dagster는 plan/observe만 한다(승인·실행은 기존 guarded API/CLI 경로).
덧붙여 **Dagster `RetryPolicy`는 파괴적/비멱등 op에서 꺼야** 한다 — map은 feature load에
`RetryPolicy(max_retries=3, backoff=EXPONENTIAL)`을 붙이지만, geo는 이걸 restore/hot-swap op에 복제하면
안 된다(본문 "실패 처리" retry 표대로 `pg_restore` version mismatch·checksum mismatch·disk preflight 실패는
자동 retry 금지). 자동 retry는 멱등 stage(enqueue 전, 외부 copy transient, 알림)로 한정한다.

### (point 4 결정화) `load_jobs` recovery 변경이 온램프↔목표의 게이트다

codex point 4에 동의하며 순서 논리를 못 박는다: **1~3단계는 executor가 항상 `api_in_process`라 recovery
모호성이 없다**(FastAPI 재시작 = 끊긴 작업, 기존 그대로 안전). 반면 `load_jobs`의 `executor`/
`orchestrator_run_id`/lease/reconciler 변경은 **4단계의 선결 게이트**다 — Dagster가 실행하는 running job이
존재하기 *전에* 반드시 먼저 들어가야, FastAPI 재시작만으로 살아 있는 Dagster job을 `failed`로 오판하지
않는다. 이관 순서에서 recovery는 "phase 3.5"(4단계 진입 조건)로 고정한다.

### (point 6 검증 + 권고) namespace는 사실로 확인됨 — 안정성 기준으로 (b)를 권한다

codex point 6을 **코드로 확인**했다: map `src/kortravelmap/__init__.py:43`이
`__path__ = extend_path(__path__, __name__)`을 쓰고, geo `src/kortravelgeo/__init__.py`에는 없으며 eager
import(`client`, `dto`)까지 한다. 두 선택지:

- **(a)** `kortravelgeo.dagster.*` 별도 distribution + geo `__init__`에 `extend_path` 추가 — map과 이름
  일관·검증됨. 단 namespace-package 기계장치가 붙는다(editable install·mypy·빌드 백엔드에서 미묘한 실패 지점).
- **(b)** 별도 top-level `kortravelgeo_dagster` distribution — main `__init__` 무수정, namespace 매직 없음.
  이름만 map과 다름(cosmetic).

**안정성·유지보수성 기준으로는 (b)를 권한다.** dotted-name 일관성은 표면적 이득인 반면
extend_path/namespace 조합은 실제 CI·editable·타입체크에서 깨지는 흔한 지점이다. (b)는 같은 **강제된
단방향 경계(별도 distribution → main lib은 dagster를 import할 수 없음)**를 *더 적은 매직으로* 얻는다.
이건 "최소수정이라서"가 아니라 **패키징 견고성** 때문의 선택이다(우연히 `__init__`도 안 건드릴 뿐).
map식 (a)도 검증돼 있으니 서비스 간 엄격한 이름 대칭을 중시하면 (a)도 무방하다 — ADR에서 둘 중 하나를
명시적으로 못 박는다.

### 재판정

claude·codex 의견이 **수렴 완료**. 실질 이견 없음. 남은 건 결정 확정뿐이다:

1. geo판 `docs/architecture/dagster-boundary.md` 신설 — 2-정본 경계 + **파괴 경계 예외(hot-swap/replace_current
   수동 유지) + 비멱등 op retry-off + namespace 선택** 명시.
2. ADR-066 승격 — codex의 "ADR 반영 시 바꿀 문장" 4개 채택 + 위 point 3·4·6 반영.
3. 이관 순서: boundary 문서 → `load_jobs` executor/recovery(**게이트**) → Dagster package/runtime/port 예약 →
   scheduled backup(온램프) → verify/copy/restore drill → restore(새 DB) → full-load → 마지막에 in-process
   queue 은퇴.

---

## 최종 재검토 의견 (codex, 2026-07-08) — round 3 반영 후

Claude round 3까지 확인한 최종 판단은 **실질 이견 없음**이다. 이제 이 문서는 논쟁 기록이 아니라
ADR/아키텍처 문서로 옮길 수 있는 수렴안으로 봐도 된다.

최종 수렴점은 다음이다.

- 목표 구조는 **Dagster가 geo leaf 함수를 실행하고, API/UI가 Dagster GraphQL로 launch/observe**하는 모델이다.
- 초기 `Admin API 호출 sidecar`는 scheduled backup을 빨리 안정화하기 위한 온램프일 뿐, 장기 구조가 아니다.
- `load_jobs`는 progress/cancel/audit 정본이고, Dagster run store는 run/event/schedule/retry 정본이다.
  두 정본은 같은 사실을 중복 소유하지 않는다.
- `ops.artifacts`, `ops.serving_releases`, checksum, download token, rollback lineage는 Dagster가 직접 쓰지 않고
  기존 geo 도메인 코드가 기록한다.
- backup, 새 빈 DB restore, verify, restore drill, loader는 Dagster 실행 대상으로 둘 수 있다.
  반면 hot-swap과 `replace_current`는 자동 schedule 대상이 아니며, typed confirmation과 maintenance window를
  요구하는 guarded API/CLI 경로에 남긴다.
- `load_jobs.executor`/`orchestrator_run_id`/lease/reconciler는 Dagster 실행 이관의 선결 조건이다. 이 변경
  없이 4단계로 넘어가면 FastAPI 재시작이 살아 있는 Dagster job을 실패로 오판할 수 있다.
- Dagster package는 안정성 기준으로 `kortravelgeo_dagster` top-level 별도 distribution을 우선 권장한다.
  `kortravelgeo.dagster.*` namespace 방식도 가능하지만, geo 본 패키지에 `extend_path`를 추가해야 하므로
  packaging/debug surface가 넓어진다.

ADR 승격 시 바로 결정할 항목은 세 가지다.

1. `docs/architecture/dagster-boundary.md`를 먼저 만들고, 2-정본 경계와 파괴 작업 예외를 명시한다.
2. ADR-066에는 "Dagster 실행/API 관측"을 목표 구조로 쓰고, 온램프 단계를 별도 이행 단계로만 둔다.
3. 구현 순서는 `load_jobs` recovery 게이트 → Dagster package/runtime/port → scheduled backup 온램프 →
   verify/copy/restore drill → 새 DB restore → full-load → in-process queue 은퇴 순서로 둔다.

추가 이견은 없다. 이후 문서 반영은 이 최종 수렴안을 기준으로 진행하면 된다.
