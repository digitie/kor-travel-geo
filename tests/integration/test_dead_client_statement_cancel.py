"""A dead client's long statement is cancelled by the server (opt-in, G-01 follow-up b).

A maintenance statement may run for hours (6 h ceiling). When its Dagster run worker dies (run
monitor terminate, OOM, container recreate) PostgreSQL does not notice a vanished client while a
query executes, so the backend kept running — holding its locks — until the statement ended. With
``pg_client_connection_check_interval_ms`` set (the Dagster maintenance engine sets it), the
server polls the socket during the query and ends the backend shortly after the client is gone.

Bound to the effect: a child process runs ``pg_sleep(60)`` through ``make_async_engine`` and is
SIGKILLed; the backend (found by a unique ``application_name``) must disappear within seconds. The
control case (check off) shows the backend surviving — that is the old behaviour.

Needs a disposable scratch DB (tests/integration/_pg_guard.py naming rule)::

    KTG_TEST_PG_DSN=postgresql+psycopg://<user>:<pw>@127.0.0.1:<port>/kor_travel_geo_test \
        pytest tests/integration/test_dead_client_statement_cancel.py
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import textwrap
import time
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(sys.platform != "linux", reason="client_connection_check is Linux-only"),
]

_CHILD = textwrap.dedent(
    """
    import asyncio, sys
    from sqlalchemy import text
    from kortravelgeo.infra.engine import make_async_engine
    from kortravelgeo.settings import Settings

    async def main() -> None:
        settings = Settings(pg_dsn=sys.argv[1]).model_copy(
            update={"pg_statement_timeout_ms": 0,
                    "pg_client_connection_check_interval_ms": int(sys.argv[3])}
        )
        engine = make_async_engine(settings)
        async with engine.connect() as conn:
            await conn.execute(text(f"SET application_name = '{sys.argv[2]}'"))
            print("READY", flush=True)
            await conn.execute(text("SELECT pg_sleep(60)"))

    asyncio.run(main())
    """
)


async def _observer() -> AsyncEngine:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
    except BaseException:
        await engine.dispose()
        raise
    return engine


async def _backend_alive(engine: AsyncEngine, app: str) -> bool:
    async with engine.connect() as conn:
        n = await conn.scalar(
            text("SELECT count(*) FROM pg_stat_activity WHERE application_name = :app"),
            {"app": app},
        )
    return bool(n)


async def _kill_child_mid_query(engine: AsyncEngine, interval_ms: int) -> str:
    app = f"ktg-g01b-{uuid.uuid4().hex[:12]}"
    child = subprocess.Popen(
        [sys.executable, "-c", _CHILD, os.environ["KTG_TEST_PG_DSN"], app, str(interval_ms)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "READY"
        deadline = time.monotonic() + 10
        while not await _backend_alive(engine, app):
            assert time.monotonic() < deadline, "child backend never appeared"
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.5)  # the pg_sleep is running now
    finally:
        child.send_signal(signal.SIGKILL)
        child.wait(timeout=10)
    return app


async def test_dead_client_backend_is_cancelled_when_the_check_is_on() -> None:
    engine = await _observer()
    try:
        app = await _kill_child_mid_query(engine, interval_ms=500)
        deadline = time.monotonic() + 10
        while await _backend_alive(engine, app):
            assert time.monotonic() < deadline, "backend outlived its dead client by 10 s"
            await asyncio.sleep(0.2)
    finally:
        await engine.dispose()


async def test_without_the_check_the_dead_client_backend_keeps_running() -> None:
    engine = await _observer()
    try:
        app = await _kill_child_mid_query(engine, interval_ms=0)
        await asyncio.sleep(3)
        assert await _backend_alive(engine, app), "control case: expected the old behaviour"
        async with engine.connect() as conn:  # clean up the orphan
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                    " WHERE application_name = :app"
                ),
                {"app": app},
            )
    finally:
        await engine.dispose()
