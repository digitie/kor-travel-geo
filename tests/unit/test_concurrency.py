from __future__ import annotations

import inspect

import pytest

from kortravelgeo.api import app as api_app
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

    async def scalar(self, statement: object, params: object) -> bool:
        self.calls.append(str(statement))
        if "pg_try_advisory_lock" in str(statement):
            return self.acquired
        return True

    async def execute(self, statement: object, params: object) -> None:
        self.calls.append(str(statement))
        _ = params


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


def test_cli_and_api_register_cross_process_lock_helpers() -> None:
    cli_source = inspect.getsource(cli_main)
    api_source = inspect.getsource(api_app)

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

    assert "_locked_job_handler" in api_source
    assert "lock_conflict" in api_source
    assert "cross_process_lock" in api_source
    assert "AdvisoryLockNamespace.LOAD_JUSO_TEXT" in api_source
    assert "AdvisoryLockNamespace.MV_REFRESH" in api_source
    assert "on_busy" not in inspect.getsource(cross_process_lock)
