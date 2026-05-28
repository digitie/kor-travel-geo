# T-050 운영 hardening

T-050은 PR #34~#47 리뷰 audit에서 남긴 운영 안전성 후속 묶음이다. 범위가 넓으므로 한 PR에 모두 넣지 않고, 실패 시 되돌리기 쉬운 단위로 나눠 진행한다.

## 진행 순서

1. [완료] upload set cleanup TTL, 실행 중 job 참조 lock, grace period
2. [완료] backup/restore callback HMAC, retry/backoff, replay protection
3. [완료] backup/restore file/archive size 기반 sub-progress
4. [완료] full-load/MV/restore 완료 hook의 `ops.dataset_snapshots`/`ops.serving_releases` 자동 생성
5. `ops.table_stats_snapshots` 주기 capture
6. destructive confirmation flow 통합
7. 실제 PostgreSQL FK/trigger/partial unique integration test

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
- byte message는 약 5초 간격으로 제한해 `log_tail`을 과도하게 늘리지 않는다.
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
- 새 active release를 만들기 전 기존 active release는 같은 transaction에서 `superseded`로 전환한다. active release partial unique index는 그대로 유지한다.
- snapshot에는 source set hash, git/alembic/PostgreSQL/PostGIS version, 주요 table/MV row count, consistency report id를 기록한다.
- release에는 `mv_geocode_target` definition+row-count 기반 `mv_hash`, consistency gate, 이전 release lineage, activation job id를 기록한다.
- active/pending release 생성은 `ops.audit_events`에 `serving_release.activate` 또는 `serving_release.candidate`로 남긴다.

restore 경로:

- `db_restore` 성공 후 현재 운영 DB의 ops metadata에 `state='validated'` dataset snapshot과 `state='pending'`, `release_kind='restore'` serving release 후보를 만든다.
- 기본 restore는 새 빈 DB에 복원하는 절차이므로, 이 시점에는 active release로 승격하지 않는다.
- pending restore release는 `target_database`, restore artifact id, 원본 backup manifest의 source set/row count/runtime 정보를 기록한다.
- restore artifact manifest에는 생성된 `snapshot_id`, `release_id`, `release_state`를 다시 연결한다.
- 실제 serving 전환과 rollback lineage 확정은 T-058 restore hot-swap에서 active maintenance window와 typed confirmation을 거쳐 수행한다.

### 4차 검증

- `tests/unit/test_ops_metadata.py`에서 repository hook, source set hash, active release supersede SQL, audit action, app/restore 연결점을 inspect 기반으로 고정한다.
- `tests/unit/test_backup_restore.py`, `tests/unit/test_infra_repo_sql.py`와 함께 기존 backup/restore·queue 계약이 유지되는지 확인한다.

## 남은 항목

다음 PR은 `ops.table_stats_snapshots` 주기 capture를 우선 진행한다. 4차에서 release hook이 snapshot id를 만들기 시작했으므로, 후속에서는 snapshot 전후의 table/MV/index size와 dead tuple 변화를 주기적으로 남기고 운영 UI가 최근 trend를 비교할 수 있게 한다.
