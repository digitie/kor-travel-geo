"""T-242 restore-drill: prove a backup is actually restorable.

"Can we restore?" is only truly answered by restoring. This runs a backup into a
**throwaway** database (``<base>_restoretest_<ts>``), reconciles row counts against the
backup manifest (T-233) and runs a smoke test, then **always drops the throwaway DB** —
on success or failure — and returns a PASS/FAIL result with duration and archive size.

Guards keep it from ever touching the live serving DB: the drill target must differ from
the current DSN's database, and the restore runs in ``new_database`` mode (never
``replace_current``). ``restore_drill_target_name``/``guard_drill_target``/
``classify_drill_outcome`` are pure so the policy is unit-tested without a database; the
live restore/drop path is integration-tested in T-244.
"""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Literal

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kortravelgeo.dto.admin import RestoreDrillResult
from kortravelgeo.exceptions import InvalidInputError, NotFoundError
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import (
    BACKUP_ARTIFACT_TYPE,
    cleanup_orphan_restore_target,
    database_name_from_dsn,
    smoke_test_restore,
    validate_database_identifier,
)
from kortravelgeo.infra.backup import (
    run_restore_job as _run_restore_job,
)
from kortravelgeo.infra.restore_reconcile import compare_restore_against_manifest
from kortravelgeo.settings import Settings

_LOGGER = logging.getLogger(__name__)
_MAX_DATABASE_IDENTIFIER_LENGTH = 63


def restore_drill_target_name(base: str, timestamp: str) -> str:
    """Throwaway DB name ``<base>_restoretest_<ts>``, truncated to PostgreSQL's 63 chars."""
    suffix = f"_restoretest_{timestamp}"
    max_prefix = _MAX_DATABASE_IDENTIFIER_LENGTH - len(suffix)
    if max_prefix < 1:
        msg = "restore-drill timestamp suffix is too long"
        raise InvalidInputError(msg)
    return validate_database_identifier(f"{base[:max_prefix]}{suffix}", "drill_target")


def guard_drill_target(temp_database: str, current_database: str | None) -> None:
    """Refuse to drill into the live serving DB (the whole point is to never touch it)."""
    if current_database is not None and temp_database == current_database:
        msg = "restore-drill target must differ from the current serving database"
        raise InvalidInputError(msg)


def classify_drill_outcome(
    *, restored: bool, reconcile_ok: bool | None, smoke_ok: bool | None
) -> Literal["PASS", "FAIL"]:
    """PASS only if the restore completed and neither reconcile nor smoke failed.

    ``reconcile_ok``/``smoke_ok`` of ``None`` means "not evaluated" (e.g. legacy manifest
    with no row_counts) — not a failure on its own, but the restore must still have run.
    """
    if not restored:
        return "FAIL"
    if reconcile_ok is False or smoke_ok is False:
        return "FAIL"
    return "PASS"


def _drill_target_dsn(pg_dsn: str, temp_database: str) -> str:
    return make_url(pg_dsn).set(database=temp_database).render_as_string(hide_password=False)


async def _create_drill_database(temp_dsn: str) -> None:
    url = make_url(temp_dsn)
    database = validate_database_identifier(url.database or "", "drill_target")
    maintenance_engine = create_async_engine(
        str(url.set(database="postgres")), isolation_level="AUTOCOMMIT"
    )
    try:
        async with maintenance_engine.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        await maintenance_engine.dispose()


async def run_restore_drill(
    engine: AsyncEngine,
    settings: Settings,
    *,
    timestamp: str,
    artifact_id: str | None = None,
    archive_path: str | None = None,
    base_database: str | None = None,
    jobs: int | None = None,
) -> RestoreDrillResult:
    """Restore a backup into a throwaway DB, reconcile + smoke, then always drop it (T-242).

    ``timestamp`` (e.g. ``20260616T120000Z``) names the throwaway DB deterministically so a
    caller controls it (the function does not read the clock). Either ``artifact_id`` or
    ``archive_path`` selects the backup; ``artifact_id`` also supplies the manifest for
    reconcile and the archive size for the result.
    """
    started = perf_counter()
    repo = AdminRepository(engine)
    current_database = database_name_from_dsn(settings.pg_dsn)
    base = base_database or current_database or "kor_travel_geo"
    temp_database = restore_drill_target_name(base, timestamp)
    guard_drill_target(temp_database, current_database)
    temp_dsn = _drill_target_dsn(settings.pg_dsn, temp_database)

    manifest = None
    archive_size_bytes: int | None = None
    if artifact_id is not None:
        artifact = await repo.get_artifact(artifact_id)
        if artifact is None:
            msg = f"backup artifact not found: {artifact_id}"
            raise NotFoundError(msg)
        if artifact.artifact_type != BACKUP_ARTIFACT_TYPE:
            msg = f"artifact is not a db_backup: {artifact_id}"
            raise InvalidInputError(msg)
        manifest = artifact.manifest
        archive_size_bytes = artifact.size_bytes

    errors: list[str] = []
    restored = False
    reconcile = None
    reconcile_ok: bool | None = None
    smoke_ok: bool | None = None
    created = False
    try:
        await _create_drill_database(temp_dsn)
        created = True
        payload = {
            "target_database": temp_database,
            "mode": "new_database",
            "run_analyze": True,
            "run_smoke_test": False,
            "run_row_count_check": False,
        }
        if artifact_id is not None:
            payload["artifact_id"] = artifact_id
        if archive_path is not None:
            payload["archive_path"] = archive_path
        if jobs is not None:
            payload["jobs"] = jobs
        await _run_restore_job(engine, settings, payload, asyncio.Event(), _drill_progress)
        restored = True
        if manifest is not None:
            reconcile = await compare_restore_against_manifest(manifest, temp_dsn)
            reconcile_ok = reconcile.ok
        try:
            await smoke_test_restore(temp_dsn)
            smoke_ok = True
        except Exception as exc:
            # A drill records a smoke failure as FAIL; it must not raise past cleanup.
            smoke_ok = False
            errors.append(f"smoke: {exc}")
    except Exception as exc:
        # Any restore failure is captured as a FAIL result (the drill still cleans up).
        errors.append(f"restore: {exc}")
    finally:
        cleanup_ok = await _drop_drill_database(temp_dsn, timestamp) if created else True

    status = classify_drill_outcome(
        restored=restored, reconcile_ok=reconcile_ok, smoke_ok=smoke_ok
    )
    return RestoreDrillResult(
        status=status,
        temp_database=temp_database,
        duration_seconds=round(perf_counter() - started, 3),
        restored=restored,
        cleanup_ok=cleanup_ok,
        reconcile_ok=reconcile_ok,
        smoke_ok=smoke_ok,
        archive_size_bytes=archive_size_bytes,
        source_artifact_id=artifact_id,
        reconcile=reconcile,
        errors=tuple(errors),
    )


async def _drop_drill_database(temp_dsn: str, timestamp: str) -> bool:
    """Best-effort drop of the throwaway DB; never raises (cleanup must not mask results)."""
    try:
        await cleanup_orphan_restore_target(temp_dsn, action="drop", timestamp=timestamp)
        return True
    except Exception:
        _LOGGER.warning("restore-drill: failed to drop throwaway DB", exc_info=True)
        return False


async def _drill_progress(
    *, progress: float | None = None, stage: str | None = None, message: str | None = None
) -> None:
    if message is not None:
        _LOGGER.debug("restore-drill [%s] %s", stage, message)
