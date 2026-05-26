"""Admin and debugging DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .common import FrozenModel

LoadJobState = Literal["queued", "running", "done", "failed", "cancelled"]
LoadJobKind = Literal[
    "full_load_batch",
    "juso_text_load",
    "daily_juso_delta",
    "juso_parcel_link_load",
    "juso_parcel_link_delta",
    "roadaddr_entrance_load",
    "locsum_load",
    "navi_load",
    "shp_polygons_load",
    "shp_polygons_delta",
    "pobox_load",
    "bulk_load",
    "mv_refresh",
    "consistency_check",
]
ConsistencySeverity = Literal["OK", "INFO", "WARN", "ERROR"]
OpsActorType = Literal["system", "cli", "api", "ui", "scheduler"]
OpsAuditOutcome = Literal["started", "succeeded", "failed", "cancelled", "denied"]
DatasetSnapshotState = Literal["building", "validated", "rejected", "released", "retired"]
ServingReleaseState = Literal["pending", "active", "superseded", "rolled_back", "failed"]
ServingReleaseKind = Literal["full_load", "daily_delta", "restore", "manual_rebuild", "rollback"]
OpsArtifactState = Literal["creating", "available", "failed", "deleted", "expired"]
OpsStorageKind = Literal["local_file", "s3", "gcs", "none"]
MaintenanceWindowKind = Literal[
    "full_load",
    "restore",
    "schema_migration",
    "mv_refresh",
    "read_only",
    "exclusive",
]
MaintenanceWindowState = Literal["scheduled", "active", "ending", "ended", "cancelled", "failed"]
StatsObjectKind = Literal["table", "materialized_view", "index", "toast", "other"]


class TableStat(FrozenModel):
    table_name: str
    row_count: int = Field(ge=0)
    size_bytes: int | None = Field(default=None, ge=0)
    updated_at: str | None = None


class UploadSidoZipResponse(FrozenModel):
    upload_id: str
    filename: str
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class NormalizeRequest(FrozenModel):
    address: str = Field(min_length=1, max_length=200)


class NormalizeResponse(FrozenModel):
    original: str
    normalized: str
    tokens: tuple[str, ...] = ()


class ExplainRequest(FrozenModel):
    sql: str = Field(min_length=1)
    analyze: bool = False
    buffers: bool = False


class ExplainResponse(FrozenModel):
    plan: object


class LoadJobStatus(FrozenModel):
    job_id: str
    kind: LoadJobKind | str
    state: LoadJobState
    load_batch_id: str | None = None
    parent_job_id: str | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_stage: str | None = None
    source_yyyymm: str | None = None
    source_set: dict[str, str] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    error_message: str | None = None
    log_tail: tuple[str, ...] = ()
    payload_summary: dict[str, Any] | None = None


class CacheMetrics(FrozenModel):
    enabled: bool
    entries: int = Field(ge=0)
    hits: int = Field(ge=0)
    expired: int = Field(ge=0)


class LoadSubmitRequest(FrozenModel):
    kind: LoadJobKind | str
    payload: dict[str, Any] = Field(default_factory=dict)


class ConsistencyRunRequest(FrozenModel):
    scope: Literal["full", "sido", "recent"] = "full"
    sido: str | None = None
    recent_days: int = Field(default=7, ge=1, le=365)
    cases: tuple[str, ...] | None = None


class ConsistencyCase(FrozenModel):
    code: str
    name: str
    severity: ConsistencySeverity
    count: int = Field(ge=0)
    ratio: float | None = Field(default=None, ge=0.0)
    threshold: str | None = None
    metric: dict[str, float] | None = None
    sample: tuple[dict[str, Any], ...] = ()
    note: str | None = None


class ConsistencyReportSummary(FrozenModel):
    report_id: str
    scope: str
    severity_max: ConsistencySeverity
    source_set: dict[str, str]
    started_at: datetime
    finished_at: datetime | None = None
    generated_by: Literal["cli", "api", "cron"] = "api"


class ConsistencyReport(ConsistencyReportSummary):
    cases: tuple[ConsistencyCase, ...] = ()


class AuditEvent(FrozenModel):
    event_id: str
    occurred_at: datetime
    actor_type: OpsActorType
    actor_id: str | None = None
    client_ip_hash: str | None = None
    user_agent_hash: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    job_id: str | None = None
    outcome: OpsAuditOutcome
    error_code: str | None = None
    payload_redacted: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = Field(min_length=64, max_length=64)


class DatasetSnapshot(FrozenModel):
    snapshot_id: str
    state: DatasetSnapshotState
    parent_snapshot_id: str | None = None
    source_set: dict[str, Any] = Field(default_factory=dict)
    source_set_hash: str = Field(min_length=64, max_length=64)
    git_commit: str | None = None
    alembic_revision: str | None = None
    postgres_version: str | None = None
    postgis_version: str | None = None
    row_counts: dict[str, int] = Field(default_factory=dict)
    table_stats_artifact_id: str | None = None
    consistency_report_id: str | None = None
    performance_artifact_id: str | None = None
    backup_artifact_id: str | None = None
    created_by_job_id: str | None = None
    created_at: datetime
    validated_at: datetime | None = None


class ServingRelease(FrozenModel):
    release_id: str
    snapshot_id: str
    state: ServingReleaseState
    release_kind: ServingReleaseKind
    previous_release_id: str | None = None
    rollback_target_release_id: str | None = None
    mv_name: str = "mv_geocode_target"
    mv_hash: str | None = None
    consistency_gate: dict[str, Any] = Field(default_factory=dict)
    performance_gate: dict[str, Any] = Field(default_factory=dict)
    activated_by_job_id: str | None = None
    activated_at: datetime | None = None
    notes: str | None = None
    created_at: datetime


class RollbackPlan(FrozenModel):
    release_id: str
    snapshot_id: str
    requires_maintenance_window: bool = True
    typed_confirmation: str
    blockers: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()


class OpsArtifact(FrozenModel):
    artifact_id: str
    artifact_type: str
    state: OpsArtifactState
    storage_kind: OpsStorageKind
    storage_uri: str | None = None
    display_name: str | None = None
    media_type: str | None = None
    compression: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    retention_class: str | None = None
    expires_at: datetime | None = None
    job_id: str | None = None
    snapshot_id: str | None = None
    release_id: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    callback_url: str | None = None
    callback_state: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class MaintenanceWindowCreate(FrozenModel):
    kind: MaintenanceWindowKind
    reason: str = Field(min_length=1, max_length=1000)
    confirmation: str = Field(min_length=3, max_length=200)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    requested_by: str | None = None
    approved_by: str | None = None
    blocks: dict[str, Any] = Field(default_factory=dict)
    created_by_job_id: str | None = None


class MaintenanceWindowEnd(FrozenModel):
    confirmation: str = Field(min_length=3, max_length=200)
    closed_by_job_id: str | None = None


class MaintenanceWindow(FrozenModel):
    window_id: str
    kind: MaintenanceWindowKind
    state: MaintenanceWindowState
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    actual_started_at: datetime | None = None
    actual_ended_at: datetime | None = None
    reason: str
    requested_by: str | None = None
    approved_by: str | None = None
    blocks: dict[str, Any] = Field(default_factory=dict)
    created_by_job_id: str | None = None
    closed_by_job_id: str | None = None
    created_at: datetime


class TableStatsSnapshot(FrozenModel):
    stats_id: str
    snapshot_id: str | None = None
    captured_at: datetime
    schema_name: str
    object_name: str
    object_kind: StatsObjectKind
    estimated_rows: int | None = Field(default=None, ge=0)
    exact_rows: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    table_bytes: int | None = Field(default=None, ge=0)
    index_bytes: int | None = Field(default=None, ge=0)
    toast_bytes: int | None = Field(default=None, ge=0)
    dead_tuples: int | None = Field(default=None, ge=0)
    last_vacuum: datetime | None = None
    last_analyze: datetime | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
