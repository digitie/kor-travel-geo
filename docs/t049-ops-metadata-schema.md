# T-049: 운영 메타데이터·감사·릴리스 스키마 구현

## 범위

본 문서는 유지보수와 운영 관리를 위해 추가한 기능, 테이블, 스키마를 정리한다. T-049 구현 PR 기준으로 DDL, Alembic migration, DTO, API, UI, 테스트가 1차 반영됐다. T-045/T-046/T-047에서 생성될 source set, backup/restore artifact, performance report는 이 스키마에 이어서 연결한다.

## 구현 상태

2026-05-27 구현 기준:

- `sql/ddl/001_schema.sql`와 `src/kraddr/geo/infra/sql.py`에 `ops` 스키마와 6개 테이블을 추가했다.
- 기존 DB upgrade용 Alembic migration은 `alembic/versions/0006_t049_ops_metadata_schema.py`다.
- `ops.audit_events`는 `BEFORE UPDATE OR DELETE` trigger로 append-only를 강제한다.
- `ops.serving_releases`는 `idx_ops_serving_releases_one_active` partial unique index로 `state='active'` row를 한 건만 허용한다.
- `kraddr.geo.core.redaction`은 audit payload를 저장하기 전에 API key, DSN, password, token, callback secret, 주소 원문을 제거하거나 hash marker로 치환한다.
- `AsyncAddressClient`와 `/v1/admin/ops/*` API는 audit event, dataset snapshot, serving release, artifact, maintenance window, table stats snapshot 조회를 제공한다.
- `/v1/admin/ops/maintenance-windows`는 typed confirmation을 hash로 저장하고, `/end`는 같은 confirmation hash가 맞는 active/scheduled/ending window만 종료한다.
- `/v1/admin/ops/table-stats/capture`는 `pg_class`, `pg_namespace`, `pg_stat_user_tables`를 읽어 table/MV/index size와 추정 row count를 `ops.table_stats_snapshots`에 저장한다.
- `kraddr-geo-ui`에는 `/admin/ops` 화면을 추가했다. release, snapshot, artifact, audit event, maintenance window, table stats snapshot을 한 화면에서 조회하고 maintenance window 생성과 table stats capture를 실행할 수 있다.
- 테스트는 redaction, DTO validation, DDL/index/trigger 문자열, Alembic migration, API route contract, repository source contract를 포함한다.

T-050 4차 이후 연결된 지점:

- full-load batch가 등록한 MV shadow swap 성공 시 `ops.dataset_snapshots` row와 active `ops.serving_releases` row를 자동 생성한다.
- 단독 MV refresh는 `release_kind='manual_rebuild'` active release로 기록한다.
- restore 성공 시에는 serving 전환 전 단계의 `validated` snapshot과 `pending` restore release 후보를 자동 생성하고 restore artifact와 연결한다.

T-050 5차 이후 연결된 지점:

- `KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES`가 1 이상이면 API lifespan에서 `ops.table_stats_snapshots` 주기 capture task를 시작한다.
- 수동/주기 capture에서 `snapshot_id`를 생략하면 현재 active serving release의 `snapshot_id`에 자동 연결한다.
- active release가 없거나 명시 연결이 아닌 경우도 `stats.snapshot_link`에 연결 방식을 남겨 trend 해석 기준을 보존한다.
- 여러 API worker가 같은 주기로 capture를 실행해도 `pg_try_advisory_xact_lock(0x4B4700A0)`으로 동시 실행을 한 번만 통과시켜 중복 row를 줄인다.

아직 남은 연결점:

- daily delta 완료 후 `ops.dataset_snapshots` row를 자동 생성하는 흐름은 후속 delta refresh gate에서 보강한다.
- T-046 백업/복원 artifact는 `ops.artifacts(artifact_type='db_backup'|'db_restore_log')`에 저장하도록 구현한다.
- T-047 성능 리포트는 `ops.artifacts(artifact_type='perf_report')`와 `ops.table_stats_snapshots` capture 전후 차이로 연결한다.

## 문제 인식

현재 운영 메타데이터는 여러 곳에 흩어져 있다.

- `load_jobs`는 작업 상태와 `log_tail`을 담지만, "누가 어떤 관리 작업을 왜 실행했는가"를 append-only 감사 이벤트로 남기지는 않는다.
- `load_manifest`는 테이블 단위 watermark에는 충분하지만, "이 DB가 어떤 원천 묶음으로 검증되어 운영에 올라갔는가"를 하나의 데이터셋 스냅샷으로 설명하지 않는다.
- `load_consistency_reports`, T-047 성능 리포트, T-046 백업 파일은 서로 연결될 수 있지만, 공통 artifact registry가 없다.
- `mv_geocode_target` shadow swap은 빠르게 운영 view를 교체하지만, 어떤 snapshot이 현재 active serving release인지, rollback 기준 release가 무엇인지 영속적으로 설명하는 테이블이 없다.
- 복원, schema migration, full-load, MV swap 같은 위험 작업을 막거나 허용하는 maintenance window/lock 테이블이 없다.

이 상태에서는 기능이 늘어날수록 운영자는 로그와 PR 본문, artifact 파일명을 사람이 맞춰 보아야 한다. 장애 복구나 데이터 회귀 분석에서는 이 비용이 작지 않다.

## 목표

T-049의 목표는 운영자가 다음 질문에 DB만 보고 답할 수 있게 하는 것이다.

- 현재 운영 중인 데이터셋은 어떤 원천 파일과 기준월로 만들어졌는가?
- 해당 데이터셋은 어떤 정합성 리포트와 성능 리포트를 통과했는가?
- 어느 job이 어떤 artifact를 만들었고, 그 artifact의 checksum과 보존 정책은 무엇인가?
- 누가 CLI/API/UI에서 위험 작업을 실행했고, 어떤 confirmation과 maintenance window 아래에서 수행됐는가?
- 지금 active serving release는 무엇이며, 직전 release로 rollback할 수 있는가?
- 특정 시점의 table row count, DB size, index size, migration revision은 무엇이었는가?

## 신규 스키마

운영 메타데이터는 `ops` 스키마에 둔다.

```sql
CREATE SCHEMA IF NOT EXISTS ops;
```

원칙:

- `public`은 주소 원천·serving 객체를 중심으로 유지한다.
- `x_extension`은 PostGIS 보조 extension 격리 용도로만 유지한다.
- `ops`는 감사, 데이터셋 snapshot, serving release, artifact, maintenance lock, table stats 같은 운영 메타데이터만 가진다.
- 애플리케이션 SQL은 `search_path`에 기대지 않고 `ops.<table>`을 명시한다.
- T-046에서 계획한 `db_backup_artifacts`는 신규 구현 시 `ops.artifacts`의 `artifact_type='db_backup'`으로 수렴한다. 이미 별도 테이블이 생성된 배포가 있다면 compatibility view 또는 migration으로 흡수한다.

## 신규 테이블

### `ops.audit_events`

append-only 운영 감사 이벤트다. 주소 검색 요청 전체를 저장하는 목적이 아니라, 관리 작업과 위험 작업의 의사결정 흔적을 남기는 목적이다.

핵심 컬럼:

| 컬럼 | 의미 |
|------|------|
| `event_id` | UUID primary key |
| `occurred_at` | 이벤트 발생 시각 |
| `actor_type` | `system`, `cli`, `api`, `ui`, `scheduler` |
| `actor_id` | 인증이 없는 현재 UI에서는 nullable. 향후 SSO 도입 시 사용자/서비스 계정 |
| `client_ip_hash`, `user_agent_hash` | 평문 IP/UA 대신 salt hash |
| `request_id`, `trace_id` | API/로그 correlation |
| `action` | `full_load.submit`, `mv_refresh.swap`, `db_restore.confirm` 등 |
| `resource_type`, `resource_id` | 대상 job, snapshot, release, artifact |
| `job_id` | 관련 `load_jobs.job_id`. 감사 이벤트가 있으면 `load_jobs` row 삭제가 막히도록 FK는 `ON DELETE NO ACTION`이다. 감사 이력에서 job 연결을 조용히 NULL 처리하지 않는다. |
| `outcome` | `started`, `succeeded`, `failed`, `cancelled`, `denied` |
| `error_code` | 실패 시 표준 error code |
| `payload_redacted` | secret과 장문 주소를 제거한 JSON |
| `payload_hash` | 원본 payload canonical hash. 원본은 저장하지 않는다 |

보안 규칙:

- API key, DSN password, backup download token, callback secret은 절대 저장하지 않는다.
- 주소 문자열은 관리 작업 근거에 꼭 필요한 경우에도 일부 마스킹하거나 hash만 저장한다.
- `ops.audit_events.job_id`는 `ON DELETE SET NULL`을 쓰지 않는다. 오래된 `load_jobs`를 정리해야 하면 먼저 retention 정책에 따라 감사 이력을 archive하거나, 삭제가 아니라 상태/보존 등급을 바꾸는 방향을 검토한다.
- retention은 기본 180일 이상으로 두되, 운영 정책에 따라 월별 partition 또는 archive를 둔다.

### `ops.dataset_snapshots`

검증 가능한 데이터셋 상태를 하나의 row로 고정한다. full-load, 승인된 mixed source set, 일변동 적용 후 MV refresh, 복원 검증 완료 시점이 snapshot 후보다.

핵심 컬럼:

| 컬럼 | 의미 |
|------|------|
| `snapshot_id` | UUID primary key |
| `state` | `building`, `validated`, `rejected`, `released`, `retired` |
| `parent_snapshot_id` | 일변동/복원/rollback lineage |
| `source_set` | 원천별 기준월, 경로, checksum, 혼합 기준월 승인 정보 |
| `source_set_hash` | source set canonical hash |
| `git_commit`, `alembic_revision` | loader/API/schema code version |
| `postgres_version`, `postgis_version` | DB runtime |
| `row_counts` | 주요 테이블/MV row count JSON |
| `table_stats_artifact_id` | 상세 table stats artifact |
| `consistency_report_id` | 통과한 정합성 리포트 |
| `performance_artifact_id` | T-047 성능 리포트 |
| `backup_artifact_id` | T-046 백업 artifact |
| `created_by_job_id` | snapshot 생성 job |
| `created_at`, `validated_at` | 생성/검증 시각 |

규칙:

- `state='released'` snapshot만 active serving release 후보가 된다.
- 정합성 `ERROR`가 남아 있으면 기본적으로 `validated`로 승격하지 않는다. 운영자가 예외 승인하면 `audit_events`에 근거를 남겨야 한다.
- source set이 혼합 기준월이면 `source_set.mixed_yyyymm_acknowledged=true`와 confirmation 근거가 있어야 한다.

### `ops.serving_releases`

운영 조회가 어떤 snapshot을 기준으로 하고 있는지 기록한다. MV swap 자체는 PostgreSQL object rename으로 수행되지만, release table은 사람이 읽는 운영 이력을 제공한다.

핵심 컬럼:

| 컬럼 | 의미 |
|------|------|
| `release_id` | UUID primary key |
| `snapshot_id` | `ops.dataset_snapshots.snapshot_id` |
| `state` | `pending`, `active`, `superseded`, `rolled_back`, `failed` |
| `release_kind` | `full_load`, `daily_delta`, `restore`, `manual_rebuild`, `rollback` |
| `previous_release_id` | 직전 active release |
| `rollback_target_release_id` | rollback release인 경우 대상 |
| `mv_name`, `mv_hash` | 운영 MV 이름과 정의/row hash 요약 |
| `consistency_gate` | 정합성 gate 결과 JSON |
| `performance_gate` | 성능 gate 결과 JSON |
| `activated_by_job_id`, `activated_at` | 활성화 job/시각 |
| `notes` | 운영 메모 |

규칙:

- active release는 한 개만 허용한다. PostgreSQL에서는 partial unique index로 `state='active'` 1건을 강제한다.
- rollback은 새 release row를 만든다. 과거 row를 다시 active로 덮어쓰지 않는다.
- active release 변경은 반드시 `ops.audit_events`에 남긴다.

### `ops.artifacts`

백업 파일, 정합성 export, 성능 리포트, source inventory, schema diff, OpenAPI snapshot 같은 운영 산출물의 공통 registry다.

핵심 컬럼:

| 컬럼 | 의미 |
|------|------|
| `artifact_id` | UUID primary key |
| `artifact_type` | `db_backup`, `db_restore_log`, `consistency_report`, `data_quality_export`, `perf_report`, `source_inventory`, `schema_diff`, `openapi_snapshot` |
| `state` | `creating`, `available`, `failed`, `deleted`, `expired` |
| `storage_kind` | `local_file`, `s3`, `gcs`, `none` |
| `storage_uri` | 서버 내부 URI 또는 object key |
| `display_name` | UI 표시명 |
| `media_type`, `compression` | 파일 형식 |
| `size_bytes`, `sha256` | 무결성 검증 |
| `retention_class`, `expires_at` | 보존 정책 |
| `job_id`, `snapshot_id`, `release_id` | 관련 job/snapshot/release |
| `manifest` | artifact별 metadata |
| `download_token_hash` | UI 다운로드용 token hash |
| `callback_url`, `callback_state` | terminal callback |
| `created_at`, `finished_at` | 생성/완료 시각 |

규칙:

- 백업 artifact의 `manifest`에는 `pg_dump` format/jobs, PostgreSQL/PostGIS version, source set, row count, checksum을 넣는다.
- `storage_uri`는 내부 경로다. API 응답은 다운로드 endpoint와 token metadata만 노출한다.
- artifact 삭제는 row 삭제가 아니라 `state='deleted'`와 삭제 시각 기록을 우선한다.

### `ops.maintenance_windows`

위험 작업의 충돌을 막고, 운영자가 의도한 maintenance 상태를 API/CLI/UI가 같이 이해하게 하는 테이블이다.

핵심 컬럼:

| 컬럼 | 의미 |
|------|------|
| `window_id` | UUID primary key |
| `kind` | `full_load`, `restore`, `schema_migration`, `mv_refresh`, `read_only`, `exclusive` |
| `state` | `scheduled`, `active`, `ending`, `ended`, `cancelled`, `failed` |
| `starts_at`, `ends_at` | 계획 시간 |
| `actual_started_at`, `actual_ended_at` | 실제 시간 |
| `reason` | 운영자가 쓴 사유 |
| `requested_by`, `approved_by` | 현재는 nullable, 향후 SSO 연동 |
| `confirmation_hash` | typed confirmation hash |
| `blocks` | 차단할 job kind/API surface JSON |
| `created_by_job_id`, `closed_by_job_id` | 관련 job |

규칙:

- `db_restore`, 운영 DB 덮어쓰기, destructive reset, schema migration은 `active` maintenance window 없이는 실패한다.
- `full_load_batch`와 `mv_refresh`는 같은 DB에서 동시에 실행하지 않는다.
- UI는 maintenance window가 active면 상단 banner와 차단된 action 상태를 표시한다.

### `ops.table_stats_snapshots`

운영 데이터 크기와 bloat, index 비용을 시간축으로 추적한다. T-047 성능 튜닝, T-046 백업 크기 예측, T-027 full-load 회귀 판단에 쓰인다.

핵심 컬럼:

| 컬럼 | 의미 |
|------|------|
| `stats_id` | UUID primary key |
| `snapshot_id` | 관련 dataset snapshot |
| `captured_at` | 수집 시각 |
| `schema_name`, `object_name`, `object_kind` | table, materialized view, index 등 |
| `estimated_rows`, `exact_rows` | 추정/실측 row count |
| `total_bytes`, `table_bytes`, `index_bytes`, `toast_bytes` | 크기 |
| `dead_tuples`, `last_vacuum`, `last_analyze` | 통계 상태 |
| `stats` | 추가 JSON |

규칙:

- 전국 full-load, MV swap, backup, restore, performance benchmark 전후에 capture한다.
- `exact_rows`는 대형 테이블에서 비용이 크므로 모든 run에서 강제하지 않는다. `estimated_rows`와 표본/핵심 테이블 exact count를 섞는다.
- API 내장 scheduler는 기본 비활성이다. `KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES`를 1 이상으로 설정하면 분 단위 주기로 capture하며, `KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_ON_STARTUP=true`일 때만 서버 시작 직후 1회를 추가 수행한다.
- `snapshot_id` 미지정 capture는 현재 active serving release의 `snapshot_id`에 연결하고, 연결 방식은 `stats.snapshot_link`에 기록한다.

## API와 UI 범위

T-049 1차 구현 API:

- `GET /v1/admin/ops/snapshots`
- `GET /v1/admin/ops/releases`
- `POST /v1/admin/ops/releases/{release_id}/rollback-plan`
- `GET /v1/admin/ops/artifacts`
- `GET /v1/admin/ops/audit-events`
- `GET /v1/admin/ops/maintenance-windows`
- `POST /v1/admin/ops/maintenance-windows`
- `POST /v1/admin/ops/maintenance-windows/{window_id}/end`
- `GET /v1/admin/ops/table-stats`
- `POST /v1/admin/ops/table-stats/capture`

UI는 `/admin/ops` 또는 기존 `/admin/backups`, `/admin/load`, `/admin/consistency` 안의 탭으로 시작한다. 첫 구현은 다음을 보여 주면 충분하다.

- 현재 active release와 snapshot 요약
- 최근 full-load/daily/restore/mv_refresh 작업과 관련 audit event
- artifact 목록과 checksum/download 상태
- maintenance window 생성/종료
- 주요 table/MV row count와 size 추세

## 구현 순서와 남은 보강

1. 완료: Alembic migration으로 `ops` 스키마와 6개 테이블을 추가한다.
2. 완료: 공통 redaction/hash helper를 만든다. secret, DSN, token, 주소 원문 저장 방지 테스트를 먼저 작성한다.
3. 부분 완료: `load.submit`, `mv_refresh.submit`, `load.cancel`, `consistency_check.submit`, maintenance window 생성/종료, rollback plan 조회는 audit event를 남긴다. T-050 4차에서 serving release activate/candidate audit을 추가했다. source set plan 확정과 backup artifact 세부 audit은 후속으로 연결한다.
4. 완료: `/v1/admin/ops/table-stats/capture`로 `ops.table_stats_snapshots`를 생성할 수 있고, opt-in scheduler가 같은 capture 경로를 주기 실행한다. full-load MV swap과 restore는 자동 dataset snapshot으로 연결했고, daily delta snapshot은 후속 delta refresh gate에서 연결한다.
5. 완료: MV swap 성공 시 `ops.serving_releases` active row를 교체한다.
6. 대기: T-046 백업 artifact와 T-047 성능 리포트를 `ops.artifacts`로 연결한다.
7. 완료: REST/AsyncAddressClient DTO와 관리 UI를 추가한다.

## 검증 기준

- migration idempotency: 빈 DB와 기존 개발 DB 양쪽에서 upgrade가 성공해야 한다.
- 감사 이벤트 redaction: secret, DSN password, API key, download token이 저장되지 않아야 한다.
- active release 유일성: 동시에 두 active release가 생기지 않아야 한다.
- restore/full-load/migration 같은 위험 작업은 maintenance window 없이 실행되지 않아야 한다.
- snapshot row count와 실제 핵심 테이블 count가 smoke 검증에서 일치해야 한다.
- artifact checksum mismatch는 download/restore를 차단해야 한다.
- UI와 API는 인증이 없는 내부망 전제를 유지하되, actor field가 미래 인증 도입을 막지 않아야 한다.
