"""Raw SQL repository for source upload sessions (T-203a).

Backs the ``/v1/admin/source-files/upload-sessions`` lifecycle defined in
``docs/t109-backup-source-upload-management.md`` ("업로드 상태 머신" and the
upload-session "API 설계" sections). Style mirrors ``infra/admin_repo.py``:
``AsyncEngine``-driven raw SQL, ``_json_text`` for JSONB binds, small row→DTO
mappers at module scope.

This slice covers the session + parts lifecycle and storage-client wiring only.
``register`` (group/file registry creation), ``recompute_group_aggregates``, the
archive structure validator, the janitor, and soft-delete/restore are explicitly
deferred to T-203b / T-203c.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.source_categories import (
    SIDO_PARTS,
    category_by_code,
    expected_file_count,
)
from kortravelgeo.dto.source import (
    TERMINAL_UPLOAD_SESSION_STATES,
    UploadSessionCreateRequest,
    UploadSessionFileSlot,
    UploadSessionPartStatus,
    UploadSessionStatus,
)
from kortravelgeo.exceptions import InvalidInputError, NotFoundError

_SESSION_SELECT = """
SELECT source_upload_session_id, source_file_group_id, category, group_kind,
       user_yyyymm, display_name, state, expected_file_count, uploaded_file_count,
       upload_strategy, storage_kind, bucket, prefix, created_by, created_at,
       updated_at, expires_at, registration_deadline_at, completed_at,
       registered_at, error_message, metadata
  FROM ops.source_upload_sessions
"""

_PART_SELECT = """
SELECT source_upload_session_id, part_key, multipart_upload_id, part_number,
       part_etag, part_sha256, received_bytes, completed_at, metadata
  FROM ops.source_upload_session_parts
"""

# PostgreSQL advisory-lock namespace for "one non-terminal session per
# (category, user_yyyymm)" (doc lock key namespace, line ~1414). Held inside the
# create transaction so two concurrent creates serialize.
_SESSION_LOCK_NAMESPACE = 0x4B47_0203


# --- Pure helpers (DB-free, unit-tested directly) --------------------------


def slot_definitions(category_code: str) -> tuple[UploadSessionFileSlot, ...]:
    """File slots a session must collect for ``category_code``.

    ``single_file`` → one ``archive`` slot; ``multi_part`` → 17 sido slots.
    """
    category = category_by_code.get(category_code)
    if category is None:
        msg = f"unknown source category: {category_code}"
        raise InvalidInputError(msg)
    if category.group_kind == "single_file":
        return (UploadSessionFileSlot(slot="archive", part_kind="single", part_key="archive"),)
    return tuple(
        UploadSessionFileSlot(
            slot=code,
            part_kind="sido",
            part_key=code,
            part_label=label,
        )
        for code, label in SIDO_PARTS
    )


def is_terminal_state(state: str) -> bool:
    return state in TERMINAL_UPLOAD_SESSION_STATES


def should_fail_storage_state(
    *,
    recorded_part_numbers: frozenset[int],
    listed_part_numbers: frozenset[int] | None,
) -> bool:
    """Decide whether a resumed slot must transition to ``failed_storage_state``.

    ``listed_part_numbers is None`` means the RustFS multipart upload id no
    longer exists (``ListParts`` 404). Otherwise the storage state is stale when
    a part the DB recorded as received is missing from the live upload. Extra
    parts on the storage side (not yet recorded) are fine — they get recorded.
    """
    if listed_part_numbers is None:
        return True
    return not recorded_part_numbers.issubset(listed_part_numbers)


# --- Repository ------------------------------------------------------------


@dataclass(frozen=True)
class SessionCreateResult:
    """``create_session`` outcome: a fresh session, or a 409 conflict."""

    session: UploadSessionStatus
    parts: tuple[UploadSessionPartStatus, ...]
    conflict: bool


class SourceUploadSessionRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def create_session(
        self,
        req: UploadSessionCreateRequest,
        *,
        bucket: str | None,
        prefix: str | None,
        created_by: str | None = None,
    ) -> SessionCreateResult:
        """Create a session, or return the existing non-terminal one (409).

        Serialized per ``(category, user_yyyymm)`` with a PostgreSQL advisory
        lock so two concurrent creators cannot both insert (doc line 1261).
        """
        category = category_by_code.get(req.category)
        if category is None:
            msg = f"unknown source category: {req.category}"
            raise InvalidInputError(msg)
        group_kind = category.group_kind
        expected = expected_file_count(category)
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),
                {
                    "ns": _SESSION_LOCK_NAMESPACE,
                    "key": f"{req.category}:{req.user_yyyymm}",
                },
            )
            existing = await self._active_session_for_conn(
                conn, category=req.category, user_yyyymm=req.user_yyyymm
            )
            if existing is not None:
                parts = await self._parts_for_conn(conn, existing.upload_session_id)
                return SessionCreateResult(session=existing, parts=parts, conflict=True)

            session_id = f"source_upload_{uuid4().hex}"
            group_id = str(uuid4())
            row = (
                await conn.execute(
                    _json_text(
                        """
INSERT INTO ops.source_upload_sessions
  (source_upload_session_id, source_file_group_id, category, group_kind,
   user_yyyymm, display_name, state, expected_file_count, uploaded_file_count,
   upload_strategy, storage_kind, bucket, prefix, created_by, metadata)
VALUES
  (:source_upload_session_id, :source_file_group_id, :category, :group_kind,
   :user_yyyymm, :display_name, 'created', :expected_file_count, 0,
   :upload_strategy, :storage_kind, :bucket, :prefix, :created_by, :metadata)
RETURNING source_upload_session_id, source_file_group_id, category, group_kind,
          user_yyyymm, display_name, state, expected_file_count,
          uploaded_file_count, upload_strategy, storage_kind, bucket, prefix,
          created_by, created_at, updated_at, expires_at,
          registration_deadline_at, completed_at, registered_at, error_message,
          metadata
""",
                        "metadata",
                    ),
                    {
                        "source_upload_session_id": session_id,
                        "source_file_group_id": group_id,
                        "category": req.category,
                        "group_kind": group_kind,
                        "user_yyyymm": req.user_yyyymm,
                        "display_name": req.display_name,
                        "expected_file_count": expected,
                        "upload_strategy": req.upload_strategy,
                        "storage_kind": req.storage_kind,
                        "bucket": bucket,
                        "prefix": prefix,
                        "created_by": created_by,
                        "metadata": {},
                    },
                )
            ).mappings().one()
        session = _session_status(dict(row), slots=slot_definitions(req.category))
        return SessionCreateResult(session=session, parts=(), conflict=False)

    async def get_session(self, session_id: str) -> UploadSessionStatus | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(_SESSION_SELECT + " WHERE source_upload_session_id = :sid"),
                    {"sid": session_id},
                )
            ).mappings().first()
            if row is None:
                return None
            parts = await self._parts_for_conn(conn, session_id)
        return _session_status(dict(row), slots=_slots_with_parts(dict(row), parts))

    async def list_sessions(
        self,
        *,
        state: str | None = None,
        category: str | None = None,
        user_yyyymm: str | None = None,
        created_by: str | None = None,
        limit: int = 50,
    ) -> list[UploadSessionStatus]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        for column, value in (
            ("state", state),
            ("category", category),
            ("user_yyyymm", user_yyyymm),
            ("created_by", created_by),
        ):
            if value is not None:
                clauses.append(f"{column} = :{column}")
                params[column] = value
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(_SESSION_SELECT + where + " ORDER BY created_at DESC LIMIT :limit"),
                    params,
                )
            ).mappings().all()
            sessions: list[UploadSessionStatus] = []
            for row in rows:
                parts = await self._parts_for_conn(
                    conn, str(row["source_upload_session_id"])
                )
                sessions.append(
                    _session_status(dict(row), slots=_slots_with_parts(dict(row), parts))
                )
        return sessions

    async def update_state(
        self,
        session_id: str,
        *,
        state: str,
        error_message: str | None = None,
    ) -> UploadSessionStatus | None:
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        """
UPDATE ops.source_upload_sessions
   SET state = :state,
       error_message = COALESCE(:error_message, error_message),
       completed_at = CASE WHEN :state = 'available' THEN now() ELSE completed_at END,
       updated_at = now()
 WHERE source_upload_session_id = :sid
RETURNING source_upload_session_id, source_file_group_id, category, group_kind,
          user_yyyymm, display_name, state, expected_file_count,
          uploaded_file_count, upload_strategy, storage_kind, bucket, prefix,
          created_by, created_at, updated_at, expires_at,
          registration_deadline_at, completed_at, registered_at, error_message,
          metadata
""",
                    ),
                    {"sid": session_id, "state": state, "error_message": error_message},
                )
            ).mappings().first()
            if row is None:
                return None
            parts = await self._parts_for_conn(conn, session_id)
        return _session_status(dict(row), slots=_slots_with_parts(dict(row), parts))

    async def record_part(
        self,
        session_id: str,
        *,
        part_key: str,
        part_number: int,
        multipart_upload_id: str | None = None,
        part_etag: str | None = None,
        part_sha256: str | None = None,
        received_bytes: int = 0,
        completed: bool = False,
    ) -> UploadSessionPartStatus:
        """Upsert one part row (etag / sha256 / received_bytes for resume)."""
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        """
INSERT INTO ops.source_upload_session_parts
  (source_upload_session_id, part_key, multipart_upload_id, part_number,
   part_etag, part_sha256, received_bytes, completed_at)
VALUES
  (:sid, :part_key, :multipart_upload_id, :part_number,
   :part_etag, :part_sha256, :received_bytes,
   CASE WHEN :completed THEN now() ELSE NULL END)
ON CONFLICT (source_upload_session_id, part_key, part_number) DO UPDATE
   SET multipart_upload_id = COALESCE(
         EXCLUDED.multipart_upload_id,
         ops.source_upload_session_parts.multipart_upload_id),
       part_etag = COALESCE(EXCLUDED.part_etag, ops.source_upload_session_parts.part_etag),
       part_sha256 = COALESCE(EXCLUDED.part_sha256, ops.source_upload_session_parts.part_sha256),
       received_bytes = EXCLUDED.received_bytes,
       completed_at = COALESCE(EXCLUDED.completed_at, ops.source_upload_session_parts.completed_at)
RETURNING source_upload_session_id, part_key, multipart_upload_id, part_number,
          part_etag, part_sha256, received_bytes, completed_at, metadata
""",
                    ),
                    {
                        "sid": session_id,
                        "part_key": part_key,
                        "multipart_upload_id": multipart_upload_id,
                        "part_number": part_number,
                        "part_etag": part_etag,
                        "part_sha256": part_sha256,
                        "received_bytes": received_bytes,
                        "completed": completed,
                    },
                )
            ).mappings().one()
        return _part_status(dict(row))

    async def replace_slot(
        self,
        session_id: str,
        *,
        part_key: str,
    ) -> int:
        """Invalidate a completed slot: drop its parts so it can be re-uploaded.

        Clears the slot's recorded parts (etag/hash/validation) and reopens the
        session to ``uploading`` so the operator re-uploads the file (doc 1314).
        Returns the number of part rows removed.
        """
        async with self.engine.begin() as conn:
            session_row = (
                await conn.execute(
                    text(_SESSION_SELECT + " WHERE source_upload_session_id = :sid FOR UPDATE"),
                    {"sid": session_id},
                )
            ).mappings().first()
            if session_row is None:
                raise NotFoundError(f"upload session not found: {session_id}")
            if session_row["registered_at"] is not None:
                msg = "register 후에는 group 전체 재등록을 사용한다 (slot replace 불가)"
                raise InvalidInputError(msg)
            deleted = (
                await conn.execute(
                    text(
                        """
DELETE FROM ops.source_upload_session_parts
 WHERE source_upload_session_id = :sid AND part_key = :part_key
RETURNING part_number
"""
                    ),
                    {"sid": session_id, "part_key": part_key},
                )
            ).all()
            remaining = await conn.scalar(
                text(
                    """
SELECT count(DISTINCT part_key)::int
  FROM ops.source_upload_session_parts
 WHERE source_upload_session_id = :sid AND completed_at IS NOT NULL
"""
                ),
                {"sid": session_id},
            )
            next_state = "uploading" if int(remaining or 0) > 0 else "created"
            await conn.execute(
                text(
                    """
UPDATE ops.source_upload_sessions
   SET state = :state,
       uploaded_file_count = :uploaded,
       updated_at = now()
 WHERE source_upload_session_id = :sid
"""
                ),
                {"sid": session_id, "state": next_state, "uploaded": int(remaining or 0)},
            )
        return len(deleted)

    async def slot_parts(
        self,
        session_id: str,
        *,
        part_key: str,
    ) -> tuple[UploadSessionPartStatus, ...]:
        """Recorded parts for one slot (resume / completion bookkeeping)."""
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        _PART_SELECT
                        + " WHERE source_upload_session_id = :sid AND part_key = :part_key"
                        + " ORDER BY part_number"
                    ),
                    {"sid": session_id, "part_key": part_key},
                )
            ).mappings().all()
        return tuple(_part_status(dict(row)) for row in rows)

    # --- connection-scoped helpers ----------------------------------------

    async def _active_session_for_conn(
        self,
        conn: AsyncConnection,
        *,
        category: str,
        user_yyyymm: str,
    ) -> UploadSessionStatus | None:
        rows = (
            await conn.execute(
                text(
                    _SESSION_SELECT
                    + " WHERE category = :category AND user_yyyymm = :user_yyyymm"
                    + " ORDER BY created_at DESC"
                ),
                {"category": category, "user_yyyymm": user_yyyymm},
            )
        ).mappings().all()
        for row in rows:
            if not is_terminal_state(str(row["state"])):
                parts = await self._parts_for_conn(conn, str(row["source_upload_session_id"]))
                return _session_status(dict(row), slots=_slots_with_parts(dict(row), parts))
        return None

    async def _parts_for_conn(
        self,
        conn: AsyncConnection,
        session_id: str,
    ) -> tuple[UploadSessionPartStatus, ...]:
        rows = (
            await conn.execute(
                text(
                    _PART_SELECT
                    + " WHERE source_upload_session_id = :sid"
                    + " ORDER BY part_key, part_number"
                ),
                {"sid": session_id},
            )
        ).mappings().all()
        return tuple(_part_status(dict(row)) for row in rows)


# --- row → DTO mappers -----------------------------------------------------


def _session_status(
    row: Mapping[str, Any],
    *,
    slots: tuple[UploadSessionFileSlot, ...],
    max_bytes: int = 2 * 1024 * 1024 * 1024,
    part_size_bytes: int = 64 * 1024 * 1024,
) -> UploadSessionStatus:
    registered = row.get("registered_at") is not None
    return UploadSessionStatus(
        upload_session_id=str(row["source_upload_session_id"]),
        source_file_group_id=str(row["source_file_group_id"]),
        category=row["category"],
        group_kind=row["group_kind"],
        user_yyyymm=str(row["user_yyyymm"]),
        display_name=str(row["display_name"]),
        state=row["state"],
        upload_strategy=row["upload_strategy"],
        storage_kind=row["storage_kind"],
        expected_file_count=int(row["expected_file_count"]),
        uploaded_file_count=int(row["uploaded_file_count"] or 0),
        max_bytes=max_bytes,
        part_size_bytes=part_size_bytes,
        registration_state="registered" if registered else "not_registered",
        bucket=row.get("bucket"),
        prefix=row.get("prefix"),
        file_slots=slots,
        created_by=row.get("created_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row.get("expires_at"),
        registration_deadline_at=row.get("registration_deadline_at"),
        completed_at=row.get("completed_at"),
        registered_at=row.get("registered_at"),
        error_message=row.get("error_message"),
        metadata=dict(row.get("metadata") or {}),
    )


def _part_status(row: Mapping[str, Any]) -> UploadSessionPartStatus:
    return UploadSessionPartStatus(
        part_key=str(row["part_key"]),
        part_number=int(row["part_number"]),
        multipart_upload_id=row.get("multipart_upload_id"),
        part_etag=row.get("part_etag"),
        part_sha256=row.get("part_sha256"),
        received_bytes=int(row["received_bytes"] or 0),
        completed_at=row.get("completed_at"),
    )


def _slots_with_parts(
    session_row: Mapping[str, Any],
    parts: tuple[UploadSessionPartStatus, ...],
) -> tuple[UploadSessionFileSlot, ...]:
    """Overlay recorded part progress onto the static slot definitions."""
    base = slot_definitions(str(session_row["category"]))
    by_key: dict[str, list[UploadSessionPartStatus]] = {}
    for part in parts:
        by_key.setdefault(part.part_key, []).append(part)
    result: list[UploadSessionFileSlot] = []
    for slot in base:
        slot_parts = by_key.get(slot.part_key, [])
        if not slot_parts:
            result.append(slot)
            continue
        received = sum(part.received_bytes for part in slot_parts)
        completed = any(part.completed_at is not None for part in slot_parts)
        upload_id = next(
            (part.multipart_upload_id for part in slot_parts if part.multipart_upload_id),
            None,
        )
        result.append(
            slot.model_copy(
                update={
                    "uploaded": completed,
                    "received_bytes": received,
                    "multipart_upload_id": upload_id,
                }
            )
        )
    return tuple(result)


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))
