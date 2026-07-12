"""Real-Postgres round-trip for ensure_scratch_database (opt-in: ``KTG_TEST_PG_DSN``).

Validates the actual ``CREATE DATABASE`` + full schema init (SCHEMA_SQL + INDEX_SQL + MV_SQL +
consistency registry) that makes a scratch DB a valid ``full_load_batch`` target — the seam the
blue-green staging run depends on. Point ``KTG_TEST_PG_DSN`` at a PostgreSQL/PostGIS cluster
whose user has CREATEDB; the test creates a uniquely-named scratch DB and drops it in teardown.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.infra.backup import normalize_sqlalchemy_dsn
from kortravelgeo.infra.scratch_db import ensure_scratch_database, scratch_database_dsn
from kortravelgeo.settings import Settings

pytestmark = pytest.mark.asyncio

_SCRATCH_DB = "kor_travel_geo_scratch_it"


async def _drop_scratch(base_dsn: str, db_name: str) -> None:
    maintenance = (
        make_url(base_dsn).set(database="postgres").render_as_string(hide_password=False)
    )
    engine = create_async_engine(
        normalize_sqlalchemy_dsn(maintenance), isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
    finally:
        await engine.dispose()


async def test_ensure_scratch_database_creates_valid_full_load_target() -> None:
    base_dsn = os.getenv("KTG_TEST_PG_DSN")
    if not base_dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL/PostGIS cluster")
    settings = Settings(pg_dsn=base_dsn)

    await _drop_scratch(base_dsn, _SCRATCH_DB)
    try:
        target_dsn = await ensure_scratch_database(settings, _SCRATCH_DB)
        assert target_dsn == scratch_database_dsn(base_dsn, _SCRATCH_DB)
        # idempotent: a second call re-applies the create (no-op) + idempotent DDL cleanly.
        await ensure_scratch_database(settings, _SCRATCH_DB)

        engine = create_async_engine(target_dsn)
        try:
            async with engine.connect() as conn:
                load_jobs = await conn.scalar(text("SELECT to_regclass('public.load_jobs')"))
                juso = await conn.scalar(text("SELECT to_regclass('public.tl_juso_text')"))
                mv = await conn.scalar(
                    text("SELECT count(*) FROM pg_matviews WHERE matviewname = 'mv_geocode_target'")
                )
                postgis = await conn.scalar(
                    text("SELECT count(*) FROM pg_extension WHERE extname = 'postgis'")
                )
        finally:
            await engine.dispose()

        # control table + data table + a serving MV + PostGIS => a valid full_load target
        assert load_jobs is not None
        assert juso is not None
        assert mv == 1
        assert postgis == 1
    finally:
        await _drop_scratch(base_dsn, _SCRATCH_DB)
