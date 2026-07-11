"""Blue-green scratch-DB provisioning for staging full-loads (T-290j staging).

A ``full_load_batch`` runs its ENTIRE DAG against ONE engine — the control plane
(``load_jobs`` / ``ops.*`` rows, consistency reports, mv-release records) AND the data
plane (``tl_juso_text`` / ``mv_geocode_target`` + the MV swap). To validate the Dagster
full-load without opening the serving DB, the batch runs against an isolated *scratch*
database that is a full schema-initialised clone. This module creates + fresh-inits that
scratch DB — the same sequence as ``ktgctl init-db`` (SCHEMA_SQL + INDEX_SQL + MV_SQL +
consistency registry) — so it is a valid ``full_load_batch`` target. The serving DB is
never opened: DDL runs only against the scratch DSN (and the maintenance ``postgres`` DB
for the ``CREATE DATABASE``).
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from sqlalchemy import text as sa_text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.infra.backup import normalize_sqlalchemy_dsn, validate_database_identifier
from kortravelgeo.infra.sql import INDEX_SQL, MV_SQL, SCHEMA_SQL, iter_sql_statements

if TYPE_CHECKING:
    from kortravelgeo.settings import Settings

__all__ = ["ensure_scratch_database", "scratch_database_dsn"]


def scratch_database_dsn(pg_dsn: str, db_name: str) -> str:
    """``pg_dsn`` with its database swapped to ``db_name`` (validated), SQLAlchemy-normalized."""
    validate_database_identifier(db_name, "target_database")
    swapped = make_url(pg_dsn).set(database=db_name).render_as_string(hide_password=False)
    return normalize_sqlalchemy_dsn(swapped)


async def _create_database_if_absent(pg_dsn: str, db_name: str) -> None:
    """``CREATE DATABASE db_name TEMPLATE template0`` via the cluster ``postgres`` DB.

    AUTOCOMMIT because ``CREATE DATABASE`` cannot run inside a transaction (mirrors
    :func:`kortravelgeo.infra.restore_drill._create_drill_database`). Idempotent — a
    concurrent create losing the race is swallowed.
    """
    maintenance_dsn = (
        make_url(pg_dsn).set(database="postgres").render_as_string(hide_password=False)
    )
    engine = create_async_engine(
        normalize_sqlalchemy_dsn(maintenance_dsn), isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                sa_text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
            )
            if not exists:
                await conn.execute(
                    sa_text(f'CREATE DATABASE "{db_name}" TEMPLATE template0 ENCODING \'UTF8\'')
                )
    finally:
        await engine.dispose()


async def ensure_scratch_database(settings: Settings, db_name: str) -> str:
    """Create ``db_name`` (if absent) and fresh-init its schema; return its scratch DSN.

    Idempotent. Applies SCHEMA_SQL (incl. ``CREATE EXTENSION postgis``) + INDEX_SQL +
    MV_SQL and seeds the C1~C17 consistency registry — identical to ``ktgctl init-db`` —
    so the scratch DB is a valid ``full_load_batch`` target. Serving is never opened:
    every statement runs against the scratch DSN (and the maintenance ``postgres`` DB for
    the ``CREATE``).
    """
    validate_database_identifier(db_name, "target_database")
    await _create_database_if_absent(settings.pg_dsn, db_name)
    target_dsn = scratch_database_dsn(settings.pg_dsn, db_name)

    engine = create_async_engine(target_dsn)
    try:
        for sql in iter_sql_statements(SCHEMA_SQL):
            async with engine.begin() as conn:
                await conn.execute(sa_text(sql))
        # INDEX_SQL / MV_SQL are idempotent-by-retry: an already-present object is fine.
        for group in (INDEX_SQL, MV_SQL):
            for sql in iter_sql_statements(group):
                with suppress(Exception):
                    async with engine.begin() as conn:
                        await conn.execute(sa_text(sql))
        # Seed the C1~C17 consistency case registry so the batch's consistency stage +
        # report recording have their case definitions (parity with ``ktgctl init-db``).
        from kortravelgeo.infra.consistency_registry_service import ConsistencyRegistryService

        await ConsistencyRegistryService(engine).seed_registry()
    finally:
        await engine.dispose()
    return target_dsn
