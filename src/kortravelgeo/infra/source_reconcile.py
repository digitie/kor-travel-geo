"""RustFS ⟷ DB registry reconciliation service (T-204).

DB + RustFS glue around the pure decisions in ``core.source_reconcile``. Covers:

* :func:`run_source_reconcile` — creates a ``source_storage_reconcile_runs`` row,
  scans ``ops.source_files`` against the RustFS prefix, and emits a
  ``source_storage_reconcile_items`` row for each of the 12 issue_types. quick vs
  deep + rolling-deep are decided per object; ``source_files.last_verified_*`` /
  ``last_deep_verified_at`` are updated as objects are checked. en-masse loss is
  detected and propagated (groups → ``missing`` via
  :func:`recompute_group_aggregates`).
* :func:`resolve_reconcile_item` — the resolve action set with a read-after-write
  recheck and the active-정본 deletion guard; each resolve audits and may call
  ``recompute_group_aggregates``.
* :func:`compute_source_capacity` — per-category capacity usage usable before an
  upload/register (the retention policy is T-212).

The pure classification / guard / capacity math lives in
``core.source_reconcile`` so it is unit-tested without a DB or RustFS; this module
reads rows, calls those functions, and writes results back.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.source_events import (
    SOURCE_HARD_DELETE,
    SOURCE_RECONCILE_RESOLVE,
    SOURCE_RECONCILE_RUN,
)
from kortravelgeo.core.source_reconcile import (
    BulkHardDeletePlan,
    CapacityUsage,
    CategoryCapacity,
    DbFileFact,
    DuplicateObjectFact,
    HardDeleteCandidateFact,
    IssueDecision,
    ObjectHeadFact,
    ReconcileIssueType,
    ReResolveCheck,
    ResolveAction,
    ResolveGuard,
    assess_bucket_loss,
    build_retention_recommendation,
    bulk_hard_delete_confirmation,
    check_pre_delete_safety,
    classify_db_file,
    classify_unregistered_object,
    compute_capacity_usage,
    decide_rehash,
    find_duplicate_object_groups,
    guard_object_deletion,
    issue_severity,
    mass_loss_issue_type,
    plan_bulk_hard_delete,
    resolve_still_applies,
)
from kortravelgeo.core.source_reconcile import (
    UnregisteredObjectFact as _UnregFact,
)
from kortravelgeo.dto.source import (
    ReconcileResolveResponse,
    SourceBulkHardDeleteResponse,
    SourceCapacityUsage,
    SourceCategoryCapacity,
    SourceHardDeleteOutcome,
    SourceReconcileItem,
    SourceReconcileRun,
    SourceRetentionRecommendation,
)
from kortravelgeo.exceptions import ConflictError, InvalidInputError, NotFoundError
from kortravelgeo.infra.metrics import (
    record_source_hard_delete,
    record_source_reconcile_item,
    record_source_reconcile_resolve,
    record_source_reconcile_run,
)
from kortravelgeo.infra.rustfs import RustfsClient
from kortravelgeo.infra.source_audit import insert_source_audit_event
from kortravelgeo.infra.source_group_service import recompute_group_aggregates

_LOGGER = logging.getLogger(__name__)


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))


# --- run -------------------------------------------------------------------


@dataclass(frozen=True)
class ReconcileRunResult:
    """What one reconciliation pass produced (response + audit shaping)."""

    source_storage_reconcile_run_id: str
    prefix: str
    mode: str
    state: str
    scanned_objects: int
    scanned_db_files: int
    rehashed_objects: int
    skipped_rehash_objects: int
    mismatch_count: int
    issue_counts: dict[str, int]
    mass_loss: bool


async def run_source_reconcile(
    engine: AsyncEngine,
    *,
    rustfs: RustfsClient,
    prefix: str,
    mode: str = "quick",
    actor: str | None,
    rolling_deep_days: int,
    object_limit: int = 50_000,
    now: datetime | None = None,
) -> ReconcileRunResult:
    """Run one reconciliation pass over ``prefix`` (doc lines ~638-726, ~1606).

    1. lists RustFS objects under ``prefix`` and loads live ``ops.source_files``;
    2. for every DB file with an object: classifies (quick skips rehash when
       size+etag unchanged, force-deeps past the rolling-deep window; deep always
       rehashes) and emits a mismatch item, updating ``last_verified_*`` /
       ``last_deep_verified_at``;
    3. for every DB file whose object is absent: emits ``db_missing_object`` (or,
       under en-masse loss, ``source_file_unavailable``) and marks the file
       ``missing``;
    4. for every object with no live DB row: ``pending_registration`` /
       ``registration_expired`` / ``object_missing_db``;
    5. detects ``duplicate_object`` sets;
    6. when the absence ratio crosses the mass-loss threshold, sets referenced
       groups ``missing`` and propagates via ``recompute_group_aggregates``.
    """
    effective_now = now or datetime.now(UTC)
    run_id = str(uuid4())
    issue_counts: dict[str, int] = {}

    listed = await rustfs.list_objects(prefix, limit=object_limit)
    objects_by_key = {obj.key: obj for obj in listed}

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
INSERT INTO ops.source_storage_reconcile_runs
  (source_storage_reconcile_run_id, prefix, mode, state)
VALUES (:rid, :prefix, :mode, 'running')
"""
            ),
            {"rid": run_id, "prefix": prefix, "mode": mode},
        )

        db_files = await _load_live_files(conn, prefix=prefix)
        scanned_db_files = len(db_files)
        scanned_objects = len(objects_by_key)

        absent_files = [
            f for f in db_files if not (f.object_key and f.object_key in objects_by_key)
        ]
        loss = assess_bucket_loss(
            scanned_live_files=scanned_db_files, missing_files=len(absent_files)
        )

        rehashed = 0
        skipped = 0
        mismatch = 0
        affected_group_ids: set[str] = set()

        for db in db_files:
            obj = objects_by_key.get(db.object_key) if db.object_key else None
            if obj is None:
                # DB row, object absent.
                issue: ReconcileIssueType = (
                    mass_loss_issue_type(present_in_registry_only=False)
                    if loss.is_mass_loss
                    else "db_missing_object"
                )
                await _emit_item(
                    conn,
                    run_id=run_id,
                    issue_type=issue,
                    db=db,
                    object_size=None,
                    object_etag=None,
                    object_sha256=None,
                    severity=issue_severity(issue),
                    details={"mass_loss": loss.is_mass_loss},
                )
                issue_counts[issue] = issue_counts.get(issue, 0) + 1
                mismatch += 1
                await _mark_file_missing(conn, db.source_file_id)
                affected_group_ids.add(db.source_file_group_id)
                continue

            # Object present: decide rehash, optionally re-read body.
            head = ObjectHeadFact(present=True, size=obj.size, etag=obj.etag)
            rehash_decision = decide_rehash(
                db,
                head,
                mode=mode,  # type: ignore[arg-type]
                now=effective_now,
                rolling_deep_days=rolling_deep_days,
            )
            rehash_sha256: str | None = None
            if rehash_decision.rehash and db.object_key:
                try:
                    rehash_sha256 = await rustfs.rehash(db.object_key)
                    rehashed += 1
                except Exception:  # treat unreadable body as absent
                    _LOGGER.warning("reconcile rehash failed", extra={"key": db.object_key})
                    await _emit_item(
                        conn,
                        run_id=run_id,
                        issue_type="db_missing_object",
                        db=db,
                        object_size=obj.size,
                        object_etag=obj.etag,
                        object_sha256=None,
                        severity=issue_severity("db_missing_object"),
                        details={"rehash_failed": True},
                    )
                    issue_counts["db_missing_object"] = (
                        issue_counts.get("db_missing_object", 0) + 1
                    )
                    mismatch += 1
                    continue
            else:
                skipped += 1

            head = ObjectHeadFact(
                present=True, size=obj.size, etag=obj.etag, rehash_sha256=rehash_sha256
            )
            decision = classify_db_file(
                db,
                head,
                mode=mode,  # type: ignore[arg-type]
                now=effective_now,
                rolling_deep_days=rolling_deep_days,
            )
            await _update_last_verified(
                conn,
                source_file_id=db.source_file_id,
                etag=obj.etag,
                size=obj.size,
                deep=rehash_sha256 is not None,
                now=effective_now,
            )
            if decision.issue_type is not None:
                await _emit_item(
                    conn,
                    run_id=run_id,
                    issue_type=decision.issue_type,
                    db=db,
                    object_size=obj.size,
                    object_etag=obj.etag,
                    object_sha256=rehash_sha256,
                    severity=decision.severity,
                    details={"reason": decision.reason},
                )
                issue_counts[decision.issue_type] = (
                    issue_counts.get(decision.issue_type, 0) + 1
                )
                mismatch += 1

        # Objects with no live DB row.
        live_keys = {f.object_key for f in db_files if f.object_key}
        unregistered = [k for k in objects_by_key if k not in live_keys]
        for key in unregistered:
            unreg = await _classify_unregistered(conn, key)
            await _emit_item(
                conn,
                run_id=run_id,
                issue_type=unreg.issue_type,  # type: ignore[arg-type]
                db=None,
                object_key=key,
                object_size=objects_by_key[key].size,
                object_etag=objects_by_key[key].etag,
                object_sha256=None,
                severity=unreg.severity,
                details={"reason": unreg.reason},
            )
            assert unreg.issue_type is not None
            issue_counts[unreg.issue_type] = issue_counts.get(unreg.issue_type, 0) + 1
            mismatch += 1

        # duplicate_object: same (sha256, size) across >1 live object key.
        dup_facts = tuple(
            DuplicateObjectFact(
                source_file_id=f.source_file_id,
                object_key=f.object_key or "",
                sha256=f.sha256,
                size_bytes=f.size_bytes,
            )
            for f in db_files
            if f.object_key and f.object_key in objects_by_key
        )
        for group in find_duplicate_object_groups(dup_facts):
            for member in group:
                await _emit_item(
                    conn,
                    run_id=run_id,
                    issue_type="duplicate_object",
                    db=None,
                    source_file_id=member.source_file_id,
                    object_key=member.object_key,
                    object_size=member.size_bytes,
                    object_etag=None,
                    object_sha256=member.sha256,
                    severity=issue_severity("duplicate_object"),
                    details={
                        "duplicate_keys": [m.object_key for m in group],
                    },
                )
                issue_counts["duplicate_object"] = (
                    issue_counts.get("duplicate_object", 0) + 1
                )
                mismatch += 1

        # Mass loss: propagate referenced groups (missing → match-set fan-out).
        if loss.is_mass_loss:
            for gid in sorted(affected_group_ids):
                await recompute_group_aggregates(conn, gid, trigger="reconcile_mass_loss")

        await conn.execute(
            _json_text(
                """
UPDATE ops.source_storage_reconcile_runs
   SET state = 'completed', finished_at = now(),
       scanned_objects = :scanned_objects,
       scanned_db_files = :scanned_db_files,
       rehashed_objects = :rehashed_objects,
       skipped_rehash_objects = :skipped_rehash_objects,
       mismatch_count = :mismatch_count,
       summary = :summary
 WHERE source_storage_reconcile_run_id = :rid
""",
                "summary",
            ),
            {
                "rid": run_id,
                "scanned_objects": scanned_objects,
                "scanned_db_files": scanned_db_files,
                "rehashed_objects": rehashed,
                "skipped_rehash_objects": skipped,
                "mismatch_count": mismatch,
                "summary": {
                    "issue_counts": issue_counts,
                    "mass_loss": loss.is_mass_loss,
                    "missing_files": loss.missing_files,
                },
            },
        )
        await _audit_reconcile(
            conn,
            action=SOURCE_RECONCILE_RUN,
            resource_id=run_id,
            actor=actor,
            outcome="completed",
            payload={
                "prefix": prefix,
                "mode": mode,
                "mismatch_count": mismatch,
                "issue_counts": issue_counts,
                "mass_loss": loss.is_mass_loss,
            },
        )

    record_source_reconcile_run(mode=mode, outcome="completed")
    for issue_name, count in issue_counts.items():
        for _ in range(count):
            record_source_reconcile_item(
                issue_type=issue_name, severity=issue_severity(issue_name)
            )

    return ReconcileRunResult(
        source_storage_reconcile_run_id=run_id,
        prefix=prefix,
        mode=mode,
        state="completed",
        scanned_objects=scanned_objects,
        scanned_db_files=scanned_db_files,
        rehashed_objects=rehashed,
        skipped_rehash_objects=skipped,
        mismatch_count=mismatch,
        issue_counts=issue_counts,
        mass_loss=loss.is_mass_loss,
    )


async def _load_live_files(conn: AsyncConnection, *, prefix: str) -> tuple[DbFileFact, ...]:
    rows = (
        await conn.execute(
            text(
                """
SELECT source_file_id, source_file_group_id, object_key, state, sha256,
       size_bytes, object_etag, last_verified_etag, last_verified_size_bytes,
       last_verified_at, last_deep_verified_at
  FROM ops.source_files
 WHERE state IN ('available', 'validating', 'missing', 'quarantined', 'delete_failed')
   AND (object_key IS NULL OR object_key LIKE :prefix)
"""
            ),
            {"prefix": f"{prefix}%"},
        )
    ).mappings().all()
    return tuple(
        DbFileFact(
            source_file_id=str(r["source_file_id"]),
            source_file_group_id=str(r["source_file_group_id"]),
            object_key=r["object_key"],
            state=str(r["state"]),
            sha256=str(r["sha256"]),
            size_bytes=int(r["size_bytes"]),
            object_etag=r["object_etag"],
            last_verified_etag=r["last_verified_etag"],
            last_verified_size_bytes=r["last_verified_size_bytes"],
            last_verified_at=r["last_verified_at"],
            last_deep_verified_at=r["last_deep_verified_at"],
        )
        for r in rows
    )


async def _classify_unregistered(
    conn: AsyncConnection, object_key: str
) -> IssueDecision:
    """Decide pending_registration / registration_expired / object_missing_db.

    Looks for an upload session whose ``prefix`` is a prefix of the object key
    and that is not yet registered, then applies the pure decision.
    """
    session = (
        await conn.execute(
            text(
                """
SELECT state, registered_at, registration_deadline_at, expires_at
  FROM ops.source_upload_sessions
 WHERE :key LIKE prefix || '%' AND prefix IS NOT NULL
 ORDER BY created_at DESC
 LIMIT 1
"""
            ),
            {"key": object_key},
        )
    ).mappings().first()
    if session is None:
        return classify_unregistered_object(_UnregFact(object_key=object_key))
    registered = session["registered_at"] is not None
    deadline = session["registration_deadline_at"]
    now = datetime.now(UTC)
    past_deadline = deadline is not None and now >= deadline
    return classify_unregistered_object(
        _UnregFact(
            object_key=object_key,
            has_live_session=not registered,
            past_registration_deadline=past_deadline,
        )
    )


async def _emit_item(
    conn: AsyncConnection,
    *,
    run_id: str,
    issue_type: str,
    db: DbFileFact | None,
    severity: str,
    object_key: str | None = None,
    source_file_id: str | None = None,
    object_size: int | None = None,
    object_etag: str | None = None,
    object_sha256: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        _json_text(
            """
INSERT INTO ops.source_storage_reconcile_items
  (source_storage_reconcile_item_id, source_storage_reconcile_run_id, issue_type,
   source_file_group_id, source_file_id, object_key, db_sha256, object_sha256,
   db_size_bytes, object_size_bytes, db_etag, object_etag, severity, state, details)
VALUES
  (:iid, :rid, :issue_type, :gid, :fid, :object_key, :db_sha256, :object_sha256,
   :db_size, :object_size, :db_etag, :object_etag, :severity, 'open', :details)
""",
            "details",
        ),
        {
            "iid": str(uuid4()),
            "rid": run_id,
            "issue_type": issue_type,
            "gid": db.source_file_group_id if db else None,
            "fid": source_file_id or (db.source_file_id if db else None),
            "object_key": object_key or (db.object_key if db else None),
            "db_sha256": db.sha256 if db else None,
            "object_sha256": object_sha256,
            "db_size": db.size_bytes if db else None,
            "object_size": object_size,
            "db_etag": db.object_etag if db else None,
            "object_etag": object_etag,
            "severity": severity,
            "details": details or {},
        },
    )


async def _mark_file_missing(conn: AsyncConnection, source_file_id: str) -> None:
    await conn.execute(
        text(
            """
UPDATE ops.source_files
   SET state = 'missing'
 WHERE source_file_id = :fid AND state IN ('available', 'validating')
"""
        ),
        {"fid": source_file_id},
    )


async def _update_last_verified(
    conn: AsyncConnection,
    *,
    source_file_id: str,
    etag: str | None,
    size: int | None,
    deep: bool,
    now: datetime,
) -> None:
    await conn.execute(
        text(
            """
UPDATE ops.source_files
   SET last_verified_etag = :etag,
       last_verified_size_bytes = :size,
       last_verified_at = :now,
       last_deep_verified_at = CASE WHEN :deep THEN :now ELSE last_deep_verified_at END
 WHERE source_file_id = :fid
"""
        ),
        {"fid": source_file_id, "etag": etag, "size": size, "deep": deep, "now": now},
    )


# --- resolve ----------------------------------------------------------------


async def resolve_reconcile_item(
    engine: AsyncEngine,
    item_id: str,
    *,
    action: ResolveAction,
    actor: str | None,
    rustfs: RustfsClient | None = None,
    category: str | None = None,
    user_yyyymm: str | None = None,
    registration_deadline_at: datetime | None = None,
    typed_confirmation: str | None = None,
) -> ReconcileResolveResponse:
    """Apply a resolve action to one reconciliation item (doc lines ~1458-1479).

    Runs the read-after-write recheck (re-reads the DB row + RustFS head), the
    active-정본 deletion guard for object deletes, then the action. Audits and —
    for state-changing resolves — calls ``recompute_group_aggregates`` so a
    referencing match set follows the group.
    """
    affected: tuple[str, ...] = ()
    async with engine.begin() as conn:
        item_row = (
            await conn.execute(
                text(
                    """
SELECT issue_type, source_file_group_id, source_file_id, object_key,
       object_sha256, state
  FROM ops.source_storage_reconcile_items
 WHERE source_storage_reconcile_item_id = :iid FOR UPDATE
"""
                ),
                {"iid": item_id},
            )
        ).mappings().first()
        if item_row is None:
            raise NotFoundError(f"reconcile item not found: {item_id}")
        item: dict[str, Any] = dict(item_row)
        if str(item["state"]) != "open":
            raise ConflictError("이미 resolve된 reconcile item입니다")

        object_key = item["object_key"]
        file_id = item["source_file_id"]

        # Read-after-write recheck: DB row presence + RustFS head.
        db_row_present = await _file_row_present(conn, file_id) if file_id else False
        object_present = False
        if object_key and rustfs is not None:
            try:
                await rustfs.head_object(object_key)
                object_present = True
            except Exception:
                object_present = False
        elif object_key and rustfs is None:
            # No storage client: trust the recorded object_key (cannot recheck).
            object_present = True

        still = resolve_still_applies(
            action=action,
            recheck=ReResolveCheck(
                db_row_present=db_row_present, object_present=object_present
            ),
        )
        if not still.allowed:
            record_source_reconcile_resolve(action=action, outcome="stale")
            return _resolve_response(
                item_id, item, action, "ignored", still.reason, affected
            )
        if action == "import_object":
            if not category or not user_yyyymm:
                raise InvalidInputError("import_object에는 category와 user_yyyymm이 필요합니다")
            outcome = "blocked:registration_flow_required"
            record_source_reconcile_resolve(action=action, outcome="blocked")
            return _resolve_response(item_id, item, action, "ignored", outcome, affected)

        outcome, affected = await _apply_resolve_action(
            conn,
            action=action,
            item=item,
            actor=actor,
            rustfs=rustfs,
            category=category,
            user_yyyymm=user_yyyymm,
            registration_deadline_at=registration_deadline_at,
            typed_confirmation=typed_confirmation,
            object_present=object_present,
        )

        new_state = "ignored" if outcome.startswith("blocked") else "resolved"
        await conn.execute(
            text(
                """
UPDATE ops.source_storage_reconcile_items
   SET state = :state, resolution_action = :action, resolved_by = :actor,
       resolved_at = now()
 WHERE source_storage_reconcile_item_id = :iid
"""
            ),
            {"state": new_state, "action": action, "actor": actor, "iid": item_id},
        )
        if new_state == "resolved":
            await conn.execute(
                text(
                    """
UPDATE ops.source_storage_reconcile_runs
   SET resolved_count = resolved_count + 1
 WHERE source_storage_reconcile_run_id = (
         SELECT source_storage_reconcile_run_id
           FROM ops.source_storage_reconcile_items
          WHERE source_storage_reconcile_item_id = :iid)
"""
                ),
                {"iid": item_id},
            )
        await _audit_reconcile(
            conn,
            action=SOURCE_RECONCILE_RESOLVE,
            resource_id=item_id,
            actor=actor,
            outcome=outcome,
            payload={
                "issue_type": str(item["issue_type"]),
                "resolve_action": action,
                "affected_match_set_ids": list(affected),
            },
        )

    record_source_reconcile_resolve(
        action=action, outcome="blocked" if outcome.startswith("blocked") else outcome
    )
    return _resolve_response(item_id, item, action, new_state, outcome, affected)


async def _apply_resolve_action(
    conn: AsyncConnection,
    *,
    action: ResolveAction,
    item: Mapping[str, Any],
    actor: str | None,
    rustfs: RustfsClient | None,
    category: str | None,
    user_yyyymm: str | None,
    registration_deadline_at: datetime | None,
    typed_confirmation: str | None,
    object_present: bool,
) -> tuple[str, tuple[str, ...]]:
    group_id = item["source_file_group_id"]
    file_id = item["source_file_id"]
    object_key = item["object_key"]
    affected: tuple[str, ...] = ()

    if action == "mark_db_missing":
        if file_id:
            await conn.execute(
                text("UPDATE ops.source_files SET state = 'missing' WHERE source_file_id = :fid"),
                {"fid": file_id},
            )
        if group_id:
            r = await recompute_group_aggregates(conn, str(group_id), trigger="reconcile_resolve")
            affected = r.affected_match_set_ids
        return "marked_missing", affected

    if action == "soft_delete_db_row":
        if file_id:
            await conn.execute(
                text(
                    "UPDATE ops.source_files SET state = 'soft_deleted', deleted_at = now() "
                    "WHERE source_file_id = :fid AND state <> 'hard_deleted'"
                ),
                {"fid": file_id},
            )
        if group_id:
            r = await recompute_group_aggregates(conn, str(group_id), trigger="reconcile_resolve")
            affected = r.affected_match_set_ids
        return "soft_deleted", affected

    if action == "restore_soft_deleted":
        if file_id:
            await conn.execute(
                text(
                    "UPDATE ops.source_files SET state = 'validating', deleted_at = NULL "
                    "WHERE source_file_id = :fid AND state = 'soft_deleted'"
                ),
                {"fid": file_id},
            )
        if group_id:
            r = await recompute_group_aggregates(conn, str(group_id), trigger="reconcile_resolve")
            affected = r.affected_match_set_ids
        return "restored", affected

    if action == "extend_registration_deadline":
        if registration_deadline_at is None:
            raise InvalidInputError("registration_deadline_at가 필요합니다")
        await conn.execute(
            text(
                """
UPDATE ops.source_upload_sessions
   SET registration_deadline_at = :deadline, updated_at = now()
 WHERE prefix IS NOT NULL AND :key LIKE prefix || '%'
"""
            ),
            {"deadline": registration_deadline_at, "key": object_key},
        )
        return "deadline_extended", affected

    if action == "import_object":
        if not category or not user_yyyymm:
            raise InvalidInputError("import_object에는 category와 user_yyyymm이 필요합니다")
        raise InvalidInputError(
            "import_object resolve는 registry 등록을 수행하지 않습니다. "
            "upload/register flow로 object를 등록하세요"
        )

    if action == "delete_object":
        guard = await _deletion_guard(conn, object_key)
        if not guard.allowed:
            return f"blocked:{guard.reason}", tuple(guard.blocking_match_set_ids)
        if object_key and object_present and rustfs is None:
            return "blocked:rustfs_unavailable", affected
        if object_key and rustfs is not None and object_present:
            await rustfs.delete_object(object_key)
        if file_id:
            await conn.execute(
                text(
                    "UPDATE ops.source_files SET state = 'hard_deleted', deleted_at = now() "
                    "WHERE source_file_id = :fid"
                ),
                {"fid": file_id},
            )
        if group_id:
            r = await recompute_group_aggregates(conn, str(group_id), trigger="reconcile_resolve")
            affected = r.affected_match_set_ids
        return "object_deleted", affected

    if action == "retry_delete_object":
        if object_key and rustfs is not None:
            await rustfs.delete_object(object_key)
        if file_id:
            await conn.execute(
                text(
                    "UPDATE ops.source_files SET state = 'hard_deleted' "
                    "WHERE source_file_id = :fid AND state = 'delete_failed'"
                ),
                {"fid": file_id},
            )
        if group_id:
            r = await recompute_group_aggregates(conn, str(group_id), trigger="reconcile_resolve")
            affected = r.affected_match_set_ids
        return "delete_retried", affected

    if action == "update_hash_after_verify":
        if not typed_confirmation:
            raise InvalidInputError(
                "update_hash_after_verify에는 typed_confirmation이 필요합니다"
            )
        new_hash = item["object_sha256"]
        if not new_hash and object_key and rustfs is not None:
            new_hash = await rustfs.rehash(object_key)
        if not new_hash:
            raise InvalidInputError("object SHA-256을 확인할 수 없습니다")
        if file_id:
            await conn.execute(
                text(
                    "UPDATE ops.source_files SET sha256 = :sha, state = 'validating', "
                    "last_deep_verified_at = now() WHERE source_file_id = :fid"
                ),
                {"sha": new_hash, "fid": file_id},
            )
        if group_id:
            r = await recompute_group_aggregates(conn, str(group_id), trigger="reconcile_resolve")
            affected = r.affected_match_set_ids
        return "hash_updated", affected

    raise InvalidInputError(f"unknown resolve action: {action}")


async def _deletion_guard(
    conn: AsyncConnection, object_key: str | None
) -> ResolveGuard:
    """Build the active-정본 deletion guard from the live DB (doc line 1479)."""
    if not object_key:
        return guard_object_deletion(
            object_key="", active_match_set_group_object_keys=frozenset()
        )
    rows = (
        await conn.execute(
            text(
                """
SELECT DISTINCT f.object_key, ms.source_match_set_id
  FROM ops.source_match_sets ms
  JOIN ops.source_match_set_items it
    ON it.source_match_set_id = ms.source_match_set_id
  JOIN ops.source_files f
    ON f.source_file_group_id = it.source_file_group_id
 WHERE ms.state = 'active' AND f.object_key IS NOT NULL
   AND f.state <> 'hard_deleted'
"""
            )
        )
    ).all()
    active_keys = frozenset(str(r[0]) for r in rows)
    referenced = tuple(str(r[1]) for r in rows if str(r[0]) == object_key)
    return guard_object_deletion(
        object_key=object_key,
        active_match_set_group_object_keys=active_keys,
        referenced_match_set_ids=referenced,
    )


async def _file_row_present(conn: AsyncConnection, file_id: str) -> bool:
    row = (
        await conn.execute(
            text(
                "SELECT 1 FROM ops.source_files "
                "WHERE source_file_id = :fid AND state <> 'hard_deleted'"
            ),
            {"fid": file_id},
        )
    ).first()
    return row is not None


def _resolve_response(
    item_id: str,
    item: Mapping[str, Any],
    action: str,
    state: str,
    outcome: str,
    affected: tuple[str, ...],
) -> ReconcileResolveResponse:
    return ReconcileResolveResponse(
        source_storage_reconcile_item_id=item_id,
        issue_type=str(item["issue_type"]),
        action=action,
        state=state,
        outcome=outcome,
        source_file_group_id=(
            str(item["source_file_group_id"]) if item["source_file_group_id"] else None
        ),
        affected_match_set_ids=affected,
        message=outcome.split(":", 1)[1] if outcome.startswith("blocked:") else None,
    )


# --- capacity preflight -----------------------------------------------------


async def compute_source_capacity(
    engine: AsyncEngine,
    *,
    capacity_limit_bytes: int | None = None,
    threshold_ratio: float = 1.0,
) -> SourceCapacityUsage:
    """Per-category storage usage usable before an upload/register (doc ~2107).

    Aggregates ``ops.source_files`` bytes by category (joined through groups),
    counting quarantined / soft-deleted bytes separately, and adds any
    unregistered (object_missing_db) bytes the latest reconcile run found. The
    retention POLICY is T-212; this is the computation + surfacing only.
    """
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
SELECT g.category AS category,
       count(*) FILTER (WHERE f.state NOT IN ('hard_deleted')) AS object_count,
       COALESCE(sum(f.size_bytes) FILTER (
         WHERE f.state IN ('available', 'validating', 'missing')), 0) AS total_bytes,
       COALESCE(sum(f.size_bytes) FILTER (WHERE f.state = 'quarantined'), 0)
         AS quarantined_bytes,
       COALESCE(sum(f.size_bytes) FILTER (WHERE f.state = 'soft_deleted'), 0)
         AS soft_deleted_bytes
  FROM ops.source_files f
  JOIN ops.source_file_groups g
    ON g.source_file_group_id = f.source_file_group_id
 WHERE f.state <> 'hard_deleted'
 GROUP BY g.category
 ORDER BY g.category
"""
                )
            )
        ).mappings().all()
        unregistered = await conn.scalar(
            text(
                """
SELECT COALESCE(sum(object_size_bytes), 0)
  FROM ops.source_storage_reconcile_items
 WHERE issue_type IN ('object_missing_db', 'registration_expired')
   AND state = 'open'
"""
            )
        )
        growth_30d = await conn.scalar(
            text(
                """
SELECT COALESCE(sum(size_bytes), 0)
  FROM ops.source_files
 WHERE state NOT IN ('hard_deleted')
   AND uploaded_at >= now() - interval '30 days'
"""
            )
        )
        # Objects a destructive_admin could currently bulk-hard-delete: registered
        # soft_deleted/quarantined files + unregistered stored objects surfaced by
        # the latest reconcile (ADR-052; advisory count only, never auto-deleted).
        eligible_files = await conn.scalar(
            text(
                """
SELECT count(*) FROM ops.source_files
 WHERE state IN ('soft_deleted', 'quarantined')
"""
            )
        )
        eligible_unregistered = await conn.scalar(
            text(
                """
SELECT count(DISTINCT object_key)
  FROM ops.source_storage_reconcile_items
 WHERE issue_type IN ('object_missing_db', 'registration_expired')
   AND state = 'open' AND object_key IS NOT NULL
"""
            )
        )

    eligible_object_count = int(eligible_files or 0) + int(eligible_unregistered or 0)

    categories = tuple(
        CategoryCapacity(
            category=str(r["category"]),
            object_count=int(r["object_count"] or 0),
            total_bytes=int(r["total_bytes"] or 0),
            quarantined_bytes=int(r["quarantined_bytes"] or 0),
            soft_deleted_bytes=int(r["soft_deleted_bytes"] or 0),
        )
        for r in rows
    )
    usage: CapacityUsage = compute_capacity_usage(
        categories,
        unregistered_bytes=int(unregistered or 0),
        growth_30d_bytes=int(growth_30d or 0),
        capacity_limit_bytes=capacity_limit_bytes,
        threshold_ratio=threshold_ratio,
    )
    return _capacity_dto(usage, eligible_object_count=eligible_object_count)


def _capacity_dto(
    usage: CapacityUsage, *, eligible_object_count: int = 0
) -> SourceCapacityUsage:
    recommendation = build_retention_recommendation(
        usage, eligible_object_count=eligible_object_count
    )
    return SourceCapacityUsage(
        categories=tuple(
            SourceCategoryCapacity(
                category=c.category,
                object_count=c.object_count,
                total_bytes=c.total_bytes,
                quarantined_bytes=c.quarantined_bytes,
                soft_deleted_bytes=c.soft_deleted_bytes,
            )
            for c in usage.categories
        ),
        total_object_count=usage.total_object_count,
        total_bytes=usage.total_bytes,
        quarantined_bytes=usage.quarantined_bytes,
        soft_deleted_bytes=usage.soft_deleted_bytes,
        unregistered_bytes=usage.unregistered_bytes,
        growth_30d_bytes=usage.growth_30d_bytes,
        capacity_limit_bytes=usage.capacity_limit_bytes,
        over_threshold=usage.over_threshold,
        retention=SourceRetentionRecommendation(
            over_threshold=recommendation.over_threshold,
            reclaimable_bytes=recommendation.reclaimable_bytes,
            eligible_object_count=recommendation.eligible_object_count,
            guidance=recommendation.guidance,
        ),
    )


# --- bulk hard-delete / restore (T-212, ADR-052) ---------------------------


async def _active_referenced_object_keys(conn: AsyncConnection) -> frozenset[str]:
    """Object keys reachable from any ACTIVE match set's groups (the 정본 guard).

    Reuses the same join as the T-204 per-item deletion guard, but returns the
    whole active-정본 key set so the bulk action can partition many candidates in
    one query. Such objects are NEVER eligible for hard-delete (ADR-052).
    """
    rows = (
        await conn.execute(
            text(
                """
SELECT DISTINCT f.object_key
  FROM ops.source_match_sets ms
  JOIN ops.source_match_set_items it
    ON it.source_match_set_id = ms.source_match_set_id
  JOIN ops.source_files f
    ON f.source_file_group_id = it.source_file_group_id
 WHERE ms.state = 'active' AND f.object_key IS NOT NULL
   AND f.state <> 'hard_deleted'
"""
            )
        )
    ).all()
    return frozenset(str(r[0]) for r in rows)


async def _backup_manifest_present(conn: AsyncConnection) -> bool:
    """Whether a completed ``db_backup`` manifest/export exists (pre-delete gate).

    A single completed backup artifact is enough evidence for the pre-delete
    safety gate (ADR-052); without one the caller must pass ``manifest_ack``.
    """
    row = (
        await conn.execute(
            text(
                """
SELECT 1 FROM ops.artifacts
 WHERE artifact_type = 'db_backup' AND state = 'completed'
 LIMIT 1
"""
            )
        )
    ).first()
    return row is not None


async def bulk_hard_delete_sources(
    engine: AsyncEngine,
    *,
    object_keys: tuple[str, ...],
    typed_confirmation: str,
    manifest_ack: bool,
    actor: str | None,
    reason: str | None = None,
    rustfs: RustfsClient | None = None,
) -> SourceBulkHardDeleteResponse:
    """Manually bulk hard-delete eligible source objects (T-212, ADR-052).

    The ONLY admin-driven hard-delete path (registered archives are never
    auto-deleted). Steps:

    1. require the exact typed confirmation (``HARD-DELETE-SOURCES``);
    2. pre-delete safety gate: a completed ``db_backup`` manifest/export must
       exist OR ``manifest_ack=true`` (explicit acknowledgement);
    3. load each candidate's registry state + active-정본 flag, then
       :func:`plan_bulk_hard_delete` partitions eligible / skipped — the
       active-정본 guard (reused from T-204) makes a live-referenced object
       never eligible, and a live ``available``/``validating``/``missing`` archive
       is skipped (registered archives are not bulk-deletable);
    4. for each eligible object: delete the RustFS object, set the registry row
       ``hard_deleted`` (or ``delete_failed`` on RustFS error), audit, and
       recompute the owning group so referencing match sets follow.
    """
    if typed_confirmation != bulk_hard_delete_confirmation():
        raise InvalidInputError(
            "bulk hard-delete에는 "
            f"typed_confirmation '{bulk_hard_delete_confirmation()}'이 필요합니다"
        )

    requested = tuple(dict.fromkeys(object_keys))  # de-dupe, keep order
    results: list[SourceHardDeleteOutcome] = []
    affected: set[str] = set()
    deleted = failed = skipped = 0

    async with engine.begin() as conn:
        safety = check_pre_delete_safety(
            backup_manifest_present=await _backup_manifest_present(conn),
            manifest_ack=manifest_ack,
        )
        if not safety.allowed:
            raise ConflictError(safety.reason)

        active_keys = await _active_referenced_object_keys(conn)
        candidates = await _load_hard_delete_candidates(conn, requested, active_keys)
        plan: BulkHardDeletePlan = plan_bulk_hard_delete(candidates)

        eligible_keys = {e.object_key for e in plan.eligible}
        # Anything requested but not found in the registry / reconcile facts.
        known_keys = {c.object_key for c in candidates}
        for key in requested:
            if key not in known_keys:
                skipped += 1
                results.append(
                    SourceHardDeleteOutcome(
                        object_key=key,
                        outcome="skipped_not_found",
                        reason="등록/미등록 어느 facts에도 없는 object_key",
                    )
                )

        for verdict in plan.skipped:
            skipped += 1
            results.append(
                SourceHardDeleteOutcome(
                    object_key=verdict.object_key,
                    source_file_id=verdict.source_file_id,
                    outcome="skipped_ineligible",
                    reason=verdict.reason,
                )
            )

        by_key = {c.object_key: c for c in candidates}
        for verdict in plan.eligible:
            if verdict.object_key not in eligible_keys:  # defensive
                continue
            cand = by_key[verdict.object_key]
            rustfs_error: str | None = None
            if rustfs is not None:
                try:
                    await rustfs.delete_object(verdict.object_key)
                except Exception as exc:  # storage failure → delete_failed
                    rustfs_error = str(exc)
                    _LOGGER.warning(
                        "bulk hard-delete RustFS delete failed",
                        extra={"key": verdict.object_key},
                    )
            new_state = "delete_failed" if rustfs_error else "hard_deleted"
            group_id = await _hard_delete_finalize(
                conn,
                source_file_id=cand.source_file_id,
                state=new_state,
            )
            if group_id:
                r = await recompute_group_aggregates(
                    conn, group_id, trigger="bulk_hard_delete"
                )
                affected.update(r.affected_match_set_ids)
            if rustfs_error:
                failed += 1
                results.append(
                    SourceHardDeleteOutcome(
                        object_key=verdict.object_key,
                        source_file_id=cand.source_file_id,
                        outcome="delete_failed",
                        reason=rustfs_error,
                    )
                )
            else:
                deleted += 1
                results.append(
                    SourceHardDeleteOutcome(
                        object_key=verdict.object_key,
                        source_file_id=cand.source_file_id,
                        outcome="hard_deleted",
                    )
                )
            await _audit_reconcile(
                conn,
                action=SOURCE_HARD_DELETE,
                resource_id=cand.source_file_id or verdict.object_key,
                actor=actor,
                outcome=new_state,
                payload={
                    "object_key": verdict.object_key,
                    "source_file_id": cand.source_file_id,
                    "manifest_ack": manifest_ack,
                    "reason": reason,
                },
            )

    for _ in range(deleted):
        record_source_hard_delete(outcome="hard_deleted")
    for _ in range(failed):
        record_source_hard_delete(outcome="delete_failed")
    for _ in range(skipped):
        record_source_hard_delete(outcome="skipped")

    return SourceBulkHardDeleteResponse(
        requested_count=len(requested),
        hard_deleted_count=deleted,
        delete_failed_count=failed,
        skipped_count=skipped,
        results=tuple(results),
        affected_match_set_ids=tuple(sorted(affected)),
    )


async def _load_hard_delete_candidates(
    conn: AsyncConnection,
    object_keys: tuple[str, ...],
    active_keys: frozenset[str],
) -> tuple[HardDeleteCandidateFact, ...]:
    """Build candidate facts for the requested keys (registered + unregistered).

    A key resolves to its live (non-hard_deleted) ``ops.source_files`` row when
    one exists; otherwise to the latest open reconcile item that classified it as
    an unregistered stored object. ``active_referenced`` is the reused T-204
    active-정본 guard input.
    """
    if not object_keys:
        return ()
    keys = list(object_keys)
    file_rows = (
        await conn.execute(
            text(
                """
SELECT object_key, source_file_id, state
  FROM ops.source_files
 WHERE object_key = ANY(:keys) AND state <> 'hard_deleted'
"""
            ).bindparams(bindparam("keys", expanding=True)),
            {"keys": keys},
        )
    ).mappings().all()
    by_key: dict[str, HardDeleteCandidateFact] = {}
    for r in file_rows:
        key = str(r["object_key"])
        by_key[key] = HardDeleteCandidateFact(
            object_key=key,
            source_file_id=str(r["source_file_id"]),
            state=str(r["state"]),
            active_referenced=key in active_keys,
        )
    # Keys with no live registry row: classify from the latest open reconcile item.
    missing = [k for k in keys if k not in by_key]
    if missing:
        unreg_rows = (
            await conn.execute(
                text(
                    """
SELECT DISTINCT ON (object_key) object_key, issue_type
  FROM ops.source_storage_reconcile_items
 WHERE object_key = ANY(:keys) AND state = 'open'
   AND issue_type IN ('object_missing_db', 'registration_expired')
 ORDER BY object_key, created_at DESC
"""
                ).bindparams(bindparam("keys", expanding=True)),
                {"keys": missing},
            )
        ).mappings().all()
        for r in unreg_rows:
            key = str(r["object_key"])
            by_key[key] = HardDeleteCandidateFact(
                object_key=key,
                source_file_id=None,
                state=None,
                issue_type=str(r["issue_type"]),
                active_referenced=key in active_keys,
            )
    return tuple(by_key[k] for k in keys if k in by_key)


async def _hard_delete_finalize(
    conn: AsyncConnection,
    *,
    source_file_id: str | None,
    state: str,
) -> str | None:
    """Set a registry row to hard_deleted/delete_failed; return its group id.

    Unregistered objects (no ``source_file_id``) have no registry row to update,
    so the RustFS object is removed and nothing further is recomputed.
    """
    if not source_file_id:
        return None
    row = (
        await conn.execute(
            text(
                """
UPDATE ops.source_files
   SET state = :state, deleted_at = now()
 WHERE source_file_id = :fid AND state <> 'hard_deleted'
RETURNING source_file_group_id
"""
            ),
            {"fid": source_file_id, "state": state},
        )
    ).first()
    return str(row[0]) if row else None


# --- read helpers + audit ---------------------------------------------------

_RUN_SELECT = """
SELECT source_storage_reconcile_run_id, prefix, mode, state, started_at,
       finished_at, scanned_objects, scanned_db_files, rehashed_objects,
       skipped_rehash_objects, mismatch_count, resolved_count, cursor, log_tail,
       summary
  FROM ops.source_storage_reconcile_runs
"""

_ITEM_SELECT = """
SELECT source_storage_reconcile_item_id, source_storage_reconcile_run_id,
       issue_type, source_file_group_id, source_file_id, object_key, db_sha256,
       object_sha256, db_size_bytes, object_size_bytes, db_etag, object_etag,
       severity, state, resolution_action, resolved_by, resolved_at, details
  FROM ops.source_storage_reconcile_items
"""


def _run_dto(row: Mapping[str, Any]) -> SourceReconcileRun:
    return SourceReconcileRun(
        source_storage_reconcile_run_id=str(row["source_storage_reconcile_run_id"]),
        prefix=str(row["prefix"]),
        mode=row["mode"],
        state=row["state"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        scanned_objects=int(row["scanned_objects"] or 0),
        scanned_db_files=int(row["scanned_db_files"] or 0),
        rehashed_objects=int(row["rehashed_objects"] or 0),
        skipped_rehash_objects=int(row["skipped_rehash_objects"] or 0),
        mismatch_count=int(row["mismatch_count"] or 0),
        resolved_count=int(row["resolved_count"] or 0),
        cursor=dict(row.get("cursor") or {}),
        log_tail=row.get("log_tail"),
        summary=dict(row.get("summary") or {}),
    )


def _item_dto(row: Mapping[str, Any]) -> SourceReconcileItem:
    return SourceReconcileItem(
        source_storage_reconcile_item_id=str(row["source_storage_reconcile_item_id"]),
        source_storage_reconcile_run_id=str(row["source_storage_reconcile_run_id"]),
        issue_type=row["issue_type"],
        source_file_group_id=(
            str(row["source_file_group_id"]) if row["source_file_group_id"] else None
        ),
        source_file_id=str(row["source_file_id"]) if row["source_file_id"] else None,
        object_key=row.get("object_key"),
        db_sha256=row.get("db_sha256"),
        object_sha256=row.get("object_sha256"),
        db_size_bytes=row.get("db_size_bytes"),
        object_size_bytes=row.get("object_size_bytes"),
        db_etag=row.get("db_etag"),
        object_etag=row.get("object_etag"),
        severity=row["severity"],
        state=row["state"],
        resolution_action=row.get("resolution_action"),
        resolved_by=row.get("resolved_by"),
        resolved_at=row.get("resolved_at"),
        details=dict(row.get("details") or {}),
    )


async def get_reconcile_run(engine: AsyncEngine, run_id: str) -> SourceReconcileRun:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(_RUN_SELECT + " WHERE source_storage_reconcile_run_id = :rid"),
                {"rid": run_id},
            )
        ).mappings().first()
    if row is None:
        raise NotFoundError(f"reconcile run not found: {run_id}")
    return _run_dto(dict(row))


async def list_reconcile_runs(
    engine: AsyncEngine, *, limit: int = 50
) -> tuple[SourceReconcileRun, ...]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(_RUN_SELECT + " ORDER BY started_at DESC LIMIT :limit"),
                {"limit": limit},
            )
        ).mappings().all()
    return tuple(_run_dto(dict(r)) for r in rows)


async def list_reconcile_items(
    engine: AsyncEngine,
    run_id: str,
    *,
    issue_type: str | None = None,
    state: str | None = None,
    limit: int = 500,
) -> tuple[SourceReconcileItem, ...]:
    clauses = ["source_storage_reconcile_run_id = :rid"]
    params: dict[str, Any] = {"rid": run_id, "limit": limit}
    if issue_type is not None:
        clauses.append("issue_type = :issue_type")
        params["issue_type"] = issue_type
    if state is not None:
        clauses.append("state = :state")
        params["state"] = state
    where = " WHERE " + " AND ".join(clauses)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(_ITEM_SELECT + where + " ORDER BY severity DESC, issue_type LIMIT :limit"),
                params,
            )
        ).mappings().all()
    return tuple(_item_dto(dict(r)) for r in rows)


async def _audit_reconcile(
    conn: AsyncConnection,
    *,
    action: str,
    resource_id: str,
    actor: str | None,
    outcome: str,
    payload: dict[str, Any],
) -> None:
    await insert_source_audit_event(
        conn,
        action=action,
        outcome=outcome,
        actor_id=actor,
        resource_type="source_storage_reconcile",
        resource_id=resource_id,
        payload=payload,
    )
