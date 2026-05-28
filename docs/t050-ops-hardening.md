# T-050 운영 hardening

T-050은 PR #34~#47 리뷰 audit에서 남긴 운영 안전성 후속 묶음이다. 범위가 넓으므로 한 PR에 모두 넣지 않고, 실패 시 되돌리기 쉬운 단위로 나눠 진행한다.

## 진행 순서

1. upload set cleanup TTL, 실행 중 job 참조 lock, grace period
2. backup/restore callback HMAC, retry/backoff, replay protection
3. backup/restore file/archive size 기반 sub-progress
4. full-load/MV/restore 완료 hook의 `ops.dataset_snapshots`/`ops.serving_releases` 자동 생성
5. `ops.table_stats_snapshots` 주기 capture
6. destructive confirmation flow 통합
7. 실제 PostgreSQL FK/trigger/partial unique integration test

## 1차: upload set cleanup

T-045 upload set은 `settings.loader_data_dir/uploads/<upload_set_id>/` 아래 JSON manifest와 실제 원천 파일을 함께 보관한다. 운영자가 업로드만 하고 적재를 시작하지 않거나, 업로드 실패·취소 후 파일이 남으면 디스크를 계속 차지한다.

이번 1차 hardening은 cleanup cron이 부를 수 있는 CLI를 추가한다.

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

## 검증

- `tests/unit/test_source_set_plan.py`에서 TTL 삭제, active job 참조 보호, dry-run, payload/path 기반 upload set id 추출을 검증한다.
- `tests/unit/test_infra_repo_sql.py`에서 active 참조 조회가 queued/running job만 보는지 확인한다.
- `tests/unit/test_settings.py`에서 새 설정 기본값을 고정한다.

## 남은 항목

다음 PR은 backup/restore callback HMAC, retry/backoff, replay protection을 우선 진행한다. callback 실패는 artifact 자체 성공/실패와 독립적으로 추적해야 하며, retry attempt와 최종 상태가 `ops.artifacts.callback_state`에 남아야 한다.
