"""``region_radius_parts`` rebuild caps its lock wait and retries (opt-in, G-01 follow-up a).

The rebuild TRUNCATEs the serving table (ACCESS EXCLUSIVE). Without a lock wait cap it queued
behind any reader for as long as the maintenance statement ceiling (6 h) allowed, and every new
radius lookup queued behind it. Bound to effects PostgreSQL reports: a held ACCESS SHARE lock makes
the rebuild give up with SQLSTATE 55P03 in seconds (not hang), and a lock released between attempts
lets the retry succeed.

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
    from sqlalchemy.ext.asyncio import AsyncEngine

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
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_ATTEMPTS", 2)
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_RETRY_DELAY_S", 0.2)


async def _ensure_table(engine: AsyncEngine) -> None:
    await postload.refresh_region_radius_parts(engine)  # creates the table if missing


async def test_a_held_reader_lock_makes_the_rebuild_give_up_instead_of_hanging(
    fast_retry: None, caplog: pytest.LogCaptureFixture
) -> None:
    engine = await _engine()
    try:
        await _ensure_table(engine)
        async with engine.connect() as holder:
            await holder.execute(text("BEGIN"))
            await holder.execute(text("LOCK TABLE region_radius_parts IN ACCESS SHARE MODE"))
            with caplog.at_level(logging.WARNING, logger=postload.LOGGER.name):
                with pytest.raises(DBAPIError) as raised:
                    # Without the cap this waits up to the 6 h maintenance ceiling.
                    await asyncio.wait_for(postload.refresh_region_radius_parts(engine), 20)
            await holder.execute(text("ROLLBACK"))
        assert getattr(raised.value.orig, "sqlstate", None) == "55P03"
        retries = [r for r in caplog.records if "region_radius_parts" in r.getMessage()]
        assert len(retries) == 1
    finally:
        await engine.dispose()


async def test_a_lock_released_between_attempts_lets_the_retry_succeed(
    fast_retry: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postload, "REGION_RADIUS_LOCK_RETRY_DELAY_S", 1.0)
    engine = await _engine()
    try:
        await _ensure_table(engine)
        async with engine.connect() as holder:
            await holder.execute(text("BEGIN"))
            await holder.execute(text("LOCK TABLE region_radius_parts IN ACCESS SHARE MODE"))

            async def release_soon() -> None:
                await asyncio.sleep(0.6)
                await holder.execute(text("ROLLBACK"))

            releaser = asyncio.create_task(release_soon())
            await asyncio.wait_for(postload.refresh_region_radius_parts(engine), 20)
            await releaser
    finally:
        await engine.dispose()
