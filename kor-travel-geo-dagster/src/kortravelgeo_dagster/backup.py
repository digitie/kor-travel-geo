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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import (
    DefaultScheduleStatus,
    DefaultSensorStatus,
    Failure,
    OpExecutionContext,
    ResourceParam,
    RunFailureSensorContext,
    RunRequest,
    ScheduleEvaluationContext,
    job,
    op,
    run_failure_sensor,
    schedule,
)
from kortravelgeo.client import AsyncAddressClient

from .mv import mv_refresh_job
from .resources import op_resource, run_coroutine_blocking

if TYPE_CHECKING:
    from .resources import DagsterAdminApiClient

__all__ = [
    "BACKUP_JOBS",
    "BACKUP_SCHEDULES",
    "BACKUP_SENSORS",
    "JOB_ID_TAG",
    "JOB_KIND_TAG",
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

JOB_ID_TAG: Final[str] = "kor_travel_geo.job_id"
"""Dagster run tag carrying the app ``load_jobs`` id when an onramp sets it (else absent)."""

JOB_KIND_TAG: Final[str] = "kor_travel_geo.job_kind"
"""Dagster run tag carrying the job kind (e.g. ``scheduled_backup_run_due``, ``mv_refresh``)."""


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

    admin_api = cast("DagsterAdminApiClient", op_resource(context, "admin_api"))
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
    return _scheduled_backup_run_request(context.scheduled_execution_time)


def _scheduled_backup_run_request(scheduled_at: datetime | None) -> RunRequest:
    """Build the scheduled-backup ``RunRequest``.

    Split out of the ``@schedule`` so ``run_key`` derivation (including the
    no-scheduled-time fallback) is unit-testable without a real
    ``ScheduleEvaluationContext`` (direct schedule invocation type-checks the context).
    The ``run_key`` is the scheduled minute's ISO timestamp so Dagster dedups one run
    per tick; ``None`` when the time is unavailable.
    """
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
def notify_run_failure_sensor(
    context: RunFailureSensorContext,
    client: ResourceParam[AsyncAddressClient],
    failure_notifier: ResourceParam[object],
) -> None:
    """Persist and forward Dagster run failures (T-290h).

    On a monitored run's failure this (1) persists a bounded alert to
    ``ops.run_failure_alerts`` through the in-process ``client`` resource
    (dagster-boundary §6: client/infra, never api) and (2) forwards the same §5
    payload — ``{job_id, run_id, job_name, status, error_code}`` — to an optional
    deployment ``failure_notifier``. The raw Dagster failure ``message`` is never
    persisted or forwarded; only a bounded ``error_code`` (the failure error's
    class name) is used.

    ``client`` and ``failure_notifier`` are declared as Pythonic ``ResourceParam``
    arguments so Dagster resolves them into ``required_resource_keys`` and injects
    them — ``@run_failure_sensor`` does not expose ``required_resource_keys``, and
    resource parameters are how run-status sensors request resources
    (dagster-boundary §3). ``failure_notifier`` defaults to ``None`` (no notifier).

    Thin wrapper: the dispatch logic lives in
    :func:`_dispatch_run_failure_notification` so its branches stay unit-testable
    with plain injected fakes instead of a real ``RunStatusSensorContext`` (direct
    sensor invocation type-checks the context and rejects a duck-typed fake).
    """

    _dispatch_run_failure_notification(context, client=client, failure_notifier=failure_notifier)


def _dispatch_run_failure_notification(
    context: RunFailureSensorContext,
    *,
    client: AsyncAddressClient | None,
    failure_notifier: object,
) -> None:
    """Persist the failure and forward it to the optional ``failure_notifier``.

    The two sinks run independently: persistence to ``ops.run_failure_alerts`` via
    the ``client`` resource, plus the optional deployment notifier. Both are
    defensive — a missing/failing sink logs a warning and is swallowed, so neither
    can turn a monitored run's failure into a *sensor* failure.
    """
    payload = _failure_notification_payload(context)
    _persist_run_failure_alert(context, payload, client)
    _forward_run_failure_notification(context, payload, failure_notifier)


def _forward_run_failure_notification(
    context: RunFailureSensorContext, payload: dict[str, object], notifier: object
) -> None:
    """Forward the §5 payload to the optional ``failure_notifier`` resource."""
    if notifier is None:
        context.log.warning("Dagster run failed without failure_notifier: %s", payload)
        return
    if not callable(notifier):
        context.log.warning("failure_notifier resource is not callable: %r", notifier)
        return
    cast("Callable[[dict[str, object]], None]", notifier)(payload)


def _persist_run_failure_alert(
    context: RunFailureSensorContext,
    payload: dict[str, object],
    client: AsyncAddressClient | None,
) -> None:
    """Persist the failure to ``ops.run_failure_alerts`` via the ``client`` resource.

    Uses the in-process ``client`` (AsyncAddressClient → repo INSERT), never the
    ``admin_api`` HTTP resource (dagster-boundary §6). Persists only bounded fields —
    the run status, error class ``error_code``, and run tags — never the raw failure
    ``message``. Idempotent on ``run_id`` (repo ``ON CONFLICT DO NOTHING``).
    """
    if client is None:
        context.log.warning("Dagster run failed without client resource; alert not persisted")
        return
    dagster_run = context.dagster_run
    try:
        run_coroutine_blocking(
            client.record_run_failure_alert(
                run_id=cast("str", payload["run_id"]),
                status=_normalized_run_status(dagster_run),
                run_failed_at=_failure_run_timestamp(context),
                job_id=cast("str | None", payload["job_id"]),
                job_name=cast("str | None", payload["job_name"]),
                job_kind=dagster_run.tags.get(JOB_KIND_TAG),
                error_code=cast("str | None", payload["error_code"]),
            )
        )
    except Exception as exc:  # never let persistence fail the sensor
        context.log.warning("run-failure alert persistence failed: %s", exc)


def _normalized_run_status(dagster_run: Any) -> str:
    """Return a clean run status name (``FAILURE``), matching the observe GraphQL status.

    ``str(DagsterRunStatus.FAILURE)`` is ``"DagsterRunStatus.FAILURE"``; normalize to
    the bare member name so the persisted status matches ``run.status`` from the
    observe GraphQL (which the admin UI classifies).
    """
    status = getattr(dagster_run, "status", "")
    name = getattr(status, "name", None)
    if isinstance(name, str):
        return name
    text = str(status)
    return text.rsplit(".", 1)[-1] if "." in text else text


def _failure_run_timestamp(context: RunFailureSensorContext) -> datetime:
    """Best-effort failure time from the failure event, else now (UTC)."""
    failure_event = getattr(context, "failure_event", None)
    raw = getattr(failure_event, "timestamp", None)
    if isinstance(raw, int | float):
        return datetime.fromtimestamp(raw, tz=UTC)
    return datetime.now(UTC)


BACKUP_JOBS: Final = [scheduled_backup_run_due_job]
BACKUP_SCHEDULES: Final = [scheduled_backup_schedule]
BACKUP_SENSORS: Final = [notify_run_failure_sensor]


def _failure_notification_payload(context: RunFailureSensorContext) -> dict[str, object]:
    """Build the dagster-boundary §5 failure payload (no raw failure message).

    ``job_id`` is the app ``load_jobs`` id when the Dagster run carries the
    ``kor_travel_geo.job_id`` tag (a later onramp sets it), otherwise ``None``.
    """
    dagster_run = context.dagster_run
    return {
        "job_id": dagster_run.tags.get(JOB_ID_TAG),
        "run_id": dagster_run.run_id,
        "job_name": dagster_run.job_name,
        "status": str(dagster_run.status),
        "error_code": _failure_error_code(context),
    }


def _failure_error_code(context: RunFailureSensorContext) -> str | None:
    """Return the failure error's class name — a bounded classifier, never the message.

    Forwarding only the error class (e.g. ``Failure``) keeps free-form/sensitive
    failure text out of the notification payload (dagster-boundary §5).
    """
    failure_event = getattr(context, "failure_event", None)
    event_data = getattr(failure_event, "event_specific_data", None)
    error = getattr(event_data, "error", None)
    cls_name = getattr(error, "cls_name", None)
    return cls_name if isinstance(cls_name, str) else None


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
