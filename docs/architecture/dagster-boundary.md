# Dagster 경계 (geo) — 구현 정본

geo 백업/복원·적재 오케스트레이션을 서비스 전용 독립 Dagster(`kor-travel-geo-dagster`)로 운영할 때의
**경계·규약·구조 정본**이다. 결정 근거는 [ADR-066](../adr/066-geo-independent-dagster-orchestration.md),
단계·분해는 [dagster-migration-plan.md](../dagster-migration-plan.md), 수렴 리뷰는
[backup-restore-orchestration.md](../backup-restore-orchestration.md). 원 청사진은
`kor-travel-map/docs/architecture/dagster-boundary.md`(ADR-045)이며 본 문서는 그 geo 이식본이다.

## 1. 책임 경계 (무엇이 어디에)

| main lib `kortravelgeo` (Dagster-free) | `kortravelgeo_dagster` 패키지 | FastAPI API / UI |
|---|---|---|
| loader(`load_juso_hangul` 등), raw SQL repo | `@op`/`@job`/`@schedule`/`@sensor`/`Definitions` | 사용자 진입점, 권한, GeoIP/auth gate |
| `run_backup_job()`/`run_restore_job()`(leaf) | job/asset 이름·group·cron·dependency graph | download token, typed confirmation |
| hot-swap SQL(ADR-036), consistency gate | resource 정의(engine/rustfs/settings) | `load_jobs` progress/cancel 조회·표면 |
| `ops.artifacts`/`serving_releases` 기록 | retry policy, run-failure 알림 배선 | Dagster launch/observe(GraphQL 클라이언트) |
| dedup/정합성 규칙 | Dagster metadata(참조·요약만) | admin `/admin/dagster` 임베드 |

**단방향 의존**: `kortravelgeo_dagster.*` → `kortravelgeo`(main lib). main lib은 `dagster`를 import하지
않는다(`@asset`/`@op`/`Definitions`/`Config`/`RunConfig` 미사용). 이 규약 덕에 integration/unit 테스트는
Dagster 없이 돈다.

## 2. 패키지 레이아웃 (ADR-066 §6 — 별도 top-level distribution)

map은 `kortravelmap.__init__`의 `pkgutil.extend_path`로 `kortravelmap.dagster.*` namespace를 확장한다.
geo `kortravelgeo.__init__`은 eager import(client·dto)를 하는 일반 패키지라 namespace 확장은 취약하다.
따라서 **별도 top-level import root `kortravelgeo_dagster`**를 채택한다(namespace 매직 없음).

```
kor-travel-geo-dagster/            # 별도 설치 distribution (pyproject: kortravelgeo-dagster)
  pyproject.toml                   # [tool.dagster] module_name = "kortravelgeo_dagster.definitions"
                                   # deps: kortravelgeo==<pin>, dagster>=1.9,<2, dagster-webserver,
                                   #       dagster-postgres, boto3, httpx
  src/kortravelgeo_dagster/
    __init__.py
    definitions.py                 # 단일 module-level defs = Definitions(...) (code location entrypoint)
    resources.py                   # engine / rustfs / settings / admin API resource factory
    backup.py                      # @schedule/@job: scheduled_backup 온램프, 이후 db_backup/verify/copy/drill
    restore.py                     # @op/@job: db_restore(새 빈 DB), (hot-swap은 plan/observe만)
    loaders.py                     # @op: juso/locsum/navi/parcel_link/shp
    full_load.py                   # @op/@job: full_load_batch (main-lib batch_dag 호출)
    mv.py                          # @op/@job: mv_refresh
    schedules.py                   # @schedule (scheduled backup, restore drill)
    sensors.py                     # @sensor (queue peek), @run_failure_sensor (알림)
    py.typed
```

`definitions.py`는 도메인 모듈의 상수 리스트(JOBS/SCHEDULES/SENSORS/ASSETS)를 합쳐 하나의 `defs`로
노출한다. `dagster-webserver -m kortravelgeo_dagster.definitions`로 기동.

## 3. Resource (설정만 공유, 객체 공유 X)

API와 같은 인프라에 붙되 **리소스 객체가 아니라 `Settings`(env prefix `KTG_*`)와 main-lib constructor를
공유**한다. map의 4-way fallback을 따른다: `value` → `settings-value` → 실제 `@resource` → `missing-guard`.
code location은 **항상 로드**되고, 자격증명 누락은 import가 아니라 **run init에서 key별 메시지**로 실패한다.

| resource key | 구성 | 비고 |
|---|---|---|
| `client` | `make_async_engine(settings.pg_dsn)` → `AsyncAddressClient(engine, settings)` | teardown에서 engine dispose |
| `rustfs` | `build_s3_object_store(...)`(`KTG_RUSTFS_*`) | backup archive/artifact 저장 |
| `settings` | `Settings()`(`KTG_*`) | value/settings 리소스의 출처 |
| `failure_notifier` | 선택(webhook/None) | `@run_failure_sensor` 배선점, 민감값 제외 |

## 4. @op / @job / @asset 규약

- **@op + @job = 명령형·다단계 DB 작업(backup/restore/full-load/mv/loader).** op은
  `context: OpExecutionContext`를 받고, main-lib leaf 하나를 호출하고, `context.add_output_metadata(...)`로
  참조·요약을 남기고, 오류 시 `dagster.Failure`를 던진다. **leaf는 재작성하지 않고 그대로 호출**한다.
- **@asset = 관측용 지속 산출물(선택, 후속).** `source_set`/`mv_geocode_target`/`dataset_snapshot`/
  `serving_release`/`db_backup_artifact` lineage 표현. metadata에는 정본 값을 복제하지 않고 식별자·요약만.
- **full_load_batch**: DAG 로직(root/child, consistency gate, mv swap)은 main lib에 두고 Dagster는
  1-op-in-job으로 호출+metadata(map `batch_dag.py`와 동일; geo ADR-017 1:1).

### 파괴적 op 규칙 (ADR-066 §3·§4)

- `db_restore`는 **새 빈 DB 대상만** Dagster가 실행한다. **hot-swap / `replace_current`는 Dagster가
  실행하지 않는다** — plan/observe만 하고, 승인·실행은 기존 guarded API(typed confirmation + maintenance
  window, ADR-036)에 맡긴다. 자동 schedule 금지.
- **RetryPolicy는 파괴적/비멱등 op에서 끈다.** 자동 retry는 멱등 stage(enqueue 전·외부 copy transient·
  알림)만. `pg_restore` mismatch·checksum mismatch·disk preflight 실패는 자동 retry 금지.

## 5. Scheduling & Sensors

- `@schedule`: scheduled backup(cron, `execution_timezone="Asia/Seoul"`, 운영 enable 전 `STOPPED` 기본),
  restore drill. 외부 cron 의존 제거(T-239 대체). overdue는 schedule tick 이력 + 선택적 freshness로 관측.
- `@sensor`: (온램프) 앱 큐 테이블 peek → RunRequest(worker가 상태 전이 담당, "peek in sensor, mutate in
  worker"). `@run_failure_sensor`: 실패 시 `failure_notifier`로 `{job_id, run_id, stage, error_code}`
  전달(민감값 제외).

## 6. 상태 경계 (2-정본) & Recovery

- **Dagster run store**(별도 DB `kor_travel_geo_dagster`) = run/event/schedule/retry 이력 정본.
- **앱 `load_jobs`** = admin progress/cancel/audit 정본. Dagster op이 기존 `progress()` 콜백으로 갱신.
- `load_jobs` 신규 필드: `executor`(`api_in_process`|`dagster`), `orchestrator_run_id`, `lease_expires_at`.
- **recovery(선결 게이트)**: `executor='api_in_process'` running → 기존대로 startup에서 `failed`.
  `executor='dagster'` running → `orchestrator_run_id`/lease 확인 후 살아 있으면 유지, terminal이면
  reconciler가 수렴, lease 만료 + run 없음이면 `failed`.
- **cancel 양방향**: API cancel → Dagster run termination, Dagster 실패/취소 → `load_jobs` terminal.
  한쪽만 취소된 상태를 만들지 않는다.

## 7. API ↔ Dagster (GraphQL 클라이언트)

- **관측(read)**: API `/v1/ops/dagster/summary`·`/v1/ops/dagster/runs/{run_id}` — Dagster webserver에
  GraphQL POST 후 forbid-extra DTO로 정규화. **SSRF guard**(scheme http/https, host allowlist, `/graphql`
  경로), **Dagster down이어도 200 + `status=unavailable`**(UI가 outage 렌더).
- **트리거(write)**: API → Dagster 방향은 `launchRun` mutation(selector=jobName/repository/location,
  runConfigData=op config). Dagster → API 온램프(T-290f scheduled backup)는
  `KTG_DAGSTER_ADMIN_API_URL`의 admin API를 호출하고, 기존 admin proxy actor/role/secret header 경계를
  그대로 사용한다.
- API 설정 키(env prefix `KTG_`): `dagster_url`(기본 `http://127.0.0.1:<port>`), `dagster_graphql_url`,
  `dagster_allowed_hosts`, `dagster_request_timeout_seconds`, `dagster_repository_name`,
  `dagster_repository_location_name`(`kortravelgeo_dagster.definitions`), `dagster_admin_api_url`.

## 8. Admin UI 임베드

`/admin/dagster` 페이지: 요약 카드(repositories/assets/active·failed runs) + code locations(schedules/
sensors tick) + recent runs 테이블 + run detail(event log, cursor 페이지네이션) + **Dagster UI iframe
임베드**(`sandbox="allow-scripts allow-forms allow-popups allow-downloads"`). 요약 DTO는 at-a-glance,
iframe이 full 제어면. 기존 `/admin/backups`·`/admin/ops` progress는 `load_jobs`에서 계속 표시.

## 9. 저장소 & 배포

- Dagster 메타 = 별도 DB `kor_travel_geo_dagster`(같은 클러스터). `dagster.yaml` `storage.postgres` ←
  `KTG_DAGSTER_PG_URL`. `telemetry.enabled=false`.
- `docker-manager` compose 신규 서비스: `kor-travel-geo-dagster-db-init`(createdb 멱등) +
  `kor-travel-geo-dagster`(webserver, `-m kortravelgeo_dagster.definitions -h 0.0.0.0 -p <port>`) +
  `kor-travel-geo-dagster-daemon`(`dagster-daemon run -m ...`, 포트 없음). 멀티스테이지 Dockerfile +
  `DAGSTER_HOME`. 포트는 `docs/ports.md`에 신규 예약(map=12702). **n150 host-network 충돌 사전 확인.**

## 10. Gotcha (map 실측)

- `@op`/`@asset` 모듈에 **`from __future__ import annotations` 금지**(Dagster가 `context` 런타임 타입 검증).
- **op 이름 ≠ job 이름**(같으면 code location 로드 실패).
- resource는 init 시점에 key별 메시지로 실패(4-way fallback) — import는 항상 성공.
- 별도 distribution이라 main lib은 dagster를 import할 수 없음(경계가 패키징으로 강제됨) — 의도된 이득.
