"""Dagster observability DTOs for the admin API."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic needs this at runtime.
from typing import Literal

from pydantic import Field

from .common import FrozenModel


class DagsterResponseMeta(FrozenModel):
    """Small response metadata block for Dagster proxy reads."""

    duration_ms: float = Field(ge=0)


class DagsterGraphqlError(FrozenModel):
    """Dagster GraphQL PythonError summary."""

    message: str | None = None
    stack: list[str] = Field(default_factory=list)
    class_name: str | None = None


class DagsterAssetGroup(FrozenModel):
    """Dagster asset group summary."""

    group_name: str
    asset_count: int = Field(ge=0)
    assets: list[str]


class DagsterJob(FrozenModel):
    """Dagster job/pipeline summary."""

    name: str
    is_job: bool


class DagsterInstigationTick(FrozenModel):
    """Dagster schedule/sensor tick summary."""

    tick_id: str
    status: str
    timestamp: float
    end_timestamp: float | None = None
    run_ids: list[str] = Field(default_factory=list)
    run_keys: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
    cursor: str | None = None
    error: DagsterGraphqlError | None = None


class DagsterSchedule(FrozenModel):
    """Dagster schedule summary."""

    name: str
    cron_schedule: str | None = None
    execution_timezone: str | None = None
    status: str | None = None
    recent_ticks: list[DagsterInstigationTick] = Field(default_factory=list)
    # Forward-looking health (T-290h). ``next_tick_at`` is the next scheduled fire
    # per Dagster's own cron evaluation (raw epoch, like tick timestamps).
    # ``overdue`` is set when a RUNNING schedule missed its expected fire by more
    # than the configured grace window (a stuck scheduler daemon).
    next_tick_at: float | None = None
    overdue: bool = False


class DagsterSensor(FrozenModel):
    """Dagster sensor summary."""

    name: str
    status: str | None = None
    recent_ticks: list[DagsterInstigationTick] = Field(default_factory=list)


class DagsterRepository(FrozenModel):
    """Dagster code location/repository summary."""

    name: str
    location_name: str
    jobs: list[DagsterJob]
    schedules: list[DagsterSchedule]
    sensors: list[DagsterSensor]
    asset_count: int = Field(ge=0)
    asset_groups: list[DagsterAssetGroup]


class DagsterRunSummary(FrozenModel):
    """Recent Dagster run summary."""

    run_id: str
    job_name: str | None = None
    status: str
    start_time: float | None = None
    end_time: float | None = None
    update_time: float | None = None
    tags: dict[str, str]


class DagsterSummaryData(FrozenModel):
    """``GET /v1/ops/dagster/summary`` data."""

    status: Literal["ok", "unavailable", "error"]
    dagster_url: str
    graphql_url: str
    version: str | None = None
    checked_at: datetime
    repository_count: int = Field(ge=0)
    job_count: int = Field(ge=0)
    asset_count: int = Field(ge=0)
    schedule_count: int = Field(ge=0)
    sensor_count: int = Field(ge=0)
    run_counts: dict[str, int]
    repositories: list[DagsterRepository]
    recent_runs: list[DagsterRunSummary]
    errors: list[str] = Field(default_factory=list)


class DagsterSummaryResponse(FrozenModel):
    """``GET /v1/ops/dagster/summary`` response."""

    data: DagsterSummaryData
    meta: DagsterResponseMeta


class DagsterRunEvent(FrozenModel):
    """Dagster run event/failure summary."""

    event_type: str
    message: str | None = None
    timestamp: str | None = None
    level: str | None = None
    step_id: str | None = None
    dagster_event_type: str | None = None
    error: DagsterGraphqlError | None = None


class DagsterBackupArtifact(FrozenModel):
    """Backup artifact linked to a Dagster ``db_backup`` run."""

    artifact_id: str
    state: str
    display_name: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    download_url: str | None = None


class DagsterRunFailureAlert(FrozenModel):
    """Persisted Dagster run-failure alert (``ops.run_failure_alerts``, T-290h).

    Written by the Dagster ``run_failure_sensor`` through the ``client`` resource
    and surfaced read-only on run detail / the recent-failures list. Carries only
    bounded fields (the failure ``error_code`` = error class name, never the raw
    failure message — dagster-boundary §5).
    """

    run_id: str
    job_id: str | None = None
    job_name: str | None = None
    job_kind: str | None = None
    status: str
    error_code: str | None = None
    run_failed_at: datetime
    recorded_at: datetime
    acknowledged_at: datetime | None = None


class DagsterRunDetailData(FrozenModel):
    """``GET /v1/ops/dagster/runs/{run_id}`` data."""

    status: Literal["ok", "not_found", "unavailable", "error"]
    dagster_url: str
    graphql_url: str
    checked_at: datetime
    run: DagsterRunSummary | None = None
    backup_artifact: DagsterBackupArtifact | None = None
    failure_alert: DagsterRunFailureAlert | None = None
    events: list[DagsterRunEvent] = Field(default_factory=list)
    event_cursor: str | None = None
    event_has_more: bool = False
    errors: list[str] = Field(default_factory=list)


class DagsterRunDetailResponse(FrozenModel):
    """``GET /v1/ops/dagster/runs/{run_id}`` response."""

    data: DagsterRunDetailData
    meta: DagsterResponseMeta


class DagsterRunFailuresData(FrozenModel):
    """``GET /v1/ops/dagster/run-failures`` data (recent, unacknowledged first)."""

    checked_at: datetime
    alerts: list[DagsterRunFailureAlert] = Field(default_factory=list)


class DagsterRunFailuresResponse(FrozenModel):
    """``GET /v1/ops/dagster/run-failures`` response."""

    data: DagsterRunFailuresData
    meta: DagsterResponseMeta


class DagsterRunFailureAckResponse(FrozenModel):
    """``POST /v1/ops/dagster/runs/{run_id}/ack`` response."""

    data: DagsterRunFailureAlert
    meta: DagsterResponseMeta
