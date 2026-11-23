"""T-230 backup retention janitor.

Removes expired backup archives so a low-reliability single-host server does not
fill its disk with old ``.tar.zst`` files. Unlike the source-archive policy
(ADR-052) where deletion is gated, ``db_backup`` archives are regenerable, so
expiry is allowed by default — with two guards:

1. ``retention_class='pinned'`` backups are never expired.
2. the newest ``keep_min_count`` available backups are always kept, even if expired.

Before applying the policy the pass reconciles the catalog with the disk: an
``available`` local-file backup whose archive is gone (removed outside the app, e.g. a
manual disk clean-up) is marked ``deleted`` and audited as ``db_backup.archive_missing``.
Otherwise such a phantom row keeps counting toward ``keep_min`` (protecting one fewer
real archive), and the restore drill — which picks the newest ``available`` backup —
fails on it. The check only fires when the backup root that should hold the archive is
present, so a container started without the backup mount does not wipe the catalog.

The pass runs under the global ``BACKUP_JANITOR`` advisory lock; if another pass
holds it, this one returns ``skipped_locked=True`` without touching anything.
``select_expired_backups`` is a pure function so the policy is unit-tested without
a database.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.dto.admin import BackupRetentionResult, OpsArtifact
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import (
    BACKUP_ARTIFACT_TYPE,
    allowed_backup_roots,
    resolve_existing_archive_path,
)
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)
from kortravelgeo.settings import Settings

_LOGGER = logging.getLogger(__name__)

PINNED_RETENTION_CLASS = "pinned"


@dataclass(frozen=True, slots=True)
class BackupRetentionSelection:
    eligible_ids: tuple[str, ...]
    protected_ids: tuple[str, ...]


def select_expired_backups(
    artifacts: Sequence[OpsArtifact],
    *,
    now: datetime,
    keep_min_count: int,
) -> BackupRetentionSelection:
    """Pure policy: which available backups are eligible to expire.

    Newest ``keep_min_count`` are protected; ``pinned`` are protected; the rest are
    eligible iff ``expires_at`` is set and has passed ``now``.
    """
    ordered = sorted(artifacts, key=lambda a: a.created_at, reverse=True)
    keep = max(0, keep_min_count)
    protected = {a.artifact_id for a in ordered[:keep]}
    eligible: list[str] = []
    for artifact in ordered:
        if artifact.artifact_id in protected:
            continue
        if (artifact.retention_class or "default") == PINNED_RETENTION_CLASS:
            continue
        if artifact.expires_at is None or artifact.expires_at > now:
            continue
        eligible.append(artifact.artifact_id)
    return BackupRetentionSelection(eligible_ids=tuple(eligible), protected_ids=tuple(protected))


LOCAL_FILE_STORAGE_KIND = "local_file"


def find_missing_archives(
    artifacts: Sequence[OpsArtifact],
    *,
    roots: Sequence[Path],
    is_dir: Callable[[Path], bool],
    is_file: Callable[[Path], bool],
) -> tuple[str, ...]:
    """Pure policy: ids of ``available`` local-file backups whose archive is gone.

    A row counts as missing only when (1) it is a ``local_file`` artifact with a
    ``storage_uri``, (2) that path lies under one of the allowed backup ``roots``, (3) that
    root directory exists (so an unmounted/misconfigured backup volume never reads as
    "every archive was deleted"), and (4) the archive itself is not a file. Rows outside
    every allowed root are left alone — the janitor cannot vouch for them.
    """
    missing: list[str] = []
    for artifact in artifacts:
        if artifact.state != "available":
            continue
        if artifact.storage_kind != LOCAL_FILE_STORAGE_KIND or not artifact.storage_uri:
            continue
        path = Path(artifact.storage_uri)
        owning_roots = [root for root in roots if path == root or root in path.parents]
        if not owning_roots or not any(is_dir(root) for root in owning_roots):
            continue
        if not is_file(path):
            missing.append(artifact.artifact_id)
    return tuple(missing)


async def run_backup_retention_janitor(
    engine: AsyncEngine,
    settings: Settings,
    *,
    dry_run: bool = False,
    keep_min_count: int | None = None,
    now: datetime | None = None,
    actor_id: str = "system:backup_janitor",
) -> BackupRetentionResult:
    keep = settings.backup_retention_keep_min if keep_min_count is None else keep_min_count
    effective_now = now if isinstance(now, datetime) else datetime.now(UTC)
    repo = AdminRepository(engine)
    key = AdvisoryLockKey.global_key(AdvisoryLockNamespace.BACKUP_JANITOR)
    try:
        async with cross_process_lock(engine, key):
            orphaned_ids = await _settle_orphaned_creating_backups(
                repo, dry_run=dry_run, actor_id=actor_id
            )
            artifacts = await repo.list_artifacts(
                limit=1000, artifact_type=BACKUP_ARTIFACT_TYPE, state="available"
            )
            missing_ids = find_missing_archives(
                artifacts,
                roots=allowed_backup_roots(settings),
                is_dir=Path.is_dir,
                is_file=Path.is_file,
            )
            if not dry_run:
                for artifact_id in missing_ids:
                    await repo.update_artifact(artifact_id, state="deleted")
                    await repo.record_audit_event(
                        action="db_backup.archive_missing",
                        actor_type="system",
                        actor_id=actor_id,
                        outcome="succeeded",
                        resource_type="artifact",
                        resource_id=artifact_id,
                        payload={"reason": "archive_missing_on_disk"},
                    )
                    _LOGGER.warning(
                        "backup retention: archive missing on disk, marked deleted: %s",
                        artifact_id,
                    )
            missing = set(missing_ids)
            present = [a for a in artifacts if a.artifact_id not in missing]
            selection = select_expired_backups(
                present, now=effective_now, keep_min_count=keep
            )
            by_id = {a.artifact_id: a for a in artifacts}
            expired_ids: list[str] = []
            failed_ids: list[str] = []
            for artifact_id in selection.eligible_ids:
                artifact = by_id[artifact_id]
                if dry_run:
                    expired_ids.append(artifact_id)
                    continue
                try:
                    if artifact.storage_uri:
                        with suppress(FileNotFoundError):
                            resolve_existing_archive_path(
                                artifact.storage_uri, settings
                            ).unlink()
                    await repo.update_artifact(artifact_id, state="expired")
                    await repo.record_audit_event(
                        action="db_backup.expire",
                        actor_type="system",
                        actor_id=actor_id,
                        outcome="succeeded",
                        resource_type="artifact",
                        resource_id=artifact_id,
                        payload={"reason": "retention_expired", "keep_min_count": keep},
                    )
                    expired_ids.append(artifact_id)
                except Exception:
                    _LOGGER.exception("backup retention: failed to expire %s", artifact_id)
                    failed_ids.append(artifact_id)
            result = BackupRetentionResult(
                dry_run=dry_run,
                keep_min_count=keep,
                scanned=len(artifacts),
                protected_count=len(selection.protected_ids),
                expired_count=len(expired_ids),
                failed_count=len(failed_ids),
                expired_artifact_ids=tuple(expired_ids),
                failed_artifact_ids=tuple(failed_ids),
                missing_count=len(missing_ids),
                missing_artifact_ids=missing_ids,
                orphaned_count=len(orphaned_ids),
                orphaned_artifact_ids=orphaned_ids,
            )
            _LOGGER.info("backup retention janitor ran", extra={"result": result.model_dump()})
            return result
    except ConcurrentExecutionError:
        _LOGGER.info("backup retention janitor skipped: lock held by another process")
        return BackupRetentionResult(dry_run=dry_run, keep_min_count=keep, skipped_locked=True)


_TERMINAL_UNSUCCESSFUL_JOB_STATES = frozenset({"failed", "cancelled"})


def is_orphaned_creating_backup(artifact: OpsArtifact, job_state: str | None) -> bool:
    """Pure policy: a ``creating`` backup whose owning job already failed or was cancelled.

    The job's own failure path marks its artifact ``failed``, but a job that the reconciler
    converges to ``failed`` (worker vanished, lease expired — or a DB restored from a dump
    taken mid-backup) never runs that path, so the artifact stays ``creating`` forever. It
    then reads as the most recent non-failed scheduled backup in the due-check
    (``backup_schedule._last_scheduled_backup_at``) and lingers in the catalog. Only a
    terminal *unsuccessful* job settles it; a missing job id or a live job is left alone.
    """
    return artifact.state == "creating" and job_state in _TERMINAL_UNSUCCESSFUL_JOB_STATES


async def _settle_orphaned_creating_backups(
    repo: AdminRepository, *, dry_run: bool, actor_id: str
) -> tuple[str, ...]:
    """Mark ``creating`` backups of failed/cancelled jobs as ``failed`` (catalog only).

    No file is touched: a crashed job may have left a partial archive, and deleting files
    from a catalog guess is not this pass's call.
    """
    creating = await repo.list_artifacts(
        limit=1000, artifact_type=BACKUP_ARTIFACT_TYPE, state="creating"
    )
    orphaned: list[str] = []
    for artifact in creating:
        if not artifact.job_id:
            continue
        job = await repo.get_load_job(artifact.job_id)
        if job is None or not is_orphaned_creating_backup(artifact, job.state):
            continue
        orphaned.append(artifact.artifact_id)
        if dry_run:
            continue
        await repo.update_artifact(artifact.artifact_id, state="failed")
        await repo.record_audit_event(
            action="db_backup.orphan_settled",
            actor_type="system",
            actor_id=actor_id,
            outcome="succeeded",
            resource_type="artifact",
            resource_id=artifact.artifact_id,
            payload={"reason": "owning_job_terminal", "job_state": job.state},
        )
    return tuple(orphaned)
