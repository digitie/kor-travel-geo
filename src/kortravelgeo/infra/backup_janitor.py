"""T-230 backup retention janitor.

Removes expired backup archives so a low-reliability single-host server does not
fill its disk with old ``.tar.zst`` files. Unlike the source-archive policy
(ADR-052) where deletion is gated, ``db_backup`` archives are regenerable, so
expiry is allowed by default — with two guards:

1. ``retention_class='pinned'`` backups are never expired.
2. the newest ``keep_min_count`` available backups are always kept, even if expired.

The pass runs under the global ``BACKUP_JANITOR`` advisory lock; if another pass
holds it, this one returns ``skipped_locked=True`` without touching anything.
``select_expired_backups`` is a pure function so the policy is unit-tested without
a database.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.dto.admin import BackupRetentionResult, OpsArtifact
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import (
    BACKUP_ARTIFACT_TYPE,
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
            artifacts = await repo.list_artifacts(
                limit=1000, artifact_type=BACKUP_ARTIFACT_TYPE, state="available"
            )
            selection = select_expired_backups(
                artifacts, now=effective_now, keep_min_count=keep
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
            )
            _LOGGER.info("backup retention janitor ran", extra={"result": result.model_dump()})
            return result
    except ConcurrentExecutionError:
        _LOGGER.info("backup retention janitor skipped: lock held by another process")
        return BackupRetentionResult(dry_run=dry_run, keep_min_count=keep, skipped_locked=True)
