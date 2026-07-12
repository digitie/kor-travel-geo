from __future__ import annotations

import inspect

import pytest

from kortravelgeo.cli import main as cli_main
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)


class _FakeConnection:
    def __init__(self, *, acquired: bool) -> None:
        self.acquired = acquired
        self.calls: list[str] = []
        self.commits = 0

    async def scalar(self, statement: object, params: object) -> bool:
        self.calls.append(str(statement))
        if "pg_try_advisory_lock" in str(statement):
            return self.acquired
        return True

    async def execute(self, statement: object, params: object) -> None:
        self.calls.append(str(statement))
        _ = params

    async def commit(self) -> None:
        self.commits += 1


class _FakeConnectContext:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn

    async def __aenter__(self) -> _FakeConnection:
        return self.conn

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = (exc_type, exc, tb)


class _FakeEngine:
    def __init__(self, conn: _FakeConnection) -> None:
        self.conn = conn

    def connect(self) -> _FakeConnectContext:
        return _FakeConnectContext(self.conn)


def test_advisory_lock_key_uses_namespace_and_resource_hash() -> None:
    key = AdvisoryLockKey.for_resource(AdvisoryLockNamespace.LOAD_JUSO_TEXT, "/data/juso.txt")

    assert key.as_int() >> 32 == AdvisoryLockNamespace.LOAD_JUSO_TEXT
    assert key.resource_hash != 0
    assert key.label().startswith("LOAD_JUSO_TEXT:")
    assert AdvisoryLockKey.global_key(AdvisoryLockNamespace.MV_REFRESH).resource_hash == 0


@pytest.mark.asyncio
async def test_cross_process_lock_unlocks_after_success() -> None:
    conn = _FakeConnection(acquired=True)

    async with cross_process_lock(
        _FakeEngine(conn),  # type: ignore[arg-type]
        AdvisoryLockKey.global_key(AdvisoryLockNamespace.MV_REFRESH),
    ):
        pass

    assert any("pg_try_advisory_lock" in call for call in conn.calls)
    assert any("pg_advisory_unlock" in call for call in conn.calls)
    assert conn.commits == 2


@pytest.mark.asyncio
async def test_cross_process_lock_raises_conflict_when_busy() -> None:
    conn = _FakeConnection(acquired=False)

    with pytest.raises(ConcurrentExecutionError) as excinfo:
        async with cross_process_lock(
            _FakeEngine(conn),  # type: ignore[arg-type]
            AdvisoryLockKey.global_key(AdvisoryLockNamespace.MV_REFRESH),
        ):
            pass

    assert excinfo.value.http_status == 409
    assert not any("pg_advisory_unlock" in call for call in conn.calls)
    assert conn.commits == 1


def test_cli_and_api_register_cross_process_lock_helpers() -> None:
    from kortravelgeo.loaders import batch_dag

    cli_source = inspect.getsource(cli_main)
    # Per-source cross-process locking moved from the retired in-process handlers into the
    # Dagster-executed batch DAG leaf (T-290k): each source loader runs under its own lock.
    dag_source = inspect.getsource(batch_dag)

    for name in (
        "LOAD_JUSO_TEXT",
        "LOAD_DAILY_JUSO",
        "LOAD_PARCEL_LINK",
        "LOAD_ROADADDR_ENTRANCES",
        "MV_REFRESH",
        "BACKUP_CREATE",
        "RESTORE_CREATE",
    ):
        assert name in cli_source

    assert "lock_conflict" in dag_source
    assert "cross_process_lock" in dag_source
    assert "AdvisoryLockNamespace.LOAD_JUSO_TEXT" in dag_source
    assert "on_busy" not in inspect.getsource(cross_process_lock)
