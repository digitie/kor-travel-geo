"""재시도 sleep 지연이 획득 예산을 넘으면 새 transaction을 시작하지 않는다."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import DBAPIError

from kortravelgeo.loaders import postload


@pytest.mark.parametrize("resume_at", [32.0, 3600.0, 4002.0])
async def test_radius_retry_checks_budget_after_sleep(monkeypatch, resume_at):
    class LockUnavailableError(Exception):
        sqlstate = "55P03"

    original_error = DBAPIError("owned lock fixture", None, LockUnavailableError(), False)
    clock = [0.0]
    transactions = []
    outcomes = []
    commands = []
    sleeps = []
    guard = AsyncMock()

    async def execute(sql):
        command = str(sql)
        commands.append(command)
        if command.startswith("LOCK TABLE") and len(transactions) == 1:
            clock[0] = 2.0
            raise original_error

    connection = SimpleNamespace(
        scalar=AsyncMock(return_value="existing"),
        execute=execute,
    )

    @asynccontextmanager
    async def begin():
        transactions.append(True)
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

    if resume_at >= postload.REGION_RADIUS_LOCK_BUDGET_S:
        with pytest.raises(DBAPIError) as captured:
            await postload.refresh_region_radius_parts(engine, publication_guard=guard)
        assert captured.value is original_error
        assert len(transactions) == 1
        assert outcomes == [postload._RegionRadiusLockBusyError]
        assert "OWNED_REBUILD" not in commands
        guard.assert_not_awaited()
    else:
        await postload.refresh_region_radius_parts(engine, publication_guard=guard)
        assert len(transactions) == 2
        assert outcomes == [postload._RegionRadiusLockBusyError, None]
        assert commands.count("OWNED_REBUILD") == 1
        guard.assert_awaited_once_with(connection)
    assert sleeps == [postload.REGION_RADIUS_LOCK_RETRY_DELAY_S]
