"""``region_radius_parts`` rebuild caps its lock wait and retries (opt-in, G-01 follow-up a).

The rebuild TRUNCATEs the serving table (ACCESS EXCLUSIVE). Without a lock wait cap it queued
behind any reader for as long as the maintenance statement ceiling (6 h) allowed, and every new
radius lookup queued behind it. Bound to effects PostgreSQL reports: a held ACCESS SHARE lock makes
the rebuild give up with SQLSTATE 55P03 in seconds (not hang), and a lock released between attempts
lets the retry succeed. Only the lock acquisition is retried — a lock timeout anywhere else (here:
in the publication guard) propagates at once.

Needs a disposable scratch DB (tests/integration/_pg_guard.py naming rule) bootstrapped with
``ktgctl init-db`` + ``alembic stamp head``::

    KTG_TEST_PG_DSN=postgresql+psycopg://<user>:<pw>@127.0.0.1:<port>/kor_travel_geo_test \
        pytest tests/integration/test_region_radius_lock_timeout.py
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders import postload
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

pytestmark = pytest.mark.asyncio


async def _engine() -> AsyncEngine:
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


@pytest.fixture
def fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_TIMEOUT", "300ms")
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_RETRY_DELAY_S", 0.2)
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_BUDGET_S", 1.2)


def _retries(caplog: pytest.LogCaptureFixture) -> int:
    return sum("region_radius_parts lock" in r.getMessage() for r in caplog.records)


async def _ensure_table(engine: AsyncEngine) -> None:
    await postload.refresh_region_radius_parts(engine)  # creates the table if missing


async def _hold(holder: AsyncConnection, table: str) -> None:
    await holder.execute(text("BEGIN"))
    await holder.execute(text(f"LOCK TABLE {table} IN ACCESS SHARE MODE"))


async def test_a_held_reader_lock_makes_the_rebuild_give_up_instead_of_hanging(
    fast_retry: None, caplog: pytest.LogCaptureFixture
) -> None:
    engine = await _engine()
    try:
        await _ensure_table(engine)
        async with engine.connect() as holder:
            await _hold(holder, "region_radius_parts")
            with (
                caplog.at_level(logging.WARNING, logger=postload.LOGGER.name),
                pytest.raises(DBAPIError) as raised,
            ):
                # Without the cap this waits up to the 6 h maintenance ceiling.
                await asyncio.wait_for(postload.refresh_region_radius_parts(engine), 20)
            await holder.execute(text("ROLLBACK"))
        assert getattr(raised.value.orig, "sqlstate", None) == "55P03"
        assert _retries(caplog) >= 1
    finally:
        await engine.dispose()


async def test_a_lock_released_between_attempts_lets_the_retry_succeed(
    fast_retry: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_RETRY_DELAY_S", 1.0)
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_BUDGET_S", 20.0)
    engine = await _engine()
    try:
        await _ensure_table(engine)
        async with engine.connect() as holder:
            await _hold(holder, "region_radius_parts")

            async def release_soon() -> None:
                await asyncio.sleep(0.6)
                await holder.execute(text("ROLLBACK"))

            releaser = asyncio.create_task(release_soon())
            try:
                with caplog.at_level(logging.WARNING, logger=postload.LOGGER.name):
                    await asyncio.wait_for(postload.refresh_region_radius_parts(engine), 20)
            finally:
                await releaser
        assert _retries(caplog) == 1
    finally:
        await engine.dispose()


async def test_a_lock_timeout_elsewhere_in_the_rebuild_is_not_retried(
    fast_retry: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_BUDGET_S", 20.0)
    engine = await _engine()

    async def guard(conn: AsyncConnection) -> None:
        await conn.execute(text("SET LOCAL lock_timeout = '200ms'"))
        await conn.execute(text("LOCK TABLE tl_scco_li IN ACCESS EXCLUSIVE MODE"))

    try:
        await _ensure_table(engine)
        async with engine.connect() as holder:
            await _hold(holder, "tl_scco_li")
            with (
                caplog.at_level(logging.WARNING, logger=postload.LOGGER.name),
                pytest.raises(DBAPIError) as raised,
            ):
                await asyncio.wait_for(
                    postload.refresh_region_radius_parts(engine, publication_guard=guard), 20
                )
            await holder.execute(text("ROLLBACK"))
        assert getattr(raised.value.orig, "sqlstate", None) == "55P03"
        assert _retries(caplog) == 0
    finally:
        await engine.dispose()
