"""재시도 sleep 지연이 획득 예산을 넘으면 새 transaction을 시작하지 않는다."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import DBAPIError

from kortravelgeo.loaders import postload


@pytest.mark.parametrize(
    ("resume_at", "delay_at", "ready_at"),
    [(32.0, None, 32.0), (3600.0, None, 3600.0), (4002.0, None, 4002.0)]
    + [
        (32.0, stage, ready)
        for stage in ("pool", "setup", "relation", "read_timeout", "set_timeout")
        for ready in (3599.0, 3600.0, 4002.0)
    ],
)
async def test_radius_retry_checks_budget_after_sleep(
    monkeypatch, resume_at, delay_at, ready_at
):
    class LockUnavailableError(Exception):
        sqlstate = "55P03"

    original_error = DBAPIError("owned lock fixture", None, LockUnavailableError(), False)
    clock = [0.0]
    transactions = []
    outcomes = []
    commands = []
    sleeps = []
    guard = AsyncMock()

    async def execute(sql, parameters=None):
        command = str(sql)
        commands.append(command)
        if (
            len(transactions) == 2
            and delay_at == "setup"
            and command.startswith("SET LOCAL statement_timeout")
        ):
            clock[0] = ready_at
        if (
            len(transactions) == 2
            and delay_at == "set_timeout"
            and command.startswith("SET LOCAL lock_timeout")
        ):
            clock[0] = ready_at
        if command.startswith("LOCK TABLE") and len(transactions) == 1:
            clock[0] = 2.0
            raise original_error

    async def scalar(sql):
        if len(transactions) == 2 and (
            (delay_at == "relation" and "to_regclass" in str(sql))
            or (delay_at == "read_timeout" and "current_setting" in str(sql))
        ):
            clock[0] = ready_at
        return "existing"

    connection = SimpleNamespace(
        scalar=scalar,
        execute=execute,
    )

    @asynccontextmanager
    async def begin():
        transactions.append(True)
        if len(transactions) == 2 and delay_at == "pool":
            clock[0] = ready_at
        try:
            yield connection
        except BaseException as error:
            outcomes.append(type(error))
            raise
        else:
            outcomes.append(None)

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] = resume_at

    monkeypatch.setattr(postload, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(postload, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(postload, "iter_sql_statements", lambda _: ("OWNED_REBUILD",))
    engine = SimpleNamespace(begin=begin)

    if max(resume_at, ready_at) >= postload.REGION_RADIUS_LOCK_BUDGET_S:
        with pytest.raises(DBAPIError) as captured:
            await postload.refresh_region_radius_parts(engine, publication_guard=guard)
        assert captured.value is original_error
        if resume_at >= postload.REGION_RADIUS_LOCK_BUDGET_S:
            assert len(transactions) == 1
            assert outcomes == [postload._RegionRadiusLockBusyError]
        else:
            assert len(transactions) == 2
            assert outcomes == [postload._RegionRadiusLockBusyError, DBAPIError]
        assert sum(command.startswith("LOCK TABLE") for command in commands) == 1
        assert "OWNED_REBUILD" not in commands
        guard.assert_not_awaited()
    else:
        await postload.refresh_region_radius_parts(engine, publication_guard=guard)
        assert len(transactions) == 2
        assert outcomes == [postload._RegionRadiusLockBusyError, None]
        assert commands.count("OWNED_REBUILD") == 1
        guard.assert_awaited_once_with(connection)
    assert sleeps == [postload.REGION_RADIUS_LOCK_RETRY_DELAY_S]


@pytest.mark.parametrize("original_timeout", ["0", "250ms", "15s"])
async def test_radius_lock_restores_inherited_timeout(original_timeout):
    state = {"timeout": original_timeout}
    locks = []

    async def scalar(sql):
        if "to_regclass" in str(sql):
            return "region_radius_parts"
        assert "current_setting('lock_timeout')" in str(sql)
        return state["timeout"]

    async def execute(sql, parameters=None):
        command = str(sql)
        if command.startswith("SET LOCAL lock_timeout"):
            state["timeout"] = "2s" if "'2s'" in command else "0"
        elif command.startswith("LOCK TABLE"):
            locks.append(state["timeout"])
        elif "set_config" in command:
            assert parameters == {"lock_timeout": original_timeout}
            assert "true" in command
            state["timeout"] = parameters["lock_timeout"]

    await postload._lock_region_radius_parts(
        SimpleNamespace(scalar=scalar, execute=execute)
    )
    assert locks == ["2s"]
    assert state["timeout"] == original_timeout
