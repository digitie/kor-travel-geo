# T-050 운영 hardening

T-050은 PR #34~#47 리뷰 audit에서 남긴 운영 안전성 후속 묶음이다. 범위가 넓으므로 한 PR에 모두 넣지 않고, 실패 시 되돌리기 쉬운 단위로 나눠 진행한다.

## 진행 순서

1. [완료] upload set cleanup TTL, 실행 중 job 참조 lock, grace period
2. [완료] backup/restore callback HMAC, retry/backoff, replay protection
3. backup/restore file/archive size 기반 sub-progress
4. full-load/MV/restore 완료 hook의 `ops.dataset_snapshots`/`ops.serving_releases` 자동 생성
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

## 남은 항목

다음 PR은 backup/restore file/archive size 기반 sub-progress를 우선 진행한다. 현재 `pg_dump`, `tar.zst`, checksum, `pg_restore`는 phase 추정 progress와 log line 기반 progress를 제공하지만, UI가 사용자가 체감할 수 있는 현재 byte 처리량과 archive 성장량을 보여 주려면 file size sampler와 job event payload 보강이 필요하다.
