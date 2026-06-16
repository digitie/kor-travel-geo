"""Reusable hot-swap/rollback round-trip helpers (T-246).

Builds on ``_backup_roundtrip`` to exercise the *live* ADR-036 rename hot-swap (T-241) and the
manual rollback (T-264) end to end: stand up an isolated "current" serving DB on the
``KTG_TEST_PG_DSN`` cluster, back it up, restore into a fresh DB (tagged with a marker row so we
can prove which physical DB is actually serving), then swap and roll back. Opt-in like the rest
of the backup integration suite (``missing_requirement``). Every DB it creates is dropped on
exit — even after the renames shuffle names around — so a re-run starts clean.

Not a test module (leading underscore → pytest skips collection).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._backup_roundtrip import (
    _PROBE_TABLE,
    _dsn_for_database,
    build_minimal_serving_schema,
    create_database,
    drop_database,
    make_backup,
    restore_into_new_database,
    roundtrip_settings,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

#: A row written into the *restored* DB's probe table (and nowhere else) so a "serving DB has
#: the marker" check proves which physical database the current name resolves to after a rename.
_MARKER_ID = 999
_MARKER_NOTE = "restored-marker"


@dataclass(frozen=True)
class HotSwapHarness:
    """Names + settings for one isolated hot-swap round-trip on the test cluster."""

    source_dsn: str
    current_database: str
    restore_database: str
    previous_alias: str
    settings: Settings  # settings.pg_dsn resolves to ``current_database``
    artifact_id: str

    @property
    def candidate_databases(self) -> tuple[str, ...]:
        """Every DB name that may exist at teardown (renames move data between these)."""
        return (self.current_database, self.restore_database, self.previous_alias)


async def _insert_marker(source_dsn: str, database: str) -> None:
    engine = make_async_engine(Settings(pg_dsn=_dsn_for_database(source_dsn, database)))
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"INSERT INTO {_PROBE_TABLE} (id, note) VALUES (:id, :note)"),
                {"id": _MARKER_ID, "note": _MARKER_NOTE},
            )
    finally:
        await engine.dispose()


async def serving_has_marker(source_dsn: str, database: str) -> bool:
    """True if ``database`` carries the restored-DB marker row (proves it is the restored DB)."""
    engine = make_async_engine(Settings(pg_dsn=_dsn_for_database(source_dsn, database)))
    try:
        async with engine.connect() as conn:
            value = await conn.scalar(
                text(f"SELECT count(*)::bigint FROM {_PROBE_TABLE} WHERE id = :id"),
                {"id": _MARKER_ID},
            )
        return int(value or 0) > 0
    finally:
        await engine.dispose()


async def database_exists(source_dsn: str, database: str) -> bool:
    engine = make_async_engine(Settings(pg_dsn=_dsn_for_database(source_dsn, "postgres")))
    try:
        async with engine.connect() as conn:
            value = await conn.scalar(
                text("SELECT count(*)::bigint FROM pg_database WHERE datname = :name"),
                {"name": database},
            )
        return int(value or 0) > 0
    finally:
        await engine.dispose()


@asynccontextmanager
async def hot_swap_harness(work_root: Path) -> AsyncIterator[HotSwapHarness]:
    """Build current+restore DBs (restore tagged with a marker); drop all candidates on exit."""
    source_dsn = os.environ["KTG_TEST_PG_DSN"]
    token = uuid4().hex[:8]
    current_database = f"ktg_t246_cur_{token}"
    restore_database = f"ktg_t246_res_{token}"
    previous_alias = f"ktg_t246_prev_{token}"
    settings = roundtrip_settings(_dsn_for_database(source_dsn, current_database), work_root)
    try:
        await create_database(source_dsn, current_database)
        current_engine = make_async_engine(settings)
        try:
            await build_minimal_serving_schema(current_engine)
            artifact_id = await make_backup(current_engine, settings)
            # Restore into a fresh DB, then tag it so we can tell it apart from the original.
            await restore_into_new_database(
                current_engine,
                settings,
                artifact_id=artifact_id,
                target_database=restore_database,
            )
        finally:
            await current_engine.dispose()
        await _insert_marker(source_dsn, restore_database)
        yield HotSwapHarness(
            source_dsn=source_dsn,
            current_database=current_database,
            restore_database=restore_database,
            previous_alias=previous_alias,
            settings=settings,
            artifact_id=artifact_id,
        )
    finally:
        # Renames shuffle which name holds which data; drop every candidate (IF EXISTS).
        for database in (current_database, restore_database, previous_alias):
            await drop_database(source_dsn, database)
