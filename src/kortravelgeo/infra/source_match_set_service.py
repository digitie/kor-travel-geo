"""Source match set repository + service (T-205a).

Raw-SQL repository (``admin_repo`` style) for ``ops.source_match_sets`` /
``ops.source_match_set_items`` implementing the create / validate / activate /
retire / list / get slice of T-109. The pure decision logic lives in
``core.source_match_set`` (validate state-split, activate precondition + swap
sequence, item invariants) and the canonical ``source_set_hash`` is reused from
``core.source_match_propagation`` — neither is reimplemented here.

State-transition rules, the validate state-split, and the activate atomic swap
follow ``docs/t109-backup-source-upload-management.md`` "ops.source_match_sets"
(lines ~804-818). The ``integrity_alert``/``invalid``→``revalidatable`` PROPAGATION
is owned by ``recompute_group_aggregates`` (T-203b); this service only *consumes*
those states via validate/activate/retire.

DEFERRED to T-205b (not implemented here): ``rebuild-db`` loader bridge, rollback
atomic swap, ``dataset_snapshots.source_match_set_id`` write-on-rebuild, the
consistency ERROR gate / ``forced_promotion``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.source_categories import category_by_code
from kortravelgeo.core.source_events import (
    SOURCE_MATCH_SET_ACTIVATE,
    SOURCE_MATCH_SET_CREATE,
    SOURCE_MATCH_SET_RETIRE,
    SOURCE_MATCH_SET_VALIDATE,
)
from kortravelgeo.core.source_match_propagation import (
    MatchSetItemFacts,
    compute_source_set_hash,
)
from kortravelgeo.core.source_match_set import (
    ActivateFacts,
    MatchSetItemSpec,
    RetireDecision,
    ValidateCoverage,
    ValidateFacts,
    aggregate_yyyymm,
    decide_activate,
    decide_retire,
    decide_validate,
    validate_item_invariants,
)
from kortravelgeo.dto.source import (
    SourceMatchSet,
    SourceMatchSetActivateResponse,
    SourceMatchSetCreateRequest,
    SourceMatchSetDetail,
    SourceMatchSetItem,
    SourceMatchSetRetireResponse,
    SourceMatchSetValidateResponse,
)
from kortravelgeo.exceptions import ConflictError, InvalidInputError, NotFoundError
from kortravelgeo.infra.concurrency import AdvisoryLockKey, AdvisoryLockNamespace

#: Categories each profile requires to be present (or explicitly omitted) at
#: validate (doc "load profile" table, lines ~150-157). ``serving_minimal`` is the
#: 4 build categories; ``serving_recommended`` adds the 2 recommended ones.
_PROFILE_REQUIRED_CATEGORIES: dict[str, frozenset[str]] = {
    "serving_minimal": frozenset(
        {
            "roadname_hangul_full",
            "locsum_full",
            "navi_full",
            "electronic_map_full",
        }
    ),
    "serving_recommended": frozenset(
        {
            "roadname_hangul_full",
            "locsum_full",
            "navi_full",
            "electronic_map_full",
            "roadaddr_entrance_full",
            "zone_shape_full",
        }
    ),
    "custom": frozenset(),
}


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))


def _match_set_row(row: Mapping[str, Any]) -> SourceMatchSet:
    return SourceMatchSet(
        source_match_set_id=str(row["source_match_set_id"]),
        name=str(row["name"]),
        description=row.get("description"),
        profile=str(row["profile"]),
        state=str(row["state"]),
        source_set_hash=row.get("source_set_hash"),
        mixed_yyyymm=bool(row.get("mixed_yyyymm")),
        yyyymm_by_category=dict(row.get("yyyymm_by_category") or {}),
        omitted_optional=dict(row.get("omitted_optional") or {}),
        created_by=row.get("created_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        validated_at=row.get("validated_at"),
        last_load_job_id=row.get("last_load_job_id"),
        last_consistency_report_id=row.get("last_consistency_report_id"),
        metadata=dict(row.get("metadata") or {}),
        integrity_alert=bool(row.get("integrity_alert")),
        integrity_alert_at=row.get("integrity_alert_at"),
        integrity_alert_detail=dict(row.get("integrity_alert_detail") or {}),
    )


def _item_row(row: Mapping[str, Any]) -> SourceMatchSetItem:
    return SourceMatchSetItem(
        source_match_set_item_id=str(row["source_match_set_item_id"]),
        source_match_set_id=str(row["source_match_set_id"]),
        category=str(row["category"]),
        role=str(row["role"]),
        source_file_group_id=str(row["source_file_group_id"])
        if row.get("source_file_group_id")
        else None,
        required=bool(row.get("required")),
        omitted=bool(row.get("omitted")),
        omitted_reason=row.get("omitted_reason"),
        effective_yyyymm=row.get("effective_yyyymm"),
        validation_enabled=bool(row.get("validation_enabled", True)),
        load_order=row.get("load_order"),
        metadata=dict(row.get("metadata") or {}),
    )


_MATCH_SET_COLUMNS = """
source_match_set_id, name, description, profile, state, source_set_hash,
mixed_yyyymm, yyyymm_by_category, omitted_optional, created_by, created_at,
updated_at, validated_at, last_load_job_id, last_consistency_report_id,
metadata, integrity_alert, integrity_alert_at, integrity_alert_detail
"""


class SourceMatchSetRepository:
    """Raw-SQL repository for source match sets (T-205a)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    # --- reads -------------------------------------------------------------

    async def list_match_sets(
        self, *, state: str | None = None, limit: int = 100
    ) -> tuple[SourceMatchSet, ...]:
        clause = "WHERE state = :state" if state else ""
        params: dict[str, Any] = {"limit": limit}
        if state:
            params["state"] = state
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        f"SELECT {_MATCH_SET_COLUMNS} FROM ops.source_match_sets "
                        f"{clause} ORDER BY created_at DESC LIMIT :limit"
                    ),
                    params,
                )
            ).mappings().all()
        return tuple(_match_set_row(dict(r)) for r in rows)

    async def get_match_set(self, source_match_set_id: str) -> SourceMatchSetDetail:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        f"SELECT {_MATCH_SET_COLUMNS} FROM ops.source_match_sets "
                        "WHERE source_match_set_id = :id"
                    ),
                    {"id": source_match_set_id},
                )
            ).mappings().first()
            if row is None:
                raise NotFoundError(f"source match set not found: {source_match_set_id}")
            items = await self._load_items(conn, source_match_set_id)
        return SourceMatchSetDetail(match_set=_match_set_row(dict(row)), items=items)

    async def _load_items(
        self, conn: AsyncConnection, source_match_set_id: str
    ) -> tuple[SourceMatchSetItem, ...]:
        rows = (
            await conn.execute(
                text(
                    """
SELECT source_match_set_item_id, source_match_set_id, category, role,
       source_file_group_id, required, omitted, omitted_reason, effective_yyyymm,
       validation_enabled, load_order, metadata
  FROM ops.source_match_set_items
 WHERE source_match_set_id = :id
 ORDER BY load_order NULLS LAST, category
"""
                ),
                {"id": source_match_set_id},
            )
        ).mappings().all()
        return tuple(_item_row(dict(r)) for r in rows)

    # --- create ------------------------------------------------------------

    async def create_match_set(
        self, req: SourceMatchSetCreateRequest, *, actor: str | None
    ) -> SourceMatchSetDetail:
        """Create a ``draft`` match set + its items in one transaction.

        Items are validated against the role/omitted/UNIQUE-category invariants
        BEFORE insert (``core.source_match_set.validate_item_invariants``); a
        referenced ``source_file_group_id`` must exist. ``source_set_hash`` stays
        NULL for a draft (computed at validate, doc line ~757).
        """
        specs = tuple(
            MatchSetItemSpec(
                category=item.category,
                role=item.role,
                source_file_group_id=item.source_file_group_id,
                omitted=item.omitted,
                omitted_reason=item.omitted_reason,
                required=item.required,
                validation_enabled=item.validation_enabled,
                load_order=item.load_order,
            )
            for item in req.items
        )
        invariant_errors = validate_item_invariants(specs)
        if invariant_errors:
            error_detail = "; ".join(
                f"{e.category}: {e.reason}" for e in invariant_errors
            )
            raise InvalidInputError(f"invalid match set items — {error_detail}")

        match_set_id = str(uuid4())
        async with self.engine.begin() as conn:
            await self._assert_groups_exist(conn, specs)
            await conn.execute(
                _json_text(
                    """
INSERT INTO ops.source_match_sets
  (source_match_set_id, name, description, profile, state, source_set_hash,
   created_by, metadata)
VALUES
  (:id, :name, :description, :profile, 'draft', NULL, :created_by, :metadata)
""",
                    "metadata",
                ),
                {
                    "id": match_set_id,
                    "name": req.name,
                    "description": req.description,
                    "profile": req.profile,
                    "created_by": actor,
                    "metadata": dict(req.metadata),
                },
            )
            for item in req.items:
                await conn.execute(
                    _json_text(
                        """
INSERT INTO ops.source_match_set_items
  (source_match_set_item_id, source_match_set_id, category, role,
   source_file_group_id, required, omitted, omitted_reason, effective_yyyymm,
   validation_enabled, load_order, metadata)
VALUES
  (:id, :msid, :category, :role, :gid, :required, :omitted, :omitted_reason,
   :effective_yyyymm, :validation_enabled, :load_order, :metadata)
""",
                        "metadata",
                    ),
                    {
                        "id": str(uuid4()),
                        "msid": match_set_id,
                        "category": item.category,
                        "role": item.role,
                        "gid": item.source_file_group_id,
                        "required": item.required,
                        "omitted": item.omitted,
                        "omitted_reason": item.omitted_reason,
                        "effective_yyyymm": item.effective_yyyymm,
                        "validation_enabled": item.validation_enabled,
                        "load_order": item.load_order,
                        "metadata": dict(item.metadata),
                    },
                )
            await self._audit(
                conn,
                action=SOURCE_MATCH_SET_CREATE,
                actor=actor,
                resource_id=match_set_id,
                outcome="draft",
                payload={"name": req.name, "profile": req.profile,
                         "item_count": len(req.items)},
            )
            detail = await self._get_detail_in_tx(conn, match_set_id)
        return detail

    async def _assert_groups_exist(
        self, conn: AsyncConnection, specs: tuple[MatchSetItemSpec, ...]
    ) -> None:
        for spec in specs:
            if spec.category not in category_by_code:
                raise InvalidInputError(f"unknown category: {spec.category}")
            if spec.source_file_group_id is None:
                continue
            exists = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM ops.source_file_groups "
                        "WHERE source_file_group_id = :gid"
                    ),
                    {"gid": spec.source_file_group_id},
                )
            ).first()
            if exists is None:
                raise InvalidInputError(
                    f"source file group not found: {spec.source_file_group_id} "
                    f"(category {spec.category})"
                )

    # --- validate ----------------------------------------------------------

    async def validate_match_set(
        self, source_match_set_id: str, *, actor: str | None
    ) -> SourceMatchSetValidateResponse:
        """Run the ``POST .../{id}/validate`` state-split (doc lines ~806/813-815).

        Gathers coverage (all referenced groups available + required categories
        present/omitted), then ``core.source_match_set.decide_validate`` picks the
        branch: ``draft``→``validated`` (compute fresh hash), ``revalidatable``→
        ``validated`` (re-check the pre-computed hash), ``active``+``integrity_alert``
        → validate-in-place (clear alert, stay active), else reject. The canonical
        hash is reused from ``core.source_match_propagation`` (no duplication).
        """
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT source_match_set_id, state, integrity_alert, profile, "
                        "source_set_hash FROM ops.source_match_sets "
                        "WHERE source_match_set_id = :id FOR UPDATE"
                    ),
                    {"id": source_match_set_id},
                )
            ).mappings().first()
            if row is None:
                raise NotFoundError(
                    f"source match set not found: {source_match_set_id}"
                )

            coverage, item_facts, yyyymm_items = await self._coverage(
                conn, source_match_set_id, profile=str(row["profile"])
            )
            facts = ValidateFacts(
                source_match_set_id=source_match_set_id,
                state=str(row["state"]),  # type: ignore[arg-type]
                integrity_alert=bool(row["integrity_alert"]),
                coverage=coverage,
            )
            decision = decide_validate(facts)

            new_hash: str | None = row["source_set_hash"]
            if decision.action == "reject":
                await self._audit(
                    conn,
                    action=SOURCE_MATCH_SET_VALIDATE,
                    actor=actor,
                    resource_id=source_match_set_id,
                    outcome="rejected",
                    payload={"reasons": list(decision.reasons), "from_state": row["state"]},
                )
                return SourceMatchSetValidateResponse(
                    source_match_set_id=source_match_set_id,
                    action=decision.action,
                    ok=False,
                    state=str(row["state"]),
                    source_set_hash=row["source_set_hash"],
                    integrity_alert=bool(row["integrity_alert"]),
                    reasons=decision.reasons,
                )

            final_state: str
            outcome: str
            if decision.ok:
                new_hash = compute_source_set_hash(item_facts)
                agg = aggregate_yyyymm(yyyymm_items)
                if decision.action == "validate_in_place":
                    await self._apply_validate_in_place(
                        conn, source_match_set_id, hash_value=new_hash, agg=agg
                    )
                    final_state = "active"
                    final_alert = False
                else:  # validate_draft / revalidate → validated
                    await self._apply_validated(
                        conn,
                        source_match_set_id,
                        hash_value=new_hash,
                        agg=agg,
                    )
                    final_state = "validated"
                    final_alert = bool(row["integrity_alert"])
                outcome = decision.action
            else:
                # validate_in_place failure: keep active + alert; audit reason.
                final_state = str(row["state"])
                final_alert = bool(row["integrity_alert"])
                outcome = f"{decision.action}_failed"

            await self._audit(
                conn,
                action=SOURCE_MATCH_SET_VALIDATE,
                actor=actor,
                resource_id=source_match_set_id,
                outcome=outcome,
                payload={
                    "action": decision.action,
                    "ok": decision.ok,
                    "reasons": list(decision.reasons),
                },
            )

        return SourceMatchSetValidateResponse(
            source_match_set_id=source_match_set_id,
            action=decision.action,
            ok=decision.ok,
            state=final_state,
            source_set_hash=new_hash if decision.ok else row["source_set_hash"],
            integrity_alert=final_alert,
            reasons=decision.reasons,
        )

    async def _apply_validated(
        self,
        conn: AsyncConnection,
        match_set_id: str,
        *,
        hash_value: str,
        agg: Any,
    ) -> None:
        await conn.execute(
            _json_text(
                """
UPDATE ops.source_match_sets
   SET state = 'validated', source_set_hash = :hash, validated_at = now(),
       mixed_yyyymm = :mixed, yyyymm_by_category = :by_cat, updated_at = now()
 WHERE source_match_set_id = :id
""",
                "by_cat",
            ),
            {
                "id": match_set_id,
                "hash": hash_value,
                "mixed": agg.mixed_yyyymm,
                "by_cat": agg.yyyymm_by_category,
            },
        )

    async def _apply_validate_in_place(
        self,
        conn: AsyncConnection,
        match_set_id: str,
        *,
        hash_value: str,
        agg: Any,
    ) -> None:
        # Active validate-in-place success: clear the alert, STAY active.
        await conn.execute(
            _json_text(
                """
UPDATE ops.source_match_sets
   SET source_set_hash = :hash, integrity_alert = false,
       integrity_alert_at = NULL, integrity_alert_detail = '{}'::jsonb,
       validated_at = now(), mixed_yyyymm = :mixed,
       yyyymm_by_category = :by_cat, updated_at = now()
 WHERE source_match_set_id = :id AND state = 'active'
""",
                "by_cat",
            ),
            {
                "id": match_set_id,
                "hash": hash_value,
                "mixed": agg.mixed_yyyymm,
                "by_cat": agg.yyyymm_by_category,
            },
        )

    async def _coverage(
        self, conn: AsyncConnection, match_set_id: str, *, profile: str
    ) -> tuple[ValidateCoverage, tuple[MatchSetItemFacts, ...], tuple[tuple[str, str | None], ...]]:
        rows = (
            await conn.execute(
                text(
                    """
SELECT it.category, it.source_file_group_id, it.effective_yyyymm, it.omitted,
       it.omitted_reason, g.state AS group_state, g.group_sha256
  FROM ops.source_match_set_items it
  LEFT JOIN ops.source_file_groups g
    ON g.source_file_group_id = it.source_file_group_id
 WHERE it.source_match_set_id = :id
"""
                ),
                {"id": match_set_id},
            )
        ).mappings().all()

        unavailable: list[str] = []
        item_facts: list[MatchSetItemFacts] = []
        yyyymm_items: list[tuple[str, str | None]] = []
        present_categories: set[str] = set()
        omitted_categories: set[str] = set()
        for r in rows:
            category = str(r["category"])
            gid = str(r["source_file_group_id"]) if r["source_file_group_id"] else None
            omitted = bool(r["omitted"])
            if omitted:
                omitted_categories.add(category)
            else:
                present_categories.add(category)
                group_ok = (
                    r["group_state"] == "available" and r["group_sha256"] is not None
                )
                if not group_ok and gid is not None:
                    unavailable.append(gid)
            item_facts.append(
                MatchSetItemFacts(
                    category=category,
                    source_file_group_id=gid,
                    group_sha256=r["group_sha256"],
                    effective_yyyymm=r["effective_yyyymm"],
                    omitted=omitted,
                    omitted_reason=r["omitted_reason"],
                )
            )
            yyyymm_items.append((category, r["effective_yyyymm"]))

        required = _PROFILE_REQUIRED_CATEGORIES.get(profile, frozenset())
        covered = present_categories | omitted_categories
        missing_required = tuple(sorted(required - covered))
        coverage = ValidateCoverage(
            all_groups_available=not unavailable,
            unavailable_group_ids=tuple(unavailable),
            missing_required_categories=missing_required,
        )
        return coverage, tuple(item_facts), tuple(yyyymm_items)

    # --- activate ----------------------------------------------------------

    async def activate_match_set(
        self, source_match_set_id: str, *, actor: str | None
    ) -> SourceMatchSetActivateResponse:
        """Atomic-swap activation under the ``SOURCE_MATCH_ACTIVATE`` advisory lock.

        In ONE transaction (doc line ~807): take a session-level advisory lock,
        re-compute the canonical hash and refuse if it drifted from the stored hash
        (stale-hash guard), then run the swap returned by
        ``core.source_match_set.decide_activate`` — retire the current active FIRST
        (the one-active partial unique index is not deferrable), then set the target
        ``active``. The single transaction means no externally-observable active gap.
        """
        lock = AdvisoryLockKey.global_key(AdvisoryLockNamespace.SOURCE_MATCH_ACTIVATE)
        async with self.engine.begin() as conn:
            # Serialize all activations on one global advisory lock (xact-scoped).
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock.as_int()}
            )
            row = (
                await conn.execute(
                    text(
                        "SELECT state, source_set_hash, profile FROM ops.source_match_sets "
                        "WHERE source_match_set_id = :id FOR UPDATE"
                    ),
                    {"id": source_match_set_id},
                )
            ).mappings().first()
            if row is None:
                raise NotFoundError(
                    f"source match set not found: {source_match_set_id}"
                )

            current_active_id = await self._current_active_id(conn)
            _, item_facts, _ = await self._coverage(
                conn, source_match_set_id, profile=str(row["profile"])
            )
            recomputed_hash = compute_source_set_hash(item_facts)

            facts = ActivateFacts(
                source_match_set_id=source_match_set_id,
                state=str(row["state"]),  # type: ignore[arg-type]
                stored_source_set_hash=row["source_set_hash"],
                recomputed_source_set_hash=recomputed_hash,
                current_active_id=current_active_id,
            )
            decision = decide_activate(facts)
            if not decision.ok:
                await self._audit(
                    conn,
                    action=SOURCE_MATCH_SET_ACTIVATE,
                    actor=actor,
                    resource_id=source_match_set_id,
                    outcome="rejected",
                    payload={"reasons": list(decision.reasons),
                             "from_state": row["state"]},
                )
                raise ConflictError("; ".join(decision.reasons))

            retired_id: str | None = None
            for step in decision.steps:
                if step.kind == "retire_current":
                    retired_id = step.source_match_set_id
                    await conn.execute(
                        text(
                            "UPDATE ops.source_match_sets SET state = 'retired', "
                            "updated_at = now() WHERE source_match_set_id = :id"
                        ),
                        {"id": step.source_match_set_id},
                    )
                else:  # activate_target
                    await conn.execute(
                        text(
                            "UPDATE ops.source_match_sets SET state = 'active', "
                            "updated_at = now() WHERE source_match_set_id = :id"
                        ),
                        {"id": step.source_match_set_id},
                    )

            await self._audit(
                conn,
                action=SOURCE_MATCH_SET_ACTIVATE,
                actor=actor,
                resource_id=source_match_set_id,
                outcome="active",
                payload={
                    "retired_match_set_id": retired_id,
                    "source_set_hash": recomputed_hash,
                },
            )

        return SourceMatchSetActivateResponse(
            source_match_set_id=source_match_set_id,
            state="active",
            retired_match_set_id=retired_id,
            source_set_hash=recomputed_hash,
        )

    async def _current_active_id(self, conn: AsyncConnection) -> str | None:
        row = (
            await conn.execute(
                text(
                    "SELECT source_match_set_id FROM ops.source_match_sets "
                    "WHERE state = 'active' LIMIT 1 FOR UPDATE"
                )
            )
        ).first()
        return str(row[0]) if row is not None else None

    # --- retire ------------------------------------------------------------

    async def retire_match_set(
        self, source_match_set_id: str, *, actor: str | None
    ) -> SourceMatchSetRetireResponse:
        """Retire a match set to ``retired`` (doc line ~808)."""
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT state FROM ops.source_match_sets "
                        "WHERE source_match_set_id = :id FOR UPDATE"
                    ),
                    {"id": source_match_set_id},
                )
            ).mappings().first()
            if row is None:
                raise NotFoundError(
                    f"source match set not found: {source_match_set_id}"
                )
            decision: RetireDecision = decide_retire(state=str(row["state"]))  # type: ignore[arg-type]
            if not decision.ok:
                raise ConflictError("; ".join(decision.reasons))
            await conn.execute(
                text(
                    "UPDATE ops.source_match_sets SET state = 'retired', "
                    "updated_at = now() WHERE source_match_set_id = :id"
                ),
                {"id": source_match_set_id},
            )
            await self._audit(
                conn,
                action=SOURCE_MATCH_SET_RETIRE,
                actor=actor,
                resource_id=source_match_set_id,
                outcome="retired",
                payload={"was_active": decision.was_active},
            )
        return SourceMatchSetRetireResponse(
            source_match_set_id=source_match_set_id,
            state="retired",
            was_active=decision.was_active,
        )

    # --- helpers -----------------------------------------------------------

    async def _get_detail_in_tx(
        self, conn: AsyncConnection, match_set_id: str
    ) -> SourceMatchSetDetail:
        row = (
            await conn.execute(
                text(
                    f"SELECT {_MATCH_SET_COLUMNS} FROM ops.source_match_sets "
                    "WHERE source_match_set_id = :id"
                ),
                {"id": match_set_id},
            )
        ).mappings().one()
        items = await self._load_items(conn, match_set_id)
        return SourceMatchSetDetail(match_set=_match_set_row(dict(row)), items=items)

    async def _audit(
        self,
        conn: AsyncConnection,
        *,
        action: str,
        actor: str | None,
        resource_id: str,
        outcome: str,
        payload: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await conn.execute(
            _json_text(
                """
INSERT INTO ops.audit_events
  (event_id, actor_type, actor_id, action, resource_type, resource_id,
   outcome, payload_redacted)
VALUES
  (:event_id, 'ui', :actor_id, :action, 'source_match_set', :resource_id,
   :outcome, :payload)
""",
                "payload",
            ),
            {
                "event_id": str(uuid4()),
                "actor_id": actor,
                "action": action,
                "resource_id": resource_id,
                "outcome": outcome,
                "payload": {**payload, "at": now},
            },
        )
