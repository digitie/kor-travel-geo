"""``db_restore mode=replace_current`` end-to-end against a real, non-empty target (opt-in,
T-292a) + ``record_restore_candidate``'s row_counts accuracy (T-292b).

T-291a's adversarial review flagged that ``replace_current`` — restoring a backup onto the
database that is ALREADY serving it, the only mode that ever skips
``ensure_target_database_empty`` — had never actually been run end-to-end. The existing
``test_replace_current_guards_reject_...`` unit tests only exercise the *rejection* path
(missing confirmation, wrong target, no active maintenance window) by monkeypatching
``build_pg_restore_command`` to raise before it can run — the real ``pg_restore`` invocation
was never exercised against a database that already has every object the dump also creates.

Running it for real surfaced two genuine, previously-undiscovered bugs, both fixed alongside
this test (see ``src/kortravelgeo/infra/backup.py``/``admin_repo.py`` in the same PR):

1. ``build_pg_restore_command`` had no ``--clean --if-exists`` — restoring onto a non-empty
   target (i.e. every real ``replace_current`` restore, since the target IS the live DB)
   failed outright with hundreds of "relation already exists" errors.
2. Even after fixing (1), the restore's OWN bookkeeping artifact row — inserted into
   ``ops.artifacts`` via ``repo``/``engine`` BEFORE ``pg_restore`` runs — turned out to live in
   the exact same database ``--clean --if-exists`` was about to drop-and-recreate from the
   backup's old content (which never had this run's row, since it didn't exist at backup
   time). The finalize step then found its own artifact row gone and raised. Fixed by
   re-inserting the artifact row immediately after a successful ``replace_current`` restore.

Run with a disposable scratch database (bootstrap via ``ktgctl init-db`` + ``alembic stamp
head`` — see ``docs/geocoding-readiness.md``)::

    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:12500/kor_travel_geo_test pytest \
        tests/integration/test_replace_current_restore.py
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from kortravelgeo.dto.admin import MaintenanceWindowCreate
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import run_backup_job, run_restore_job
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine


async def _noop_progress(**_kwargs: Any) -> None:
    return None


async def _fresh_engine_and_settings(tmp_path: Path) -> tuple[AsyncEngine, Settings, str]:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    dest = tmp_path / "dest"
    dest.mkdir(exist_ok=True)
    settings = Settings(
        pg_dsn=dsn,
        backup_temp_dir=tmp_path / "work",
        backup_allowed_dirs=(dest,),
        backup_require_free_space_check=False,
    )
    engine = make_async_engine(settings)
    try:
        database_name = await require_disposable_database(engine)
    except BaseException:
        await engine.dispose()
        raise
    return engine, settings, database_name


@pytest.mark.asyncio
async def test_replace_current_restore_succeeds_end_to_end_against_nonempty_target(
    tmp_path: Path,
) -> None:
    """The core T-292a assertion: a replace_current restore of a backup ONTO the exact
    database it was taken from (the harshest non-empty case — literally every object the
    dump creates already exists) must complete without raising, and must record an active
    serving_releases row with a working FK to the restore's own artifact.

    Unlike this repo's other opt-in integration tests, this one does NOT clean up its own
    rows afterward — a `--clean --if-exists` replace_current restore rewrites the entire
    target database by design, so "restore to pre-test state" isn't meaningful here the way
    it is for tests that only add a few rows to an otherwise-untouched DB. Point
    KTG_TEST_PG_DSN at a database you're fine leaving in a freshly-restored state (or one
    you'll drop/recreate afterward) — require_disposable_database already refuses anything
    that doesn't read as scratch."""
    engine, settings, database_name = await _fresh_engine_and_settings(tmp_path)
    repo = AdminRepository(engine)
    try:
        await run_backup_job(
            engine,
            settings,
            {"destination_dir": str(settings.backup_allowed_dirs[0]), "profile": "serving-ready"},
            asyncio.Event(),
            _noop_progress,
        )
        backups = await repo.list_artifacts(limit=1, artifact_type="db_backup")
        assert backups, "backup did not produce an artifact"
        backup_artifact = backups[0]

        confirmation = f"RESTORE {database_name}"
        window = await repo.create_maintenance_window(
            MaintenanceWindowCreate(
                kind="restore",
                reason="T-292 integration test — replace_current end-to-end",
                confirmation=confirmation,
            )
        )

        # The core assertion: this must not raise.
        await run_restore_job(
            engine,
            settings,
            {
                "artifact_id": backup_artifact.artifact_id,
                "target_database": database_name,
                "mode": "replace_current",
                "confirmation": confirmation,
            },
            asyncio.Event(),
            _noop_progress,
        )

        async with engine.connect() as conn:
            active = (
                await conn.execute(
                    text(
                        "SELECT serving_release_id, release_kind, dataset_snapshot_id"
                        "  FROM ops.serving_releases WHERE state = 'active'"
                    )
                )
            ).mappings().one()
        assert active["release_kind"] == "restore"

        restore_artifacts = await repo.list_artifacts(limit=5, artifact_type="db_restore_log")
        active_release_id = str(active["serving_release_id"])
        matching = [a for a in restore_artifacts if a.serving_release_id == active_release_id]
        assert matching, (
            "the restore's own artifact row must survive (or be recreated) with a working "
            "FK to the new active release — this is exactly what 'restore artifact "
            "disappeared' regressed on"
        )
        assert matching[0].dataset_snapshot_id == str(active["dataset_snapshot_id"])

        await repo.end_maintenance_window(
            maintenance_window_id=window.maintenance_window_id, confirmation=confirmation
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_restore_candidate_prefers_row_counts_override_over_manifest(
    tmp_path: Path,
) -> None:
    """T-292b, isolated from the full restore cycle: when the caller supplies
    row_counts_override (a real post-restore reconcile), it must win over
    source_manifest["row_counts"] (the backup-time snapshot) — the two are deliberately set
    to different values here so a fallback-to-manifest regression fails loudly rather than
    coincidentally matching."""
    engine, _settings, database_name = await _fresh_engine_and_settings(tmp_path)
    repo = AdminRepository(engine)
    restore_artifact_id = str(uuid4())
    release_id: str | None = None
    snapshot_id: str | None = None
    try:
        snapshot, release = await repo.record_restore_candidate(
            restore_artifact_id=restore_artifact_id,
            target_database=database_name,
            source_manifest={
                "row_counts": {"tl_juso_text": 999},  # stale backup-time value — must lose
                "source_set": {"yyyymm_by_kind": {"juso": "202601"}},
            },
            row_counts_override={"tl_juso_text": 42},  # real post-restore value — must win
            activate=False,
        )
        release_id, snapshot_id = release.serving_release_id, snapshot.dataset_snapshot_id
        assert snapshot.row_counts == {"tl_juso_text": 42}
    finally:
        async with engine.begin() as conn:
            if release_id is not None:
                await conn.execute(
                    text("DELETE FROM ops.serving_releases WHERE serving_release_id = :id"),
                    {"id": release_id},
                )
            if snapshot_id is not None:
                await conn.execute(
                    text("DELETE FROM ops.dataset_snapshots WHERE dataset_snapshot_id = :id"),
                    {"id": snapshot_id},
                )
        await engine.dispose()
