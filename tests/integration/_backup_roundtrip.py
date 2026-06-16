"""Reusable backup→restore round-trip helpers (T-244 fixture foundation).

Not a test module (leading underscore → pytest skips collection). T-244 uses these to
verify a full ``run_backup_job`` → ``.tar.zst`` → ``run_restore_job`` round-trip; T-245
(fault injection) reuses the same setup/backup/restore/cleanup steps with a corrupted
archive. Everything is opt-in: callers ``pytest.skip`` unless ``KTG_TEST_PG_DSN`` and the
backup CLI tools are present, so CI (which sets neither) stays green.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from pathlib import Path

from kortravelgeo.infra.backup import (
    BACKUP_ARTIFACT_TYPE,
    collect_row_counts,
    run_backup_job,
    run_restore_job,
)
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.sql import INDEX_SQL, MV_SQL, SCHEMA_SQL, iter_sql_statements
from kortravelgeo.settings import Settings

#: A control table outside ROW_COUNT_OBJECTS whose rows we own end-to-end, so the round-trip
#: proves *data* (not just schema) survives backup+restore — independent of the constrained
#: serving tables.
_PROBE_TABLE = "_ktg_roundtrip_probe"
_PROBE_ROWS = 3
_REQUIRED_TOOLS = ("pg_dump", "pg_restore", "tar", "zstd")


def missing_requirement() -> str | None:
    """Return a skip reason if this environment can't run a live round-trip, else ``None``."""
    if not os.getenv("KTG_TEST_PG_DSN"):
        return "set KTG_TEST_PG_DSN to run the live backup→restore round-trip"
    missing = [tool for tool in _REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        return f"backup tools not installed: {', '.join(missing)}"
    return None


async def _noop_progress(
    *, progress: float | None = None, stage: str | None = None, message: str | None = None
) -> None:
    return None


async def build_minimal_serving_schema(engine: AsyncEngine) -> None:
    """Create the serving schema (tables/indexes/MVs) + a seeded probe table, idempotently."""
    async with engine.begin() as conn:
        for sql in iter_sql_statements(SCHEMA_SQL):
            await conn.execute(text(sql))
        for sql in iter_sql_statements(INDEX_SQL):
            await conn.execute(text(sql))
        for sql in iter_sql_statements(MV_SQL):
            await conn.execute(text(sql))
        await conn.execute(
            text(f"CREATE TABLE IF NOT EXISTS {_PROBE_TABLE} (id INTEGER PRIMARY KEY, note TEXT)")
        )
        await conn.execute(text(f"TRUNCATE {_PROBE_TABLE}"))
        for i in range(_PROBE_ROWS):
            await conn.execute(
                text(f"INSERT INTO {_PROBE_TABLE} (id, note) VALUES (:id, :note)"),
                {"id": i, "note": f"roundtrip-{i}"},
            )


async def capture_round_trip_state(engine: AsyncEngine) -> tuple[dict[str, int], int]:
    """Capture (ROW_COUNT_OBJECTS counts, probe row count) for original-vs-restored compare."""
    async with engine.connect() as conn:
        counts = await collect_row_counts(conn)
        probe = await conn.scalar(text(f"SELECT count(*)::bigint FROM {_PROBE_TABLE}"))
    return counts, int(probe or 0)


def roundtrip_settings(source_dsn: str, work_root: Path) -> Settings:
    backups = work_root / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    return Settings(
        pg_dsn=source_dsn,
        backup_allowed_dirs=(backups,),
        backup_temp_dir=work_root / "tmp",
        backup_require_free_space_check=False,
    )


async def make_backup(engine: AsyncEngine, settings: Settings) -> str:
    """Run a full backup job and return the resulting db_backup artifact_id."""
    from kortravelgeo.infra.admin_repo import AdminRepository

    payload = {"profile": "serving-ready", "jobs": 2, "compression_level": 3}
    await run_backup_job(engine, settings, payload, asyncio.Event(), _noop_progress)
    artifacts = await AdminRepository(engine).list_artifacts(
        limit=1, artifact_type=BACKUP_ARTIFACT_TYPE, state="available"
    )
    if not artifacts:
        msg = "backup did not produce an available artifact"
        raise AssertionError(msg)
    return artifacts[0].artifact_id


async def restore_into_new_database(
    engine: AsyncEngine, settings: Settings, *, artifact_id: str, target_database: str
) -> None:
    """Create an empty target DB and run a full restore job (pg_restore/analyze/smoke)."""
    await create_database(settings.pg_dsn, target_database)
    payload = {
        "artifact_id": artifact_id,
        "target_database": target_database,
        "mode": "new_database",
        "run_analyze": True,
        "run_smoke_test": True,
        "run_row_count_check": True,
    }
    await run_restore_job(engine, settings, payload, asyncio.Event(), _noop_progress)


@dataclass(frozen=True)
class RoundTripResult:
    original_counts: dict[str, int]
    restored_counts: dict[str, int]
    original_probe: int
    restored_probe: int


async def run_backup_restore_round_trip(work_root: Path, target_database: str) -> RoundTripResult:
    """Full round-trip: build → backup → restore → compare; always drops the target DB."""
    source_dsn = os.environ["KTG_TEST_PG_DSN"]
    settings = roundtrip_settings(source_dsn, work_root)
    source_engine = make_async_engine(settings)
    try:
        await build_minimal_serving_schema(source_engine)
        original_counts, original_probe = await capture_round_trip_state(source_engine)
        artifact_id = await make_backup(source_engine, settings)
        target_dsn = _dsn_for_database(source_dsn, target_database)
        try:
            await restore_into_new_database(
                source_engine, settings, artifact_id=artifact_id, target_database=target_database
            )
            target_engine = make_async_engine(Settings(pg_dsn=target_dsn))
            try:
                restored_counts, restored_probe = await capture_round_trip_state(target_engine)
            finally:
                await target_engine.dispose()
        finally:
            await drop_database(source_dsn, target_database)
    finally:
        await source_engine.dispose()
    return RoundTripResult(
        original_counts=original_counts,
        restored_counts=restored_counts,
        original_probe=original_probe,
        restored_probe=restored_probe,
    )


def _dsn_for_database(dsn: str, database: str) -> str:
    return make_url(dsn).set(database=database).render_as_string(hide_password=False)


async def create_database(dsn: str, database: str) -> None:
    await _admin_exec(dsn, f'CREATE DATABASE "{database}"')


async def drop_database(dsn: str, database: str) -> None:
    await _admin_exec(
        dsn,
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{database}' AND pid <> pg_backend_pid()",
    )
    await _admin_exec(dsn, f'DROP DATABASE IF EXISTS "{database}"')


async def _admin_exec(dsn: str, statement: str) -> None:
    engine = create_async_engine(
        _dsn_for_database(dsn, "postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement))
    finally:
        await engine.dispose()
