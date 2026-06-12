# T-058: 적재 완료 DB Restore Hot-Swap 패턴

## 상태

- 상태: 1차 구현 완료 (hot-swap plan/preflight API·CLI)
- 대상 브랜치: `codex/t058-restore-hot-swap`
- 관련 ADR: ADR-036, ADR-030(amend)
- 사용자 RFC: 2026-05-27 — "리스토어 시 핫스왑과 유사한 방식 → 반영되어 있으면 스킵."

## 현황 확인 (먼저 스킵 가능 여부 검토)

`docs/t046-db-backup-restore.md` 및 ADR-030(2026-05-27 기준)의 정책:

- "기본 모드는 새 빈 DB에 `pg_restore -Fd --jobs`로 복원한다."
- "복원은 archive를 풀어 `pg_restore -Fd --jobs <N>`로 새 빈 DB에 수행한다."
- "`replace_current`가 필요하면 T-046 기본 구현 밖의 위험 경로로 두고, maintenance mode와 명시 확인을 요구한다."
- T-050 6차에서 `replace_current` preflight는 현재 DB명 target, `RESTORE <현재 DB 이름>` typed confirmation, active `restore` maintenance window를 요구하도록 보강됐다.

→ 현재 명문화된 정책은 "**새 빈 DB 복원만 기본 지원**"이고, 운영 serving DB로의 즉시 전환(hot-swap)은 **별도 위험 경로**로만 언급되어 있으며 절차 자체는 미명문화 상태다.

**결론**: T-058은 스킵하지 않고 진행했다. 명문화되지 않은 hot-swap 패턴을 두 가지 옵션(DB rename / DSN switch)으로 비교했고, 1차 구현에서는 실제 rename 실행 전 운영자가 확인해야 하는 plan/preflight 표면을 API·CLI로 제공한다.

## 목적

운영 시나리오:

1. T-046으로 백업한 archive를 새 DB(`kor_travel_geo_restore_<timestamp>`)에 복원했다.
2. 복원 후 smoke/consistency/performance gate가 통과했다.
3. 이제 운영 serving DB(`kor_travel_geo`)를 복원본으로 즉시 교체하고 싶다.

이 과정에서 다음을 보장해야 한다:

- 운영 latency 영향 최소(가능하면 sub-second).
- 실패 시 rollback 가능.
- audit/snapshot/release 추적성.
- 동시 connection의 정상 transition (in-flight query 처리).

## 옵션 비교

### Option A — PostgreSQL `ALTER DATABASE ... RENAME TO`

```sql
-- 1. 모든 connection을 새 DB로 이동(또는 끊기)
SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
 WHERE datname IN ('kor_travel_geo', 'kor_travel_geo_restore_<ts>')
   AND pid <> pg_backend_pid();

-- 2. 운영 DB → 백업 alias로 rename
ALTER DATABASE kor_travel_geo RENAME TO kor_travel_geo_previous_<ts>;

-- 3. 복원본 → 운영 DB 이름으로 rename
ALTER DATABASE kor_travel_geo_restore_<ts> RENAME TO kor_travel_geo;
```

- 장점:
  - DSN 변경 불필요. application은 같은 connection string 유지.
  - rename은 metadata-only ALTER → 매우 빠름(<1초).
  - rollback: 반대 순서로 다시 rename.
- 단점:
  - 모든 connection을 한 번 끊어야 한다(rename은 `pg_terminate_backend` 또는 DB가 idle해야 함).
  - 같은 PostgreSQL cluster 안의 두 DB만 swap 가능. 다른 host 간 swap 불가.
  - 같은 DB 이름 충돌 windows가 짧지만 존재.

### Option B — Application DSN switch + connection pool drain

```text
1. 새 DSN(=복원본 DB)에 별도 connection pool 생성.
2. 새 pool로 smoke test(전체 endpoint 1회 호출).
3. application의 active DSN을 새 DSN으로 atomic switch(in-memory).
4. 기존 pool drain(in-flight query 완료 대기, 새 호출은 새 pool로).
5. 기존 pool close + 기존 DB 삭제(또는 alias retention).
```

- 장점:
  - cluster 경계를 넘는 swap 가능(다른 host간).
  - drain 패턴으로 in-flight query 손실 없음.
  - 새 pool 검증 후 switch — 안전성 ↑.
- 단점:
  - application code 변경 필요(DSN registry, drain 신호).
  - drain 시간 동안 두 connection pool 동시 보유 → 메모리 ×2.
  - rollback은 같은 패턴(다시 DSN switch). 빠르지만 application 협조 필요.

### Option C — pg_basebackup + logical replication cutover (out of scope)

streaming replication / logical slot으로 따라가게 한 뒤 cutover. 본 task scope 밖.

### 결정 sketch

본 task는 **Option A를 기본**으로 한다. 같은 cluster 안 single-host serving 가정에서 가장 단순하고 안전. Option B는 다른 host로의 fail-over 시나리오(향후 cluster 분리 시)를 위해 design만 남겨두고 구현은 별도 ADR/task에서.

ADR-030 amend로 본 결정을 반영한다(ADR-036에서 신규 결정 + ADR-030 결과 섹션 갱신).

## hot-swap 실행 절차 (Option A 기준)

### 사전 조건

- `ops.maintenance_windows`에 `kind='restore'`, `state='active'`, `confirmation_hash` 검증 완료.
- 복원본 DB가 같은 cluster 안에 존재(`kor_travel_geo_restore_<ts>`).
- 복원본 DB에서 smoke test + consistency check 통과(`load_consistency_reports.severity_max` ≠ `ERROR`).
- 복원본 DB에서 `mv_geocode_target` 존재 + ANALYZE 완료.

### 절차

```python
async def hot_swap_database(
    *,
    current_db: str = "kor_travel_geo",
    restore_db: str,
    previous_alias: str | None = None,
    audit_actor: str,
    confirmation_token: str,
) -> HotSwapResult:
    # 1. precondition checks
    require_active_maintenance_window(kind="restore", token=confirmation_token)
    require_smoke_passed(restore_db)
    require_consistency_passed(restore_db)
    require_same_cluster(current_db, restore_db)

    # 2. plan
    if previous_alias is None:
        previous_alias = f"{current_db}_previous_{utc_timestamp()}"

    # 3. record audit pre-swap
    pre_event = await record_audit_event(
        action="serving_release.hot_swap.started",
        outcome="started",
        payload={"from": current_db, "to": restore_db, "previous_alias": previous_alias},
    )

    # 4. drain + terminate
    await pg_admin_terminate_other_backends(current_db)
    await pg_admin_terminate_other_backends(restore_db)

    # 5. rename swap (within maintenance connection, NOT current_db or restore_db)
    async with maintenance_connection() as conn:
        await conn.execute(f'ALTER DATABASE "{current_db}" RENAME TO "{previous_alias}"')
        await conn.execute(f'ALTER DATABASE "{restore_db}" RENAME TO "{current_db}"')

    # 6. application connection pool refresh
    await engine_factory.refresh_engine()  # re-create engine with same DSN

    # 7. post-swap smoke
    await smoke_test_serving()

    # 8. record release row
    release = await record_serving_release(
        snapshot_id=...,
        release_kind="restore",
        previous_release_id=...,
        rollback_target_release_id=...,
        notes=f"hot-swap from {previous_alias} to {current_db}",
    )

    # 9. record audit post-swap
    await record_audit_event(
        action="serving_release.hot_swap.completed",
        outcome="succeeded",
        payload={"release_id": release.release_id, "previous_alias": previous_alias},
    )
    return HotSwapResult(release_id=release.release_id, previous_alias=previous_alias)
```

### maintenance connection

rename은 `current_db`와 `restore_db` 둘 다 sessions이 없어야 가능. 따라서 maintenance용 별도 DB(`postgres` 기본 DB 또는 `kor_travel_geo_admin`)에 연결한 connection에서 ALTER 실행. 같은 cluster의 다른 DB에 연결한 superuser session이 rename 수행.

### rollback

```python
async def rollback_hot_swap(release_id: UUID) -> HotSwapResult:
    release = await get_serving_release(release_id)
    if release.release_kind != "restore":
        raise InvalidRollbackError(...)
    previous_alias = release.notes_parsed.previous_alias  # e.g. kor_travel_geo_previous_20260527
    current_db = release.notes_parsed.from  # restored DB가 현재 운영 alias로 이동했음

    # current_db (e.g. kor_travel_geo) was renamed-to restore alias before
    # restore was renamed to current_db
    # rollback = swap them back

    swap_alias = f"{current_db}_swap_{utc_timestamp()}"
    async with maintenance_connection() as conn:
        await conn.execute(f'ALTER DATABASE "{current_db}" RENAME TO "{swap_alias}"')
        await conn.execute(f'ALTER DATABASE "{previous_alias}" RENAME TO "{current_db}"')

    # 새 release row (rollback)
    await record_serving_release(release_kind="rollback", rollback_target_release_id=release_id, ...)
```

`previous_alias` 보존 기간 동안만 rollback 가능. 보존 기간(예: 7일) 후 자동 삭제 또는 운영자 명시 삭제.

## 1차 구현 표면

### REST

```text
POST /v1/admin/restores/hot-swap-plan
{
  "restore_database": "kor_travel_geo_restore_20260529",
  "previous_alias_retention_days": 7,
  "maintenance_database": "postgres"
}
```

응답은 다음을 포함한다.

- `current_database`: 현재 `KTG_PG_DSN`의 DB 이름
- `restore_database`: rename 대상 복원본 DB
- `previous_alias`: 현재 DB를 보존할 alias
- `maintenance_database`: `ALTER DATABASE ... RENAME`을 실행할 maintenance 연결 DB (기본 `postgres`, managed/hardened cluster는 다른 DB 지정 가능)
- `typed_confirmation`: maintenance window 생성/실행 시 사용할 확인 문구 (`HOT_SWAP <current> FROM <restore>`)
- `rollback_confirmation`: alias 보존 기간 안에 수동 rollback할 때 사용할 확인 문구
- `can_execute`, `blockers`: 현재 cluster 안 DB 존재 여부와 alias 충돌 검증 결과
- `steps`, `sql`: 운영자가 리뷰할 절차와 SQL

실제 rename은 1차 API에서 자동 실행하지 않는다. `SCHEMA_SQL`/ops metadata가 어느 DB에 기록되는지, application worker별 engine refresh가 어떻게 전파되는지, 실패 시 자동 rollback 기준을 별도 검증해야 하기 때문이다. 대신 plan은 정확한 SQL과 typed confirmation을 제공해 운영자가 maintenance window를 열고 수동으로 수행하거나, 후속 실행 API에서 같은 계약을 재사용할 수 있게 한다.

후속 확장:

- 같은 maintenance window 안에서 hot-swap → smoke → (자동) rollback 시도 시퀀스.
- `/v1/admin/restores/{job_id}` 응답에 "hot-swap 가능 여부" 필드.
- `POST /v1/admin/restores/{job_id}/hot-swap`: plan과 같은 typed confirmation을 받아 실제 rename을 수행.
- `POST /v1/admin/serving-releases/{release_id}/rollback`: `previous_alias` 보존 기간 안 rollback 수행.

### CLI

```bash
ktgctl serving hot-swap-plan \
  --restore-db kor_travel_geo_restore_20260527_123456 \
  --previous-alias-retention-days 7 \
  --maintenance-db postgres
```

CLI는 REST와 같은 `RestoreHotSwapPlan` JSON을 출력한다. `typed_confirmation`을 그대로 사용해 `ops.maintenance_windows(kind='restore')`를 열고, `sql` 배열을 운영자가 실행 전 리뷰한다.

자동 `previous_alias`는 `datetime.now(UTC)`를 한 번만 고정해 DB 존재 확인과 반환 plan이 같은 alias를 보도록 한다. 현재 DB 이름이 긴 경우에는 `_previous_YYYYMMDD_HHMMSS` suffix를 보존하고 앞부분을 잘라 PostgreSQL 63자 제한 안에 맞춘다.

## audit / release / window 연계 (T-049)

- `ops.maintenance_windows(kind='restore', state='active')` 필요.
- `ops.audit_events`: `serving_release.hot_swap.started/succeeded/failed/rolled_back` 4종 outcome 기록.
- `ops.serving_releases`: 새 release row + `previous_release_id`(직전 active) + `rollback_target_release_id`(rollback 시 원본).
- active partial unique index가 active 1건 보장.

## 위험 시나리오

| 시나리오 | 영향 | 완화 |
|----------|------|------|
| 두 DB에 connection 잔존 | rename 실패 | `pg_terminate_backend` + 재시도 + timeout |
| rename 중간에 cluster 재시작 | 두 DB가 둘 다 `_previous_<ts>` 상태일 수도 | 운영자가 수동 점검 + audit log로 마지막 상태 추적 |
| application engine refresh 실패 | 새 serving DB 인식 불가 | rollback 또는 process 재시작 |
| smoke test 실패 | 잘못된 데이터가 serving | 자동 rollback (configurable) |
| `previous_alias` retention 종료 후 rollback 요청 | 불가 | 명시 에러 + `/v1/admin/serving-releases/{id}/rollback`이 미리 검증 |
| 다른 application(외부 BI tool 등)이 같은 DB 연결 | rename 시 연결 실패 | 미리 LB drain + DNS TTL 짧게 + 운영 공지 |

## 검증 기준

- 1차 구현 단위 테스트: `RestoreHotSwapPlan` DTO, typed confirmation, rollback confirmation, `previous_alias` naming, SQL command 순서, blocker 산출.
- 1차 구현 API/OpenAPI: `/v1/admin/restores/hot-swap-plan` schema export와 frontend type generation drift 없음.
- 후속 실행 통합 테스트: 대구광역시 부분 DB 적재 + T-046 backup + 새 DB 복원 + hot-swap + smoke + rollback. WSL Docker PostGIS에서 end-to-end.
- 후속 동시성: 두 hot-swap이 같은 maintenance window에서 동시 시작 시 두 번째는 fail-fast(active maintenance window와 advisory lock 조합).
- 후속 rollback round-trip: 같은 release pair에 대한 swap + rollback이 데이터/release lineage를 정확히 보존.

## 남은 위험

- 같은 cluster 가정. 다른 host 또는 cluster fail-over는 별도 ADR/task.
- application이 `engine_factory.refresh_engine()` 같은 hook을 갖고 있어야 한다. uvicorn 단일 process 가정 시 동작 검증 필요. multi-process(Gunicorn/Uvicorn workers) 환경에서는 worker별 refresh 신호 필요.
- `pg_terminate_backend`는 in-flight query를 강제 중단. 응답 실패가 호출자에게 노출되므로 LB drain + queue retry로 보완.
- 복원본 DB가 다른 PostgreSQL major version으로 생성됐다면 hot-swap 거절(major mismatch는 hard-fail).

## 관련 ADR/Task

- ADR-030: T-046 backup/restore. 본 task에서 amend(hot-swap 절차 명문화).
- ADR-033: maintenance_windows + audit_events 연계.
- ADR-036(예정): hot-swap 결정.
- T-046: 복원본 DB 준비 절차.
- T-049: ops.serving_releases / maintenance_windows / audit_events 인프라.
- T-050: callback HMAC/retry 등 운영 hardening (본 task와 함께 다룰 수 있음).
