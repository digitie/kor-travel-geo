"""Dagster jobs for the non-destructive backup-maintenance leaves (T-290g ③).

``verify`` / ``copy`` / ``restore-drill`` are stored-backup operations that never touch the
serving DB. Each is a thin Dagster job over exactly one ``AsyncAddressClient`` leaf — the same
shape as ``mv_refresh`` (dagster-boundary §4). The on-demand sync API/CLI keeps calling those
same leaves; Dagster just adds scheduling + run observability on top.

The daily restore-drill ``@schedule`` proves the latest backup is restorable without a human
in the loop, replacing the external cron (T-239). A bad result — verify corruption, a copy
sha256 mismatch, or a FAIL drill — raises ``Failure`` so the run fails visibly and the
run-failure sensor fires. None of the three carries a ``RetryPolicy``: all are hard-fail
(dagster-boundary §6/§9), and a copy retry would risk a double write.

IMPORTANT (dagster-boundary §10): this module must NOT use
``from __future__ import annotations`` — Dagster reads the decorated functions' annotations
at runtime, and stringized annotations break ``@op`` context typing.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import (
    DefaultScheduleStatus,
    Enum,
    EnumValue,
    Failure,
    Field,
    OpExecutionContext,
    RunRequest,
    ScheduleEvaluationContext,
    String,
    job,
    op,
    schedule,
)
from kortravelgeo.infra.backup import BACKUP_ARTIFACT_TYPE

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient

__all__ = [
    "BACKUP_MAINTENANCE_JOBS",
    "BACKUP_MAINTENANCE_SCHEDULES",
    "backup_copy_job",
    "backup_restore_drill_job",
    "backup_verify_job",
    "copy_backup_op",
    "restore_drill_op",
    "restore_drill_schedule",
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


def _client(context: OpExecutionContext) -> "AsyncAddressClient":
    """The ``AsyncAddressClient`` resource — the geo main-lib entrypoint the ops call."""
    return cast("AsyncAddressClient", cast("Any", context.resources).client)


@op(
    name="verify_backup",
    description="Verify a stored db_backup's integrity (client.verify_backup); corruption raises.",
    required_resource_keys={"client"},
    config_schema={"artifact_id": Field(String), "mode": _VERIFY_MODE_FIELD},
)
async def verify_backup_op(context: OpExecutionContext) -> dict[str, object]:
    config = cast("Mapping[str, str]", context.op_config)
    artifact_id = config["artifact_id"]

    result = await _client(context).verify_backup(artifact_id, mode=config["mode"])

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

    result = await _client(context).copy_backup(artifact_id, target_dir=config["target_dir"])

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
    client = _client(context)
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


BACKUP_MAINTENANCE_JOBS: Final = [backup_verify_job, backup_copy_job, backup_restore_drill_job]
"""Job list aggregated by ``definitions.py``."""

BACKUP_MAINTENANCE_SCHEDULES: Final = [restore_drill_schedule]
"""Schedule list aggregated by ``definitions.py``."""
