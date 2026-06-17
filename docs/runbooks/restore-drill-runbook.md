# 복원 드릴 런북 (restore-drill, T-242)

> "복원 가능한가?"는 **복원을 해봐야** 알 수 있다. 이 런북은 운영 serving DB를 건드리지 않고
> 백업이 실제로 복원 가능한지 주기적으로 증명하는 절차를 고정한다. 개인 서버(낮은 HW 신뢰성)에서는
> 백업 파일이 멀쩡해 보여도 복원이 깨질 수 있으므로 **정기 드릴이 백업 정책의 핵심**이다.

## 무엇을 하나

`ktgctl backup restore-drill`은 1회 명령으로 다음을 완주한다.

1. throwaway DB `<base>_restoretest_<ts>`를 **새로 만든다**(현재 serving DB와 절대 같은 이름일 수 없게 가드).
2. 지정한 백업을 `new_database` 모드로 그 throwaway DB에 복원한다(`replace_current` 절대 사용 안 함).
3. 백업 manifest와 복원 결과를 대조(reconcile, T-233: ROW_COUNT 10종·MV 비어있음/parity·source_set 기준월)하고 smoke test(테이블 수·PostGIS 확장)를 돌린다.
4. **성공/실패와 무관하게 throwaway DB를 drop**하고 work_dir을 정리한다.
5. PASS/FAIL·소요시간·archive 크기를 담은 결과 artifact(JSON)를 출력하고, `--output`이 있으면 파일로 남긴다.
6. **FAIL이면 비0 exit**(reconcile 불일치/smoke 실패/복원 자체 실패) → cron/CI가 알림을 띄울 수 있다.

## 명령

```bash
# 최신 백업 artifact로 드릴 (결과를 파일로 남김)
ktgctl backup restore-drill --artifact-id <backup_artifact_id> \
  --output /mnt/f/dev/geodata/restore-drill/$(date -u +%Y%m%dT%H%M%SZ).json

# 로컬 archive 파일로 드릴
ktgctl backup restore-drill --archive-path /path/to/backup.tar.zst

# throwaway DB 이름 base를 직접 지정 (기본은 현재 serving DB 이름)
ktgctl backup restore-drill --artifact-id <id> --base-db kor_travel_geo --jobs 4
```

- `--artifact-id` 또는 `--archive-path` 중 **하나는 필수**. `--artifact-id`를 쓰면 manifest에서 reconcile 기댓값과 archive 크기를 가져온다.
- throwaway DB는 maintenance(`postgres`) 연결로 `CREATE DATABASE` 후 복원하고, 끝나면 `DROP DATABASE`로 정리한다.

## 결과 artifact

```json
{
  "status": "PASS",            // 또는 "FAIL"
  "temp_database": "kor_travel_geo_restoretest_20260616T120000Z",
  "duration_seconds": 83.4,
  "restored": true,
  "cleanup_ok": true,          // throwaway DB drop 성공 여부
  "reconcile_ok": true,        // null = manifest에 row_counts 없음(legacy)
  "smoke_ok": true,
  "archive_size_bytes": 87241216,
  "source_artifact_id": "…",
  "errors": []
}
```

- `status=FAIL`이면 `errors`에 원인(restore/smoke 메시지)이 담기고 CLI는 exit 1을 반환한다.
- `cleanup_ok=false`는 drop이 실패했다는 뜻이므로 **수동으로 `<temp_database>`를 정리**해야 한다(아래 점검 참고).

## 운영 주기 · 디스크 점검

- **주기**: 최소 백업 보존주기마다 1회(예: 주 1회) 외부 cron으로 실행한다. full-load/대규모 변경 직후에는 추가로 1회.
- **디스크**: throwaway DB는 serving DB와 같은 cluster·같은 디스크에 잠깐 **DB 1개 분량**을 더 쓴다. 드릴 전 여유 공간이
  `pg_database_size(serving) x 1.3` 이상인지 확인한다(백업 자체의 디스크 가드는 T-228). 여유가 부족하면 드릴을 미루거나 별도 cluster를 쓴다.
- **work_dir**: 복원 job이 `backup_temp_dir/restore_<id>/`에 archive를 풀므로, 같은 디스크에 archive 해제 크기만큼 임시 공간이 필요하다(job 종료 시 정리됨).

## 실패 알림

- cron wrapper에서 **exit code != 0**이면 알림(메일/웹훅)을 보낸다. `--output` JSON의 `status`/`errors`를 본문에 포함한다.
- `cleanup_ok=false`(throwaway DB 잔존): `psql -c "DROP DATABASE IF EXISTS \"<temp_database>\""`로 수동 정리하고, `<base>_restoretest_*` 패턴으로 누적 잔존이 없는지 주기적으로 확인한다.
- 반복 FAIL: 백업 무결성 온디맨드 검증(`ktgctl backup verify <id> --deep`, T-231)으로 archive 손상 여부를 먼저 가른 뒤, manifest 버전/PostGIS 호환(T-232/T-234)을 점검한다.

## 안전 가드 (설계상 보장)

- throwaway DB 이름이 현재 serving DB와 같으면 **거부**(`guard_drill_target`).
- 항상 `new_database` 모드 — `replace_current`(라이브 서빙 DB 교체)는 드릴에서 쓰지 않는다.
- 성공/실패/예외 어느 경로든 `finally`에서 throwaway DB drop을 시도한다(drop 실패는 결과를 가리지 않고 `cleanup_ok=false`로 보고).

## 연계

- 라이브 round-trip(backup→restore→reconcile) 통합 검증: **T-244**.
- 무결성 온디맨드 검증: **T-231**(`backup verify`). 복원 dry-run preflight: **T-232**. 버전 hard-fail: **T-234**.
- hot-swap(서빙 DB 교체) 실행: **T-241**(드릴과 달리 라이브 serving을 바꾸므로 maintenance window+typed confirmation 필요).
