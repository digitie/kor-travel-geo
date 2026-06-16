"""Admin and debugging DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .common import FrozenModel

LoadJobState = Literal["queued", "running", "done", "failed", "cancelled"]
LoadJobKind = Literal[
    "full_load_batch",
    "db_backup",
    "db_restore",
    "juso_text_load",
    "daily_juso_delta",
    "juso_parcel_link_load",
    "juso_parcel_link_delta",
    "roadaddr_entrance_load",
    "sppn_makarea_load",
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
ConsistencyDecisionState = Literal["unreviewed", "approved", "rejected", "deferred"]
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
SourceKind = Literal[
    "juso",
    "parcel_link",
    "locsum",
    "navi",
    "shp",
    "roadaddr_entrance",
    "sppn_makarea",
    "pobox",
    "bulk",
]
SourceConfidence = Literal["high", "medium", "low"]
UploadSetState = Literal["created", "uploading", "uploaded", "cancelled", "failed"]
UploadFileState = Literal["pending", "uploading", "uploaded", "cancelled", "failed"]
UploadStorageKind = Literal["local", "rustfs"]
BackupFormat = Literal["directory_tar_zstd"]
BackupProfile = Literal["serving-ready", "lean-serving", "forensic"]
# T-229/T-230/T-239: retention policy class on a backup artifact. ``pinned`` is never
# expired by the janitor; ``scheduled`` marks cron-driven backups (respects keep_min).
BackupRetentionClass = Literal["default", "scheduled", "pinned"]
RestoreMode = Literal["new_database", "replace_current"]


class TableStat(FrozenModel):
    table_name: str
    row_count: int = Field(ge=0)
    size_bytes: int | None = Field(default=None, ge=0)
    updated_at: str | None = None


class BackupAllowedDirs(FrozenModel):
    """Server-side allowlist of directories usable for backup output."""

    dirs: tuple[str, ...] = ()
    default_dir: str | None = None


class UploadSidoZipResponse(FrozenModel):
    upload_id: str
    filename: str
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class BackupCreateRequest(FrozenModel):
    destination_dir: str | None = None
    profile: BackupProfile = "serving-ready"
    format: BackupFormat = "directory_tar_zstd"
    jobs: int | None = Field(default=None, ge=1, le=64)
    compression_level: int | None = Field(default=None, ge=1, le=19)
    callback_url: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    # T-239: tag the artifact's retention class at create time. ``scheduled`` is set
    # by the cron run-due trigger; ``pinned`` opts a backup out of janitor expiry.
    retention_class: BackupRetentionClass = "default"
    include_materialized_views: bool = True


class RestoreCreateRequest(FrozenModel):
    artifact_id: str | None = None
    archive_path: str | None = None
    target_database: str | None = Field(default=None, min_length=1, max_length=63)
    target_dsn: str | None = None
    mode: RestoreMode = "new_database"
    jobs: int | None = Field(default=None, ge=1, le=64)
    run_analyze: bool = True
    run_smoke_test: bool = True
    run_consistency: bool = False
    run_row_count_check: bool = True
    allow_version_mismatch: bool = False
    # T-243: emergency last resort — restore intact tables, skipping corrupted data files.
    allow_partial: bool = False
    callback_url: str | None = None
    confirmation: str | None = Field(default=None, max_length=200)


class RestoreHotSwapPlanRequest(FrozenModel):
    restore_database: str = Field(min_length=1, max_length=63)
    previous_alias: str | None = Field(default=None, min_length=1, max_length=63)
    previous_alias_retention_days: int = Field(default=7, ge=1, le=3650)
    maintenance_database: str = Field(default="postgres", min_length=1, max_length=63)


class RestoreHotSwapPlan(FrozenModel):
    current_database: str
    restore_database: str
    previous_alias: str
    maintenance_database: str
    typed_confirmation: str
    rollback_confirmation: str
    previous_alias_retention_days: int = Field(ge=1)
    can_execute: bool = False
    blockers: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    sql: tuple[str, ...] = ()


class RestoreHotSwapExecuteRequest(FrozenModel):
    """T-241 request to actually execute the ADR-036 rename hot-swap.

    Requires an active ``ops.maintenance_windows(kind='restore')`` whose confirmation
    equals ``typed_confirmation`` (= ``HOT_SWAP <current> FROM <restore>``). The swap runs
    under the ``HOT_SWAP`` advisory lock; a concurrent second call fails fast (409).
    """

    restore_database: str = Field(min_length=1, max_length=63)
    typed_confirmation: str = Field(min_length=1, max_length=200)
    previous_alias: str | None = Field(default=None, min_length=1, max_length=63)
    previous_alias_retention_days: int = Field(default=7, ge=1, le=3650)
    maintenance_database: str = Field(default="postgres", min_length=1, max_length=63)
    run_smoke_test: bool = True
    allow_version_mismatch: bool = False


class RestoreHotSwapResult(FrozenModel):
    """T-241 result of a hot-swap execution attempt."""

    swapped: bool
    current_database: str
    restore_database: str
    previous_alias: str
    rolled_back: bool = False
    smoke_ok: bool | None = None
    serving_release_id: str | None = None
    previous_release_id: str | None = None
    rollback_confirmation: str | None = None
    message: str | None = None


class RestoreHotSwapRollbackRequest(FrozenModel):
    """T-264 request to manually roll back a previously-completed hot-swap.

    Brings ``previous_alias`` (the pre-swap serving DB, retained for
    ``previous_alias_retention_days``) back as the current database, renaming the currently
    serving (restored) DB to ``restore_database``. Requires an active
    ``ops.maintenance_windows(kind='restore')`` whose confirmation equals
    ``rollback_confirmation`` (= ``ROLLBACK_HOT_SWAP <current> FROM <previous_alias>``). Rejected
    once retention has dropped ``previous_alias``; runs under the ``HOT_SWAP`` lock (fail-fast).
    """

    previous_alias: str = Field(min_length=1, max_length=63)
    restore_database: str = Field(min_length=1, max_length=63)
    rollback_confirmation: str = Field(min_length=1, max_length=200)
    maintenance_database: str = Field(default="postgres", min_length=1, max_length=63)
    run_smoke_test: bool = True


class RestoreHotSwapRollbackResult(FrozenModel):
    """T-264 result of a manual hot-swap rollback attempt."""

    rolled_back: bool
    current_database: str
    restore_database: str
    previous_alias: str
    smoke_ok: bool | None = None
    serving_release_id: str | None = None
    previous_release_id: str | None = None
    blockers: tuple[str, ...] = ()
    message: str | None = None


class SourceCandidate(FrozenModel):
    kind: SourceKind
    path: str
    inferred_yyyymm: str | None = Field(default=None, pattern=r"^\d{6}$")
    sido_count: int | None = Field(default=None, ge=0)
    file_count: int | None = Field(default=None, ge=0)
    byte_size: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    confidence: SourceConfidence
    note: str | None = None


class SourceSetDiscoveryRequest(FrozenModel):
    root_path: str | None = None
    upload_set_id: str | None = None
    include_optional: bool = True


class SourceSetDiscovery(FrozenModel):
    root_path: str
    candidates: tuple[SourceCandidate, ...] = ()
    recommended: dict[str, SourceCandidate] = Field(default_factory=dict)
    missing_required: tuple[str, ...] = ()
    mixed_yyyymm: bool = False
    yyyymm_by_kind: dict[str, str | None] = Field(default_factory=dict)
    warning: str | None = None


class SourceSetPlanRequest(FrozenModel):
    root_path: str | None = None
    upload_set_id: str | None = None
    versions: dict[str, str] = Field(default_factory=dict)
    explicit_paths: dict[str, str] = Field(default_factory=dict)
    include_optional: bool = True
    allow_mixed_yyyymm: bool = False
    confirmation_token: str | None = None
    acknowledged_by: Literal["cli", "api", "ui"] = "api"


class SourceSetPlan(FrozenModel):
    source_set_id: str
    root_path: str | None = None
    candidates: tuple[SourceCandidate, ...] = ()
    selected: dict[str, SourceCandidate] = Field(default_factory=dict)
    missing_required: tuple[str, ...] = ()
    yyyymm_by_kind: dict[str, str | None] = Field(default_factory=dict)
    mixed_yyyymm: bool = False
    mixed_yyyymm_acknowledged: bool = False
    acknowledged_by: Literal["cli", "api", "ui"] | None = None
    acknowledged_at: datetime | None = None
    confirmation_token_hash: str | None = Field(default=None, min_length=64, max_length=64)
    expected_confirmation_token: str | None = None
    candidate_paths: dict[str, str] = Field(default_factory=dict)
    candidate_sha256: dict[str, str | None] = Field(default_factory=dict)
    batch_payload: dict[str, Any] = Field(default_factory=dict)
    warning: str | None = None


class UploadSetCreateRequest(FrozenModel):
    purpose: Literal["full_load_source_set"] = "full_load_source_set"
    storage_kind: UploadStorageKind | None = None


class UploadFileStatus(FrozenModel):
    upload_set_id: str
    file_id: str
    filename: str
    relative_path: str | None = None
    path: str
    state: UploadFileState
    storage_kind: UploadStorageKind = "local"
    storage_uri: str | None = None
    object_key: str | None = None
    object_etag: str | None = None
    size_bytes: int = Field(default=0, ge=0)
    uploaded_bytes: int = Field(default=0, ge=0)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    inferred_yyyymm: str | None = Field(default=None, pattern=r"^\d{6}$")
    source_kind: SourceKind | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class UploadSetStatus(FrozenModel):
    upload_set_id: str
    purpose: str
    state: UploadSetState
    root_path: str
    storage_kind: UploadStorageKind = "local"
    storage_uri: str | None = None
    storage_prefix: str | None = None
    materialized_path: str | None = None
    files: tuple[UploadFileStatus, ...] = ()
    total_bytes: int = Field(default=0, ge=0)
    uploaded_bytes: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None


class RustfsSecretStatus(FrozenModel):
    configured: bool = False
    hint: str | None = None


class RustfsStorageConfig(FrozenModel):
    enabled: bool = False
    endpoint_url: str
    bucket: str
    prefix: str
    region: str = "us-east-1"
    force_path_style: bool = True
    retention_days: int = Field(default=0, ge=0)
    access_key: RustfsSecretStatus = Field(default_factory=RustfsSecretStatus)
    secret_key: RustfsSecretStatus = Field(default_factory=RustfsSecretStatus)


class RustfsStorageConfigPatch(FrozenModel):
    enabled: bool | None = None
    endpoint_url: str | None = Field(default=None, min_length=1)
    bucket: str | None = Field(default=None, min_length=1, max_length=63)
    prefix: str | None = Field(default=None, min_length=1)
    region: str | None = Field(default=None, min_length=1)
    force_path_style: bool | None = None
    retention_days: int | None = Field(default=None, ge=0)
    access_key: str | None = Field(default=None, min_length=1)
    secret_key: str | None = Field(default=None, min_length=1)


class RustfsConnectionCheck(FrozenModel):
    ok: bool
    endpoint_url: str
    bucket: str
    prefix: str
    message: str | None = None


class RustfsImportPrefixRequest(FrozenModel):
    prefix: str = Field(min_length=1)
    purpose: Literal["full_load_source_set"] = "full_load_source_set"


class RustfsSyncLocalRequest(FrozenModel):
    root_path: str = Field(min_length=1)
    prefix: str | None = Field(default=None, min_length=1)
    purpose: Literal["full_load_source_set"] = "full_load_source_set"


class RustfsSyncLocalResult(FrozenModel):
    upload_set: UploadSetStatus
    uploaded_files: int = Field(ge=0)
    uploaded_bytes: int = Field(ge=0)
    skipped_files: int = Field(default=0, ge=0)


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
    source_set: dict[str, Any] | None = None
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
    source_set: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None = None
    generated_by: Literal["cli", "api", "cron"] = "api"


class ConsistencyReport(ConsistencyReportSummary):
    cases: tuple[ConsistencyCase, ...] = ()


class ConsistencyCaseInput(FrozenModel):
    """One registry input (``ops.consistency_case_inputs``).

    ``required=False`` encodes an optional/conditional input (e.g. C11's
    ``roadaddr_entrance_full``, only a full comparison when its 기준월 matches).
    """

    category: str
    required: bool = True


class ConsistencyCaseDefinition(FrozenModel):
    """A consistency case from the ``ops.consistency_case_definitions`` registry.

    ``code`` is ``consistency_case_code``. The first eight fields are the
    original C1~C10 contract (kept for the existing UI tab); the rest are the
    T-206 registry columns the dynamic case tab (T-209) renders for C11~C17.
    """

    code: str
    name: str
    compares: str
    abnormal_criteria: str
    evidence: tuple[str, ...] = ()
    likely_causes: tuple[str, ...] = ()
    decision_guide: str
    threshold: str | None = None
    display_order: int | None = None
    default_severity: ConsistencySeverity | None = None
    state: Literal["enabled", "disabled", "retired"] = "enabled"
    inputs: tuple[ConsistencyCaseInput, ...] = ()
    skip_policy: dict[str, Any] = Field(default_factory=dict)
    sample_schema: dict[str, Any] = Field(default_factory=dict)
    introduced_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


ConsistencyInputState = Literal[
    "passed",
    "warning",
    "skipped",
    "failed",
    "not_started",
    "validating",
]


class ConsistencyRunValidationRequest(FrozenModel):
    """``POST /v1/admin/source-match-sets/{id}/run-validation`` body (doc ~1564).

    Runs the registry C11~C17 validation cases against an existing DB (no
    rebuild). ``cases`` limits which registry cases run (default: all enabled
    augment cases). The optional inputs are materialized + integrity-gated; an
    absent input is ``skipped``, a corrupt/mismatched archive is ``failed``.
    """

    cases: tuple[str, ...] | None = None


class ConsistencyValidationInput(FrozenModel):
    """Per-input run-validation outcome (``validation_inputs.<category>``)."""

    category: str
    state: ConsistencyInputState
    required: bool = True
    failure_reason: str | None = None
    source_file_group_id: str | None = None


class ConsistencyCaseValidationResult(FrozenModel):
    """One registry case's run-validation outcome."""

    case_code: str
    runnable: bool
    skipped: bool
    failed: bool
    inputs: tuple[ConsistencyValidationInput, ...] = ()
    quarantine_group_ids: tuple[str, ...] = ()
    metric: dict[str, Any] | None = None


class ConsistencyRunValidationResponse(FrozenModel):
    """``run-validation`` result (doc ~1564-1578).

    No new DB / snapshot / release is created. ``validator_version`` is the
    validator that ran; ``revalidated_case_codes`` are cases whose prior
    ``passed`` was reverted to ``not_started`` because the validator changed
    (doc ~1620). ``affected_match_set_ids`` are sets marked needing
    re-validation by the integrity-failure or validator-change propagation.
    """

    source_match_set_id: str
    validator_version: str
    dataset_snapshot_id: str | None = None
    cases: tuple[ConsistencyCaseValidationResult, ...] = ()
    revalidated_case_codes: tuple[str, ...] = ()
    quarantined_group_ids: tuple[str, ...] = ()
    affected_match_set_ids: tuple[str, ...] = ()
    skipped_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    runnable_count: int = Field(default=0, ge=0)


class ConsistencySamplePoint(FrozenModel):
    x: float
    y: float


class ConsistencyCaseSample(FrozenModel):
    sample_id: str
    report_id: str
    case_code: str
    severity: ConsistencySeverity
    sample_rank: int = Field(ge=0)
    bd_mgt_sn: str | None = None
    rncode_full: str | None = None
    sig_cd: str | None = None
    bjd_cd: str | None = None
    distance_m: float | None = None
    source_yyyymm: str | None = None
    source_kind: str | None = None
    case_metric: dict[str, Any] = Field(default_factory=dict)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    point: ConsistencySamplePoint | None = None
    bbox_4326: dict[str, Any] = Field(default_factory=dict)
    has_polygon: bool = False
    has_line: bool = False
    decision_state: ConsistencyDecisionState = "unreviewed"
    reason_code: str | None = None
    note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class ConsistencySamplePage(FrozenModel):
    report_id: str
    case_code: str
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    items: tuple[ConsistencyCaseSample, ...] = ()


class ConsistencyCaseSummary(FrozenModel):
    report_id: str
    case_code: str
    total: int = Field(ge=0)
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_decision: dict[str, int] = Field(default_factory=dict)
    by_sig_cd: dict[str, int] = Field(default_factory=dict)
    distance: dict[str, float] = Field(default_factory=dict)


class ConsistencySampleDecisionRequest(FrozenModel):
    decision_state: Literal["approved", "rejected", "deferred"]
    reason_code: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=120)


class ConsistencyBulkDecisionRequest(ConsistencySampleDecisionRequest):
    sample_ids: tuple[str, ...] = Field(min_length=1, max_length=1000)


class ConsistencyBulkDecisionResponse(FrozenModel):
    report_id: str
    case_code: str
    updated_count: int = Field(ge=0)
    items: tuple[ConsistencyCaseSample, ...] = ()


class ConsistencySampleRecheckResponse(FrozenModel):
    sample_id: str
    report_id: str
    case_code: str
    exists_in_current_mv: bool
    point: ConsistencySamplePoint | None = None
    stale: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(FrozenModel):
    audit_event_id: str
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
    dataset_snapshot_id: str
    state: DatasetSnapshotState
    parent_dataset_snapshot_id: str | None = None
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
    serving_release_id: str
    dataset_snapshot_id: str
    state: ServingReleaseState
    release_kind: ServingReleaseKind
    previous_serving_release_id: str | None = None
    rollback_target_serving_release_id: str | None = None
    mv_name: str = "mv_geocode_target"
    mv_hash: str | None = None
    consistency_gate: dict[str, Any] = Field(default_factory=dict)
    performance_gate: dict[str, Any] = Field(default_factory=dict)
    activated_by_job_id: str | None = None
    activated_at: datetime | None = None
    notes: str | None = None
    created_at: datetime


class RollbackPlan(FrozenModel):
    serving_release_id: str
    dataset_snapshot_id: str
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
    dataset_snapshot_id: str | None = None
    serving_release_id: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    callback_url: str | None = None
    callback_state: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class BackupArtifact(OpsArtifact):
    download_url: str | None = None
    # T-240: manifest-derived catalog summary (expires_at/retention_class inherited).
    source_set_yyyymm: dict[str, str | None] | None = None
    source_set_mixed: bool | None = None
    source_inventory_ok: bool | None = None


class BackupRetentionRunRequest(FrozenModel):
    """T-230 backup retention janitor request."""

    dry_run: bool = False
    keep_min_count: int | None = Field(default=None, ge=0)


class RestoreRowCountDiff(FrozenModel):
    """T-233 per-object row-count comparison (manifest vs restored DB)."""

    object: str
    expected: int | None = None
    actual: int
    match: bool


class RestoreReconcileResult(FrozenModel):
    """T-233 post-restore data reconcile (manifest vs restored DB)."""

    ok: bool
    target_database: str | None = None
    row_count_diffs: tuple[RestoreRowCountDiff, ...] = ()
    mv_geocode_target_rows: int | None = None
    mv_geocode_text_search_rows: int | None = None
    mv_nonempty_ok: bool | None = None
    sppn_rows: int | None = None
    pt_source_distribution: dict[str, int] | None = None
    source_set_yyyymm: dict[str, str | None] | None = None
    warnings: tuple[str, ...] = ()


class RestoreDryRunResult(FrozenModel):
    """T-232 restore dry-run: preflight checks without running pg_restore."""

    can_restore: bool
    mode: RestoreMode
    target_database: str | None = None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    archive_sha256_ok: bool | None = None
    internal_checksums_ok: bool | None = None
    manifest_ok: bool | None = None
    backup_postgres_version: str | None = None
    backup_postgis_version: str | None = None
    target_postgres_version: str | None = None
    target_postgis_version: str | None = None
    row_counts: dict[str, int] | None = None


class RestoreDrillResult(FrozenModel):
    """T-242 restore-drill outcome (restore into a throwaway DB → reconcile/smoke → drop).

    ``status`` is ``FAIL`` if the restore raised, reconcile mismatched, or smoke failed.
    ``cleanup_ok`` reports whether the throwaway DB was dropped (always attempted).
    """

    status: Literal["PASS", "FAIL"]
    temp_database: str
    duration_seconds: float
    restored: bool
    cleanup_ok: bool
    reconcile_ok: bool | None = None
    smoke_ok: bool | None = None
    archive_size_bytes: int | None = None
    source_artifact_id: str | None = None
    reconcile: RestoreReconcileResult | None = None
    errors: tuple[str, ...] = ()


class BackupCopyRequest(FrozenModel):
    """T-236 off-host backup copy request."""

    target_dir: str = Field(min_length=1)


class BackupCopyResult(FrozenModel):
    """T-236 result of copying a backup archive to another allowlisted directory."""

    artifact_id: str
    source_path: str
    destination_path: str
    sha256: str
    verified: bool


class BackupVerifyRequest(FrozenModel):
    """T-231 on-demand backup integrity check request."""

    mode: Literal["quick", "deep"] = "quick"


class BackupVerifyResult(FrozenModel):
    """T-231 non-destructive backup integrity result (corruption → ok=False)."""

    artifact_id: str
    mode: Literal["quick", "deep"]
    ok: bool
    archive_sha256: str | None = None
    archive_sha256_matches: bool | None = None
    internal_checksums_ok: bool | None = None
    manifest_ok: bool | None = None
    row_counts: dict[str, int] | None = None
    errors: tuple[str, ...] = ()


class BackupRetentionResult(FrozenModel):
    """T-230 result of one backup retention janitor pass."""

    dry_run: bool
    keep_min_count: int
    skipped_locked: bool = False
    scanned: int = 0
    protected_count: int = 0
    expired_count: int = 0
    failed_count: int = 0
    expired_artifact_ids: tuple[str, ...] = ()
    failed_artifact_ids: tuple[str, ...] = ()


class ScheduledBackupStatus(FrozenModel):
    """T-239 scheduled-backup due-check status (read-only).

    ``due`` reflects the decision at ``now``: ``True`` iff scheduling is enabled, no
    scheduled backup is in progress, and ``interval_hours`` has elapsed since the last
    scheduled run (or none has ever run).
    """

    enabled: bool
    interval_hours: float
    keep_min: int
    retention_class: BackupRetentionClass = "scheduled"
    due: bool
    reason: Literal["disabled", "in_progress", "due_initial", "due", "not_due"]
    in_progress: bool = False
    last_scheduled_at: datetime | None = None
    next_due_at: datetime | None = None


class ScheduledBackupRunResult(FrozenModel):
    """T-239 result of one idempotent ``run-due`` trigger.

    ``enqueued`` is ``True`` only when this call actually queued a backup job.
    ``skipped_locked`` means another concurrent trigger held the schedule lock, so this
    call did nothing (still a successful 200 for an external cron).
    """

    enqueued: bool
    job_id: str | None = None
    skipped_locked: bool = False
    status: ScheduledBackupStatus


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
    maintenance_window_id: str
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
    table_stats_snapshot_id: str
    dataset_snapshot_id: str | None = None
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
