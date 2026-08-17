"""Dagster jobs for the non-destructive backup-maintenance leaves (T-290g ③).

``verify`` / ``copy`` / ``restore-drill`` are stored-backup operations that never touch the
serving DB. Each is a thin Dagster job over exactly one ``AsyncAddressClient`` leaf — the same
shape as ``mv_refresh`` (dagster-boundary §4). The on-demand sync API/CLI keeps calling those
same leaves; Dagster just adds scheduling + run observability on top.

The daily restore-drill ``@schedule`` proves the latest backup is restorable without a human
in the loop, replacing the external cron (T-239). The daily retention-janitor ``@schedule``
(T-230 leaf) expires TTL-passed archives so a scheduled daily backup (T-239) has bounded disk
use — without it nothing ever deletes an expired ``.tar.zst``. A bad result — verify corruption,
a copy sha256 mismatch, a FAIL drill, or a janitor that could not remove an archive — raises
``Failure`` so the run fails visibly and the run-failure sensor fires. None of the four carries
a ``RetryPolicy``: all are hard-fail (dagster-boundary §6/§9), and a copy retry would risk a
double write.

IMPORTANT (dagster-boundary §10): this module must NOT use
``from __future__ import annotations`` — Dagster reads the decorated functions' annotations
at runtime, and stringized annotations break ``@op`` context typing.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, cast

from dagster import (
    Bool,
    DefaultScheduleStatus,
    Enum,
    EnumValue,
    Failure,
    Field,
    Int,
    OpExecutionContext,
    RunRequest,
    ScheduleEvaluationContext,
    String,
    job,
    op,
    schedule,
)
from kortravelgeo.infra.backup import BACKUP_ARTIFACT_TYPE

from .resources import op_resource

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient

__all__ = [
    "BACKUP_MAINTENANCE_JOBS",
    "BACKUP_MAINTENANCE_SCHEDULES",
    "backup_copy_job",
    "backup_restore_drill_job",
    "backup_retention_janitor_job",
    "backup_verify_job",
    "copy_backup_op",
    "restore_drill_op",
    "restore_drill_schedule",
    "retention_janitor_op",
    "retention_janitor_schedule",
    "verify_backup_op",
]

_MAINTENANCE_TAGS: Final[dict[str, str]] = {"kor_travel_geo.job_scope": "maintenance"}

_VERIFY_MODE_FIELD: Final = Field(
    Enum("BackupVerifyMode", [EnumValue("quick"), EnumValue("deep")]),
    default_value="quick",
    description="'quick' = archive sha256; 'deep' also checks internal checksums + manifest.",
)

RESTORE_DRILL_CRON: Final[str] = "0 4 * * *"
"""Daily 04:00 restore drill (external-cron replacement, T-239)."""

RESTORE_DRILL_TIMEZONE: Final[str] = "Asia/Seoul"

RETENTION_JANITOR_CRON: Final[str] = "0 6 * * *"
"""Daily 06:00 backup retention janitor (T-230 leaf).

The 04:00 restore drill is protected by ``keep_min >= 1``, not by this spacing: the drill always
targets the newest ``available`` backup and the janitor keeps the newest ``keep_min`` by
``created_at`` regardless of expiry. 06:00 is only operational ordering (drill log first, janitor
log second). The leaf holds just the ``BACKUP_JANITOR`` advisory lock and has no per-artifact
in-use guard, so an explicit-artifact restore/verify/copy of an *expired, non-newest* archive can
still race an expiry — the same exposure the on-demand janitor always had.

Disk bound with a daily scheduled backup ≈ ``ceil(backup_artifact_ttl_days * 24 /
backup_schedule_interval_hours)`` archives (``keep_min`` is a floor, not a cap): size
``KTG_BACKUP_ARTIFACT_TTL_DAYS`` for the deployment (e.g. 7 → ~8 archives)."""

RETENTION_JANITOR_TIMEZONE: Final[str] = "Asia/Seoul"


@op(
    name="verify_backup",
    description="Verify a stored db_backup's integrity (client.verify_backup); corruption raises.",
    required_resource_keys={"client"},
    config_schema={"artifact_id": Field(String), "mode": _VERIFY_MODE_FIELD},
)
async def verify_backup_op(context: OpExecutionContext) -> dict[str, object]:
    config = cast("Mapping[str, str]", context.op_config)
    artifact_id = config["artifact_id"]
    client = cast("AsyncAddressClient", op_resource(context, "client"))

    result = await client.verify_backup(artifact_id, mode=config["mode"])

    metadata: dict[str, object] = {
        "artifact_id": result.artifact_id,
        "mode": result.mode,
        "ok": result.ok,
        "archive_sha256_matches": result.archive_sha256_matches,
        "internal_checksums_ok": result.internal_checksums_ok,
        "manifest_ok": result.manifest_ok,
    }
    context.add_output_metadata(metadata)
    if not result.ok:
        raise Failure(description=f"db_backup verify FAILED (corruption): {artifact_id}")
    return metadata


@op(
    name="copy_backup",
    description="Copy a stored db_backup off-host with a sha256 re-check (client.copy_backup).",
    required_resource_keys={"client"},
    config_schema={
        "artifact_id": Field(String),
        "target_dir": Field(
            String, description="allowlisted destination dir (backup_copy_targets / backup roots)"
        ),
    },
)
async def copy_backup_op(context: OpExecutionContext) -> dict[str, object]:
    config = cast("Mapping[str, str]", context.op_config)
    artifact_id = config["artifact_id"]
    client = cast("AsyncAddressClient", op_resource(context, "client"))

    result = await client.copy_backup(artifact_id, target_dir=config["target_dir"])

    metadata: dict[str, object] = {
        "artifact_id": result.artifact_id,
        "destination_path": result.destination_path,
        "sha256": result.sha256,
        "verified": result.verified,
    }
    context.add_output_metadata(metadata)
    if not result.verified:
        raise Failure(description=f"db_backup copy sha256 re-check FAILED: {artifact_id}")
    return metadata


@op(
    name="restore_drill",
    description=(
        "Restore a db_backup into a throwaway DB, reconcile + smoke, then always drop it "
        "(client.run_restore_drill). Omit artifact_id to drill the latest available backup. "
        "A FAIL status raises Failure."
    ),
    required_resource_keys={"client"},
    config_schema={
        "artifact_id": Field(
            String,
            is_required=False,
            description="db_backup to drill; omit to drill the latest available backup.",
        ),
    },
)
async def restore_drill_op(context: OpExecutionContext) -> dict[str, object]:
    client = cast("AsyncAddressClient", op_resource(context, "client"))
    config = cast("Mapping[str, str]", context.op_config)

    artifact_id = config.get("artifact_id") or await _latest_backup_artifact_id(client)
    # run_restore_drill is clock-free and names the throwaway DB from this timestamp; a fresh
    # per-run value keeps repeat/concurrent drills from colliding on the temp DB name.
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    result = await client.run_restore_drill(timestamp=timestamp, artifact_id=artifact_id)

    metadata: dict[str, object] = {
        "artifact_id": artifact_id,
        "status": result.status,
        "temp_database": result.temp_database,
        "duration_seconds": result.duration_seconds,
        "restored": result.restored,
        "reconcile_ok": result.reconcile_ok,
        "smoke_ok": result.smoke_ok,
        "cleanup_ok": result.cleanup_ok,
    }
    context.add_output_metadata(metadata)
    if result.status == "FAIL":
        raise Failure(
            description=(
                f"restore drill FAILED for {artifact_id} "
                f"(temp_db={result.temp_database}, cleanup_ok={result.cleanup_ok})"
            )
        )
    return metadata


@op(
    name="retention_janitor",
    description=(
        "Expire db_backup archives whose TTL passed, keeping pinned ones and the newest "
        "keep_min (client.run_backup_retention_janitor, T-230). A pass that could not remove "
        "an archive raises Failure; skipped_locked (another janitor holds the advisory lock) is "
        "a no-op success."
    ),
    required_resource_keys={"client"},
    config_schema={
        "dry_run": Field(
            Bool,
            default_value=False,
            description="report expiry targets without touching files or artifact state.",
        ),
        "keep_min_count": Field(
            Int,
            is_required=False,
            description="override Settings.backup_retention_keep_min for this pass.",
        ),
    },
)
async def retention_janitor_op(context: OpExecutionContext) -> dict[str, object]:
    client = cast("AsyncAddressClient", op_resource(context, "client"))
    config = cast("Mapping[str, object]", context.op_config)
    dry_run = bool(config.get("dry_run", False))
    keep_min_raw = config.get("keep_min_count")
    keep_min_count = int(cast("int", keep_min_raw)) if keep_min_raw is not None else None
    if keep_min_count is not None and keep_min_count < 0:
        # HTTP (ge=0) and CLI (min=0) reject this; the leaf would clamp silently.
        raise Failure(description=f"keep_min_count must be >= 0, got {keep_min_count}")

    result = await client.run_backup_retention_janitor(
        dry_run=dry_run, keep_min_count=keep_min_count
    )
    if result.skipped_locked:
        context.log.warning(
            "backup retention janitor skipped: BACKUP_JANITOR advisory lock held by another process"
        )
    else:
        context.log.info(
            "backup retention janitor: dry_run=%s scanned=%s protected=%s expired=%s failed=%s",
            result.dry_run,
            result.scanned,
            result.protected_count,
            result.expired_count,
            result.failed_count,
        )

    metadata: dict[str, object] = {
        "dry_run": result.dry_run,
        "keep_min_count": result.keep_min_count,
        "skipped_locked": result.skipped_locked,
        "scanned": result.scanned,
        "protected_count": result.protected_count,
        "expired_count": result.expired_count,
        "failed_count": result.failed_count,
        "expired_artifact_ids": list(result.expired_artifact_ids),
        "failed_artifact_ids": list(result.failed_artifact_ids),
    }
    context.add_output_metadata(metadata)
    if result.failed_count:
        raise Failure(
            description=(
                f"backup retention janitor could not expire {result.failed_count} archive(s): "
                f"{', '.join(result.failed_artifact_ids)}"
            )
        )
    return metadata


async def _latest_backup_artifact_id(client: "AsyncAddressClient") -> str:
    """The newest ``available`` db_backup's id (list_artifacts is newest-first)."""
    backups = await client.list_artifacts(
        artifact_type=BACKUP_ARTIFACT_TYPE, state="available", limit=1
    )
    if not backups:
        raise Failure(description="restore drill: no available db_backup to drill")
    return backups[0].artifact_id


@job(
    name="backup_verify",
    tags={**_MAINTENANCE_TAGS, "kor_travel_geo.job_kind": "backup_verify"},
    description="Verify a stored db_backup's integrity (T-290g ③).",
)
def backup_verify_job() -> None:
    verify_backup_op()


@job(
    name="backup_copy",
    tags={**_MAINTENANCE_TAGS, "kor_travel_geo.job_kind": "backup_copy"},
    description="Copy a stored db_backup off-host with a sha256 re-check (T-290g ③).",
)
def backup_copy_job() -> None:
    copy_backup_op()


@job(
    name="backup_restore_drill",
    tags={**_MAINTENANCE_TAGS, "kor_travel_geo.job_kind": "backup_restore_drill"},
    description="Restore-drill a db_backup into a throwaway DB, proving restorability (T-290g ③).",
)
def backup_restore_drill_job() -> None:
    restore_drill_op()


@job(
    name="backup_retention_janitor",
    tags={**_MAINTENANCE_TAGS, "kor_travel_geo.job_kind": "backup_retention_janitor"},
    description="Expire TTL-passed db_backup archives, keeping pinned + newest keep_min (T-230).",
)
def backup_retention_janitor_job() -> None:
    retention_janitor_op()


@schedule(
    name="backup_restore_drill_daily",
    job=backup_restore_drill_job,
    cron_schedule=RESTORE_DRILL_CRON,
    execution_timezone=RESTORE_DRILL_TIMEZONE,
    default_status=DefaultScheduleStatus.STOPPED,
    description=(
        "Daily 04:00 restore drill of the latest available backup (external-cron replacement, "
        "T-239). STOPPED by default; enable per deployment. The op selects the latest backup, "
        "so the schedule needs no run config."
    ),
)
def restore_drill_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    scheduled_at = context.scheduled_execution_time
    return RunRequest(
        run_key=scheduled_at.isoformat() if scheduled_at is not None else None,
        tags={
            **_MAINTENANCE_TAGS,
            "kor_travel_geo.job_kind": "backup_restore_drill",
            "kor_travel_geo.schedule": "backup_restore_drill_daily",
        },
    )


@schedule(
    name="backup_retention_janitor_daily",
    job=backup_retention_janitor_job,
    cron_schedule=RETENTION_JANITOR_CRON,
    execution_timezone=RETENTION_JANITOR_TIMEZONE,
    default_status=DefaultScheduleStatus.STOPPED,
    description=(
        "Daily 06:00 backup retention janitor (T-230). STOPPED by default; enable together with "
        "KTG_BACKUP_SCHEDULE_ENABLED so a daily scheduled backup has bounded disk use - about "
        "ceil(KTG_BACKUP_ARTIFACT_TTL_DAYS*24 / KTG_BACKUP_SCHEDULE_INTERVAL_HOURS) archives "
        "(keep_min is a floor). The op reads keep_min from Settings, so no run config."
    ),
)
def retention_janitor_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    scheduled_at = context.scheduled_execution_time
    return RunRequest(
        run_key=scheduled_at.isoformat() if scheduled_at is not None else None,
        tags={
            **_MAINTENANCE_TAGS,
            "kor_travel_geo.job_kind": "backup_retention_janitor",
            "kor_travel_geo.schedule": "backup_retention_janitor_daily",
        },
    )


BACKUP_MAINTENANCE_JOBS: Final = [
    backup_verify_job,
    backup_copy_job,
    backup_restore_drill_job,
    backup_retention_janitor_job,
]
"""Job list aggregated by ``definitions.py``."""

BACKUP_MAINTENANCE_SCHEDULES: Final = [restore_drill_schedule, retention_janitor_schedule]
"""Schedule list aggregated by ``definitions.py``."""
