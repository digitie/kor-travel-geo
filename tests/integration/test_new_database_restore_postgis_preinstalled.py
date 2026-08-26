"""``db_restore mode=new_database`` against a target whose PostGIS extension is ALREADY
installed before the restore runs (opt-in, T-296c).

T-292 added a global ``--clean --if-exists`` to ``build_pg_restore_command`` so a
``replace_current`` restore (target = the already-populated serving DB) doesn't fail with
"already exists" on every object. ``ensure_target_database_empty`` (the ``new_database``-mode
target guard) only checks for tables in the ``public``/``ops`` schemas — it does not check
whether extensions are already installed. On a real cluster where ``template1`` has PostGIS
pre-installed (a common admin convention so every future ``CREATE DATABASE`` inherits it), a
freshly ``CREATE DATABASE``'d ``new_database``-mode target passes that empty-check while
already having the ``postgis`` extension present — precisely the scenario ``--clean
--if-exists`` needs to survive: ``pg_restore`` emits ``DROP EXTENSION IF EXISTS postgis``
before ``CREATE EXTENSION postgis`` (pg_dump includes extension DDL for installed extensions
by default), and this test confirms that drop-then-recreate against an already-installed
extension actually succeeds cleanly rather than erroring or leaving PostGIS in a broken state
(this repo's own scratch Postgres image does NOT put PostGIS in ``template1`` by default, so
this scenario was previously untested by ``test_backup_restore_roundtrip.py``'s always-vanilla
target).

Known limitation (T-296 review): this test installs PostGIS using the SAME role that later
runs the restore, so ownership always matches. In a real cluster, ``template1``'s PostGIS is
typically installed by an admin/superuser role distinct from the restore service account —
``DROP EXTENSION`` requires the extension's owner or a superuser, so a real ownership mismatch
would make ``pg_restore``'s ``DROP EXTENSION IF EXISTS postgis`` fail with a permission error
that this same-role setup can never reproduce. Confirming --clean --if-exists tolerates that
would need a second, lower-privileged role in the test fixture — out of scope here.

Run with a disposable scratch database (see ``tests/integration/_pg_guard.py``)::

    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:12500/kor_travel_geo_test pytest \
        tests/integration/test_new_database_restore_postgis_preinstalled.py
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.infra.backup import run_restore_job
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._backup_roundtrip import (
    _noop_progress,
    build_minimal_serving_schema,
    create_database,
    drop_database,
    make_backup,
    missing_requirement,
    roundtrip_settings,
)
from tests.integration._pg_guard import require_disposable_database

if TYPE_CHECKING:
    from pathlib import Path

_TARGET_DATABASE = "ktg_t296c_postgis_preinstalled"


def _dsn_for(dsn: str, database: str) -> str:
    return make_url(dsn).set(database=database).render_as_string(hide_password=False)


async def _install_postgis(target_dsn: str) -> None:
    engine = create_async_engine(target_dsn)
    try:
        async with engine.begin() as conn:
            # Matches this project's own SCHEMA_SQL convention (src/kortravelgeo/infra/sql.py)
            # — postgis lives in x_extension, not public. That's the whole point of this
            # test: a default `CREATE EXTENSION postgis` (no SCHEMA clause) creates
            # spatial_ref_sys as a real table in `public`, which ensure_target_database_empty
            # already catches and rejects — the x_extension convention is what lets a
            # PostGIS-preinstalled target slip past that check with zero public/ops tables.
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS x_extension"))
            await conn.execute(
                text("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA x_extension")
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_new_database_restore_survives_preinstalled_postgis_extension(
    tmp_path: Path,
) -> None:
    reason = missing_requirement()
    if reason:
        pytest.skip(reason)

    source_dsn = os.environ["KTG_TEST_PG_DSN"]
    settings = roundtrip_settings(source_dsn, tmp_path)
    source_engine = make_async_engine(settings)
    try:
        await require_disposable_database(source_engine)
        await build_minimal_serving_schema(source_engine)
        artifact_id = await make_backup(source_engine, settings)

        await create_database(source_dsn, _TARGET_DATABASE)
        try:
            target_dsn = _dsn_for(source_dsn, _TARGET_DATABASE)
            # Simulate a cluster whose template1 already has PostGIS installed — the target
            # is still "empty" by ensure_target_database_empty's own definition (no
            # public/ops tables), but the extension pre-exists.
            await _install_postgis(target_dsn)

            payload = {
                "artifact_id": artifact_id,
                "target_database": _TARGET_DATABASE,
                "mode": "new_database",
                "run_analyze": True,
                "run_smoke_test": True,
            }
            # The core assertion: must not raise. Before this test existed, whether
            # --clean --if-exists's DROP EXTENSION IF EXISTS postgis + CREATE EXTENSION
            # against an already-installed extension succeeds was unverified — smoke_test_
            # restore's own postgis check (raises InvalidInputError if absent) is what would
            # catch a restore that silently left PostGIS missing/broken.
            await run_restore_job(
                source_engine, settings, payload, asyncio.Event(), _noop_progress
            )

            target_engine = make_async_engine(Settings(pg_dsn=target_dsn))
            try:
                async with target_engine.connect() as conn:
                    version = await conn.scalar(text("SELECT PostGIS_version()"))
                    # A real spatial query, not just extension presence — confirms PostGIS
                    # is genuinely functional post-restore, not merely re-listed in
                    # pg_extension with broken internals.
                    point_count = await conn.scalar(
                        text(
                            "SELECT count(*)::bigint FROM"
                            " (SELECT ST_MakePoint(127.0, 37.5) AS geom) AS probe"
                            " WHERE ST_X(geom) = 127.0"
                        )
                    )
            finally:
                await target_engine.dispose()
            assert version, "PostGIS_version() must return a value post-restore"
            assert point_count == 1, "a basic PostGIS spatial function must work post-restore"
        finally:
            await drop_database(source_dsn, _TARGET_DATABASE)
    finally:
        await source_engine.dispose()
