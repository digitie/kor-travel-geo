"""재시도 sleep 지연이 획득 예산을 넘으면 새 LOCK을 요청하지 않는다(G-01 후속 a/a2).

a2부터 재생성은 한 transaction 안에서 ``_next``를 먼저 채우고, 교체 잠금만 savepoint에서
재시도한다. 그래서 재생성 SQL은 시도 수와 무관하게 한 번만 실행돼야 하고, 예산 초과는
원래 lock 오류를 그대로 올려 바깥 transaction 전체를 rollback시킨다.
"""

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
        for stage in ("savepoint", "relation", "read_timeout", "set_timeout")
        for ready in (3599.0, 3600.0, 4002.0)
    ],
)
async def test_radius_retry_checks_budget_after_sleep(monkeypatch, resume_at, delay_at, ready_at):
    class LockUnavailableError(Exception):
        sqlstate = "55P03"

    original_error = DBAPIError("owned lock fixture", None, LockUnavailableError(), False)
    clock = [0.0]
    savepoints = []
    outcomes = []
    commands = []
    sleeps = []
    guard = AsyncMock()
    swap = AsyncMock()

    async def execute(sql, parameters=None):
        command = str(sql)
        commands.append(command)
        if (
            len(savepoints) == 2
            and delay_at == "set_timeout"
            and command.startswith("SET LOCAL lock_timeout")
        ):
            clock[0] = ready_at
        if command.startswith("LOCK TABLE") and len(savepoints) == 1:
            clock[0] = 2.0
            raise original_error

    async def scalar(sql):
        if len(savepoints) == 2 and (
            (delay_at == "relation" and "to_regclass" in str(sql))
            or (delay_at == "read_timeout" and "current_setting" in str(sql))
        ):
            clock[0] = ready_at
        return "existing"

    @asynccontextmanager
    async def begin_nested():
        savepoints.append(True)
        if len(savepoints) == 2 and delay_at == "savepoint":
            clock[0] = ready_at
        try:
            yield
        except BaseException as error:
            outcomes.append(type(error))
            raise
        else:
            outcomes.append(None)

    connection = SimpleNamespace(scalar=scalar, execute=execute, begin_nested=begin_nested)

    @asynccontextmanager
    async def begin():
        yield connection

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] = resume_at

    monkeypatch.setattr(postload, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(postload, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(postload, "iter_sql_statements", lambda _: ("OWNED_REBUILD",))
    monkeypatch.setattr(postload, "_swap_region_radius_parts", swap)
    engine = SimpleNamespace(begin=begin)

    if max(resume_at, ready_at) >= postload.REGION_RADIUS_LOCK_BUDGET_S:
        with pytest.raises(DBAPIError) as captured:
            await postload.refresh_region_radius_parts(engine, publication_guard=guard)
        assert captured.value is original_error
        if resume_at >= postload.REGION_RADIUS_LOCK_BUDGET_S:
            assert len(savepoints) == 1
            assert outcomes == [postload._RegionRadiusLockBusyError]
        else:
            assert len(savepoints) == 2
            assert outcomes == [postload._RegionRadiusLockBusyError, DBAPIError]
        assert sum(command.startswith("LOCK TABLE") for command in commands) == 1
        swap.assert_not_awaited()
        guard.assert_awaited_once_with(connection)  # the pre-lock check only
    else:
        await postload.refresh_region_radius_parts(engine, publication_guard=guard)
        assert len(savepoints) == 2
        assert outcomes == [postload._RegionRadiusLockBusyError, None]
        swap.assert_awaited_once_with(connection, live_exists=True)
        assert guard.await_count == 2  # before the lock, and once more before commit
    # The long build runs once, before any lock attempt, whatever the retries do.
    assert commands.count("OWNED_REBUILD") == 1
    assert commands.index("OWNED_REBUILD") < next(
        i for i, c in enumerate(commands) if c.startswith("LOCK TABLE")
    )
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

    assert await postload._lock_region_radius_parts(SimpleNamespace(scalar=scalar, execute=execute))
    assert locks == ["2s"]
    assert state["timeout"] == original_timeout


def test_next_build_sql_is_the_refresh_sql_retargeted() -> None:
    sql = postload.build_region_radius_parts_next_sql()
    # The stale-table DROP runs after the SQL's own search_path, right before a strict CREATE.
    assert sql.index("SET search_path") < sql.index(
        "DROP TABLE IF EXISTS region_radius_parts_next;"
    )
    assert (
        "DROP TABLE IF EXISTS region_radius_parts_next;\nCREATE TABLE region_radius_parts_next ("
        in sql
    )
    assert "IF NOT EXISTS region_radius_parts_next " not in sql
    assert "TRUNCATE" not in sql
    # Every live name is retargeted: no statement in the build touches the live table.
    assert "region_radius_parts" not in sql.replace("region_radius_parts_next", "")
    assert "INSERT INTO region_radius_parts_next" in sql
    assert "idx_region_radius_parts_next_geom" in sql
    assert "ANALYZE region_radius_parts_next" in sql
