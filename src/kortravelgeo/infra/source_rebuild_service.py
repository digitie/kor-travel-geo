"""DB + RustFS glue for ``rebuild-db`` and rollback match-set swap (T-205b).

Companion to ``infra/source_match_set_service.py`` (T-205a). This module:

* assembles the ``full_load_batch`` payload the EXISTING loader DAG consumes
  from a ``validated``/``active`` match set's groups — the rebuild "bridge"
  (replacing the removed ``build_full_load_source_set_plan`` entry point);
* runs the **pre-load source-archive integrity gate** (re-verify each group's
  RustFS objects' ``sha256``/``size``/presence + ``group_sha256`` against the
  registry) BEFORE any child loader is enqueued; on mismatch it transitions the
  failing groups to ``quarantined`` and propagates via
  ``recompute_group_aggregates`` (active → ``integrity_alert``, non-active
  ``validated`` → ``invalid``);
* force-closes stale prior rebuild jobs (heartbeat timeout) and re-inits staging;
* records ``ops.dataset_snapshots.source_match_set_id`` (정본 FK) on success;
* performs the rollback atomic match-set swap.

The pure decisions (integrity gate, forced-promotion gate, rollback target
resolution, stale-job detection) live in ``core.source_rebuild`` and are reused
here — none is reimplemented. This module never imports the ``api`` JobQueue
(layered-architecture contract): the endpoint owns the lock + enqueue and calls
these methods.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.source_categories import category_by_code
from kortravelgeo.core.source_events import (
    SOURCE_FORCED_PROMOTION,
    SOURCE_REBUILD_DB,
)
from kortravelgeo.core.source_rebuild import (
    GroupArchiveCheck,
    IntegrityGateDecision,
    RebuildStartFacts,
    RollbackIntegrityFacts,
    RollbackTargetDecision,
    RollbackTargetFacts,
    RunningJobFacts,
    StaleJobDecision,
    decide_integrity_gate,
    decide_rebuild_start,
    decide_rollback_target,
    decide_stale_jobs,
    recompute_rollback_integrity_alert,
)
from kortravelgeo.exceptions import ConflictError, InvalidInputError, NotFoundError
from kortravelgeo.infra.concurrency import AdvisoryLockKey, AdvisoryLockNamespace
from kortravelgeo.infra.source_group_service import recompute_group_aggregates

#: How a match set category maps onto the existing loader job kind + the
#: filesystem subdirectory the loader expects the materialized archive under.
#: Only the build categories that the legacy ``full_load_batch`` DAG handles are
#: bridged; optional validation/enrichment categories are loaded by
#: ``run-validation`` (T-205b run-validation is out of this slice's scope).
_CATEGORY_TO_LOAD_KIND: dict[str, str] = {
    "roadname_hangul_full": "juso_text_load",
    "locsum_full": "locsum_load",
    "navi_full": "navi_load",
    "electronic_map_full": "shp_polygons_load",
    "roadaddr_entrance_full": "roadaddr_entrance_load",
    "zone_shape_full": "sppn_makarea_load",
}

#: Default heartbeat timeout for stale rebuild-job detection (seconds).
DEFAULT_REBUILD_HEARTBEAT_TIMEOUT_S = 900.0


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))


@dataclass(frozen=True)
class RebuildGroupRef:
    """One build-category group the rebuild will materialize + load."""

    category: str
    source_file_group_id: str
    group_sha256: str | None
    user_yyyymm: str | None
    effective_yyyymm: str | None
    load_kind: str
    object_keys: tuple[str, ...]
    file_ids: tuple[str, ...]
    storage_uris: tuple[str, ...]


@dataclass(frozen=True)
class RebuildPlan:
    """Assembled rebuild inputs: the group refs + the full_load_batch payload."""

    source_match_set_id: str
    groups: tuple[RebuildGroupRef, ...]
    batch_payload: dict[str, Any]


class SourceRebuildService:
    """Raw-SQL + RustFS glue for ``rebuild-db`` and rollback (T-205b)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    # --- lock key ----------------------------------------------------------

    @staticmethod
    def rebuild_lock_key() -> AdvisoryLockKey:
        """The global ``source_rebuild_db`` advisory lock (doc line ~1417/1555).

        Shared serialization domain with legacy ``full_load_batch`` /
        ``mv_refresh`` / restore hot-swap: the rebuild handler holds this for the
        download/integrity/enqueue phase; the existing serial JobQueue +
        per-stage locks serialize the actual COPY/MV steps.
        """
        return AdvisoryLockKey.global_key(AdvisoryLockNamespace.SOURCE_REBUILD_DB)

    # --- start precondition + stale-job sweep ------------------------------

    async def prepare_rebuild(
        self,
        source_match_set_id: str,
        *,
        heartbeat_timeout_s: float = DEFAULT_REBUILD_HEARTBEAT_TIMEOUT_S,
    ) -> tuple[RebuildPlan, StaleJobDecision]:
        """Validate the match set, sweep stale jobs, and assemble the batch plan.

        Raises ``NotFoundError`` for an unknown set, ``ConflictError`` when the
        start precondition fails or a LIVE rebuild job is still running, and
        ``InvalidInputError`` when no bridgeable build category is present.
        """
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT state, integrity_alert, source_set_hash "
                        "FROM ops.source_match_sets "
                        "WHERE source_match_set_id = :id FOR UPDATE"
                    ),
                    {"id": source_match_set_id},
                )
            ).mappings().first()
            if row is None:
                raise NotFoundError(
                    f"source match set not found: {source_match_set_id}"
                )

            groups = await self._build_group_refs(conn, source_match_set_id)
            all_available = await self._all_groups_available(conn, source_match_set_id)
            start = decide_rebuild_start(
                RebuildStartFacts(
                    state=str(row["state"]),
                    integrity_alert=bool(row["integrity_alert"]),
                    source_set_hash=row["source_set_hash"],
                    all_groups_available=all_available,
                )
            )
            if not start.ok:
                raise ConflictError("; ".join(start.reasons))
            if not groups:
                raise InvalidInputError(
                    "match set has no bridgeable build category for rebuild-db"
                )

            stale = await self._sweep_stale_jobs(
                conn,
                source_match_set_id,
                heartbeat_timeout_s=heartbeat_timeout_s,
            )
            if stale.live_blocking_job_id is not None:
                raise ConflictError(
                    "a rebuild job is already running for this match set "
                    f"(job_id={stale.live_blocking_job_id})"
                )

        plan = self._assemble_plan(source_match_set_id, groups)
        return plan, stale

    async def _sweep_stale_jobs(
        self,
        conn: AsyncConnection,
        source_match_set_id: str,
        *,
        heartbeat_timeout_s: float,
    ) -> StaleJobDecision:
        rows = (
            await conn.execute(
                text(
                    """
SELECT job_id, state,
       EXTRACT(EPOCH FROM (now() - heartbeat_at))::float8 AS secs_since_heartbeat
  FROM load_jobs
 WHERE kind = 'full_load_batch'
   AND state = 'running'
   AND payload ->> 'source_match_set_id' = :msid
"""
                ),
                {"msid": source_match_set_id},
            )
        ).mappings().all()
        decision = decide_stale_jobs(
            tuple(
                RunningJobFacts(
                    job_id=str(r["job_id"]),
                    state=str(r["state"]),
                    seconds_since_heartbeat=(
                        float(r["secs_since_heartbeat"])
                        if r["secs_since_heartbeat"] is not None
                        else None
                    ),
                )
                for r in rows
            ),
            heartbeat_timeout_s=heartbeat_timeout_s,
        )
        for job_id in decision.stale_job_ids:
            # Force-close the stale batch root + its children idempotently; the
            # staging directory is keyed by job_id so re-init is implicit.
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'failed',
       current_stage = 'failed',
       error_message = COALESCE(error_message || E'\n', '')
                       || 'rebuild stale: heartbeat timeout, force-closed',
       finished_at = now(),
       heartbeat_at = now()
 WHERE (job_id = :job_id OR load_batch_id = :job_id)
   AND state IN ('queued','running')
"""
                ),
                {"job_id": job_id},
            )
        return decision

    # --- group refs + batch payload assembly (the bridge) ------------------

    async def _build_group_refs(
        self, conn: AsyncConnection, source_match_set_id: str
    ) -> tuple[RebuildGroupRef, ...]:
        rows = (
            await conn.execute(
                text(
                    """
SELECT it.category, it.source_file_group_id, it.effective_yyyymm, it.omitted,
       it.load_order, g.group_sha256, g.user_yyyymm
  FROM ops.source_match_set_items it
  JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id
   AND it.omitted = false
 ORDER BY it.load_order NULLS LAST, it.category
"""
                ),
                {"id": source_match_set_id},
            )
        ).mappings().all()
        refs: list[RebuildGroupRef] = []
        for r in rows:
            category = str(r["category"])
            load_kind = _CATEGORY_TO_LOAD_KIND.get(category)
            if load_kind is None:
                # Optional validation/enrichment category — not part of the
                # full_load_batch DAG (handled by run-validation, out of scope).
                continue
            gid = str(r["source_file_group_id"])
            files = (
                await conn.execute(
                    text(
                        """
SELECT source_file_id, object_key, storage_uri
  FROM ops.source_files
 WHERE source_file_group_id = :gid
   AND state NOT IN ('hard_deleted','soft_deleted')
 ORDER BY part_key
"""
                    ),
                    {"gid": gid},
                )
            ).mappings().all()
            refs.append(
                RebuildGroupRef(
                    category=category,
                    source_file_group_id=gid,
                    group_sha256=r["group_sha256"],
                    user_yyyymm=r["user_yyyymm"],
                    effective_yyyymm=r["effective_yyyymm"],
                    load_kind=load_kind,
                    object_keys=tuple(
                        str(f["object_key"]) for f in files if f["object_key"]
                    ),
                    file_ids=tuple(str(f["source_file_id"]) for f in files),
                    storage_uris=tuple(
                        str(f["storage_uri"]) for f in files if f["storage_uri"]
                    ),
                )
            )
        return tuple(refs)

    def _assemble_plan(
        self, source_match_set_id: str, groups: tuple[RebuildGroupRef, ...]
    ) -> RebuildPlan:
        """Build the ``full_load_batch`` payload the existing DAG consumes.

        Each build group becomes a child ``{"kind": <load_kind>, "payload":
        {...}}`` — the same structure ``batch_children`` already accepts. The
        ``path`` is the materialized staging directory the loader reads; the root
        payload carries ``source_match_set_id`` + per-category provenance (doc
        step 7, ~1548).
        """
        staging_root = self.staging_dir(source_match_set_id)
        children: list[dict[str, Any]] = []
        source_set: dict[str, Any] = {}
        for ref in groups:
            yyyymm = ref.effective_yyyymm or ref.user_yyyymm
            child_payload: dict[str, Any] = {
                "path": str(self.category_staging_dir(staging_root, ref.category)),
                "source_yyyymm": yyyymm,
                "source_file_group_id": ref.source_file_group_id,
                "source_file_ids": list(ref.file_ids),
                "group_sha256": ref.group_sha256,
                "storage_uris": list(ref.storage_uris),
            }
            children.append({"kind": ref.load_kind, "payload": child_payload})
            source_set[ref.category] = {
                "source_file_group_id": ref.source_file_group_id,
                "group_sha256": ref.group_sha256,
                "user_yyyymm": ref.user_yyyymm,
                "effective_yyyymm": ref.effective_yyyymm,
            }
        batch_payload: dict[str, Any] = {
            "children": children,
            "source_match_set_id": source_match_set_id,
            "source_set": source_set,
            "staging_dir": str(staging_root),
        }
        return RebuildPlan(
            source_match_set_id=source_match_set_id,
            groups=groups,
            batch_payload=batch_payload,
        )

    @staticmethod
    def staging_dir(source_match_set_id: str) -> Path:
        return Path("rebuild_staging") / source_match_set_id

    @staticmethod
    def category_staging_dir(staging_root: Path, category: str) -> Path:
        return staging_root / category

    # --- pre-load source-archive integrity gate ----------------------------

    def integrity_gate(
        self, checks: tuple[GroupArchiveCheck, ...]
    ) -> IntegrityGateDecision:
        """Run the pure pre-load integrity gate (doc line ~1544)."""
        return decide_integrity_gate(checks)

    async def quarantine_failed_groups(
        self,
        source_match_set_id: str,
        failed_group_ids: tuple[str, ...],
        *,
        actor: str | None,
        reason: str,
    ) -> tuple[str, ...]:
        """Quarantine each gated group + propagate to referencing match sets.

        Mirrors the doc: failing groups go ``quarantined``; their non-deleted
        children go ``quarantined``; then ``recompute_group_aggregates`` folds
        that into the group state and propagates (active set → ``integrity_alert``,
        non-active ``validated`` → ``invalid``, pre-hash stays). Returns the
        affected match set ids for the response. No child load jobs are created.
        """
        affected: set[str] = set()
        async with self.engine.begin() as conn:
            for gid in failed_group_ids:
                await conn.execute(
                    text(
                        """
UPDATE ops.source_files
   SET state = 'quarantined', validation_state = 'failed'
 WHERE source_file_group_id = :gid
   AND state NOT IN ('hard_deleted','soft_deleted')
"""
                    ),
                    {"gid": gid},
                )
                await conn.execute(
                    text(
                        """
UPDATE ops.source_file_groups
   SET state = 'quarantined', validation_state = 'failed', updated_at = now()
 WHERE source_file_group_id = :gid
"""
                    ),
                    {"gid": gid},
                )
                recompute = await recompute_group_aggregates(
                    conn,
                    gid,
                    trigger="rebuild_integrity_gate",
                    structure_validation_state="failed",
                )
                affected.update(recompute.affected_match_set_ids)
            await self._audit(
                conn,
                action=SOURCE_REBUILD_DB,
                actor=actor,
                resource_id=source_match_set_id,
                outcome="integrity_gate_failed",
                payload={
                    "failed_group_ids": list(failed_group_ids),
                    "reason": reason,
                },
            )
        return tuple(sorted(affected))

    # --- snapshot FK + audit on success ------------------------------------

    async def record_rebuild_audit(
        self,
        source_match_set_id: str,
        *,
        actor: str | None,
        outcome: str,
        job_id: str | None,
        load_batch_id: str | None,
        forced_promotion: bool,
        reason: str | None,
    ) -> None:
        async with self.engine.begin() as conn:
            await self._audit(
                conn,
                action=SOURCE_REBUILD_DB,
                actor=actor,
                resource_id=source_match_set_id,
                outcome=outcome,
                job_id=job_id,
                payload={
                    "load_batch_id": load_batch_id,
                    "forced_promotion": forced_promotion,
                    "reason": reason,
                },
            )
            if forced_promotion:
                await self._audit(
                    conn,
                    action=SOURCE_FORCED_PROMOTION,
                    actor=actor,
                    resource_id=source_match_set_id,
                    outcome=outcome,
                    job_id=job_id,
                    payload={
                        "load_batch_id": load_batch_id,
                        "reason": reason,
                        "bypassed": "consistency_error_only",
                    },
                )

    # --- rollback atomic match-set swap ------------------------------------

    async def rollback_swap(
        self,
        serving_release_id: str,
        *,
        actor: str | None,
        reason: str | None,
    ) -> tuple[RollbackTargetDecision, bool]:
        """Resolve + apply the rollback's match-set side (doc ~818/1530, #18).

        Under the ``SOURCE_MATCH_ACTIVATE`` advisory lock in ONE transaction:
        resolve the target snapshot's ``source_match_set_id``; if present, retire
        the current active match set and restore the target to ``active`` (the
        same one-active invariant as activate), recomputing the target's
        ``integrity_alert`` from a pre-rollback DB quick reconcile of its groups.
        Legacy snapshots (no FK) make NO match-set change. Returns the decision +
        the recomputed ``integrity_alert``.
        """
        lock = AdvisoryLockKey.global_key(AdvisoryLockNamespace.SOURCE_MATCH_ACTIVATE)
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock.as_int()}
            )
            release = (
                await conn.execute(
                    text(
                        """
SELECT r.serving_release_id, r.dataset_snapshot_id, r.state, s.source_match_set_id
  FROM ops.serving_releases r
  JOIN ops.dataset_snapshots s ON s.dataset_snapshot_id = r.dataset_snapshot_id
 WHERE r.serving_release_id = :rid
"""
                    ),
                    {"rid": serving_release_id},
                )
            ).mappings().first()
            if release is None:
                raise NotFoundError(f"serving release not found: {serving_release_id}")

            current_active = (
                await conn.execute(
                    text(
                        "SELECT source_match_set_id FROM ops.source_match_sets "
                        "WHERE state = 'active' LIMIT 1 FOR UPDATE"
                    )
                )
            ).first()
            decision = decide_rollback_target(
                RollbackTargetFacts(
                    release_id=str(release["serving_release_id"]),
                    snapshot_id=str(release["dataset_snapshot_id"]),
                    release_state=str(release["state"]),
                    target_source_match_set_id=(
                        str(release["source_match_set_id"])
                        if release["source_match_set_id"]
                        else None
                    ),
                    current_active_match_set_id=(
                        str(current_active[0]) if current_active else None
                    ),
                )
            )
            if not decision.ok:
                raise ConflictError("; ".join(decision.reasons))

            integrity_alert = False
            if decision.mode == "match_set_swap":
                integrity_alert = await self._apply_match_set_swap(
                    conn, decision
                )
            await self._audit(
                conn,
                action="serving_release.rollback",
                actor=actor,
                resource_id=serving_release_id,
                outcome=decision.mode,
                resource_type="serving_release",
                payload={
                    "mode": decision.mode,
                    "activated_match_set_id": decision.activate_match_set_id,
                    "retired_match_set_id": decision.retire_match_set_id,
                    "target_integrity_alert": integrity_alert,
                    "reason": reason,
                },
            )
        return decision, integrity_alert

    async def _apply_match_set_swap(
        self, conn: AsyncConnection, decision: RollbackTargetDecision
    ) -> bool:
        target_id = decision.activate_match_set_id
        assert target_id is not None  # mode == match_set_swap guarantees this
        if decision.retire_match_set_id is not None:
            await conn.execute(
                text(
                    "UPDATE ops.source_match_sets SET state = 'retired', "
                    "updated_at = now() WHERE source_match_set_id = :id"
                ),
                {"id": decision.retire_match_set_id},
            )
        # Pre-rollback source quick reconcile: derive integrity_alert from the
        # registry state of the target's referenced groups.
        facts = await self._rollback_integrity_facts(conn, target_id)
        integrity_alert = recompute_rollback_integrity_alert(facts)
        await conn.execute(
            _json_text(
                """
UPDATE ops.source_match_sets
   SET state = 'active',
       integrity_alert = :alert,
       integrity_alert_at = CASE WHEN :alert THEN now() ELSE NULL END,
       integrity_alert_detail = CASE WHEN :alert THEN :detail
                                     ELSE '{}'::jsonb END,
       updated_at = now()
 WHERE source_match_set_id = :id
""",
                "detail",
            ),
            {
                "id": target_id,
                "alert": integrity_alert,
                "detail": {
                    "trigger": "rollback_quick_reconcile",
                    "unavailable_group_ids": list(facts.unavailable_group_ids),
                    "at": datetime.now(UTC).isoformat(),
                },
            },
        )
        return integrity_alert

    async def _rollback_integrity_facts(
        self, conn: AsyncConnection, match_set_id: str
    ) -> RollbackIntegrityFacts:
        rows = (
            await conn.execute(
                text(
                    """
SELECT it.source_file_group_id, g.state AS group_state
  FROM ops.source_match_set_items it
  JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id AND it.omitted = false
"""
                ),
                {"id": match_set_id},
            )
        ).mappings().all()
        unavailable = tuple(
            str(r["source_file_group_id"])
            for r in rows
            if r["group_state"] != "available"
        )
        return RollbackIntegrityFacts(
            all_groups_available=not unavailable and bool(rows),
            unavailable_group_ids=unavailable,
        )

    # --- helpers -----------------------------------------------------------

    async def _all_groups_available(
        self, conn: AsyncConnection, source_match_set_id: str
    ) -> bool:
        row = (
            await conn.execute(
                text(
                    """
SELECT bool_and(g.state = 'available') AS all_available, count(*) AS n
  FROM ops.source_match_set_items it
  JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id AND it.omitted = false
"""
                ),
                {"id": source_match_set_id},
            )
        ).mappings().first()
        return bool(row and row["n"] and row["all_available"])

    async def _audit(
        self,
        conn: AsyncConnection,
        *,
        action: str,
        actor: str | None,
        resource_id: str,
        outcome: str,
        payload: dict[str, Any],
        job_id: str | None = None,
        resource_type: str = "source_match_set",
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            _json_text(
                """
INSERT INTO ops.audit_events
  (audit_event_id, actor_type, actor_id, action, resource_type, resource_id,
   job_id, outcome, payload_redacted)
VALUES
  (:audit_event_id, 'ui', :actor_id, :action, :resource_type, :resource_id,
   :job_id, :outcome, :payload)
""",
                "payload",
            ),
            {
                "audit_event_id": str(uuid4()),
                "actor_id": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "job_id": job_id,
                "outcome": outcome,
                "payload": {**payload, "at": now},
            },
        )


def category_load_kind(category: str) -> str | None:
    """Public accessor: the loader job kind for a build category (or ``None``)."""
    if category not in category_by_code:
        return None
    return _CATEGORY_TO_LOAD_KIND.get(category)


def _coerce_source_match_set_id(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("source_match_set_id")
    return str(value) if isinstance(value, str) and value else None
