"""Unified stored-file inventory repository (T-283 파일 관리).

Raw-SQL read-only queries over ``ops.source_file_groups`` + 연결 테이블
(업로드 세션·매칭 세트·load_jobs·reconcile)로 파일별 연결·사용·임시·시각
추적 정보를 도출한다. lifecycle 판정은 ``core.file_inventory``의 순수 함수를
사용한다. 이 저장소는 조회 전용이며 어떤 상태도 변경하지 않는다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.file_inventory import (
    SourceGroupFacts,
    derive_artifact_lifecycle,
    derive_source_group_lifecycle,
    orphan_lifecycle,
)
from kortravelgeo.dto.admin import OpsArtifact
from kortravelgeo.dto.file_inventory import (
    FileInventoryFileInfo,
    FileInventoryIssue,
    FileInventoryItem,
    FileInventorySessionInfo,
    FileInventorySourceDetail,
    FileInventoryUsage,
)

# 그룹 목록: 파일 집계 + 최신 세션 + 매칭 세트 사용/마지막 적재 + 미해결 이슈 수.
# LATERAL 서브쿼리는 그룹 수(수십~수백) 규모에서 충분히 저렴하다.
_GROUP_INVENTORY_SELECT = """
SELECT
  g.source_file_group_id::text AS group_id,
  g.category,
  g.display_name,
  g.state AS group_state,
  g.validation_state,
  g.user_yyyymm,
  g.group_sha256,
  g.uploaded_at,
  g.validated_at,
  g.deleted_at,
  agg.file_count,
  agg.total_bytes,
  agg.last_verified_at,
  agg.storage_kind,
  agg.object_key,
  s.source_upload_session_id AS session_id,
  s.state AS session_state,
  s.registered_at,
  s.expires_at,
  ms.match_set_count,
  ms.candidate_match_set_count,
  ms.active_match_set_id,
  ms.last_loaded_at,
  ms.last_load_job_id,
  COALESCE(iss.open_issue_count, 0) AS open_issue_count
FROM ops.source_file_groups g
LEFT JOIN LATERAL (
  SELECT
    COUNT(*) AS file_count,
    COALESCE(SUM(f.size_bytes), 0)::bigint AS total_bytes,
    MAX(f.last_verified_at) AS last_verified_at,
    MAX(f.storage_kind) AS storage_kind,
    MIN(f.object_key) AS object_key
  FROM ops.source_files f
  WHERE f.source_file_group_id = g.source_file_group_id
    AND f.state <> 'hard_deleted'
) agg ON true
LEFT JOIN LATERAL (
  SELECT
    s.source_upload_session_id,
    s.state,
    s.registered_at,
    s.expires_at
  FROM ops.source_upload_sessions s
  WHERE s.source_file_group_id = g.source_file_group_id
  ORDER BY s.created_at DESC
  LIMIT 1
) s ON true
LEFT JOIN LATERAL (
  SELECT
    COUNT(*)::int AS match_set_count,
    COUNT(*) FILTER (
      WHERE m.state IN ('draft', 'validated', 'active', 'revalidatable', 'restored_from_backup')
    )::int AS candidate_match_set_count,
    MAX(CASE WHEN m.state = 'active' THEN m.source_match_set_id::text END)
      AS active_match_set_id,
    MAX(j.finished_at) AS last_loaded_at,
    (ARRAY_AGG(j.job_id ORDER BY j.finished_at DESC NULLS LAST)
       FILTER (WHERE j.job_id IS NOT NULL))[1] AS last_load_job_id
  FROM ops.source_match_set_items i
  JOIN ops.source_match_sets m
    ON m.source_match_set_id = i.source_match_set_id
  LEFT JOIN load_jobs j
    ON j.job_id = m.last_load_job_id AND j.state = 'done'
  WHERE i.source_file_group_id = g.source_file_group_id
) ms ON true
LEFT JOIN LATERAL (
  SELECT COUNT(*)::int AS open_issue_count
  FROM ops.source_storage_reconcile_items ri
  WHERE ri.source_file_group_id = g.source_file_group_id
    AND ri.state = 'open'
) iss ON true
"""

_ORPHAN_SELECT = """
SELECT
  ri.source_storage_reconcile_item_id::text AS item_id,
  ri.issue_type,
  ri.severity,
  ri.object_key,
  ri.object_size_bytes,
  ri.object_sha256,
  r.finished_at AS detected_at
FROM ops.source_storage_reconcile_items ri
JOIN ops.source_storage_reconcile_runs r
  ON r.source_storage_reconcile_run_id = ri.source_storage_reconcile_run_id
WHERE ri.state = 'open'
  AND ri.source_file_group_id IS NULL
  AND ri.object_key IS NOT NULL
ORDER BY r.finished_at DESC NULLS LAST, ri.object_key
LIMIT :limit
"""

_GROUP_FILES_SELECT = """
SELECT
  f.source_file_id::text AS source_file_id,
  f.original_filename,
  f.part_key,
  f.state,
  f.validation_state,
  f.size_bytes,
  f.sha256,
  f.storage_kind,
  f.bucket,
  f.object_key,
  f.uploaded_at,
  f.validated_at,
  f.last_verified_at,
  f.last_deep_verified_at,
  f.deleted_at
FROM ops.source_files f
WHERE f.source_file_group_id = :group_id
ORDER BY f.part_key, f.original_filename
"""

_GROUP_SESSIONS_SELECT = """
SELECT
  s.source_upload_session_id,
  s.state,
  s.created_at,
  s.updated_at,
  s.completed_at,
  s.registered_at,
  s.expires_at,
  s.registration_deadline_at
FROM ops.source_upload_sessions s
WHERE s.source_file_group_id = :group_id
ORDER BY s.created_at DESC
"""

_GROUP_USAGES_SELECT = """
SELECT
  m.source_match_set_id::text AS source_match_set_id,
  m.name,
  m.state,
  i.role,
  m.last_load_job_id,
  j.state AS last_load_job_state,
  j.finished_at AS last_loaded_at
FROM ops.source_match_set_items i
JOIN ops.source_match_sets m
  ON m.source_match_set_id = i.source_match_set_id
LEFT JOIN load_jobs j ON j.job_id = m.last_load_job_id
WHERE i.source_file_group_id = :group_id
ORDER BY (m.state = 'active') DESC, m.updated_at DESC
"""

_GROUP_ISSUES_SELECT = """
SELECT
  ri.source_storage_reconcile_item_id::text AS source_storage_reconcile_item_id,
  ri.issue_type,
  ri.severity,
  ri.state,
  ri.object_key,
  r.finished_at AS detected_at
FROM ops.source_storage_reconcile_items ri
JOIN ops.source_storage_reconcile_runs r
  ON r.source_storage_reconcile_run_id = ri.source_storage_reconcile_run_id
WHERE ri.source_file_group_id = :group_id
  AND ri.state = 'open'
ORDER BY r.finished_at DESC NULLS LAST
"""


def _group_item(row: dict[str, Any]) -> FileInventoryItem:
    facts = SourceGroupFacts(
        group_state=row["group_state"],
        session_state=row["session_state"],
        registered_at_present=row["registered_at"] is not None,
        active_match_set_id=row["active_match_set_id"],
        match_set_count=row["match_set_count"] or 0,
        candidate_match_set_count=row["candidate_match_set_count"] or 0,
    )
    verdict = derive_source_group_lifecycle(facts)
    return FileInventoryItem(
        file_kind="source_group",
        id=row["group_id"],
        name=row["display_name"],
        category=row["category"],
        state=row["group_state"],
        lifecycle=verdict.lifecycle,
        in_use=verdict.in_use,
        temporary=verdict.temporary,
        size_bytes=row["total_bytes"],
        file_count=row["file_count"],
        sha256=row["group_sha256"],
        storage_kind=row["storage_kind"],
        storage_ref=row["object_key"],
        user_yyyymm=row["user_yyyymm"],
        acquired_at=row["uploaded_at"],
        registered_at=row["registered_at"],
        last_verified_at=row["last_verified_at"],
        last_loaded_at=row["last_loaded_at"],
        last_load_job_id=row["last_load_job_id"],
        expires_at=row["expires_at"],
        upload_session_id=row["session_id"],
        upload_session_state=row["session_state"],
        active_match_set_id=row["active_match_set_id"],
        match_set_count=row["match_set_count"] or 0,
        open_issue_count=row["open_issue_count"] or 0,
        detail={"validation_state": row["validation_state"]},
    )


def _orphan_item(row: dict[str, Any]) -> FileInventoryItem:
    verdict = orphan_lifecycle()
    return FileInventoryItem(
        file_kind="orphan_object",
        id=row["item_id"],
        name=row["object_key"],
        category="rustfs_object",
        state=row["issue_type"],
        lifecycle=verdict.lifecycle,
        in_use=verdict.in_use,
        temporary=verdict.temporary,
        size_bytes=row["object_size_bytes"],
        sha256=row["object_sha256"],
        storage_kind="rustfs",
        storage_ref=row["object_key"],
        acquired_at=row["detected_at"],
        detail={"severity": row["severity"]},
    )


def artifact_inventory_item(artifact: OpsArtifact) -> FileInventoryItem:
    """``ops.artifacts`` 행(백업 등 산출물)을 통합 인벤토리 항목으로 변환한다."""

    verdict = derive_artifact_lifecycle(artifact.state)
    return FileInventoryItem(
        file_kind="artifact",
        id=artifact.artifact_id,
        name=artifact.display_name or artifact.artifact_id,
        category=artifact.artifact_type,
        state=artifact.state,
        lifecycle=verdict.lifecycle,
        in_use=verdict.in_use,
        temporary=verdict.temporary,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        storage_kind=artifact.storage_kind,
        storage_ref=artifact.storage_uri,
        acquired_at=artifact.created_at,
        last_verified_at=artifact.finished_at,
        expires_at=artifact.expires_at,
        job_id=artifact.job_id,
        dataset_snapshot_id=artifact.dataset_snapshot_id,
        serving_release_id=artifact.serving_release_id,
        detail={
            "retention_class": artifact.retention_class,
            "media_type": artifact.media_type,
        },
    )


class FileInventoryRepository:
    """Read-only inventory queries (viewer 권한 표면)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_source_groups(
        self,
        *,
        category: str | None = None,
        include_hard_deleted: bool = False,
        limit: int = 200,
    ) -> tuple[FileInventoryItem, ...]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if category:
            clauses.append("g.category = :category")
            params["category"] = category
        if not include_hard_deleted:
            clauses.append("g.state <> 'hard_deleted'")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"{_GROUP_INVENTORY_SELECT}{where} ORDER BY g.uploaded_at DESC LIMIT :limit"
        async with self._engine.connect() as conn:
            rows = (await conn.execute(text(sql), params)).mappings().all()
        return tuple(_group_item(dict(row)) for row in rows)

    async def list_orphan_objects(self, *, limit: int = 200) -> tuple[FileInventoryItem, ...]:
        async with self._engine.connect() as conn:
            rows = (
                (await conn.execute(text(_ORPHAN_SELECT), {"limit": limit})).mappings().all()
            )
        return tuple(_orphan_item(dict(row)) for row in rows)

    async def get_source_group_detail(
        self, source_file_group_id: str
    ) -> FileInventorySourceDetail | None:
        params = {"group_id": source_file_group_id}
        sql = f"{_GROUP_INVENTORY_SELECT} WHERE g.source_file_group_id = :group_id"
        async with self._engine.connect() as conn:
            row = (await conn.execute(text(sql), params)).mappings().first()
            if row is None:
                return None
            files = (await conn.execute(text(_GROUP_FILES_SELECT), params)).mappings().all()
            sessions = (
                (await conn.execute(text(_GROUP_SESSIONS_SELECT), params)).mappings().all()
            )
            usages = (await conn.execute(text(_GROUP_USAGES_SELECT), params)).mappings().all()
            issues = (await conn.execute(text(_GROUP_ISSUES_SELECT), params)).mappings().all()
        return FileInventorySourceDetail(
            item=_group_item(dict(row)),
            files=tuple(FileInventoryFileInfo(**dict(entry)) for entry in files),
            sessions=tuple(FileInventorySessionInfo(**dict(entry)) for entry in sessions),
            usages=tuple(FileInventoryUsage(**dict(entry)) for entry in usages),
            open_issues=tuple(FileInventoryIssue(**dict(entry)) for entry in issues),
        )
