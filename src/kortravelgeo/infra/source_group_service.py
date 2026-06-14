"""Source-file-group register + ``recompute_group_aggregates`` (T-203b).

Companion to ``infra/source_upload_repo.py``. Implements:

* :func:`recompute_group_aggregates` — the SINGLE service (raw SQL, run inside
  the caller's transaction) that recomputes a group's derived state and
  propagates to referencing match sets, per the doc contract table
  (``docs/t109-backup-source-upload-management.md`` lines ~345-356, ~804-818).
* :class:`SourceGroupRegistrar` — consumes a *completed* upload session and
  creates the ``ops.source_file_groups`` + ``ops.source_files`` +
  ``ops.source_file_members`` rows, head-verifies each RustFS object, computes
  ``group_sha256``, marks the session ``registered``, and audits the action.
  Idempotent retry on ``failed_register`` (storage-first: objects are never
  auto-deleted).

The pure decision logic lives in ``core.source_match_propagation`` and
``core.source_validation`` so propagation / hashing / structure decisions are
unit-tested without a database. This module is the DB glue only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.source_match_propagation import (
    ChildFileFacts,
    MatchSetFacts,
    MatchSetItemFacts,
    compute_source_set_hash,
    decide_match_set_transition,
    recompute_group_derived,
)
from kortravelgeo.core.source_validation import (
    GroupValidation,
    validate_group_manifest,
)
from kortravelgeo.dto.source import (
    GroupValidationResult,
    RegisterResponse,
    SourceFileRegistered,
)
from kortravelgeo.exceptions import InvalidInputError, NotFoundError
from kortravelgeo.infra.rustfs import rustfs_uri

# Audit actor_type for register (matches admin_repo "ui"/"system" convention).
_REGISTER_LOCK_NAMESPACE = 0x4B47_0204


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))


# --- recompute_group_aggregates -------------------------------------------


@dataclass(frozen=True)
class RecomputeResult:
    """What recompute changed (for audit / response shaping)."""

    source_file_group_id: str
    state: str
    validation_state: str
    actual_file_count: int
    group_sha256: str | None
    coverage: dict[str, str]
    affected_match_set_ids: tuple[str, ...]


async def _child_facts(conn: AsyncConnection, group_id: str) -> tuple[ChildFileFacts, ...]:
    rows = (
        await conn.execute(
            text(
                """
SELECT part_kind, part_key, state, sha256, size_bytes
  FROM ops.source_files
 WHERE source_file_group_id = :gid
"""
            ),
            {"gid": group_id},
        )
    ).mappings().all()
    return tuple(
        ChildFileFacts(
            part_kind=str(r["part_kind"]),
            part_key=str(r["part_key"]),
            state=str(r["state"]),
            sha256=str(r["sha256"]),
            size_bytes=int(r["size_bytes"]),
        )
        for r in rows
    )


async def _expected_part_keys(conn: AsyncConnection, group_id: str) -> tuple[str, ...]:
    row = (
        await conn.execute(
            text(
                """
SELECT group_kind, expected_file_count, metadata
  FROM ops.source_file_groups
 WHERE source_file_group_id = :gid
"""
            ),
            {"gid": group_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError(f"source file group not found: {group_id}")
    if row["group_kind"] == "single_file":
        return ("archive",)
    metadata = dict(row.get("metadata") or {})
    keys = metadata.get("expected_part_keys")
    if isinstance(keys, list) and keys:
        return tuple(str(k) for k in keys)
    # Fall back to whatever children exist (caller persists keys in metadata).
    rows = (
        await conn.execute(
            text(
                "SELECT DISTINCT part_key FROM ops.source_files "
                "WHERE source_file_group_id = :gid"
            ),
            {"gid": group_id},
        )
    ).all()
    return tuple(str(r[0]) for r in rows)


async def _referencing_match_sets(
    conn: AsyncConnection, group_id: str
) -> tuple[Mapping[str, Any], ...]:
    rows = (
        await conn.execute(
            text(
                """
SELECT DISTINCT ms.source_match_set_id, ms.state, ms.integrity_alert,
       ms.source_set_hash
  FROM ops.source_match_sets ms
  JOIN ops.source_match_set_items it
    ON it.source_match_set_id = ms.source_match_set_id
 WHERE it.source_file_group_id = :gid
"""
            ),
            {"gid": group_id},
        )
    ).mappings().all()
    return tuple(dict(row) for row in rows)


async def _all_referenced_groups_available(
    conn: AsyncConnection, match_set_id: str
) -> bool:
    row = (
        await conn.execute(
            text(
                """
SELECT bool_and(g.state = 'available') AS all_available, count(*) AS n
  FROM ops.source_match_set_items it
  JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :msid AND it.omitted = false
"""
            ),
            {"msid": match_set_id},
        )
    ).mappings().first()
    return bool(row and row["n"] and row["all_available"])


async def _match_set_item_facts(
    conn: AsyncConnection, match_set_id: str
) -> tuple[MatchSetItemFacts, ...]:
    rows = (
        await conn.execute(
            text(
                """
SELECT it.category, it.source_file_group_id, it.effective_yyyymm,
       it.omitted, it.omitted_reason, g.group_sha256
  FROM ops.source_match_set_items it
  LEFT JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :msid
"""
            ),
            {"msid": match_set_id},
        )
    ).mappings().all()
    return tuple(
        MatchSetItemFacts(
            category=str(r["category"]),
            source_file_group_id=str(r["source_file_group_id"])
            if r["source_file_group_id"]
            else None,
            group_sha256=r["group_sha256"],
            effective_yyyymm=r["effective_yyyymm"],
            omitted=bool(r["omitted"]),
            omitted_reason=r["omitted_reason"],
        )
        for r in rows
    )


async def recompute_group_aggregates(
    conn: AsyncConnection,
    source_file_group_id: str,
    *,
    trigger: str,
    structure_validation_state: str | None = None,
    structure_coverage: dict[str, str] | None = None,
) -> RecomputeResult:
    """Recompute group derived state + propagate to referencing match sets.

    MUST be called inside the caller's transaction (the ``conn`` is the active
    transactional connection). Implements the doc contract table exactly:

    * recompute ``state``/``validation_state``/``actual_file_count``/``coverage``
      /``group_sha256`` from child files;
    * DOWN: bad group → non-active ``validated`` → ``invalid``; active → keep
      ``active`` + ``integrity_alert=true`` (+detail); ``draft``/
      ``restored_from_backup`` pre-hash stay;
    * UP: recovered group → non-active ``invalid`` → ``revalidatable``;
      ``restored_from_backup`` (all refs available) → compute canonical
      ``source_set_hash`` FIRST then → ``revalidatable``; active → mark
      ``integrity_alert_detail.recovered=true`` candidate only;
    * does NOT finalize active ``integrity_alert=false``, activate, or enqueue
      rebuild (those belong to ``POST /validate`` / T-205).
    """
    group_row = (
        await conn.execute(
            text(
                """
SELECT group_kind, validation_state
  FROM ops.source_file_groups
 WHERE source_file_group_id = :gid
"""
            ),
            {"gid": source_file_group_id},
        )
    ).mappings().first()
    if group_row is None:
        raise NotFoundError(f"source file group not found: {source_file_group_id}")

    children = await _child_facts(conn, source_file_group_id)
    expected_keys = await _expected_part_keys(conn, source_file_group_id)
    val_state = structure_validation_state or str(group_row["validation_state"])

    derived = recompute_group_derived(
        group_kind=str(group_row["group_kind"]),
        expected_part_keys=expected_keys,
        children=children,
        structure_validation_state=val_state,  # type: ignore[arg-type]
        structure_coverage=structure_coverage,
    )

    await conn.execute(
        _json_text(
            """
UPDATE ops.source_file_groups
   SET state = :state,
       validation_state = :validation_state,
       actual_file_count = :actual_file_count,
       coverage = :coverage,
       group_sha256 = :group_sha256,
       validated_at = CASE
         WHEN :validation_state IN ('passed','warning') THEN now()
         ELSE validated_at END,
       updated_at = now()
 WHERE source_file_group_id = :gid
""",
            "coverage",
        ),
        {
            "gid": source_file_group_id,
            "state": derived.state,
            "validation_state": derived.validation_state,
            "actual_file_count": derived.actual_file_count,
            "coverage": derived.coverage,
            "group_sha256": derived.group_sha256,
        },
    )

    affected = await _propagate_to_match_sets(
        conn, source_file_group_id, group_state=derived.state, trigger=trigger
    )

    return RecomputeResult(
        source_file_group_id=source_file_group_id,
        state=derived.state,
        validation_state=derived.validation_state,
        actual_file_count=derived.actual_file_count,
        group_sha256=derived.group_sha256,
        coverage=derived.coverage,
        affected_match_set_ids=affected,
    )


async def _propagate_to_match_sets(
    conn: AsyncConnection,
    group_id: str,
    *,
    group_state: str,
    trigger: str,
) -> tuple[str, ...]:
    affected: list[str] = []
    now = datetime.now(UTC).isoformat()
    for ms in await _referencing_match_sets(conn, group_id):
        msid = str(ms["source_match_set_id"])
        recomputed_hash: str | None = None
        all_available = False
        if str(ms["state"]) == "restored_from_backup":
            all_available = await _all_referenced_groups_available(conn, msid)
            if all_available and ms["source_set_hash"] is None:
                recomputed_hash = compute_source_set_hash(
                    await _match_set_item_facts(conn, msid)
                )
        elif str(ms["state"]) == "active":
            all_available = await _all_referenced_groups_available(conn, msid)

        facts = MatchSetFacts(
            source_match_set_id=msid,
            state=str(ms["state"]),  # type: ignore[arg-type]
            integrity_alert=bool(ms["integrity_alert"]),
            all_groups_available=all_available,
            recomputed_source_set_hash=recomputed_hash
            if recomputed_hash is not None
            else ms["source_set_hash"],
        )
        detail: dict[str, object] = {
            "trigger": trigger,
            "group_id": group_id,
            "group_state": group_state,
            "at": now,
        }
        transition = decide_match_set_transition(
            facts, group_state=group_state, detail=detail
        )
        if transition is None:
            continue
        affected.append(msid)
        await _apply_transition(conn, transition)
    return tuple(affected)


async def _apply_transition(conn: AsyncConnection, transition: Any) -> None:
    sets: list[str] = ["updated_at = now()"]
    params: dict[str, Any] = {"msid": transition.source_match_set_id}
    json_params: list[str] = []
    if transition.new_state is not None:
        sets.append("state = :state")
        params["state"] = transition.new_state
    if transition.set_source_set_hash is not None:
        sets.append("source_set_hash = :hash")
        params["hash"] = transition.set_source_set_hash
    if transition.set_integrity_alert is not None:
        sets.append("integrity_alert = :alert")
        params["alert"] = transition.set_integrity_alert
        if transition.set_integrity_alert:
            sets.append("integrity_alert_at = now()")
    if transition.integrity_alert_detail:
        # Merge into existing detail rather than clobbering.
        sets.append("integrity_alert_detail = integrity_alert_detail || :detail")
        params["detail"] = transition.integrity_alert_detail
        json_params.append("detail")
    sql = f"UPDATE ops.source_match_sets SET {', '.join(sets)} WHERE source_match_set_id = :msid"
    stmt = _json_text(sql, *json_params) if json_params else text(sql)
    await conn.execute(stmt, params)


# --- register --------------------------------------------------------------


@dataclass(frozen=True)
class RegisterContext:
    """One verified slot/part the registrar will turn into a source_files row."""

    part_key: str
    part_kind: str
    part_label: str | None
    original_filename: str
    sha256: str
    size_bytes: int
    object_key: str
    object_etag: str | None
    compression_format: str


class SourceGroupRegistrar:
    """Creates registry rows from a completed upload session (doc "register")."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def register(
        self,
        *,
        session_id: str,
        contexts: tuple[RegisterContext, ...],
        structure_validation: GroupValidation,
        storage_kind: str,
        bucket: str | None,
        actor: str | None,
        yyyymm_mismatch_ack: bool,
        display_name: str | None = None,
    ) -> RegisterResponse:
        """Idempotent register: create/locate group + child files in one tx.

        ``contexts`` are the verified parts (sha256/size/object_key already
        head-verified by the caller against the session record). Duplicate
        same-SHA archives surface as a warning candidate, not a hard error.
        """
        async with self.engine.begin() as conn:
            session = (
                await conn.execute(
                    text(
                        """
SELECT source_upload_session_id, source_file_group_id, category, group_kind,
       user_yyyymm, display_name, state, expected_file_count, registered_at,
       metadata
  FROM ops.source_upload_sessions
 WHERE source_upload_session_id = :sid
 FOR UPDATE
"""
                    ),
                    {"sid": session_id},
                )
            ).mappings().first()
            if session is None:
                raise NotFoundError(f"upload session not found: {session_id}")

            category = str(session["category"])
            group_id = str(session["source_file_group_id"])
            user_yyyymm = str(session["user_yyyymm"])
            group_kind = str(session["group_kind"])
            meta = dict(session.get("metadata") or {})
            inferred = meta.get("inferred_yyyymm")
            yyyymm_mismatch = bool(inferred and inferred != user_yyyymm)
            if yyyymm_mismatch and not yyyymm_mismatch_ack:
                msg = "기준년월 mismatch — yyyymm_mismatch_ack=true가 필요합니다"
                raise InvalidInputError(msg)

            # Serialize register for this (category, user_yyyymm) slot.
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),
                {
                    "ns": _REGISTER_LOCK_NAMESPACE,
                    "key": f"{category}:{user_yyyymm}",
                },
            )

            # Idempotent retry: drop any partially-written child rows for this
            # group (failed_register) before re-inserting. Storage objects stay.
            existing_group = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM ops.source_file_groups WHERE source_file_group_id = :gid"
                    ),
                    {"gid": group_id},
                )
            ).first()
            if existing_group is not None:
                await conn.execute(
                    text(
                        "DELETE FROM ops.source_file_members WHERE source_file_id IN "
                        "(SELECT source_file_id FROM ops.source_files "
                        " WHERE source_file_group_id = :gid)"
                    ),
                    {"gid": group_id},
                )
                await conn.execute(
                    text("DELETE FROM ops.source_files WHERE source_file_group_id = :gid"),
                    {"gid": group_id},
                )

            expected_keys = tuple(c.part_key for c in contexts)
            await self._upsert_group(
                conn,
                group_id=group_id,
                category=category,
                group_kind=group_kind,
                display_name=display_name or str(session["display_name"]),
                user_yyyymm=user_yyyymm,
                inferred_yyyymm=inferred,
                yyyymm_mismatch=yyyymm_mismatch,
                expected_file_count=int(session["expected_file_count"]),
                expected_part_keys=expected_keys,
                uploaded_by=actor,
            )

            duplicate_of_group_id = await self._first_duplicate_group(
                conn, group_id=group_id, contexts=contexts
            )

            registered: list[SourceFileRegistered] = []
            for ctx in contexts:
                file_id = str(uuid4())
                storage_uri = (
                    rustfs_uri(bucket, ctx.object_key)
                    if bucket
                    else f"{storage_kind}://{ctx.object_key}"
                )
                file_state = "validating"
                await self._insert_file(
                    conn,
                    file_id=file_id,
                    group_id=group_id,
                    ctx=ctx,
                    storage_kind=storage_kind,
                    storage_uri=storage_uri,
                    bucket=bucket,
                    state=file_state,
                    uploaded_by=actor,
                )
                await self._insert_members(
                    conn,
                    file_id=file_id,
                    part_validation=structure_validation,
                    ctx=ctx,
                )
                registered.append(
                    SourceFileRegistered(
                        source_file_id=file_id,
                        original_filename=ctx.original_filename,
                        part_kind=ctx.part_kind,
                        part_key=ctx.part_key,
                        sha256=ctx.sha256,
                        size_bytes=ctx.size_bytes,
                        storage_uri=storage_uri,
                        object_key=ctx.object_key,
                        bucket=bucket,
                        state=file_state,
                    )
                )

            # group validation row (scope='group') from the structure decision.
            await self._insert_group_validation(
                conn, group_id=group_id, structure_validation=structure_validation
            )

            # Promote children to available iff structure passed/warning.
            if structure_validation.outcome in {"passed", "warning"}:
                await conn.execute(
                    text(
                        """
UPDATE ops.source_files
   SET state = 'available', validation_state = :vstate, validated_at = now()
 WHERE source_file_group_id = :gid AND state = 'validating'
"""
                    ),
                    {"gid": group_id, "vstate": structure_validation.outcome},
                )
            else:
                await conn.execute(
                    text(
                        """
UPDATE ops.source_files
   SET state = 'quarantined', validation_state = 'failed'
 WHERE source_file_group_id = :gid AND state = 'validating'
"""
                    ),
                    {"gid": group_id},
                )

            recompute = await recompute_group_aggregates(
                conn,
                group_id,
                trigger="register",
                structure_validation_state=structure_validation.outcome,
                structure_coverage=structure_validation.coverage,
            )

            await conn.execute(
                text(
                    """
UPDATE ops.source_upload_sessions
   SET state = 'registered', registered_at = now(), updated_at = now()
 WHERE source_upload_session_id = :sid
"""
                ),
                {"sid": session_id},
            )

            await self._audit_register(
                conn,
                group_id=group_id,
                actor=actor,
                category=category,
                user_yyyymm=user_yyyymm,
                outcome="registered",
                duplicate=duplicate_of_group_id is not None,
            )

            group_state_row = (
                await conn.execute(
                    text(
                        """
SELECT state, validation_state, group_sha256
  FROM ops.source_file_groups WHERE source_file_group_id = :gid
"""
                    ),
                    {"gid": group_id},
                )
            ).mappings().one()

        return RegisterResponse(
            source_file_group_id=group_id,
            category=category,
            group_kind=group_kind,
            state=group_state_row["state"],
            validation_state=group_state_row["validation_state"],
            user_yyyymm=user_yyyymm,
            group_sha256=recompute.group_sha256,
            files=tuple(registered),
            duplicate_warning=duplicate_of_group_id is not None,
            duplicate_of_group_id=duplicate_of_group_id,
        )

    async def _upsert_group(
        self,
        conn: AsyncConnection,
        *,
        group_id: str,
        category: str,
        group_kind: str,
        display_name: str,
        user_yyyymm: str,
        inferred_yyyymm: str | None,
        yyyymm_mismatch: bool,
        expected_file_count: int,
        expected_part_keys: tuple[str, ...],
        uploaded_by: str | None,
    ) -> None:
        await conn.execute(
            _json_text(
                """
INSERT INTO ops.source_file_groups
  (source_file_group_id, category, group_kind, display_name, state,
   validation_state, user_yyyymm, inferred_yyyymm, yyyymm_mismatch,
   expected_file_count, actual_file_count, uploaded_by, metadata)
VALUES
  (:gid, :category, :group_kind, :display_name, 'validating',
   'running', :user_yyyymm, :inferred_yyyymm, :yyyymm_mismatch,
   :expected_file_count, 0, :uploaded_by, :metadata)
ON CONFLICT (source_file_group_id) DO UPDATE
   SET display_name = EXCLUDED.display_name,
       state = 'validating',
       validation_state = 'running',
       yyyymm_mismatch = EXCLUDED.yyyymm_mismatch,
       inferred_yyyymm = EXCLUDED.inferred_yyyymm,
       metadata = ops.source_file_groups.metadata || EXCLUDED.metadata,
       deleted_at = NULL,
       updated_at = now()
""",
                "metadata",
            ),
            {
                "gid": group_id,
                "category": category,
                "group_kind": group_kind,
                "display_name": display_name,
                "user_yyyymm": user_yyyymm,
                "inferred_yyyymm": inferred_yyyymm,
                "yyyymm_mismatch": yyyymm_mismatch,
                "expected_file_count": expected_file_count,
                "uploaded_by": uploaded_by,
                "metadata": {"expected_part_keys": list(expected_part_keys)},
            },
        )

    async def _first_duplicate_group(
        self,
        conn: AsyncConnection,
        *,
        group_id: str,
        contexts: tuple[RegisterContext, ...],
    ) -> str | None:
        """Same (sha256,size,part_key) child in another group → warning."""
        for ctx in contexts:
            row = (
                await conn.execute(
                    text(
                        """
SELECT source_file_group_id
  FROM ops.source_files
 WHERE sha256 = :sha AND size_bytes = :size AND part_key = :pk
   AND source_file_group_id <> :gid
   AND state <> 'hard_deleted'
 LIMIT 1
"""
                    ),
                    {
                        "sha": ctx.sha256,
                        "size": ctx.size_bytes,
                        "pk": ctx.part_key,
                        "gid": group_id,
                    },
                )
            ).first()
            if row is not None:
                return str(row[0])
        return None

    async def _insert_file(
        self,
        conn: AsyncConnection,
        *,
        file_id: str,
        group_id: str,
        ctx: RegisterContext,
        storage_kind: str,
        storage_uri: str,
        bucket: str | None,
        state: str,
        uploaded_by: str | None,
    ) -> None:
        await conn.execute(
            text(
                """
INSERT INTO ops.source_files
  (source_file_id, source_file_group_id, original_filename, part_kind, part_key,
   part_label, compression_format, state, validation_state, size_bytes, sha256,
   storage_kind, storage_uri, bucket, object_key, object_etag, uploaded_by)
VALUES
  (:fid, :gid, :original_filename, :part_kind, :part_key,
   :part_label, :compression_format, :state, 'running', :size_bytes, :sha256,
   :storage_kind, :storage_uri, :bucket, :object_key, :object_etag, :uploaded_by)
"""
            ),
            {
                "fid": file_id,
                "gid": group_id,
                "original_filename": ctx.original_filename,
                "part_kind": ctx.part_kind,
                "part_key": ctx.part_key,
                "part_label": ctx.part_label,
                "compression_format": ctx.compression_format,
                "state": state,
                "size_bytes": ctx.size_bytes,
                "sha256": ctx.sha256,
                "storage_kind": storage_kind,
                "storage_uri": storage_uri,
                "bucket": bucket,
                "object_key": ctx.object_key,
                "object_etag": ctx.object_etag,
                "uploaded_by": uploaded_by,
            },
        )

    async def _insert_members(
        self,
        conn: AsyncConnection,
        *,
        file_id: str,
        part_validation: GroupValidation,
        ctx: RegisterContext,
    ) -> None:
        part = next((p for p in part_validation.parts if p.part_key == ctx.part_key), None)
        if part is None:
            return
        for layer in sorted(part.present_layers):
            await self._insert_member_row(
                conn,
                file_id=file_id,
                member_path=f"{layer}",
                member_kind="shp_layer",
                ctx=ctx,
                layer_name=layer,
            )

    async def _insert_member_row(
        self,
        conn: AsyncConnection,
        *,
        file_id: str,
        member_path: str,
        member_kind: str,
        ctx: RegisterContext,
        layer_name: str | None = None,
    ) -> None:
        await conn.execute(
            text(
                """
INSERT INTO ops.source_file_members
  (source_file_member_id, source_file_id, member_path, member_kind, part_kind,
   part_key, part_label, layer_name)
VALUES
  (:mid, :fid, :member_path, :member_kind, :part_kind, :part_key, :part_label,
   :layer_name)
"""
            ),
            {
                "mid": str(uuid4()),
                "fid": file_id,
                "member_path": member_path,
                "member_kind": member_kind,
                "part_kind": ctx.part_kind,
                "part_key": ctx.part_key,
                "part_label": ctx.part_label,
                "layer_name": layer_name,
            },
        )

    async def _insert_group_validation(
        self,
        conn: AsyncConnection,
        *,
        group_id: str,
        structure_validation: GroupValidation,
    ) -> None:
        from kortravelgeo.core.source_validation import VALIDATOR_VERSION

        await conn.execute(
            _json_text(
                """
INSERT INTO ops.source_file_validations
  (source_file_validation_id, source_file_group_id, scope, validator_version,
   state, finished_at, progress, details)
VALUES
  (:vid, :gid, 'group', :validator_version, :state, now(), 1.0, :details)
""",
                "details",
            ),
            {
                "vid": str(uuid4()),
                "gid": group_id,
                "validator_version": VALIDATOR_VERSION,
                "state": structure_validation.outcome,
                "details": {
                    "reasons": list(structure_validation.reasons),
                    "coverage": structure_validation.coverage,
                },
            },
        )

    async def _audit_register(
        self,
        conn: AsyncConnection,
        *,
        group_id: str,
        actor: str | None,
        category: str,
        user_yyyymm: str,
        outcome: str,
        duplicate: bool,
    ) -> None:
        from kortravelgeo.core.source_events import SOURCE_UPLOAD_REGISTER

        await conn.execute(
            _json_text(
                """
INSERT INTO ops.audit_events
  (event_id, actor_type, actor_id, action, resource_type, resource_id,
   outcome, payload_redacted)
VALUES
  (:event_id, :actor_type, :actor_id, :action, :resource_type, :resource_id,
   :outcome, :payload)
""",
                "payload",
            ),
            {
                "event_id": str(uuid4()),
                "actor_type": "ui",
                "actor_id": actor,
                "action": SOURCE_UPLOAD_REGISTER,
                "resource_type": "source_file_group",
                "resource_id": group_id,
                "outcome": outcome,
                "payload": {
                    "category": category,
                    "user_yyyymm": user_yyyymm,
                    "duplicate_warning": duplicate,
                },
            },
        )


async def revalidate_group(
    engine: AsyncEngine,
    source_file_group_id: str,
    *,
    decision: GroupValidation,
    actor: str | None,
    trigger: str = "revalidate",
) -> GroupValidationResult:
    """Persist a fresh structure decision and recompute, in one transaction.

    The caller supplies the already-computed :class:`GroupValidation` (from
    materialized archives via the GDAL/zip adapter) so this DB-glue function
    stays storage-free and testable; it writes the validation row, folds the
    decision into ``validation_state``/``coverage`` via recompute, and propagates
    to referencing match sets.
    """
    from kortravelgeo.core.source_validation import VALIDATOR_VERSION

    async with engine.begin() as conn:
        group_row = (
            await conn.execute(
                text(
                    """
SELECT category, group_kind FROM ops.source_file_groups
 WHERE source_file_group_id = :gid FOR UPDATE
"""
                ),
                {"gid": source_file_group_id},
            )
        ).mappings().first()
        if group_row is None:
            raise NotFoundError(f"source file group not found: {source_file_group_id}")
        await conn.execute(
            _json_text(
                """
INSERT INTO ops.source_file_validations
  (source_file_validation_id, source_file_group_id, scope, validator_version,
   state, finished_at, progress, details)
VALUES
  (:vid, :gid, 'group', :validator_version, :state, now(), 1.0, :details)
""",
                "details",
            ),
            {
                "vid": str(uuid4()),
                "gid": source_file_group_id,
                "validator_version": VALIDATOR_VERSION,
                "state": decision.outcome,
                "details": {
                    "reasons": list(decision.reasons),
                    "coverage": decision.coverage,
                },
            },
        )
        recompute = await recompute_group_aggregates(
            conn,
            source_file_group_id,
            trigger=trigger,
            structure_validation_state=decision.outcome,
            structure_coverage=decision.coverage,
        )
        # Keep child states consistent with the group decision.
        if decision.outcome in {"passed", "warning"}:
            await conn.execute(
                text(
                    """
UPDATE ops.source_files
   SET state = 'available', validation_state = :vstate, validated_at = now()
 WHERE source_file_group_id = :gid AND state IN ('validating','quarantined')
"""
                ),
                {"gid": source_file_group_id, "vstate": decision.outcome},
            )
        else:
            await conn.execute(
                text(
                    """
UPDATE ops.source_files
   SET state = 'quarantined', validation_state = 'failed'
 WHERE source_file_group_id = :gid AND state = 'validating'
"""
                ),
                {"gid": source_file_group_id},
            )
    return GroupValidationResult(
        source_file_group_id=source_file_group_id,
        category=str(group_row["category"]),
        validation_state=recompute.validation_state,
        state=recompute.state,
        coverage=recompute.coverage,
        reasons=decision.reasons,
        validator_version=VALIDATOR_VERSION,
    )


def build_group_validation(
    *, category: str, group_kind: str, parts: dict[str, Any]
) -> GroupValidationResult:
    """Convenience for the validate endpoint: scan manifests → decide → DTO.

    ``parts`` maps ``part_key -> archive Path``. Imports the GDAL/zip adapter
    lazily so importing this module never requires it.
    """
    from kortravelgeo.core.source_validation import VALIDATOR_VERSION
    from kortravelgeo.infra.source_member_scan import scan_group_manifest

    manifest = scan_group_manifest(category=category, group_kind=group_kind, parts=parts)
    decision = validate_group_manifest(manifest)
    return GroupValidationResult(
        source_file_group_id="",  # filled by caller
        category=category,
        validation_state=decision.outcome,
        state="validating",
        coverage=decision.coverage,
        reasons=decision.reasons,
        validator_version=VALIDATOR_VERSION,
    )
