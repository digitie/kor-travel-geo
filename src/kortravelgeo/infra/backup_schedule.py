"""T-239 scheduled backup due-check trigger.

Manual backups alone mean a forgotten operator = a gap in coverage, which is exactly
the failure mode a low-reliability single-host server cannot afford. This module adds
an *idempotent* due-check: an external cron periodically hits
``POST /v1/admin/backups/scheduled/run-due`` and a new backup is enqueued only once
``backup_schedule_interval_hours`` has elapsed since the last scheduled run.

The decision (`decide_scheduled_backup`) is a pure function so the policy is unit-tested
without a database. `resolve_scheduled_backup_status` resolves the two DB inputs it needs:

1. the most recent **non-failed** ``retention_class='scheduled'`` backup artifact, and
2. whether a scheduled backup job is currently ``queued``/``running``.

(2) closes the enqueue→worker-start window where the artifact does not exist yet, so two
near-simultaneous triggers cannot both decide "due" and double-enqueue. The router additionally
serializes the decide+enqueue critical section under the ``BACKUP_SCHEDULE`` advisory lock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.dto.admin import BackupCreateRequest, ScheduledBackupStatus
from kortravelgeo.infra.backup import BACKUP_ARTIFACT_TYPE
from kortravelgeo.settings import Settings

SCHEDULED_RETENTION_CLASS = "scheduled"


def decide_scheduled_backup(
    *,
    enabled: bool,
    last_scheduled_at: datetime | None,
    has_active_scheduled_job: bool,
    interval_hours: float,
    keep_min: int,
    now: datetime,
) -> ScheduledBackupStatus:
    """Pure policy: should a scheduled backup be enqueued at ``now``?

    Order of precedence: disabled → in-progress → never-run (due) → interval elapsed.
    ``next_due_at`` is ``last_scheduled_at + interval`` (``None`` if none has ever run);
    the ``due`` flag already encodes whether ``now`` has reached it.
    """
    interval = timedelta(hours=interval_hours)
    next_due_at = last_scheduled_at + interval if last_scheduled_at is not None else None

    def status(*, due: bool, reason: str) -> ScheduledBackupStatus:
        return ScheduledBackupStatus(
            enabled=enabled,
            interval_hours=interval_hours,
            keep_min=keep_min,
            retention_class=SCHEDULED_RETENTION_CLASS,
            due=due,
            reason=reason,
            in_progress=has_active_scheduled_job,
            last_scheduled_at=last_scheduled_at,
            next_due_at=next_due_at,
        )

    if not enabled:
        return status(due=False, reason="disabled")
    if has_active_scheduled_job:
        return status(due=False, reason="in_progress")
    if last_scheduled_at is None:
        return status(due=True, reason="due_initial")
    if now >= next_due_at:  # type: ignore[operator]
        return status(due=True, reason="due")
    return status(due=False, reason="not_due")


def scheduled_backup_payload(settings: Settings) -> dict[str, Any]:
    """Build the ``db_backup`` job payload for a cron-triggered scheduled backup.

    Uses the default backup profile/jobs/compression but tags the artifact
    ``retention_class='scheduled'`` so the retention janitor (T-230) keeps the newest
    ``keep_min`` and expires older ones once their TTL passes (it is not ``pinned``).
    """
    req = BackupCreateRequest(retention_class=SCHEDULED_RETENTION_CLASS)
    return req.model_dump(exclude_none=True)


async def _last_scheduled_backup_at(engine: AsyncEngine) -> datetime | None:
    """created_at of the most recent non-failed scheduled backup artifact."""
    async with engine.connect() as conn:
        value = await conn.scalar(
            text(
                """
SELECT created_at
  FROM ops.artifacts
 WHERE artifact_type = :artifact_type
   AND retention_class = :retention_class
   AND state <> 'failed'
 ORDER BY created_at DESC
 LIMIT 1
"""
            ),
            {
                "artifact_type": BACKUP_ARTIFACT_TYPE,
                "retention_class": SCHEDULED_RETENTION_CLASS,
            },
        )
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _has_active_scheduled_backup_job(engine: AsyncEngine) -> bool:
    """True if a scheduled backup job is currently queued or running."""
    async with engine.connect() as conn:
        count = await conn.scalar(
            text(
                """
SELECT count(*)
  FROM load_jobs
 WHERE kind = 'db_backup'
   AND state IN ('queued', 'running')
   AND payload ->> 'retention_class' = :retention_class
"""
            ),
            {"retention_class": SCHEDULED_RETENTION_CLASS},
        )
    return bool(count)


async def resolve_scheduled_backup_status(
    engine: AsyncEngine,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> ScheduledBackupStatus:
    """Resolve the DB inputs and compute the current scheduled-backup decision.

    Read-only — safe to call from the ``GET .../status`` endpoint and from inside the
    ``run-due`` critical section.
    """
    effective_now = now if isinstance(now, datetime) else datetime.now(UTC)
    last_scheduled_at = await _last_scheduled_backup_at(engine)
    has_active = await _has_active_scheduled_backup_job(engine)
    return decide_scheduled_backup(
        enabled=settings.backup_schedule_enabled,
        last_scheduled_at=last_scheduled_at,
        has_active_scheduled_job=has_active,
        interval_hours=settings.backup_schedule_interval_hours,
        keep_min=settings.backup_retention_keep_min,
        now=effective_now,
    )
