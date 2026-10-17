"""Maintenance ``statement_timeout`` floor against a real PostgreSQL (opt-in, G-01).

The post-load maintenance transactions (link resolution, MV refresh/swap, release record) used a
bare ``SET LOCAL statement_timeout = '30min'``. On the Dagster maintenance engine the session
timeout is ``0`` (unlimited — the run is bounded by ``dagster/max_runtime``), so that line
*lowered* it, and an odroid ``mv_refresh`` was cancelled at exactly 30 min (2026-10-15,
``job_fb535a34…``). ``raise_statement_timeout_floor`` only raises a shorter positive timeout.

Every case is bound to an effect PostgreSQL itself reports — a ``pg_sleep`` that would be
cancelled, or ``SHOW statement_timeout`` — not to the helper's source text.

Needs a disposable scratch DB (tests/integration/_pg_guard.py naming rule) bootstrapped with
``ktgctl init-db`` + ``alembic stamp head``::

    KTG_TEST_PG_DSN=postgresql+psycopg://<user>:<pw>@127.0.0.1:<port>/kor_travel_geo_test \
        pytest tests/integration/test_postload_link_resolution.py
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.engine import make_async_engine, raise_statement_timeout_floor
from kortravelgeo.loaders import postload
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

pytestmark = pytest.mark.asyncio


async def _engine(session_timeout_ms: int) -> AsyncEngine:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    # model_copy skips the ge=1 bound on purpose: 0 is the maintenance engine's "unlimited"
    # (kortravelgeo_dagster.resources._maintenance_engine_settings does the same).
    settings = Settings(pg_dsn=dsn).model_copy(
        update={"pg_statement_timeout_ms": session_timeout_ms}
    )
    engine = make_async_engine(settings)
    try:
        await require_disposable_database(engine)
    except BaseException:
        await engine.dispose()
        raise
    return engine


async def _show(engine: AsyncEngine, floor_ms: int) -> tuple[str, str]:
    """``SHOW statement_timeout`` inside a transaction that raised ``floor_ms``, then after it."""
    async with engine.begin() as conn:
        await raise_statement_timeout_floor(conn, floor_ms)
        inside = str(await conn.scalar(text("SHOW statement_timeout")))
    async with engine.connect() as conn:
        after = str(await conn.scalar(text("SHOW statement_timeout")))
    return inside, after


async def test_unlimited_session_timeout_is_not_lowered() -> None:
    engine = await _engine(0)
    try:
        inside, after = await _show(engine, 300)
        assert (inside, after) == ("0", "0")
        async with engine.begin() as conn:
            await raise_statement_timeout_floor(conn, 300)
            # Would be cancelled if the floor had been applied as a ceiling (old bare SET LOCAL).
            await conn.execute(text("SELECT pg_sleep(0.8)"))
    finally:
        await engine.dispose()


async def test_short_session_timeout_is_raised_to_the_floor_for_the_transaction_only() -> None:
    engine = await _engine(200)
    try:
        inside, after = await _show(engine, 3_000)
        assert (inside, after) == ("3s", "200ms")
        async with engine.begin() as conn:
            await raise_statement_timeout_floor(conn, 3_000)
            await conn.execute(text("SELECT pg_sleep(0.6)"))  # > 200 ms session, < 3 s floor
        with pytest.raises(DBAPIError, match="statement timeout"):
            async with engine.connect() as conn:  # the raise was transaction-local
                await conn.execute(text("SELECT pg_sleep(0.6)"))
    finally:
        await engine.dispose()


async def test_longer_session_timeout_is_kept() -> None:
    engine = await _engine(7_200_000)
    try:
        inside, after = await _show(engine, 1_800_000)
        assert (inside, after) == ("2h", "2h")
    finally:
        await engine.dispose()


async def test_link_resolution_on_the_maintenance_engine_is_not_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real wiring: resolve_text_geometry_links with a (shrunk) floor on an unlimited session.
    # Before G-01 it set the floor as the timeout, so this statement was cancelled.
    monkeypatch.setattr(postload, "POSTLOAD_SQL", "SELECT pg_sleep(0.8);")
    engine = await _engine(0)
    try:
        await postload.resolve_text_geometry_links(engine, statement_timeout_ms=300)
    finally:
        await engine.dispose()
    short = await _engine(200)
    try:
        await postload.resolve_text_geometry_links(short, statement_timeout_ms=3_000)
    finally:
        await short.dispose()
