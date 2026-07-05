"""Unified stored-file inventory DTOs (T-283 파일 관리).

`/v1/admin/storage/files` 응답 모델. 원천 파일 그룹·백업/산출물(artifact)·
RustFS 고아 객체를 하나의 목록으로 통합하고, 각 항목이 어디에 연결됐는지
(업로드 세션·매칭 세트·작업)와 사용/임시 여부, 취득·등록·검증·마지막 적재
시각을 제공한다.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .common import FrozenModel

FileInventoryKind = Literal["source_group", "artifact", "orphan_object"]


class FileInventoryItem(FrozenModel):
    """통합 파일 인벤토리의 한 행."""

    file_kind: FileInventoryKind
    #: source_file_group_id / artifact_id / reconcile item id.
    id: str
    name: str
    #: 원천 카테고리 또는 artifact_type.
    category: str
    #: 원본 상태 값 (그룹 state / artifact state / reconcile issue_type).
    state: str
    #: core.file_inventory 도출 lifecycle 버킷.
    lifecycle: str
    #: 활성 매칭 세트 포함 여부 (서빙 구성에 사용 중).
    in_use: bool
    #: 임시/정리 대상 성격 (진행 중 업로드, 등록 만료, 고아 객체 등).
    temporary: bool
    size_bytes: int | None = None
    file_count: int | None = None
    sha256: str | None = None
    storage_kind: str | None = None
    #: object_key(RustFS) 또는 storage_uri.
    storage_ref: str | None = None
    user_yyyymm: str | None = Field(default=None, pattern=r"^\d{6}$")
    #: 파일을 받은 시각 (업로드/서버 다운로드/artifact 생성).
    acquired_at: datetime | None = None
    registered_at: datetime | None = None
    last_verified_at: datetime | None = None
    #: 이 파일이 포함된 매칭 세트의 마지막 완료 적재 시각.
    last_loaded_at: datetime | None = None
    last_load_job_id: str | None = None
    expires_at: datetime | None = None
    # --- 연결 정보 -----------------------------------------------------------
    upload_session_id: str | None = None
    upload_session_state: str | None = None
    active_match_set_id: str | None = None
    match_set_count: int = 0
    open_issue_count: int = 0
    job_id: str | None = None
    dataset_snapshot_id: str | None = None
    serving_release_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class FileInventorySummary(FrozenModel):
    total_count: int
    total_bytes: int
    in_use_count: int
    temporary_count: int
    open_issue_count: int
    by_lifecycle: dict[str, int] = Field(default_factory=dict)
    by_kind: dict[str, int] = Field(default_factory=dict)


class FileInventoryPage(FrozenModel):
    """``GET /v1/admin/storage/files`` 응답."""

    items: tuple[FileInventoryItem, ...] = ()
    summary: FileInventorySummary


class FileInventoryFileInfo(FrozenModel):
    """그룹 상세의 개별 파일 (``ops.source_files``)."""

    source_file_id: str
    original_filename: str
    part_key: str
    state: str
    validation_state: str
    size_bytes: int
    sha256: str
    storage_kind: str
    bucket: str | None = None
    object_key: str | None = None
    uploaded_at: datetime
    validated_at: datetime | None = None
    last_verified_at: datetime | None = None
    last_deep_verified_at: datetime | None = None
    deleted_at: datetime | None = None


class FileInventorySessionInfo(FrozenModel):
    """그룹 상세의 업로드 세션 이력."""

    source_upload_session_id: str
    state: str
    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    registered_at: datetime | None = None
    expires_at: datetime | None = None
    registration_deadline_at: datetime | None = None


class FileInventoryUsage(FrozenModel):
    """그룹 상세의 매칭 세트 사용처 한 건."""

    source_match_set_id: str
    name: str
    state: str
    role: str | None = None
    last_load_job_id: str | None = None
    last_load_job_state: str | None = None
    last_loaded_at: datetime | None = None


class FileInventoryIssue(FrozenModel):
    """그룹 상세의 미해결 저장소 정합성 이슈."""

    source_storage_reconcile_item_id: str
    issue_type: str
    severity: str
    state: str
    object_key: str | None = None
    detected_at: datetime | None = None


class FileInventorySourceDetail(FrozenModel):
    """``GET /v1/admin/storage/files/source-groups/{id}`` 응답 — 연결 추적 상세."""

    item: FileInventoryItem
    files: tuple[FileInventoryFileInfo, ...] = ()
    sessions: tuple[FileInventorySessionInfo, ...] = ()
    usages: tuple[FileInventoryUsage, ...] = ()
    open_issues: tuple[FileInventoryIssue, ...] = ()
