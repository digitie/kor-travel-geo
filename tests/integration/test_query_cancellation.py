from __future__ import annotations

import asyncio
import os
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_cancelled_query_has_no_orphan_activity_or_pool_leak() -> None:
    dsn = os.environ.get("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN is required for query cancellation integration test")

    application_name = f"ktg_t161_{uuid4().hex[:8]}"
    engine = make_async_engine(
        Settings(
            pg_dsn=dsn,
            pg_pool_size=1,
            pg_max_overflow=0,
            pg_pool_timeout_ms=200,
            pg_statement_timeout_ms=30_000,
            pg_query_metrics_enabled=True,
        ),
        connect_args={"application_name": application_name},
    )
    monitor_engine = make_async_engine(
        Settings(pg_dsn=dsn, pg_query_metrics_enabled=False),
        connect_args={"application_name": f"{application_name}_monitor"},
    )
    try:
        task = asyncio.create_task(_run_sleep_query(engine))
        await _wait_for_active_sleep(monitor_engine, application_name)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

        await _wait_for_no_active_sleep(monitor_engine, application_name)
        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()
        await monitor_engine.dispose()


async def _run_sleep_query(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_sleep(10)"))


async def _wait_for_active_sleep(engine: AsyncEngine, application_name: str) -> None:
    deadline = perf_counter() + 5
    while perf_counter() < deadline:
        if await _active_sleep_count(engine, application_name) > 0:
            return
        await asyncio.sleep(0.05)
    pytest.fail("pg_sleep query did not become active before cancellation")


async def _wait_for_no_active_sleep(engine: AsyncEngine, application_name: str) -> None:
    deadline = perf_counter() + 5
    while perf_counter() < deadline:
        if await _active_sleep_count(engine, application_name) == 0:
            return
        await asyncio.sleep(0.05)
    pytest.fail("cancelled pg_sleep query remained active in pg_stat_activity")


async def _active_sleep_count(engine: AsyncEngine, application_name: str) -> int:
    statement = text(
        """
        SELECT count(*)
          FROM pg_stat_activity
         WHERE application_name = :application_name
           AND state = 'active'
           AND query ILIKE '%pg_sleep%'
        """
    )
    async with engine.connect() as conn:
        result = await conn.execute(statement, {"application_name": application_name})
        return int(result.scalar_one())
