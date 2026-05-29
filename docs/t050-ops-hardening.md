# T-050 운영 hardening

T-050은 PR #34~#47 리뷰 audit에서 남긴 운영 안전성 후속 묶음이다. 범위가 넓으므로 한 PR에 모두 넣지 않고, 실패 시 되돌리기 쉬운 단위로 나눠 진행한다.

## 진행 순서

1. [완료] upload set cleanup TTL, 실행 중 job 참조 lock, grace period
2. [완료] backup/restore callback HMAC, retry/backoff, replay protection
3. [완료] backup/restore file/archive size 기반 sub-progress
4. [완료] full-load/MV/restore 완료 hook의 `ops.dataset_snapshots`/`ops.serving_releases` 자동 생성
5. [완료] `ops.table_stats_snapshots` 주기 capture
6. [완료] destructive confirmation flow 통합
7. [완료] 실제 PostgreSQL FK/trigger/partial unique integration test

## 1차: upload set cleanup

T-045 upload set은 `settings.loader_data_dir/uploads/<upload_set_id>/` 아래 JSON manifest와 실제 원천 파일을 함께 보관한다. 운영자가 업로드만 하고 적재를 시작하지 않거나, 업로드 실패·취소 후 파일이 남으면 디스크를 계속 차지한다.

1차 hardening은 cleanup cron이 부를 수 있는 CLI를 추가했다.

```bash
kraddr-geo uploads cleanup --dry-run
kraddr-geo uploads cleanup --ttl-days 30 --active-grace-minutes 360
```

정리 규칙:

- 기본 TTL은 `KRADDR_GEO_UPLOAD_SET_TTL_DAYS=30`이다.
- 기본 active grace는 `KRADDR_GEO_UPLOAD_SET_ACTIVE_GRACE_MINUTES=360`이다.
- `load_jobs.state IN ('queued','running')`인 payload에서 `upload_set_id` 또는 upload set 경로가 발견되면 해당 upload set은 삭제하지 않는다.
- `uploaded`, `cancelled`, `failed` 상태는 TTL이 지나면 삭제 후보가 된다.
- `created`, `uploading` 상태도 TTL이 지나야 삭제 후보가 되며, active grace 이전에는 삭제하지 않는다.
- manifest가 깨졌거나 없는 `upload_*` 디렉터리는 orphan으로 보고 TTL과 grace가 모두 지난 경우에만 삭제한다.
- `--dry-run`은 삭제 후보를 JSON으로 보여 주지만 실제 파일은 지우지 않는다.

T-059 cross-process advisory lock이 들어가기 전까지 cleanup cron은 full-load enqueue와 같은 시간대에 겹치지 않게 단독 스케줄로 둔다. 구현은 active job 참조를 한 번 스냅샷한 뒤 파일을 지우므로, 오래된 upload set을 cleanup하는 바로 그 순간에 새 job이 같은 set을 참조하는 좁은 TOCTOU 창은 T-059에서 `uploads cleanup`까지 advisory lock 대상에 포함해 닫는다.

### 1차 검증

- `tests/unit/test_source_set_plan.py`에서 TTL 삭제, active job 참조 보호, dry-run, payload/path 기반 upload set id 추출을 검증한다.
- `tests/unit/test_infra_repo_sql.py`에서 active 참조 조회가 queued/running job만 보는지 확인한다.
- `tests/unit/test_settings.py`에서 새 설정 기본값을 고정한다.

## 2차: backup/restore callback hardening

T-046 1차 callback은 terminal state에서 1회 전송만 시도했다. 2차 hardening은 callback 실패가 백업/복원 artifact의 성공 여부를 뒤집지 않는다는 원칙은 유지하되, 수신자가 전송의 진위와 재전송 여부를 판별할 수 있도록 payload와 기록을 보강했다.

설정:

```bash
KRADDR_GEO_BACKUP_CALLBACK_MAX_ATTEMPTS=3
KRADDR_GEO_BACKUP_CALLBACK_BACKOFF_MS=500
KRADDR_GEO_BACKUP_CALLBACK_SECRET=
```

- `KRADDR_GEO_BACKUP_CALLBACK_MAX_ATTEMPTS`는 1~10 범위이며 기본값은 3이다.
- `KRADDR_GEO_BACKUP_CALLBACK_BACKOFF_MS`는 첫 retry 전 대기 시간이며 기본값은 500ms다. retry 간격은 `backoff_ms * 2^(attempt-1)`로 증가한다.
- `KRADDR_GEO_BACKUP_CALLBACK_SECRET`이 있으면 callback HMAC 전용 secret으로 사용한다. 비어 있으면 download token secret 또는 DSN 기반 fallback secret을 재사용한다.

전송 계약:

- callback URL은 기존과 같이 `KRADDR_GEO_BACKUP_CALLBACK_ALLOWED_HOSTS` allowlist host만 허용한다.
- 각 attempt는 새 `callback_id`(`cb_<uuid>`)와 UTC timestamp를 가진다.
- JSON payload는 `sort_keys=True`, compact separator로 byte 직렬화한 뒤 전송한다.
- 서명 대상은 `timestamp + "." + callback_id + "." + body` byte sequence다.
- HTTP header는 `x-kraddr-geo-event`, `x-kraddr-geo-callback-id`, `x-kraddr-geo-timestamp`, `x-kraddr-geo-signature: sha256=<hex>`를 포함한다.
- 수신자는 timestamp 허용 window와 `callback_id` de-duplication을 적용해 replay를 거절할 수 있다. 이 저장소는 송신자이므로 수신자 저장소까지 대신 관리하지 않는다.
- retry 중복은 replay와 별도다. attempt 1을 수신자가 처리했지만 응답이 유실되면 attempt 2는 새 `callback_id`로 다시 전송된다. 수신자는 replay 방어에는 `(timestamp, callback_id)` window/de-duplication을 쓰고, 실제 업무 처리는 stable key인 `(artifact_id, event)`로 멱등 처리해야 한다.
- 외부 수신자가 서명을 검증해야 하는 운영에서는 `KRADDR_GEO_BACKUP_CALLBACK_SECRET`을 반드시 설정한다. 미설정이면 송신자는 내부 download-token secret 또는 `pg_dsn` 파생 secret으로 서명하지만, 외부 수신자는 그 값을 재현할 수 없어 검증 가능한 webhook 계약이 되지 않는다.
- 모든 retry가 실패해도 artifact state는 그대로 두고 `callback_state='failed'`만 기록한다.

기록:

- `ops.artifacts.callback_state`에는 최종 delivery 상태(`delivered` 또는 `failed`)가 남는다.
- `ops.artifacts.manifest.callback_delivery`에는 `state`, `attempts`, `callback_ids`, `last_error`, `recorded_at`을 저장한다.
- backup 성공, backup 실패, restore 성공, restore 실패 경로 모두 같은 기록 helper를 사용한다.

### 2차 검증

- `tests/unit/test_backup_restore.py`에서 callback body에 secret이 섞이지 않는지, HMAC header가 helper와 일치하는지 검증한다.
- 같은 테스트 파일에서 첫 attempt 실패 후 두 번째 attempt 성공 시 callback ID가 새로 발급되고 attempt 수가 기록되는지 검증한다.
- `tests/unit/test_settings.py`에서 retry/backoff/secret 기본값을 고정한다.

## 3차: backup/restore file/archive size 기반 sub-progress

T-046 1차 진행률은 phase와 subprocess verbose line count 중심이었다. 대용량 작업에서는 line이 오래 나오지 않는 구간이 있어 UI가 멈춘 것처럼 보일 수 있으므로, 3차 hardening에서는 파일 크기 sampler를 추가해 기존 `load_jobs.progress`, `current_stage`, `log_tail` 표면 안에서 byte 기반 보조 진행률을 제공한다.

보강된 구간:

- `dump`: `pg_dump -Fd` 실행 중 `dump` 디렉터리 크기를 주기적으로 샘플링해 `dump 디렉터리 <bytes>` 메시지를 남긴다.
- `dump checksum`: `manifest.json`과 dump 디렉터리 내부 파일 checksum 생성은 `0.65~0.70` 구간으로 분리하고, 처리 byte/전체 byte를 기록한다.
- `archive`: `tar.zst` 생성 전에 work directory 입력 크기를 계산하고, `.part` archive 파일 성장량을 입력 크기와 비교해 `archive 파일 <current>/<input>` 메시지를 남긴다.
- `checksum`: 최종 archive SHA256 계산 중 읽은 byte/전체 byte를 `checksum <current>/<total>` 메시지로 남긴다.
- `extract`: 복원 archive 해제 중 `extract` 디렉터리 성장량을 archive 크기와 함께 기록한다.
- `restore`: `pg_restore` 시작 메시지에 dump 디렉터리 총량을 포함한다. `pg_restore` 자체는 안정적인 byte progress를 제공하지 않으므로 기존 verbose line 기반 추정 progress를 유지한다.

구현 원칙:

- DB schema와 API DTO는 바꾸지 않는다. 기존 `progress`, `current_stage`, `log_tail`만 사용한다.
- byte message와 디렉터리 size sample은 약 5초 간격으로 제한해 `log_tail`과 파일시스템 `stat()` 부하를 과도하게 늘리지 않는다. `SizeProgressProbe`는 interval 안에서는 마지막 sample을 재사용하고, completion/report 경계에서만 강제 재샘플링을 쓴다.
- 디렉터리 크기는 파일이 생성·삭제되는 중에도 실패하지 않도록 `OSError`를 0 byte로 처리한다.
- `tar.zst` compressed output은 입력 크기와 1:1로 대응하지 않을 수 있으므로 "정확한 완료율"이 아니라 정체 여부를 보기 위한 sub-progress로 문서화한다.

### 3차 검증

- `tests/unit/test_backup_restore.py`에서 directory/file size 합산, byte formatter, size sample 기반 progress 계산을 고정한다.
- 기존 backup/restore callback과 command builder 단위 테스트를 함께 유지한다.

## 4차: dataset snapshot / serving release 자동 기록

T-049에서 `ops.dataset_snapshots`와 `ops.serving_releases` schema/API/UI 골격을 만들었지만, 실제 full-load/MV/restore 성공 지점과는 아직 연결되지 않았다. 4차 hardening은 성공한 운영 작업이 "어떤 데이터셋 상태를 serving으로 노출했는지"를 자동으로 남기도록 hook을 추가했다.

반영된 경로:

- `mv_refresh` handler 성공 후 `AdminRepository.record_mv_refresh_release()`를 호출한다.
- `full_load_batch`에서 자동 등록된 `mv_refresh`는 root payload의 `source_set`과 최신 consistency report gate를 읽어 `release_kind='full_load'` active release를 만든다.
- 단독 `kraddr-geo refresh mv` 또는 `/admin/maintenance/refresh-mv` 경로는 `release_kind='manual_rebuild'` active release를 만든다.
- full-load batch의 consistency gate `ERROR` 차단은 MV swap 이전에 `AdminRepository.ensure_load_batch_release_gate()`로 확인한다. swap 이후의 release 기록 hook은 gate를 다시 raise하지 않고 보고용 gate metadata를 release에 남긴다. 따라서 gate가 막는 경우에는 serving MV가 바뀌기 전 job이 실패한다.
- 새 active release를 만들기 전 기존 active release는 같은 transaction에서 `superseded`로 전환한다. active release partial unique index는 그대로 유지한다.
- snapshot에는 source set hash, git/alembic/PostgreSQL/PostGIS version, 주요 table/MV row count, consistency report id를 기록한다.
- release에는 `mv_geocode_target` definition+row-count 기반 `mv_hash`, consistency gate, 이전 release lineage, activation job id를 기록한다. `mv_geocode_target` row count는 snapshot row_counts 수집값을 재사용해 `mv_hash` 계산에서 같은 대형 MV를 두 번 count하지 않는다.
- active/pending release 생성은 `ops.audit_events`에 `serving_release.activate` 또는 `serving_release.candidate`로 남긴다.

MV refresh와 release ledger 기록은 서로 다른 transaction 경계다. `refresh_mv()`가 shadow swap 또는 concurrent refresh를 완료한 뒤 ledger 기록이 실패하면 serving MV는 이미 새 상태이고 job은 실패로 남을 수 있다. 이 경우 운영자는 job error와 `ops.serving_releases` 누락을 보고 수동 repair 또는 재실행해야 한다. 4차 구현은 gate 검사를 swap 전에 옮기고 `mv_hash` 중복 count를 제거해 이 창을 줄였지만, DDL swap과 운영 ledger를 하나의 긴 transaction으로 묶지는 않는다.

`manual_rebuild` release는 concurrent refresh도 포함한다. serving row 내용 또는 MV 정의가 바뀔 수 있는 refresh 실행을 운영 release lineage에 남기려는 의도다. 정기 concurrent refresh를 매우 자주 돌리는 환경에서는 release 보존 정책 또는 별도 retention을 후속으로 정한다.

restore 경로:

- `db_restore` 성공 후 현재 운영 DB의 ops metadata에 `state='validated'` dataset snapshot과 `state='pending'`, `release_kind='restore'` serving release 후보를 만든다.
- 기본 restore는 새 빈 DB에 복원하는 절차이므로, 이 시점에는 active release로 승격하지 않는다.
- pending restore release는 `target_database`, restore artifact id, 원본 backup manifest의 source set/row count/runtime 정보를 기록한다.
- restore artifact manifest에는 생성된 `snapshot_id`, `release_id`, `release_state`를 다시 연결한다.
- 실제 serving 전환과 rollback lineage 확정은 T-058 restore hot-swap에서 active maintenance window와 typed confirmation을 거쳐 수행한다.

### 4차 검증

- `tests/unit/test_ops_metadata.py`에서 repository hook, source set hash, active release supersede SQL, audit action, app/restore 연결점을 inspect 기반으로 고정한다.
- `tests/unit/test_backup_restore.py`, `tests/unit/test_infra_repo_sql.py`와 함께 기존 backup/restore·queue 계약이 유지되는지 확인한다.

## 5차: table stats 주기 capture

T-049 1차에서는 `/v1/admin/ops/table-stats/capture`를 눌러 수동으로 table/MV/index size snapshot을 만들 수 있었다. 5차 hardening은 API 프로세스 안에 opt-in 주기 capture를 추가해 운영자가 별도 cron wrapper를 만들지 않아도 같은 표면에 시계열을 쌓을 수 있게 했다.

설정:

```bash
KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES=0
KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_LIMIT=500
KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_ON_STARTUP=false
```

- `KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_INTERVAL_MINUTES=0`이면 비활성화된다. 기본값은 0으로 두어 개발 서버나 테스트 실행이 예기치 않은 DB write를 만들지 않게 한다.
- 1 이상의 값으로 설정하면 FastAPI lifespan에서 background task를 만들고, 지정한 분 간격마다 `AdminRepository.capture_table_stats_snapshots()`를 실행한다.
- `KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_ON_STARTUP=true`이면 서버 시작 직후 한 번 capture한 뒤 주기 loop로 들어간다. 기본값은 false라 첫 capture는 첫 interval 이후 수행된다.
- `KRADDR_GEO_OPS_TABLE_STATS_CAPTURE_LIMIT`는 한 번에 수집할 `pg_class` object 수이며 기본값은 500, 최대 2,000이다.
- 여러 API worker가 같은 interval로 깨어나는 경우를 대비해 capture transaction은 `pg_try_advisory_xact_lock(0x4B4700A0)`을 먼저 잡는다. 이미 다른 worker가 capture 중이면 해당 run은 빈 결과로 건너뛰어 중복 row 폭증을 막는다.

연결 규칙:

- 호출자가 `snapshot_id`를 명시하면 기존처럼 해당 dataset snapshot에 직접 연결한다.
- `snapshot_id`를 생략하면 현재 `ops.serving_releases.state='active'` row의 `snapshot_id`를 찾아 연결한다.
- active release가 없으면 기존과 같이 `snapshot_id=NULL`로 저장하되, `stats.snapshot_link='unlinked'`를 남긴다.
- 연결 방식은 `stats.snapshot_link`에 `explicit`, `active_serving_release`, `unlinked` 중 하나로 기록한다.

현재 구현은 exact row count를 늘리지 않는다. 대형 테이블에서 `count(*)`를 주기적으로 수행하면 운영 부하가 커질 수 있으므로, 이번 단계는 `pg_class`, `pg_namespace`, `pg_stat_user_tables`, `pg_total_relation_size()` 기반의 추정 row count/size/dead tuple 시계열을 만드는 데 집중한다. benchmark 전후 핵심 테이블 exact count나 artifact 연결은 T-047 performance report 연계 PR에서 별도 gate로 다룬다.

### 5차 검증

- `tests/unit/test_settings.py`에서 scheduler 설정 기본값을 고정한다.
- `tests/unit/test_ops_metadata.py`에서 active release snapshot 자동 연결, advisory lock, scheduler opt-in, 설정 limit 사용을 source contract로 고정한다.

## 6차: destructive confirmation flow 통합

T-049에서 `ops.maintenance_windows.confirmation_hash`를 만들었지만, 실제 위험 실행 경로는 일부가 자체 문자열 확인만 사용하고 있었다. 6차 hardening은 기존 `db_restore`의 `replace_current` 위험 경로를 maintenance window와 연결했다.

적용된 규칙:

- 기본 복원 모드 `new_database`는 기존처럼 현재 운영 DB와 다른 target DB만 허용하고, target DB가 비어 있는지 확인한다.
- `replace_current`는 target database 이름이 현재 설정의 DB 이름과 정확히 같아야 한다. 다른 target을 `replace_current`로 넘기면 빈 DB 확인을 우회할 수 있으므로 즉시 거절한다.
- `replace_current`는 `target_dsn`을 받지 않는다. 다른 host에 있는 같은 DB 이름을 현재 DB로 오인하지 않도록 `target_database`만 허용한다.
- `replace_current` 확인 문구는 `RESTORE <현재 DB 이름>`이다. 예: `RESTORE kraddr_geo`.
- 같은 확인 문구 hash를 가진 active `ops.maintenance_windows(kind='restore')` row가 있어야 한다. `starts_at <= now()`이고 `ends_at`이 없거나 아직 지나지 않은 window만 인정한다.
- 확인 문구 원문은 기존 정책대로 DB에 저장하지 않고 hash만 비교한다.

운영 절차 예:

```bash
# 1. 먼저 maintenance window를 만든다.
# confirmation: RESTORE kraddr_geo

# 2. 같은 confirmation으로 replace_current 복원을 등록한다.
POST /v1/admin/restores
{
  "artifact_id": "artifact-...",
  "target_database": "kraddr_geo",
  "mode": "replace_current",
  "confirmation": "RESTORE kraddr_geo"
}
```

이 PR은 위험 경로의 gate를 통합하는 단계이며, 실제 운영 DB alias 전환/hot-swap은 T-058에서 별도 절차로 구현한다. backup artifact 삭제, full reset, schema migration 같은 다른 destructive action도 같은 helper를 재사용할 수 있게 `AdminRepository.require_active_maintenance_window()`로 분리했다.

### 6차 검증

- `tests/unit/test_backup_restore.py`에서 `replace_current` target DB명과 확인 문구 검증을 고정한다.
- `tests/unit/test_ops_metadata.py`에서 active maintenance window 조회 조건과 restore job 연결점을 source contract로 고정한다.

## 7차: 실제 PostgreSQL 제약 통합 테스트

T-049/T-050의 운영 메타데이터는 단위 테스트에서 SQL 문자열과 repository 동작을 확인했지만, FK·trigger·partial unique index는 PostgreSQL catalog에 실제로 올라간 뒤에만 의미가 있다. 7차에서는 `KRADDR_GEO_TEST_PG_DSN`이 설정된 경우에만 실행되는 선택형 통합 테스트를 추가했다. 이 DSN은 `postgis`, `pg_trgm`, `unaccent`, `pg_stat_statements` extension package를 사용할 수 있는 disposable test DB를 가리켜야 한다.

```bash
KRADDR_GEO_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo_t050_ops_constraints \
  python -m pytest tests/integration/test_optional_real_postgres_ops_constraints.py -q
```

검증 항목:

- `ops.audit_events.job_id`가 `load_jobs(job_id)`를 `ON DELETE NO ACTION`으로 참조해, 감사 이벤트가 붙은 job 삭제가 실제 FK 오류로 막히는지 확인한다.
- `ops.audit_events_append_only()` trigger가 `UPDATE`와 `DELETE`를 모두 차단하는지 확인한다.
- `idx_ops_serving_releases_one_active` partial unique index가 `state='active'` release를 하나만 허용하는지 확인한다. 이미 active release가 있는 테스트 DB도 고려해 기존 row를 변경하지 않고 새 active insert 실패만 확인하며, `pending` release는 허용되는지 함께 본다.
- `ops.table_stats_snapshots.snapshot_id` FK가 없는 dataset snapshot 참조를 막고, 유효한 snapshot 참조는 저장되는지 확인한다.

테스트 데이터는 하나의 outer transaction 안에 넣고 마지막에 rollback한다. 실패 기대 케이스는 savepoint로 감싸므로, 실제 PostgreSQL 오류가 발생해도 같은 테스트 안에서 다음 제약을 계속 확인할 수 있다. DDL과 index 적용은 기존 선택형 PostgreSQL 테스트와 동일하게 `SCHEMA_SQL`/`INDEX_SQL`을 사용한다.

안전장치:

- DSN 대상 DB 이름이 `test`를 포함하거나 `kraddr_geo_t*`, `tmp_*` 형태가 아니면 skip한다. `SCHEMA_SQL`/`INDEX_SQL`은 idempotent지만 DDL은 commit되므로 운영 DB 오지정을 방지하기 위한 guard다.
- 필수 extension package가 없는 일반 PostgreSQL DB는 schema 적용 전에 skip한다.

### 7차 검증

- DSN 미설정 경로: `1 skipped`
- 실제 Docker PostgreSQL 별도 DB `kraddr_geo_t050_ops_constraints`: `1 passed`
- 테스트 완료 후 별도 DB는 삭제했다.

## 후속

T-050은 7차 실제 PostgreSQL 제약 통합 테스트까지 완료했다. 이후 운영 안전성 후속은 T-058 restore hot-swap, T-059 CLI/Job 동시 실행 보호 표준화 순서로 진행한다.
