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
