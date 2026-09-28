"""T-312: an app-role backup restores on a shared-instance layout by BOTH restore paths (opt-in).

Recreates the shared PostgreSQL instance's layout (T-308): a NOSUPERUSER/NOCREATEDB app role that
owns its databases, and an ``x_extension`` schema created by the cluster admin — the app role only
has ``USAGE`` on it — holding the extensions. ``run_backup_job`` runs ``pg_dump`` AS THE APP ROLE,
then the archive is restored into a fresh, admin-provisioned database owned by the app role:

- ``superuser`` — ``target_dsn`` carries cluster-admin credentials (the gate-exempt operator path).
  ``pg_restore --clean --if-exists`` drops ``x_extension`` and recreates it from the dump, so the
  app role's ``USAGE`` survives only through the dump's ``ACL - SCHEMA x_extension`` entry. A dump
  taken with ``--no-privileges`` lost it: pg_restore exited 0, the old smoke test passed, and every
  PostGIS call by the app role then failed (T-312 review).
- ``app_role`` — ``target_dsn`` carries the app role's credentials: ``--no-owner --no-privileges``
  plus the admin-provisioned extension/``x_extension`` TOC entries filtered out.

Both are checked the way production uses the result — from an APP ROLE connection with
``search_path=public,x_extension``: PostGIS resolves, the restored rows are there, and the restored
tables belong to the app role.

Needs a SUPERUSER ``KTG_TEST_PG_DSN`` — it creates and drops a throwaway LOGIN role and three
``*_rt`` databases (never the DSN's own database)::

    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:12500/kor_travel_geo_test pytest \
        tests/integration/test_t312_shared_instance_restore.py
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import RESTORE_LOG_ARTIFACT_TYPE, run_restore_job
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._backup_roundtrip import (
    _noop_progress,
    build_minimal_serving_schema,
    drop_database,
    make_backup,
    missing_requirement,
    roundtrip_settings,
)
from tests.integration._pg_guard import is_protected_database, require_disposable_database

if TYPE_CHECKING:
    from pathlib import Path

_APP_ROLE = "ktg_t312_app_rt"
_APP_PASSWORD = "ktg_t312_app_rt"  # throwaway role, dropped in teardown
_SOURCE_DATABASE = "ktg_t312_src_rt"
_TARGET_DATABASES = {"superuser": "ktg_t312_dst_su_rt", "app_role": "ktg_t312_dst_app_rt"}
_EXTENSIONS = ("postgis", "pg_trgm", "unaccent", "pg_stat_statements")
_PROBE_TABLE = "_ktg_roundtrip_probe"  # seeded with 3 rows by build_minimal_serving_schema


def _dsn(base: str, database: str, *, as_app_role: bool = False) -> str:
    url = make_url(base).set(database=database)
    if as_app_role:
        url = url.set(username=_APP_ROLE, password=_APP_PASSWORD)
    return url.render_as_string(hide_password=False)


async def _exec(dsn: str, *statements: str) -> None:
    engine = create_async_engine(dsn, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            for statement in statements:
                await conn.execute(text(statement))
    finally:
        await engine.dispose()


async def _require_disposable_superuser(admin_dsn: str) -> None:
    engine = create_async_engine(admin_dsn)
    try:
        # This module never writes to the DSN's own database, but a DSN that does not name a
        # disposable scratch database must not get a role and three databases created either.
        await require_disposable_database(engine)
        async with engine.connect() as conn:
            is_superuser = await conn.scalar(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            )
    finally:
        await engine.dispose()
    if not is_superuser:
        pytest.skip("KTG_TEST_PG_DSN must be a superuser to create the throwaway app role")


async def _drop_fixture(admin_dsn: str) -> None:
    # Every DB the throwaway role owns, too — a failed new_database restore quarantines its
    # target as `<target>_quarantine_<ts>` instead of dropping it (T-235), and DROP ROLE fails
    # while any of them is left.
    engine = create_async_engine(_dsn(admin_dsn, "postgres"))
    try:
        async with engine.connect() as conn:
            owned = (
                (
                    await conn.execute(
                        text(
                            "SELECT d.datname FROM pg_database d"
                            " JOIN pg_roles r ON r.oid = d.datdba WHERE r.rolname = :role"
                        ),
                        {"role": _APP_ROLE},
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()
    for database in sorted({_SOURCE_DATABASE, *_TARGET_DATABASES.values(), *owned}):
        if not is_protected_database(database):
            await drop_database(admin_dsn, database)
    await _exec(_dsn(admin_dsn, "postgres"), f"DROP ROLE IF EXISTS {_APP_ROLE}")


async def _provision_database(admin_dsn: str, database: str) -> None:
    """Like the shared instance: app-role-owned DB + admin-owned x_extension (USAGE only)."""
    await _exec(
        _dsn(admin_dsn, "postgres"),
        f'CREATE DATABASE "{database}" OWNER {_APP_ROLE} TEMPLATE template0',
    )
    await _exec(
        _dsn(admin_dsn, database),
        "CREATE SCHEMA x_extension",
        f"GRANT USAGE ON SCHEMA x_extension TO {_APP_ROLE}",
        *(f"CREATE EXTENSION {ext} WITH SCHEMA x_extension" for ext in _EXTENSIONS),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("restorer", ["superuser", "app_role"])
async def test_app_role_backup_restores_with_extension_schema_usage(
    tmp_path: Path, restorer: str
) -> None:
    reason = missing_requirement()
    if reason:
        pytest.skip(reason)
    admin_dsn = os.environ["KTG_TEST_PG_DSN"]
    await _require_disposable_superuser(admin_dsn)

    await _drop_fixture(admin_dsn)  # leftovers from an interrupted run
    await _exec(
        _dsn(admin_dsn, "postgres"),
        f"CREATE ROLE {_APP_ROLE} LOGIN PASSWORD '{_APP_PASSWORD}' "
        "NOSUPERUSER NOCREATEDB NOCREATEROLE",
    )
    try:
        await _provision_database(admin_dsn, _SOURCE_DATABASE)
        settings = roundtrip_settings(_dsn(admin_dsn, _SOURCE_DATABASE, as_app_role=True), tmp_path)
        source_engine = make_async_engine(settings)
        try:
            await build_minimal_serving_schema(source_engine)
            artifact_id = await make_backup(source_engine, settings)  # pg_dump as the app role

            target_database = _TARGET_DATABASES[restorer]
            await _provision_database(admin_dsn, target_database)
            payload = {
                "artifact_id": artifact_id,
                "target_dsn": _dsn(admin_dsn, target_database, as_app_role=restorer == "app_role"),
                "mode": "new_database",
                "run_analyze": True,
                "run_smoke_test": True,
                "run_row_count_check": True,
            }
            await run_restore_job(source_engine, settings, payload, asyncio.Event(), _noop_progress)
            restore_logs = await AdminRepository(source_engine).list_artifacts(
                limit=1, artifact_type=RESTORE_LOG_ARTIFACT_TYPE, state="available"
            )
        finally:
            await source_engine.dispose()

        skipped = (restore_logs[0].manifest or {}).get("preprovisioned_toc_skipped")
        if restorer == "app_role":
            assert skipped, "the app-role restore must skip the admin-provisioned TOC entries"
        else:
            assert skipped is None, "a superuser restore must not rewrite the TOC"

        # Production's view of the result: the app role, search_path=public,x_extension.
        app_engine = make_async_engine(
            Settings(pg_dsn=_dsn(admin_dsn, target_database, as_app_role=True))
        )
        try:
            async with app_engine.connect() as conn:
                has_usage = await conn.scalar(
                    text("SELECT has_schema_privilege(current_user, 'x_extension', 'USAGE')")
                )
                x = await conn.scalar(
                    text("SELECT ST_X(ST_SetSRID(ST_MakePoint(127.0, 37.5), 4326))")
                )
                probe_rows = await conn.scalar(text(f"SELECT count(*)::bigint FROM {_PROBE_TABLE}"))
                probe_owner = await conn.scalar(
                    text("SELECT tableowner FROM pg_tables WHERE tablename = :t"),
                    {"t": _PROBE_TABLE},
                )
        finally:
            await app_engine.dispose()
        assert has_usage is True, "the app role lost USAGE on x_extension"
        assert x == 127.0, "PostGIS must resolve for the app role after the restore"
        assert probe_rows == 3
        assert probe_owner == _APP_ROLE
    finally:
        await _drop_fixture(admin_dsn)
