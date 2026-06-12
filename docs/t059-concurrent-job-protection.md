# T-059: CLI / Job 동시 실행 보호 표준화

## 상태

- 상태: 1차 구현 완료 (2026-05-29)
- 대상 브랜치: `codex/t059-concurrent-job-protection`
- 사용자 RFC: 2026-05-27 — "CLI 중 중복실행되면 안 되는 옵션인 경우 명시적으로 막을 것 (구현되어 있으면 생략)."

## 1차 구현 요약

- `src/kortravelgeo/infra/concurrency.py`를 추가해 `AdvisoryLockNamespace`, `AdvisoryLockKey`, `ConcurrentExecutionError(E0409/HTTP 409)`, `cross_process_lock()`을 표준 helper로 둔다.
- CLI 직접 실행 경로는 같은 helper를 사용해 중복 실행 시 exit code 2로 fail-fast한다.
- FastAPI `JobQueue` handler 등록도 같은 lock key를 공유하므로 CLI와 API job이 같은 자원을 동시에 만지면 두 번째 작업이 `E0409`로 실패한다.
- 실제 Docker PostgreSQL에서 같은 `MV_REFRESH` key를 두 connection으로 잡아 두 번째 lock이 `E0409/409`로 막히는 smoke를 확인했다.
- CLI 단독 실행을 `load_jobs` row로 노출하는 운영 가시화는 후속으로 남긴다. 이번 1차는 cross-process 실행 차단에 집중한다.

## 현황 인벤토리

본 task는 먼저 "이미 보호되는 경로"와 "보호되지 않는 경로"를 분리한다.

### 이미 보호되는 경로

| 경로 | 보호 메커니즘 | 비고 |
|------|---------------|------|
| in-process API job queue | `asyncio.Semaphore(1)` (ADR-006) | 같은 process 안에서만 직렬 |
| `load_jobs` row pickup | `pg_try_advisory_xact_lock` + `FOR UPDATE SKIP LOCKED` (ADR-011) | 다중 worker process여도 1개만 pickup |
| `TL_SPBD_BULD` staging table | session advisory lock (PR #42 follow-up) | 같은 staging table 동시 사용 차단 |
| `mv_geocode_target` swap | `SET LOCAL lock_timeout` + rename (T-035) | rename은 ACCESS EXCLUSIVE → 자동 직렬 |
| `ops.serving_releases` active | partial unique index (T-049) | DB constraint 강제 |
| `ops.maintenance_windows` active | application + DB | 위험 작업 차단 |

### 보호되지 않는 경로 (RFC 대상)

| 경로 | 위험 | 우선순위 |
|------|------|----------|
| `ktgctl init-db` 중복 실행 | DDL 중복 → 부분 실패 가능 | 중 |
| `ktgctl load all-sidos` 중복 실행 | 같은 batch가 두 process에서 동시 시작 | 높음 |
| `ktgctl load full-set` 중복 실행 | source set discover + plan + submit이 두 process | 높음 |
| `ktgctl load juso/locsum/navi/...` 단일 source 중복 실행 | 같은 table 동시 적재 → PK 충돌 가능 | 높음 |
| `ktgctl load daily-juso` 중복 실행 | 같은 ZIP을 두 번 → manifest 충돌 | 중 |
| `ktgctl refresh mv [--swap]` 중복 실행 | MV swap window 충돌 | 높음 |
| `ktgctl backup create` 중복 실행 | 같은 destination에 동시 dump | 높음 |
| `ktgctl restore create` 중복 실행 | 같은 target DB에 동시 복원 | 높음 |
| `ktgctl validate consistency` 중복 실행 | 같은 scope의 report가 두 개 동시 생성 | 낮음 |
| `ktgctl benchmark queries` 중복 실행 | DB 부하 ↑, 결과 신뢰성 ↓ | 낮음 |
| `ktgctl uploads cleanup` 중복 실행 | stale upload set 삭제 race | 중 |

`load_jobs` 영속 큐가 일부를 직렬화하지만, CLI는 큐를 거치지 않고 직접 loader를 호출하는 경우도 있어 cross-process 보호가 필요하다.

## 보호 메커니즘 표준 — PostgreSQL `pg_try_advisory_lock`

PostgreSQL advisory lock은 cross-process 보호에 적합하다.

- `pg_try_advisory_lock(key bigint)`: session-level. 같은 connection 유지 동안만.
- `pg_try_advisory_xact_lock(key bigint)`: transaction-level. 트랜잭션 commit/rollback 시 자동 해제.
- 두 connection이 같은 key를 lock하려 하면 두 번째는 `false` 반환 → fail-fast.

같은 DB에 연결하는 모든 process가 같은 key 영역을 공유한다.

### key 영역 표준화

`infra/concurrency.py`의 key 영역 enum:

```python
class AdvisoryLockNamespace(IntEnum):
    """advisory lock key namespace (high 32 bits)"""
    INIT_DB              = 0x4B47_0001  # 'KG' + 0001
    LOAD_FULL_BATCH      = 0x4B47_0010
    LOAD_FULL_SET        = 0x4B47_0011
    LOAD_JUSO_TEXT       = 0x4B47_0020
    LOAD_DAILY_JUSO      = 0x4B47_0021
    LOAD_LOCSUM          = 0x4B47_0022
    LOAD_NAVI            = 0x4B47_0023
    LOAD_PARCEL_LINK     = 0x4B47_0024
    LOAD_DAILY_PARCEL    = 0x4B47_0025
    LOAD_SHP_POLYGONS    = 0x4B47_0030
    LOAD_SHP_DELTA       = 0x4B47_0031
    LOAD_ROADADDR_ENTRANCES = 0x4B47_0040
    LOAD_SPPN_MAKAREA    = 0x4B47_0041
    LOAD_POBOX           = 0x4B47_0050
    LOAD_BULK            = 0x4B47_0051
    LOAD_EPOST           = 0x4B47_0052
    UPLOADS_CLEANUP      = 0x4B47_0053
    MV_REFRESH           = 0x4B47_0060
    BACKUP_CREATE        = 0x4B47_0070
    RESTORE_CREATE       = 0x4B47_0071
    HOT_SWAP             = 0x4B47_0072
    CONSISTENCY_RUN      = 0x4B47_0080
    BENCHMARK_QUERY      = 0x4B47_0090
```

high 32 bits = namespace, low 32 bits = resource ID(예: source path hash, target DB name hash). 충돌 없이 같은 namespace 안에서 여러 lock 가능.

`ops.table_stats_snapshots` capture는 PR #81에서 이미 `_OPS_TABLE_STATS_ADVISORY_LOCK = 0x4B47_00A0`와 transaction-level lock으로 분리 구현되어 있다. 이번 T-059의 session-level namespace enum에는 넣지 않아 "같은 lock 체계"처럼 오해하지 않게 한다.

### helper

```python
# infra/concurrency.py
@dataclass(frozen=True, slots=True)
class AdvisoryLockKey:
    namespace: AdvisoryLockNamespace
    resource_hash: int  # CRC32(resource_str) & 0xFFFFFFFF

    def as_int(self) -> int:
        return (self.namespace.value << 32) | self.resource_hash


@asynccontextmanager
async def cross_process_lock(
    engine: AsyncEngine,
    key: AdvisoryLockKey,
) -> AsyncIterator[None]:
    """PostgreSQL advisory lock으로 cross-process 직렬화.

    이미 같은 key를 다른 session이 잡고 있으면 즉시 ConcurrentExecutionError를 발생시킨다.
    """
    async with engine.connect() as conn:
        acquired = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": key.as_int()},
        )
        if not acquired:
            raise ConcurrentExecutionError(
                f"{key.namespace.name} (resource_hash={key.resource_hash:08x}) "
                f"is already running in another process. Wait for it to finish."
            )
        try:
            yield
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key.as_int()})
```

## CLI 적용 표준

CLI 명령 진입 시 advisory lock 획득:

```python
# cli/main.py
@load_app.command("juso")
def load_juso_command(path: Path, yyyymm: str | None = typer.Option(None)) -> None:
    async def run():
        async with AsyncAddressClient() as client:
            engine = client._engine()
            key = AdvisoryLockKey(
                namespace=AdvisoryLockNamespace.LOAD_JUSO_TEXT,
                resource_hash=zlib.crc32(str(path.resolve()).encode("utf-8")) & 0xFFFFFFFF,
            )
            try:
                async with cross_process_lock(engine, key):
                    await load_juso_hangul(engine, path, source_yyyymm=yyyymm)
            except ConcurrentExecutionError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=2)

    asyncio.run(run())
```

resource_hash로 path 별 분리:

- 같은 path 두 번 → 두 번째 fail-fast.
- 다른 path(예: 두 개의 다른 source set) → 동시 가능.

global lock(같은 namespace의 모든 resource 차단)이 필요한 경우:

- `MV_REFRESH`, `INIT_DB`, `HOT_SWAP` 등은 resource_hash=0 고정(`global`).
- 그 외(`LOAD_JUSO_TEXT` 같은 path 단위)는 path hash.

## API 적용 표준

`load_jobs` 큐를 거치는 경로는 이미 `FOR UPDATE SKIP LOCKED`로 보호된다. 다만 CLI 단독 호출과 API 호출이 같은 자원을 만지면 두 곳에서 advisory lock 충돌 가능. API handler도 같은 helper 사용:

```python
# api/_jobs.py
async def juso_load_handler(payload, cancel_event, progress):
    key = AdvisoryLockKey(
        namespace=AdvisoryLockNamespace.LOAD_JUSO_TEXT,
        resource_hash=zlib.crc32(payload["path"].encode("utf-8")) & 0xFFFFFFFF,
    )
    async with cross_process_lock(engine, key):
        result = await load_juso_hangul(engine, Path(payload["path"]), source_yyyymm=payload.get("source_yyyymm"))
        ...
```

CLI과 API의 lock key가 같으면 cross-process 보호 자연 작동.

## 에러 메시지 표준화

```python
class ConcurrentExecutionError(Exception):
    """동시 실행 차단 시 발생. CLI는 exit code 2, API는 HTTP 409 매핑."""
    code = "E0409"
    http_status = 409

    def __init__(self, namespace: str, resource_hash: int, running_since: datetime | None = None):
        self.namespace = namespace
        self.resource_hash = resource_hash
        self.running_since = running_since
        super().__init__(
            f"{namespace} (resource={resource_hash:08x}) is already running"
            + (f" since {running_since.isoformat()}" if running_since else "")
        )
```

API 응답:

```json
{
  "response": {
    "status": "ERROR",
    "errorCode": "E0409",
    "errorMessage": "LOAD_JUSO_TEXT is already running for resource a1b2c3d4",
    "hint": "기존 작업이 끝난 뒤 다시 시도하세요."
  }
}
```

HTTP 409 Conflict.

## 진행 중 job 표시

advisory lock만으로는 "지금 누가 잠그고 있는지" 정보가 없다. `load_jobs` 큐를 거치는 경로는 이미 `load_jobs(state='running')`에서 확인 가능. CLI 단독 실행은 `load_jobs`에 row를 만들지 않으므로 별도 가시화 필요.

옵션:

1. CLI 단독 실행도 `load_jobs(kind, payload)` row 생성(가시화 + audit). 같은 advisory lock 키로 cross-process 직렬화 + `load_jobs`로 진행 상태 노출.
2. `pg_locks` view 직접 조회(advisory lock holder process info).

권장: **1번**. 모든 운영 작업은 `load_jobs`에 등록되어 `/admin/load` UI에서 가시화. CLI는 큐를 거치지 않더라도 `load_jobs.kind='cli:load_juso_text'` 등으로 audit row 생성. 1차 구현에서는 아직 이 가시화 row를 만들지 않고 advisory lock fail-fast만 적용했다.

## 진행 순서

1. [완료] **인벤토리 확정**: 본 문서 "보호되는 경로 / 보호되지 않는 경로" 표를 실제 코드 grep으로 검증 + 갱신.
2. [완료] **`infra/concurrency.py` 신규**: `AdvisoryLockNamespace`, `AdvisoryLockKey`, `cross_process_lock`, `ConcurrentExecutionError`.
3. [완료] **단위 테스트**: key 직렬화, lock/unlock, busy fail-fast.
4. [완료] **CLI 적용**: 주요 `load *`, `refresh mv`, `validate consistency`, `uploads cleanup`, `backup create`, `restore create`에 advisory lock 적용.
5. [완료] **API handler 적용**: `JobQueue` 기본 handler 등록 시 같은 lock key를 획득.
6. [완료] **에러 코드 등록**: `ConcurrentExecutionError(E0409, HTTP 409)`를 도메인 오류로 둔다.
7. [완료] **queue 충돌 가시성**: API job handler가 lock 충돌을 만나면 `lock_conflict` progress event를 먼저 남긴 뒤 job을 `failed`로 닫는다.
8. [후속] **운영 가시성**: CLI 단독 실행도 `load_jobs` row 생성 + advisory lock과 연계.
9. [완료] **문서화**:
   - `docs/backend-package.md`에 cross-process protection 정책 섹션 추가.
   - `docs/api-reference/library/error-codes.md`에 `E0409` 항목.
   - `docs/operators/runbook.md`(향후)에 "동시 실행 차단 만났을 때 처리 절차".

## 검증

- 단위 테스트: `AdvisoryLockKey` 직렬화, `cross_process_lock` unlock, busy fail-fast, CLI/API handler source contract.
- `wait` 모드는 1차에서 사용하지 않아 제거했다. 모든 호출부는 fail-fast이며, 큐 worker를 오래 막지 않는다.
- smoke(WSL Docker PostGIS): 같은 `MV_REFRESH` key를 두 connection에서 획득 시도 → 두 번째 `ConcurrentExecutionError(E0409/409)`.
- targeted gate:
  - `ruff check src/kortravelgeo/infra/concurrency.py src/kortravelgeo/cli/main.py src/kortravelgeo/api/app.py tests/unit/test_concurrency.py tests/unit/test_api_app_contract.py`
  - `pytest tests/unit/test_api_app_contract.py tests/unit/test_concurrency.py -q` → `6 passed`
  - `pytest tests/unit/test_concurrency.py tests/unit/test_client_submit_load_batch.py tests/unit/test_backup_restore.py -q` → `23 passed`
  - `mypy --no-incremental src/kortravelgeo/infra/concurrency.py src/kortravelgeo/cli/main.py src/kortravelgeo/api/app.py`
- full backend gate:
  - `ruff check .`
  - `pytest -q` → `261 passed, 8 skipped`
  - `mypy --no-incremental src/kortravelgeo`
  - `lint-imports`
- 후속 통합 테스트 후보:
  - 두 CLI shell에서 같은 `load juso` 동시 실행 → 두 번째 fail-fast.
  - 한 CLI + 한 API 호출 동시 → 두 번째 fail-fast.
  - 다른 path 두 개 동시 → 모두 정상 실행.
  - lock holder가 ctrl+C로 종료 → connection close → advisory lock 자동 해제 → 다음 실행 가능.

## 운영 가이드

- 운영자가 "왜 fail-fast?" 보면 `ktgctl jobs running` 또는 `/admin/load`에서 진행 중 작업 확인 후 결정.
- API queue handler에서 lock 충돌이 나면 해당 job은 `failed`가 된다. 일반 loader 실패와 구분할 수 있게 `log_tail`에 `current_stage='lock_conflict'`, `message='E0409: ...'` progress event를 먼저 남긴다. 자동 재큐/재시도는 이번 1차 범위 밖이다.
- advisory lock은 connection이 살아 있는 동안만 유지. process kill -9 시 connection 종료 → lock 자동 해제.
- 단, connection이 LB/network 단절로 살아 있는 것처럼 보이고 실제로는 idle인 경우 lock이 stale될 수 있음. PostgreSQL `tcp_keepalives_*` 설정으로 detect.

## 남은 위험

- `pg_advisory_lock`의 key 공간 (bigint) 자체 충돌은 거의 없지만, namespace를 16-bit 안에 너무 많이 둘 경우 namespace 충돌 가능. 본 task에서는 32-bit namespace + 32-bit resource로 분리.
- 한 process가 같은 advisory lock을 nested로 호출 가능. session-level lock은 reentrant이므로 안전 — 다만 unlock 횟수가 lock 횟수와 일치해야 함.
- `pg_try_advisory_lock(bigint)` 외 `(int, int)` 시그니처도 있다. 본 task는 `bigint` 단일 인자 형태 사용.
- application engine이 connection pool을 사용하면 lock 해제 후 같은 connection이 풀로 돌아가도 lock이 풀려 있음(connection-level). 다만 connection이 풀에 있는 동안에도 lock이 살아 있을 경우 다른 caller가 같은 connection을 가져가면 unexpected behavior. helper에서 `lock + unlock`을 한 connection 안에서 명시적으로 처리(위 코드 그대로).
- 이번 1차는 동일 명령/동일 job kind + 동일 resource의 cross-process 중복 실행 차단을 우선한다. 예를 들어 full snapshot load와 daily delta처럼 서로 다른 namespace가 같은 물리 table을 쓸 수 있는 kind 간 경합은 `JobQueue` in-process 직렬화와 개별 loader의 staging/table lock에 의존하며, 필요하면 table 단위 공유 namespace를 후속으로 추가한다.

## 관련 ADR/Task

- ADR-006: single backend instance. 본 task는 cross-process로 확장.
- ADR-011: load_jobs advisory lock. 본 task는 같은 패턴을 CLI까지 일반화.
- T-037 staging advisory lock: 본 task의 선행 사례. 같은 helper로 통합 가능성 검토.
- T-058 hot-swap: HOT_SWAP namespace 활용.
- T-046 backup/restore: BACKUP_CREATE / RESTORE_CREATE namespace 활용.
- T-053: `/admin/load` UI에서 "지금 실행 중인 작업" + "lock 대기 작업" 시각화.
