"""``db_restore mode=replace_current`` end-to-end against a real, non-empty target (opt-in,
T-292a) + ``record_restore_candidate``'s row_counts accuracy (T-292b).

T-291a's adversarial review flagged that ``replace_current`` — restoring a backup onto the
database that is ALREADY serving it, the only mode that ever skips
``ensure_target_database_empty`` — had never actually been run end-to-end. The existing
``test_replace_current_guards_reject_...`` unit tests only exercise the *rejection* path
(missing confirmation, wrong target, no active maintenance window) by monkeypatching
``build_pg_restore_command`` to raise before it can run — the real ``pg_restore`` invocation
was never exercised against a database that already has every object the dump also creates.

Running it for real (with a real ``job_id``, matching how ``replace_current`` is actually
invoked in production via ``POST /admin/restores`` — the CLI has no flag for this mode at
all) surfaced THREE genuine, previously-undiscovered bugs, all fixed alongside this test (see
``src/kortravelgeo/infra/backup.py``/``admin_repo.py`` in the same PR):

1. ``build_pg_restore_command`` had no ``--clean --if-exists`` — restoring onto a non-empty
   target (i.e. every real ``replace_current`` restore, since the target IS the live DB)
   failed outright with hundreds of "relation already exists" errors.
2. Even after fixing (1): ``replace_current``'s target IS the database ``repo``/``engine``
   are already connected to, so ``--clean --if-exists`` doesn't just wipe address-serving
   data — it drops and recreates EVERY table in the whole database, including ``ops.*`` and
   ``load_jobs``, from the backup's OLD content. Every row this function (or its caller)
   wrote into any of those tables before ``pg_restore`` ran — the restore's own
   ``ops.artifacts`` bookkeeping row, the ``load_jobs`` row a real caller always creates
   first, and the ``ops.maintenance_windows`` row required to even reach this code — is gone
   the same way, because none of them existed yet when the backup was taken. Two distinct,
   serious failure modes followed: the finalize step couldn't find its own artifact row and
   raised outright, and (found only when testing with a REAL, non-``None`` ``job_id`` — a
   first attempt at this fix that only re-inserted the artifact row passed its own test but
   would have hit a `ForeignKeyViolation` on `job_id` in every real invocation, since
   `ops.artifacts.job_id` references the now-also-wiped `load_jobs`) the same wipe silently
   killed the running job's OWN progress/heartbeat/cancel tracking and, separately, made
   ``end_maintenance_window`` 404 after every real restore (a documented runbook step —
   see ``docs/t050-ops-hardening.md``). Fixed by snapshotting the ``load_jobs`` and
   ``ops.maintenance_windows`` rows before ``pg_restore`` runs and re-inserting all three
   rows (``load_jobs`` first — the other two both FK-reference it) immediately after a
   successful ``replace_current`` restore.
3. (T-292b) ``record_restore_candidate`` used the backup-time manifest's ``row_counts``
   instead of the real post-restore reconcile counts, which is the canonical "what's now
   being served" figure for ``activate=True``. Fixed via a new ``row_counts_override``
   parameter.

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
from kortravelgeo.infra.backup import (
    _snapshot_restore_audit_events,
    run_backup_job,
    run_restore_job,
)
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.load_job_executor import LoadJobExecutor
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
    database it was taken from — the target is guaranteed non-empty (every object the dump
    creates already exists), though a schema-drifted OLDER backup restored onto a target
    that's since migrated further is a harsher, currently-untested scenario this doesn't
    cover — must complete without raising, with a REAL job_id (every production invocation
    has one; job_id=None would hide the ForeignKeyViolation this test is specifically here
    to catch), and must leave every piece of bookkeeping this restore touched in a working
    state: the active release's FK to the restore's own artifact, the artifact's FK to the
    job, the job's own post-restore progress tracking, the recorded row_counts (real
    reconcile values, not the stale backup-time manifest), and the maintenance window's
    ability to actually close afterward.

    Unlike this repo's other opt-in integration tests, this one does NOT clean up its own
    rows afterward — a `--clean --if-exists` replace_current restore rewrites the entire
    target database by design, so "restore to pre-test state" isn't meaningful here the way
    it is for tests that only add a few rows to an otherwise-untouched DB. Point
    KTG_TEST_PG_DSN at a database you're fine leaving in a freshly-restored state (or one
    you'll drop/recreate afterward) — require_disposable_database already refuses anything
    that doesn't read as scratch."""
    engine, settings, database_name = await _fresh_engine_and_settings(tmp_path)
    repo = AdminRepository(engine)
    executor = LoadJobExecutor(engine)
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
        # A real job_id — every actual replace_current invocation has one (POST
        # /admin/restores always creates this row first). job_id=None would silently hide
        # the ForeignKeyViolation this test exists to catch.
        job = await repo.insert_load_job(kind="db_restore", payload={"mode": "replace_current"})

        # The core assertion: this must not raise — neither the original "already exists"
        # pg_restore failure, nor the "restore artifact disappeared" bookkeeping failure,
        # nor (with a real job_id) a ForeignKeyViolation on ops.artifacts.job_id.
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
            job_id=job.job_id,
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
        # The artifact's job_id FK must still resolve — this is exactly the
        # ForeignKeyViolation a job_id=None test would never see.
        assert matching[0].job_id == job.job_id

        # T-292b, exercised through the REAL run_restore_job wiring (not just the isolated
        # record_restore_candidate call below) — row_counts must be the actual restored
        # counts, not the stale backup-time manifest values.
        async with engine.connect() as conn:
            snapshot_row_counts = await conn.scalar(
                text(
                    "SELECT row_counts FROM ops.dataset_snapshots"
                    " WHERE dataset_snapshot_id = :id"
                ),
                {"id": str(active["dataset_snapshot_id"])},
            )
        assert snapshot_row_counts, "row_counts must be populated from the reconcile result"

        # The job's own post-restore progress tracking must still work — this is what
        # regressed silently (no exception, just permanently frozen job state) before the
        # load_jobs row was re-inserted.
        await executor.set_progress(job.job_id, progress=1.0, stage="done")
        await executor.mark_done(job.job_id)
        async with engine.connect() as conn:
            job_state = await conn.scalar(
                text("SELECT state FROM load_jobs WHERE job_id = :id"), {"id": job.job_id}
            )
        assert job_state == "done", (
            "load_jobs progress tracking must survive the restore — a regression here is "
            "silent (no exception), just a job that never leaves 'running'"
        )

        # The maintenance window must actually close — before the fix, this returned None
        # (row wiped, same mechanism as the artifact bug) and the client-level API would
        # 404 an operator's routine "close the window" step after every real restore.
        ended = await repo.end_maintenance_window(
            maintenance_window_id=window.maintenance_window_id, confirmation=confirmation
        )
        assert ended is not None, (
            "end_maintenance_window must find the window row post-restore — None here means "
            "a real operator's runbook step (docs/t050-ops-hardening.md) 404s after every "
            "production replace_current restore"
        )
        assert ended.state == "ended"

        # T-296a: the maintenance_window.authorize audit event, logged just before pg_restore
        # ran, must survive too — wiped by the same --clean mechanism as the other rows.
        async with engine.connect() as conn:
            audit_row = (
                await conn.execute(
                    text(
                        "SELECT outcome, resource_id, job_id"
                        "  FROM ops.audit_events"
                        " WHERE action = 'maintenance_window.authorize'"
                        "   AND resource_id = :window_id"
                    ),
                    {"window_id": window.maintenance_window_id},
                )
            ).mappings().one_or_none()
        assert audit_row is not None, (
            "the maintenance_window.authorize audit event must survive the restore — a "
            "regression here is silent (no exception), just a missing audit trail entry"
        )
        assert audit_row["outcome"] == "succeeded"
        assert audit_row["job_id"] == job.job_id

        # T-296b: the source backup artifact's OWN ops.artifacts row — a DIFFERENT row from
        # the restore-log artifact checked above — must come back exactly as it was before
        # the restore (state='available', real checksum), not the stale state='creating'
        # copy pg_restore recreates from the backup's own (pre-finalization) dump content.
        async with engine.connect() as conn:
            source_artifact_row = (
                await conn.execute(
                    text(
                        "SELECT state, sha256, size_bytes"
                        "  FROM ops.artifacts WHERE artifact_id = :id"
                    ),
                    {"id": backup_artifact.artifact_id},
                )
            ).mappings().one()
        assert source_artifact_row["state"] == "available", (
            "the source backup artifact's row must come back in its finalized state, not the "
            "stale 'creating' snapshot pg_restore's --clean recreates from the backup's own "
            "(pre-finalization) dump content"
        )
        assert source_artifact_row["sha256"] == backup_artifact.sha256
        assert source_artifact_row["size_bytes"] == backup_artifact.size_bytes
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


@pytest.mark.asyncio
async def test_snapshot_restore_audit_events_finds_all_setup_events_by_job_id_or_window(
    tmp_path: Path,
) -> None:
    """T-296 follow-up (from adversarial review of the initial T-296a fix): a real
    ``replace_current`` restore's audit trail isn't just the ``maintenance_window.authorize``
    event this module itself writes — the API router writes ``db_restore.submit`` (keyed by
    ``job_id``, no ``resource_id`` tie to the window) and the client writes
    ``maintenance_window.create`` (keyed by ``resource_id`` = the window id, no ``job_id`` yet
    at that point, since the window is opened before the restore job exists). This exercises
    ``_snapshot_restore_audit_events`` directly against all three shapes plus an unrelated
    event that must NOT match, rather than through the full router/client stack (the
    end-to-end test above calls ``AdminRepository`` directly, bypassing the router/client
    layers that actually write ``db_restore.submit``/``maintenance_window.create``)."""
    engine, _settings, database_name = await _fresh_engine_and_settings(tmp_path)
    repo = AdminRepository(engine)
    job = await repo.insert_load_job(kind="db_restore", payload={"mode": "replace_current"})
    confirmation = f"RESTORE {database_name}"
    window = await repo.create_maintenance_window(
        MaintenanceWindowCreate(
            kind="restore",
            reason="T-296 _snapshot_restore_audit_events coverage",
            confirmation=confirmation,
        )
    )
    try:
        # maintenance_window.create shape: resource_id = window id, job_id = None.
        create_event = await repo.record_audit_event(
            action="maintenance_window.create",
            actor_type="system",
            outcome="started",
            payload={},
            resource_type="maintenance_window",
            resource_id=window.maintenance_window_id,
        )
        # db_restore.submit shape: job_id set, resource_id = job_id (not the window).
        submit_event = await repo.record_audit_event(
            action="db_restore.submit",
            actor_type="system",
            outcome="started",
            payload={},
            resource_type="load_job",
            resource_id=job.job_id,
            job_id=job.job_id,
        )
        # maintenance_window.authorize shape: both job_id and resource_id = window id.
        authorize_event = await repo.record_audit_event(
            action="maintenance_window.authorize",
            actor_type="system",
            outcome="succeeded",
            payload={},
            resource_type="maintenance_window",
            resource_id=window.maintenance_window_id,
            job_id=job.job_id,
        )
        # An unrelated event with neither this job_id nor this resource_id — must NOT match.
        unrelated_job = await repo.insert_load_job(kind="db_backup", payload={})
        unrelated_event = await repo.record_audit_event(
            action="db_backup.submit",
            actor_type="system",
            outcome="started",
            payload={},
            resource_type="load_job",
            resource_id=unrelated_job.job_id,
            job_id=unrelated_job.job_id,
        )

        snapshots = await _snapshot_restore_audit_events(
            engine, job_id=job.job_id, maintenance_window_id=window.maintenance_window_id
        )
        found_ids = {str(row["audit_event_id"]) for row in snapshots}

        assert found_ids == {
            create_event.audit_event_id,
            submit_event.audit_event_id,
            authorize_event.audit_event_id,
        }
        assert unrelated_event.audit_event_id not in found_ids
    finally:
        await engine.dispose()
