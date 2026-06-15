"""Source file registry and match set read-model DTOs (T-200).

These mirror the ``ops.source_file_groups`` / ``ops.source_files`` /
``ops.source_match_sets`` tables defined in
``docs/t109-backup-source-upload-management.md`` and ``infra/sql.py``.
They are read-only API DTOs with no behavior.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Any, Literal

from pydantic import Field

from .common import FrozenModel

SourceFileCategory = Literal[
    "roadname_hangul_full",
    "locsum_full",
    "navi_full",
    "electronic_map_full",
    "roadaddr_entrance_full",
    "zone_shape_full",
    "roadaddr_building_shape_bundle",
    "detail_dong_shape_bundle",
    "detail_address_db_full",
    "national_point_grid_shape",
    "national_point_grid_center",
    "civil_service_institution_map",
    "address_db_full",
    "building_db_full",
    "epost_pobox_full",
    "epost_bulk_full",
]
SourceGroupKind = Literal["single_file", "multi_part"]
SourceGroupState = Literal[
    "validating",
    "available",
    "quarantined",
    "missing",
    "soft_deleted",
    "hard_deleted",
    "delete_failed",
]
SourceFileState = SourceGroupState
SourceValidationState = Literal[
    "unknown",
    "not_started",
    "running",
    "passed",
    "warning",
    "failed",
    "skipped",
]
SourceFilePartKind = Literal["single", "sido", "grid_layer", "custom"]
SourceMatchSetState = Literal[
    "draft",
    "validated",
    "active",
    "retired",
    "invalid",
    "revalidatable",
    "restored_from_backup",
]
SourceMatchSetItemRole = Literal[
    "build_required",
    "build_recommended",
    "validation_optional",
    "enrichment_candidate",
]


class SourceFileCategoryInfo(FrozenModel):
    """One entry in the static upload-category catalog (T-201).

    Serialized form of ``core.source_categories.SourceCategory`` for the
    ``GET /v1/admin/source-file-categories`` endpoint. ``role``/``default_role``
    are UI defaults; the authoritative role lives on
    ``ops.source_match_set_items.role``.
    """

    category: SourceFileCategory
    label: str
    group_kind: SourceGroupKind
    default_role: SourceMatchSetItemRole
    role: SourceMatchSetItemRole
    expected_member_kinds: tuple[str, ...] = ()
    optional: bool = False


class SourceFileCategoryCatalog(FrozenModel):
    """Response wrapper for the static upload-category catalog."""

    categories: tuple[SourceFileCategoryInfo, ...] = ()


class SourceFileGroup(FrozenModel):
    """Registry unit referenced directly by a match set."""

    source_file_group_id: str
    category: str
    group_kind: SourceGroupKind
    display_name: str
    state: SourceGroupState
    validation_state: SourceValidationState
    user_yyyymm: str = Field(pattern=r"^\d{6}$")
    inferred_yyyymm: str | None = Field(default=None, pattern=r"^\d{6}$")
    inferred_yyyymm_basis: str | None = None
    yyyymm_mismatch: bool = False
    expected_file_count: int = Field(default=1, ge=1)
    actual_file_count: int = Field(default=0, ge=0)
    coverage: dict[str, Any] = Field(default_factory=dict)
    group_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    uploaded_by: str | None = None
    uploaded_at: datetime
    updated_at: datetime
    validated_at: datetime | None = None
    deleted_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)


class SourceFile(FrozenModel):
    """Canonical registry of an uploaded compressed source archive."""

    source_file_id: str
    source_file_group_id: str
    original_filename: str
    part_kind: SourceFilePartKind = "single"
    part_key: str = "archive"
    part_label: str | None = None
    file_role: str | None = None
    content_type: str | None = None
    compression_format: str
    state: SourceFileState
    validation_state: SourceValidationState
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    duplicate_of_file_id: str | None = None
    storage_kind: str
    storage_uri: str
    bucket: str | None = None
    object_key: str | None = None
    object_etag: str | None = None
    object_version_id: str | None = None
    last_verified_etag: str | None = None
    last_verified_size_bytes: int | None = Field(default=None, ge=0)
    last_verified_at: datetime | None = None
    last_deep_verified_at: datetime | None = None
    rustfs_endpoint_hash: str | None = None
    uploaded_by: str | None = None
    uploaded_at: datetime
    validated_at: datetime | None = None
    deleted_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)


# --- Upload session lifecycle (T-203a) ------------------------------------
# State machine + endpoint shapes follow the t109 doc "업로드 상태 머신"
# (lines ~1052-1115) and "API 설계" upload-session sections (~1220-1345).

#: Non-terminal session states the duplicate-session (409) check guards
#: against and that the resume entry point can continue.
SourceUploadSessionState = Literal[
    # progress states
    "created",
    "uploading",
    "uploaded_to_temp",
    "storing_to_rustfs",
    "verifying_rustfs_object",
    "extracting",
    "validating_structure",
    "hashing",
    "duplicate_check",
    "awaiting_registration",
    "registered",
    "available",
    # failure states
    "failed_upload",
    "failed_extract",
    "failed_structure",
    "failed_hash",
    "failed_rustfs_put",
    "failed_rustfs_verify",
    "failed_storage_state",
    "failed_register",
    "cancelled",
    "expired",
    # janitor (T-203c): stored-but-unregistered object past the registration
    # deadline; user must re-register, extend the deadline, or discard.
    "registration_expired",
]

#: Terminal states: a session here cannot be resumed and no longer blocks a new
#: session for the same ``(category, user_yyyymm)``.
TERMINAL_UPLOAD_SESSION_STATES: frozenset[str] = frozenset(
    {
        "registered",
        "available",
        "cancelled",
        "expired",
        "registration_expired",
        "failed_upload",
        "failed_extract",
        "failed_structure",
        "failed_hash",
        "failed_rustfs_put",
        "failed_rustfs_verify",
        "failed_storage_state",
    }
)

SourceUploadStrategy = Literal["multipart"]
SourceUploadStorageKind = Literal["rustfs", "local"]


class UploadSessionCreateRequest(FrozenModel):
    """``POST /v1/admin/source-files/upload-sessions`` body.

    ``user_yyyymm`` is server-mandatory (``^\\d{6}$``): the backend never fills a
    missing month from the filename or the current date (doc line 1259).
    """

    category: SourceFileCategory
    user_yyyymm: str = Field(pattern=r"^\d{6}$")
    display_name: str = Field(min_length=1)
    storage_kind: SourceUploadStorageKind = "rustfs"
    upload_strategy: SourceUploadStrategy = "multipart"


class UploadSessionFileSlot(FrozenModel):
    """One upload slot: ``archive`` for single_file, a sido for multi_part."""

    slot: str
    part_kind: SourceFilePartKind = "single"
    part_key: str = "archive"
    part_label: str | None = None
    required: bool = True
    uploaded: bool = False
    multipart_upload_id: str | None = None
    received_bytes: int = Field(default=0, ge=0)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    object_etag: str | None = None
    object_key: str | None = None


class UploadSessionPartStatus(FrozenModel):
    """One ``ops.source_upload_session_parts`` row (resume bookkeeping)."""

    part_key: str
    part_number: int = Field(ge=1)
    multipart_upload_id: str | None = None
    part_etag: str | None = None
    part_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    received_bytes: int = Field(default=0, ge=0)
    completed_at: datetime | None = None


class UploadSessionStatus(FrozenModel):
    """Session create / list / get response (resumable entry point)."""

    upload_session_id: str
    source_file_group_id: str
    category: SourceFileCategory
    group_kind: SourceGroupKind
    user_yyyymm: str = Field(pattern=r"^\d{6}$")
    display_name: str
    state: SourceUploadSessionState
    upload_strategy: SourceUploadStrategy = "multipart"
    storage_kind: SourceUploadStorageKind = "rustfs"
    expected_file_count: int = Field(ge=1)
    uploaded_file_count: int = Field(default=0, ge=0)
    max_bytes: int = Field(ge=1)
    part_size_bytes: int = Field(ge=1)
    registration_state: Literal["not_registered", "registered", "quarantined"] = "not_registered"
    bucket: str | None = None
    prefix: str | None = None
    file_slots: tuple[UploadSessionFileSlot, ...] = ()
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    registration_deadline_at: datetime | None = None
    completed_at: datetime | None = None
    registered_at: datetime | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadSessionConflict(FrozenModel):
    """``409`` body when a non-terminal session already exists for the slot.

    Carries enough to let the UI resume the existing session instead of
    silently creating a duplicate group + orphan object (doc line 1261).
    """

    error: Literal["upload_session_conflict"] = "upload_session_conflict"
    message: str
    upload_session_id: str
    state: SourceUploadSessionState
    category: SourceFileCategory
    user_yyyymm: str = Field(pattern=r"^\d{6}$")
    uploaded_file_count: int = Field(default=0, ge=0)
    expected_file_count: int = Field(ge=1)
    resumable_actions: tuple[str, ...] = ()
    existing_session: UploadSessionStatus


class MultipartInitiateResponse(FrozenModel):
    """``POST .../files/{slot}/multipart`` response."""

    upload_session_id: str
    slot: str
    part_key: str
    multipart_upload_id: str
    object_key: str
    part_size_bytes: int = Field(ge=1)


class UploadPartResponse(FrozenModel):
    """``PUT .../files/{slot}/multipart/{part_number}`` response."""

    upload_session_id: str
    slot: str
    part_key: str
    part_number: int = Field(ge=1)
    received_bytes: int = Field(ge=0)
    part_etag: str
    part_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class MultipartCompleteRequest(FrozenModel):
    """``POST .../files/{slot}/multipart/complete`` body."""

    part_etags: tuple[tuple[int, str], ...] = Field(
        default=(),
        description="optional (part_number, etag) pairs; falls back to recorded parts",
    )


class SlotReplaceResponse(FrozenModel):
    """``POST .../files/{slot}/replace`` response.

    Replace invalidates the slot's prior validation + hash results and reopens
    it for a fresh upload (doc line 1314).
    """

    upload_session_id: str
    slot: str
    part_key: str
    invalidated: bool = True
    state: SourceUploadSessionState


class SourceUploadProgressEvent(FrozenModel):
    """SSE ``source_upload.progress`` event payload (doc lines 1330-1342)."""

    event: Literal["source_upload.progress"] = "source_upload.progress"
    upload_session_id: str
    state: SourceUploadSessionState
    stage: str | None = None
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    current_item: str | None = None
    uploaded_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    message: str | None = None
    log_tail: str | None = None


EpostServerFetchCategory = Literal["epost_pobox_full", "epost_bulk_full"]
EpostDownloadKind = Literal["1", "4"]
EpostLoadJobKind = Literal["pobox_load", "bulk_load"]


class EpostServerFetchRequest(FrozenModel):
    """``POST /v1/admin/source-files/epost-fetch`` body (T-207).

    Manual operator-triggered server fetch. The server downloads the epost ZIP
    from configured OpenAPI settings, extracts the requested postal auxiliary
    text file, validates it with the T-120 validator, registers it as a
    ``single_file`` source archive in RustFS, then optionally enqueues the
    corresponding loader job. It is not a scheduled downloader and it does not
    participate in core ``rebuild-db`` source match sets.
    """

    category: EpostServerFetchCategory
    user_yyyymm: str = Field(pattern=r"^\d{6}$")
    download_kind: EpostDownloadKind | None = None
    display_name: str | None = Field(default=None, min_length=1)
    yyyymm_mismatch_ack: bool = False
    enqueue_load: bool = True


class EpostServerFetchResponse(FrozenModel):
    """Result of one manual epost server-fetch/register/load enqueue run."""

    category: EpostServerFetchCategory
    upload_session: UploadSessionStatus
    registration: RegisterResponse | None = None
    load_job_id: str | None = None
    load_job_kind: EpostLoadJobKind | None = None
    selected_filename: str | None = None
    selected_path: str | None = None
    validation: dict[str, Any] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()


# --- Registry register / validate (T-203b) --------------------------------
# Shapes for ``POST .../upload-sessions/{id}/register`` and
# ``POST .../source-file-groups/{id}/validate`` (doc "Registry 등록 승인" ~1347
# and "카테고리별 기대 구조" ~868).


class RegisterRequest(FrozenModel):
    """``POST .../upload-sessions/{id}/register`` body (doc lines ~1355-1364).

    ``confirm_user_yyyymm`` must equal the session ``user_yyyymm`` (the server
    never reinterprets it as a month edit). When the inferred month differs,
    ``yyyymm_mismatch_ack=true`` is required.
    """

    confirm_user_yyyymm: str = Field(pattern=r"^\d{6}$")
    display_name: str | None = None
    yyyymm_mismatch_ack: bool = False
    registration_note: str | None = None


class SourceFileRegistered(FrozenModel):
    """One ``ops.source_files`` row created by register (doc lines ~1376-1384)."""

    source_file_id: str
    original_filename: str
    part_kind: SourceFilePartKind = "single"
    part_key: str = "archive"
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    storage_uri: str
    object_key: str | None = None
    bucket: str | None = None
    state: SourceFileState
    duplicate_of_file_id: str | None = None


class RegisterResponse(FrozenModel):
    """``register`` success body (doc lines ~1368-1385)."""

    source_file_group_id: str
    category: SourceFileCategory
    group_kind: SourceGroupKind
    state: SourceGroupState
    validation_state: SourceValidationState
    user_yyyymm: str = Field(pattern=r"^\d{6}$")
    group_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    files: tuple[SourceFileRegistered, ...] = ()
    duplicate_warning: bool = False
    duplicate_of_group_id: str | None = None


class GroupValidationResult(FrozenModel):
    """``POST .../source-file-groups/{id}/validate`` response.

    The structure-validation outcome that recompute folds into the group's
    ``validation_state`` and ``coverage`` (doc "source_file_validations").
    """

    source_file_group_id: str
    category: SourceFileCategory
    validation_state: SourceValidationState
    state: SourceGroupState
    coverage: dict[str, str] = Field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    validator_version: str


# --- Soft-delete / restore (T-203c) ---------------------------------------
# Shapes for ``POST .../source-file-groups/{id}/soft-delete`` and ``/restore``
# (doc "파일 목록/다운로드/삭제" lines ~1438-1445).


class SourceGroupSoftDeleteRequest(FrozenModel):
    """``POST .../source-file-groups/{id}/soft-delete`` body."""

    reason: str | None = None


class SourceGroupSoftDeleteResponse(FrozenModel):
    """``soft-delete`` result: the group + its children are now ``soft_deleted``."""

    source_file_group_id: str
    state: SourceGroupState
    deleted_at: datetime | None = None
    affected_file_count: int = Field(default=0, ge=0)
    affected_match_set_ids: tuple[str, ...] = ()


class SourceGroupRestoreFile(FrozenModel):
    """Per-child restore outcome (object verified vs missing/quarantined)."""

    source_file_id: str
    part_key: str
    state: SourceFileState
    reasons: tuple[str, ...] = ()


class SourceGroupRestoreResponse(FrozenModel):
    """``restore`` result: the canonical recovery path (not re-upload).

    Children land in ``available`` (object present + structure ok), ``missing``
    (object absent), or ``quarantined`` (hash/size mismatch). The group state is
    recomputed and propagated to referencing match sets.
    """

    source_file_group_id: str
    category: SourceFileCategory
    state: SourceGroupState
    validation_state: SourceValidationState
    files: tuple[SourceGroupRestoreFile, ...] = ()
    affected_match_set_ids: tuple[str, ...] = ()


class SourceJanitorRunResponse(FrozenModel):
    """``run_source_upload_janitor`` summary (CLI + admin)."""

    processed_sessions: int = Field(default=0, ge=0)
    expired_sessions: int = Field(default=0, ge=0)
    cancelled_sessions: int = Field(default=0, ge=0)
    registration_expired: int = Field(default=0, ge=0)
    aborts_succeeded: int = Field(default=0, ge=0)
    aborts_failed: int = Field(default=0, ge=0)
    skipped_locked: bool = False


# --- RustFS reconciliation (T-204) ----------------------------------------
# DB/RustFS consistency scan + resolve. Tables: ``ops.source_storage_reconcile_runs``
# / ``ops.source_storage_reconcile_items`` (doc lines ~638-726, ~1449-1479).

ReconcileMode = Literal["quick", "deep"]
ReconcileIssueType = Literal[
    "db_missing_object",
    "object_missing_db",
    "pending_registration",
    "registration_expired",
    "source_file_unavailable",
    "source_file_group_incomplete",
    "size_mismatch",
    "hash_mismatch",
    "etag_mismatch",
    "duplicate_object",
    "orphaned_multipart",
    "delete_failed",
]
ReconcileItemState = Literal["open", "resolved", "ignored"]
ReconcileRunState = Literal["running", "completed", "failed"]
ReconcileSeverity = Literal["info", "warning", "error"]
ReconcileResolveAction = Literal[
    "mark_db_missing",
    "soft_delete_db_row",
    "restore_soft_deleted",
    "import_object",
    "delete_object",
    "extend_registration_deadline",
    "retry_delete_object",
    "update_hash_after_verify",
]


class ReconcileRunRequest(FrozenModel):
    """``POST /v1/admin/source-files/reconcile`` body.

    ``prefix=None`` scans the configured RustFS source prefix. ``mode='deep'``
    streams every object body for a SHA-256 rehash; ``quick`` skips rehash for
    objects unchanged since their ``last_verified_*`` (force-deeping ones past the
    rolling-deep window).
    """

    prefix: str | None = None
    mode: ReconcileMode = "quick"


class SourceReconcileRun(FrozenModel):
    """One ``ops.source_storage_reconcile_runs`` row (doc lines ~638-659)."""

    source_storage_reconcile_run_id: str
    prefix: str
    mode: ReconcileMode
    state: ReconcileRunState
    started_at: datetime
    finished_at: datetime | None = None
    scanned_objects: int = Field(default=0, ge=0)
    scanned_db_files: int = Field(default=0, ge=0)
    rehashed_objects: int = Field(default=0, ge=0)
    skipped_rehash_objects: int = Field(default=0, ge=0)
    mismatch_count: int = Field(default=0, ge=0)
    resolved_count: int = Field(default=0, ge=0)
    cursor: dict[str, Any] = Field(default_factory=dict)
    log_tail: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class SourceReconcileItem(FrozenModel):
    """One ``ops.source_storage_reconcile_items`` row (doc lines ~662-704)."""

    source_storage_reconcile_item_id: str
    source_storage_reconcile_run_id: str
    issue_type: ReconcileIssueType
    source_file_group_id: str | None = None
    source_file_id: str | None = None
    object_key: str | None = None
    db_sha256: str | None = None
    object_sha256: str | None = None
    db_size_bytes: int | None = None
    object_size_bytes: int | None = None
    db_etag: str | None = None
    object_etag: str | None = None
    severity: ReconcileSeverity
    state: ReconcileItemState = "open"
    resolution_action: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SourceReconcileItemPage(FrozenModel):
    """List response for a run's items."""

    items: tuple[SourceReconcileItem, ...] = ()


class ReconcileResolveRequest(FrozenModel):
    """``POST .../reconcile/items/{id}/resolve`` body (doc lines ~1458-1469).

    ``import_object`` requires ``category`` + ``user_yyyymm``;
    ``extend_registration_deadline`` requires ``registration_deadline_at``;
    ``update_hash_after_verify`` requires a non-empty ``typed_confirmation``.
    """

    action: ReconcileResolveAction
    category: SourceFileCategory | None = None
    user_yyyymm: str | None = Field(default=None, pattern=r"^\d{6}$")
    registration_deadline_at: datetime | None = None
    typed_confirmation: str | None = None


class ReconcileResolveResponse(FrozenModel):
    """Resolve outcome after the read-after-write recheck (doc line ~1479)."""

    source_storage_reconcile_item_id: str
    issue_type: ReconcileIssueType
    action: ReconcileResolveAction
    state: ReconcileItemState
    outcome: str
    source_file_group_id: str | None = None
    affected_match_set_ids: tuple[str, ...] = ()
    message: str | None = None


# --- Capacity preflight (T-204; retention POLICY is T-212) ------------------


class SourceCategoryCapacity(FrozenModel):
    """Per-category object-count / byte usage (doc line ~2107)."""

    category: str
    object_count: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    quarantined_bytes: int = Field(default=0, ge=0)
    soft_deleted_bytes: int = Field(default=0, ge=0)


class SourceRetentionRecommendation(FrozenModel):
    """Retention guidance surfaced with capacity (T-212, ADR-052; not auto-delete).

    Advisory only: the retention policy never auto-deletes registered archives.
    ``reclaimable_bytes`` is the soft_deleted + quarantined + unregistered bytes a
    ``destructive_admin`` could manually clean up, and ``eligible_object_count``
    is how many objects the bulk hard-delete action would currently accept.
    """

    over_threshold: bool = False
    reclaimable_bytes: int = Field(default=0, ge=0)
    eligible_object_count: int = Field(default=0, ge=0)
    guidance: str = ""


class SourceCapacityUsage(FrozenModel):
    """``GET /v1/admin/source-files/capacity`` response (doc lines ~2107-2108).

    Computation + surfacing only: the retention/cleanup POLICY is T-212 (ADR-052),
    which forbids auto-deleting registered archives. ``retention`` carries the
    advisory cleanup recommendation derived from this usage.
    """

    categories: tuple[SourceCategoryCapacity, ...] = ()
    total_object_count: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    quarantined_bytes: int = Field(default=0, ge=0)
    soft_deleted_bytes: int = Field(default=0, ge=0)
    unregistered_bytes: int = Field(default=0, ge=0)
    growth_30d_bytes: int = Field(default=0, ge=0)
    capacity_limit_bytes: int | None = Field(default=None, ge=0)
    over_threshold: bool = False
    retention: SourceRetentionRecommendation | None = None


# --- Bulk hard-delete / restore (T-212, ADR-052) ---------------------------


class SourceBulkHardDeleteRequest(FrozenModel):
    """``POST /v1/admin/source-files/bulk-hard-delete`` body (T-212, ADR-052).

    ``destructive_admin`` only. ``typed_confirmation`` must equal
    ``HARD-DELETE-SOURCES``. Targets are addressed by ``object_keys`` (the bulk
    selection from the reconcile / source-files admin list). NEVER deletes an
    active-정본 object (the T-204 active-match-set guard is reused). A completed
    backup ``db_backup`` manifest/export must exist OR ``manifest_ack=true`` must
    be passed to acknowledge proceeding without one (pre-delete safety gate).
    """

    object_keys: tuple[str, ...] = Field(min_length=1, max_length=1000)
    typed_confirmation: str
    manifest_ack: bool = False
    reason: str | None = Field(default=None, max_length=500)


class SourceHardDeleteOutcome(FrozenModel):
    """Per-object result of the bulk hard-delete (T-212)."""

    object_key: str
    source_file_id: str | None = None
    outcome: Literal[
        "hard_deleted", "delete_failed", "skipped_ineligible", "skipped_not_found"
    ]
    reason: str | None = None


class SourceBulkHardDeleteResponse(FrozenModel):
    """``POST .../bulk-hard-delete`` response (T-212, ADR-052)."""

    requested_count: int = Field(default=0, ge=0)
    hard_deleted_count: int = Field(default=0, ge=0)
    delete_failed_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    results: tuple[SourceHardDeleteOutcome, ...] = ()
    affected_match_set_ids: tuple[str, ...] = ()


class SourceMatchSet(FrozenModel):
    """Top-level combination of source groups used for rebuild or validation."""

    source_match_set_id: str
    name: str
    description: str | None = None
    profile: str
    state: SourceMatchSetState
    source_set_hash: str | None = Field(default=None, min_length=64, max_length=64)
    mixed_yyyymm: bool = False
    yyyymm_by_category: dict[str, Any] = Field(default_factory=dict)
    omitted_optional: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    validated_at: datetime | None = None
    last_load_job_id: str | None = None
    last_consistency_report_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    integrity_alert: bool = False
    integrity_alert_at: datetime | None = None
    integrity_alert_detail: dict[str, Any] = Field(default_factory=dict)


# --- Match set CRUD / validate / activate / retire (T-205a) ----------------
# Shapes for ``POST /v1/admin/source-match-sets`` and the
# ``{id}/validate|activate|retire`` lifecycle endpoints. State-transition rules
# follow ``docs/t109-backup-source-upload-management.md`` "ops.source_match_sets"
# (lines ~804-818) and "ops.source_match_set_items" (lines ~820-857).

#: Build/validation profile the match set targets (doc "load profile", ~150-157).
SourceMatchSetProfile = Literal["serving_minimal", "serving_recommended", "custom"]


class SourceMatchSetItemRequest(FrozenModel):
    """One requested ``ops.source_match_set_items`` row (create body element).

    Invariants (enforced by the DTO + ``core.source_match_set.validate_item_invariants``
    + DB CHECK): ``omitted=false`` ⇒ ``source_file_group_id`` set; ``omitted=true``
    ⇒ ``source_file_group_id`` null; at most one item per ``category``.
    """

    category: SourceFileCategory
    role: SourceMatchSetItemRole
    source_file_group_id: str | None = None
    required: bool = False
    omitted: bool = False
    omitted_reason: str | None = None
    effective_yyyymm: str | None = Field(default=None, pattern=r"^\d{6}$")
    validation_enabled: bool = True
    load_order: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceMatchSetCreateRequest(FrozenModel):
    """``POST /v1/admin/source-match-sets`` body — creates a ``draft`` set.

    ``source_set_hash`` is NULL for a draft (computed at ``validate``). The items'
    referenced groups need not all be ``available`` yet at create time; coverage is
    enforced at ``validate`` (doc lines ~757/764).
    """

    name: str = Field(min_length=1)
    description: str | None = None
    profile: SourceMatchSetProfile = "serving_recommended"
    items: tuple[SourceMatchSetItemRequest, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceMatchSetItem(FrozenModel):
    """One ``ops.source_match_set_items`` row (read model)."""

    source_match_set_item_id: str
    source_match_set_id: str
    category: SourceFileCategory
    role: SourceMatchSetItemRole
    source_file_group_id: str | None = None
    required: bool = False
    omitted: bool = False
    omitted_reason: str | None = None
    effective_yyyymm: str | None = Field(default=None, pattern=r"^\d{6}$")
    validation_enabled: bool = True
    load_order: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceMatchSetDetail(FrozenModel):
    """A match set plus its items (get / create / lifecycle response)."""

    match_set: SourceMatchSet
    items: tuple[SourceMatchSetItem, ...] = ()


class SourceMatchSetPage(FrozenModel):
    """List response (match sets without their items)."""

    match_sets: tuple[SourceMatchSet, ...] = ()


class SourceMatchSetValidateResponse(FrozenModel):
    """``POST .../{id}/validate`` result (the state-split outcome, doc ~806/813-815).

    ``action`` is which branch ran (``validate_draft`` / ``revalidate`` /
    ``validate_in_place`` / ``reject``); ``ok`` is whether coverage/hash passed.
    For ``validate_in_place`` success ``state`` stays ``active`` and
    ``integrity_alert`` is cleared.
    """

    source_match_set_id: str
    action: Literal["validate_draft", "revalidate", "validate_in_place", "reject"]
    ok: bool
    state: SourceMatchSetState
    source_set_hash: str | None = Field(default=None, min_length=64, max_length=64)
    integrity_alert: bool = False
    reasons: tuple[str, ...] = ()


class SourceMatchSetActivateResponse(FrozenModel):
    """``POST .../{id}/activate`` result — the atomic-swap outcome (doc ~807).

    ``retired_match_set_id`` is the previously-active set retired in the same
    transaction (``None`` when none was active). No externally-observable active
    gap: retire-current + activate-target run under one advisory lock in one tx.
    """

    source_match_set_id: str
    state: SourceMatchSetState
    retired_match_set_id: str | None = None
    source_set_hash: str = Field(min_length=64, max_length=64)


class SourceMatchSetRetireResponse(FrozenModel):
    """``POST .../{id}/retire`` result."""

    source_match_set_id: str
    state: SourceMatchSetState
    was_active: bool = False


# --- rebuild-db + rollback (T-205b) ----------------------------------------
# Shapes for ``POST .../{id}/rebuild-db`` and ``POST /ops/releases/{id}/rollback``.
# Follow ``docs/t109-backup-source-upload-management.md`` "DB 재구성"
# (lines ~1532-1562) and the rollback rows (~818/1530/1631), ADR-049 #13/#18.


class SourceRebuildDbRequest(FrozenModel):
    """``POST /v1/admin/source-match-sets/{id}/rebuild-db`` body (doc ~1532).

    A rebuild assembles a ``full_load_batch`` payload from the match set's groups
    and bridges it to the existing loader DAG. ``force_promotion`` is the
    exception path for a known source-quality consistency ERROR: it requires the
    ``destructive_admin`` role AND a ``typed_confirmation`` of
    ``REBUILD-PROMOTE {source_match_set_id}``. It bypasses ONLY the consistency
    ERROR promotion block — never the source-archive integrity gate, an
    unavailable group, or a match set ``integrity_alert`` (doc ~1559, ADR-049 #13).
    """

    force_promotion: bool = False
    typed_confirmation: str | None = None
    reason: str | None = None
    download_concurrency: int = Field(default=3, ge=1, le=8)
    materialize_concurrency: int = Field(default=2, ge=1, le=8)


class SourceRebuildDbResponse(FrozenModel):
    """``rebuild-db`` enqueue result.

    The rebuild runs asynchronously in a ``full_load_batch`` job under the
    ``source_rebuild_db`` advisory lock; ``job_id``/``load_batch_id`` track it.
    The integrity gate runs before any child loader is enqueued; on a gate
    failure ``enqueued=false`` and ``failed_group_ids`` name the quarantined
    groups. ``forced_promotion`` echoes whether the ERROR-bypass path was armed.
    """

    source_match_set_id: str
    enqueued: bool
    job_id: str | None = None
    load_batch_id: str | None = None
    forced_promotion: bool = False
    integrity_gate_ok: bool = True
    failed_group_ids: tuple[str, ...] = ()
    stale_jobs_closed: tuple[str, ...] = ()
    affected_match_set_ids: tuple[str, ...] = ()
    message: str | None = None


class ServingReleaseRollbackRequest(FrozenModel):
    """``POST /v1/admin/ops/releases/{serving_release_id}/rollback`` body (doc ~818/1530).

    ``typed_confirmation`` must equal the rollback-plan token
    (``ROLLBACK {serving_release_id}``). When the target snapshot carries a
    ``source_match_set_id`` the match set is swapped atomically (current active →
    ``retired``, target → ``active``) under the match-activate lock, with the
    target's ``integrity_alert`` recomputed from a pre-rollback source quick
    reconcile. Legacy snapshots (no FK) stay ``알수없음/추정`` (ADR-049 #18).
    """

    typed_confirmation: str
    reason: str | None = None


class ServingReleaseRollbackResponse(FrozenModel):
    """``rollback`` result — the serving + match-set swap outcome."""

    serving_release_id: str
    mode: Literal["match_set_swap", "legacy_estimate"]
    activated_match_set_id: str | None = None
    retired_match_set_id: str | None = None
    target_integrity_alert: bool = False
    message: str | None = None


# --- restored_from_backup + relink (T-208) ---------------------------------
# Shapes for ``POST .../restored-from-backup`` (reconstruct a read-only match set
# from a backup manifest's source_match_set block) and ``POST
# .../source-file-groups/{id}/relink`` (reattach a stub group's RustFS objects).
# Follow ``docs/t109-backup-source-upload-management.md`` "백업/복원 manifest 확장"
# (lines ~1848-1914), ADR-049 backup/restore rows.


class RestoredFromBackupCreateRequest(FrozenModel):
    """``POST /v1/admin/source-match-sets/restored-from-backup`` body (doc step 1-2).

    Reconstruct a read-only ``restored_from_backup`` match set from a backup
    ``db_backup`` artifact's manifest ``source_match_set`` block. The created match
    set's groups/files are ``missing``/``unknown`` stubs (objects not verified);
    the manifest ``group_sha256`` is preserved as UNTRUSTED metadata. Rebuild stays
    disabled until every referenced group is relinked to ``available``.
    """

    artifact_id: str


class RestoredFromBackupCreateResponse(FrozenModel):
    """``restored-from-backup`` result — the reconstructed stub match set."""

    source_match_set_id: str
    state: SourceMatchSetState
    profile: str
    source_set_hash: str | None = Field(default=None, min_length=64, max_length=64)
    created_group_ids: tuple[str, ...] = ()
    created_file_count: int = Field(default=0, ge=0)
    omitted_categories: tuple[str, ...] = ()
    rebuild_enabled: bool = False
    message: str | None = None


class SourceGroupRelinkFile(FrozenModel):
    """Per-child relink outcome (object present + manifest-hash consistent?)."""

    source_file_id: str
    part_key: str
    state: SourceFileState
    reasons: tuple[str, ...] = ()


class SourceGroupRelinkResponse(FrozenModel):
    """``POST .../source-file-groups/{id}/relink`` result (doc steps 7-9).

    Reattaches a ``restored_from_backup`` stub group's RustFS objects: each child
    ``missing → validating`` (present + manifest-hash/size consistent → streaming
    rehash recorded), ``missing`` (absent), or ``quarantined`` (mismatch); the
    group then recomputes ``group_sha256`` and, when all referenced groups are
    ``available``, the match set precomputes its canonical ``source_set_hash`` and
    transitions ``restored_from_backup → revalidatable`` (M-A option 2).
    """

    source_file_group_id: str
    category: SourceFileCategory
    state: SourceGroupState
    validation_state: SourceValidationState
    group_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    files: tuple[SourceGroupRelinkFile, ...] = ()
    affected_match_set_ids: tuple[str, ...] = ()


class RestoreSourceVerificationResult(FrozenModel):
    """Result of the post-restore source quick reconcile (doc ~1896-1902).

    Surfaced after a ``pg_restore`` manifest restore or an ADR-036 rename
    hot-swap. ``run_quick_reconcile`` is False (and ``legacy_estimate_only`` True)
    when the active snapshot has no ``source_match_set_id`` FK. When the reconcile
    finds missing source objects, serving stays up but ``reconstruct_unavailable``
    is True and a "재구성 불가" warning is surfaced.
    """

    entrypoint: Literal["pg_restore", "rename_hot_swap"]
    run_quick_reconcile: bool
    legacy_estimate_only: bool = False
    active_source_match_set_id: str | None = None
    reconcile_run_id: str | None = None
    mismatch_count: int = Field(default=0, ge=0)
    reconstruct_unavailable: bool = False
    message: str | None = None
