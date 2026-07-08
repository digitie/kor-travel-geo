"""Dagster scheduled-backup onramp (T-290f).

This milestone deliberately does NOT move the backup leaf into Dagster yet. The
schedule creates a Dagster run that calls the existing idempotent admin endpoint
``POST /v1/admin/backups/scheduled/run-due``. The API keeps the due decision,
advisory lock, audit event, and in-process job queue ownership until T-290g moves
``db_backup`` execution itself into Dagster.

IMPORTANT (dagster-boundary §10): this module must NOT use
``from __future__ import annotations`` — Dagster validates decorated function
annotations at runtime.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import (
    DefaultScheduleStatus,
    DefaultSensorStatus,
    Failure,
    OpExecutionContext,
    RunFailureSensorContext,
    RunRequest,
    ScheduleEvaluationContext,
    job,
    op,
    run_failure_sensor,
    schedule,
)

from .mv import mv_refresh_job

if TYPE_CHECKING:
    from .resources import DagsterAdminApiClient

__all__ = [
    "BACKUP_JOBS",
    "BACKUP_SCHEDULES",
    "BACKUP_SENSORS",
    "SCHEDULED_BACKUP_JOB_TAGS",
    "notify_run_failure_sensor",
    "run_due_scheduled_backup_op",
    "scheduled_backup_run_due_job",
    "scheduled_backup_schedule",
]

SCHEDULED_BACKUP_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "maintenance",
    "kor_travel_geo.job_kind": "scheduled_backup_run_due",
}
"""Common tags for the scheduled-backup onramp Dagster job."""

SCHEDULED_BACKUP_CRON: Final[str] = "*/15 * * * *"
"""Frequent safe tick; the API ``run-due`` endpoint remains the due/no-op authority."""

SCHEDULED_BACKUP_TIMEZONE: Final[str] = "Asia/Seoul"


@op(
    name="run_due_scheduled_backup",
    description=(
        "Call the geo admin run-due endpoint. The API decides whether a scheduled "
        "db_backup should be enqueued and keeps the advisory lock/audit boundary."
    ),
    required_resource_keys={"admin_api"},
)
async def run_due_scheduled_backup_op(context: OpExecutionContext) -> dict[str, Any]:
    """Trigger the existing scheduled-backup due-check endpoint once."""

    admin_api = cast("DagsterAdminApiClient", _resource_object(context, "admin_api"))
    try:
        payload = await admin_api.run_due_scheduled_backup()
    except Exception as exc:
        raise Failure(
            description=f"scheduled backup run-due call failed: {exc}",
        ) from exc

    metadata = _run_due_metadata(payload)
    context.add_output_metadata(metadata)
    if payload.get("enqueued"):
        context.log.info("scheduled backup enqueued: %s", payload.get("job_id"))
    else:
        reason = _nested_value(payload, "status", "reason") or "unknown"
        context.log.info("scheduled backup not enqueued: %s", reason)
    return payload


@job(
    name="scheduled_backup_run_due",
    tags=SCHEDULED_BACKUP_JOB_TAGS,
    description=(
        "Dagster schedule onramp for scheduled backups. The job calls the existing "
        "API run-due endpoint; T-290g moves db_backup execution into Dagster."
    ),
)
def scheduled_backup_run_due_job() -> None:
    run_due_scheduled_backup_op()


@schedule(
    name="scheduled_backup",
    job=scheduled_backup_run_due_job,
    cron_schedule=SCHEDULED_BACKUP_CRON,
    execution_timezone=SCHEDULED_BACKUP_TIMEZONE,
    default_status=DefaultScheduleStatus.STOPPED,
    description=(
        "Every 15 minutes, call the idempotent geo API scheduled-backup run-due "
        "endpoint. Kept STOPPED by default; enable in Dagster when the deployment's "
        "KTG_BACKUP_SCHEDULE_ENABLED policy is ready."
    ),
)
def scheduled_backup_schedule(context: ScheduleEvaluationContext) -> RunRequest:
    scheduled_at = context.scheduled_execution_time
    run_key = scheduled_at.isoformat() if scheduled_at is not None else None
    return RunRequest(
        run_key=run_key,
        tags={
            **SCHEDULED_BACKUP_JOB_TAGS,
            "kor_travel_geo.schedule": "scheduled_backup",
        },
    )


@run_failure_sensor(
    name="run_failure_sensor",
    monitored_jobs=[scheduled_backup_run_due_job, mv_refresh_job],
    minimum_interval_seconds=60,
    default_status=DefaultSensorStatus.STOPPED,
)
def notify_run_failure_sensor(context: RunFailureSensorContext) -> None:
    """Forward Dagster run failures to an optional deployment-supplied notifier."""

    dagster_run = context.dagster_run
    payload: dict[str, object] = {
        "run_id": dagster_run.run_id,
        "job_name": dagster_run.job_name,
        "status": str(dagster_run.status),
        "message": getattr(context.failure_event, "message", None),
    }
    notifier = _optional_resource_object(context, "failure_notifier")
    if notifier is None:
        context.log.warning("Dagster run failed without failure_notifier: %s", payload)
        return
    if not callable(notifier):
        context.log.warning("failure_notifier resource is not callable: %r", notifier)
        return
    cast("Callable[[dict[str, object]], None]", notifier)(payload)


BACKUP_JOBS: Final = [scheduled_backup_run_due_job]
BACKUP_SCHEDULES: Final = [scheduled_backup_schedule]
BACKUP_SENSORS: Final = [notify_run_failure_sensor]


def _resource_object(context: object, name: str) -> object:
    resources = cast("Any", context).resources
    if not hasattr(resources, name):
        raise AttributeError(f"Dagster resource missing: {name}")
    return getattr(resources, name)


def _optional_resource_object(context: object, name: str) -> object | None:
    context_obj = cast("Any", context)
    if not hasattr(context_obj, "resources"):
        return None
    resources = context_obj.resources
    if not hasattr(resources, name):
        return None
    value: object = getattr(resources, name)
    return value


def _run_due_metadata(payload: dict[str, Any]) -> dict[str, object]:
    status = payload.get("status")
    return {
        "enqueued": bool(payload.get("enqueued")),
        "job_id": payload.get("job_id"),
        "skipped_locked": bool(payload.get("skipped_locked")),
        "due": _dict_value(status, "due"),
        "reason": _dict_value(status, "reason"),
        "next_due_at": _dict_value(status, "next_due_at"),
    }


def _nested_value(payload: dict[str, Any], key: str, nested_key: str) -> object:
    return _dict_value(payload.get(key), nested_key)


def _dict_value(value: object, key: str) -> object:
    return value.get(key) if isinstance(value, dict) else None
