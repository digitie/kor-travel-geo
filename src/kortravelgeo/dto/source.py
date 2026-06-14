"""Source file registry and match set read-model DTOs (T-200).

These mirror the ``ops.source_file_groups`` / ``ops.source_files`` /
``ops.source_match_sets`` tables defined in
``docs/t109-backup-source-upload-management.md`` and ``infra/sql.py``.
They are read-only API DTOs with no behavior.
"""

from datetime import datetime
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
]

#: Terminal states: a session here cannot be resumed and no longer blocks a new
#: session for the same ``(category, user_yyyymm)``.
TERMINAL_UPLOAD_SESSION_STATES: frozenset[str] = frozenset(
    {
        "available",
        "cancelled",
        "expired",
        "failed_upload",
        "failed_extract",
        "failed_hash",
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
