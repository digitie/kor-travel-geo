"""Run-validation orchestration glue (T-206, infra layer).

``POST /v1/admin/source-match-sets/{id}/run-validation`` runs the registry
C11~C17 validation cases against an existing DB without rebuilding it
(``docs/t109-backup-source-upload-management.md`` lines ~1564-1578). This module
is the DB/RustFS glue:

* read which registry-case inputs the match set carries (its non-omitted items),
* run the **사용 직전 무결성 게이트** (re-verify each present input's RustFS
  archive — the SAME pre-load gate reused from T-204/T-205 via
  ``core.source_rebuild.decide_integrity_gate``),
* turn the gate + presence into per-input states with the pure decision logic in
  ``core.consistency_run_validation`` (absent → ``skipped``; corrupt/mismatch →
  ``failed``; ok → ``not_started``/runnable),
* on integrity ``failed`` quarantine the failing group + propagate via
  ``recompute_group_aggregates(trigger='run_validation_integrity_gate')``,
* on a ``validator_version`` change revert prior ``passed`` results to
  ``not_started`` and propagate via
  ``recompute_group_aggregates(trigger='validator_version_change')``.

It imports only ``core``/``dto``/sibling-infra — **no loaders**. The prototype
metric computation (the C11~C17 ``.metrics()``) is the api router's job via
``loaders/consistency_run_validation.py`` (the one layer allowed to import
loaders). This module decides states + handles propagation; it does not compute
metrics, so the ``infra ↛ loaders`` rule holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.consistency_run_validation import (
    CaseInputFacts,
    CaseRunDecision,
    ValidatorVersionFacts,
    decide_case_run,
    decide_validator_version_change,
)
from kortravelgeo.core.source_rebuild import GroupArchiveCheck, decide_integrity_gate
from kortravelgeo.core.source_validation import VALIDATOR_VERSION
from kortravelgeo.dto.admin import (
    ConsistencyCaseValidationResult,
    ConsistencyRunValidationResponse,
    ConsistencyValidationInput,
)
from kortravelgeo.exceptions import NotFoundError
from kortravelgeo.infra.consistency_registry_service import ConsistencyRegistryService
from kortravelgeo.infra.source_group_service import recompute_group_aggregates

RUN_VALIDATION_INTEGRITY_TRIGGER = "run_validation_integrity_gate"
VALIDATOR_VERSION_CHANGE_TRIGGER = "validator_version_change"


@dataclass(frozen=True, slots=True)
class _RevertResult:
    case_codes: tuple[str, ...]
    affected_match_set_ids: tuple[str, ...]


class ConsistencyRunValidationService:
    """Orchestrate ``run-validation`` for the registry cases (T-206)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def run_validation(
        self,
        source_match_set_id: str,
        *,
        actor: str | None,
        cases: tuple[str, ...] | None,
        integrity_verifier: Any | None = None,
        validator_version: str = VALIDATOR_VERSION,
    ) -> ConsistencyRunValidationResponse:
        """Decide + apply per-input states for the selected registry cases.

        ``integrity_verifier`` is an async callable ``(group_id, category) ->
        GroupArchiveCheck`` (the RustFS re-verification). When ``None`` (no RustFS
        configured / tests), a present input is treated as integrity-ok so the
        decision still exercises absent→skipped and runnable paths; the api layer
        injects the real verifier for production.
        """
        registry = await ConsistencyRegistryService(self.engine).list_case_definitions()
        augment_cases = tuple(
            d for d in registry if d.metadata.get("family") == "augment_validation"
        )
        if cases is not None:
            wanted = set(cases)
            augment_cases = tuple(d for d in augment_cases if d.code in wanted)

        snapshot_id = await self._active_snapshot_id(source_match_set_id)
        present = await self._present_categories(source_match_set_id)
        if not present and not await self._match_set_exists(source_match_set_id):
            raise NotFoundError(f"source match set not found: {source_match_set_id}")

        results: list[ConsistencyCaseValidationResult] = []
        all_quarantine: set[str] = set()
        for definition in augment_cases:
            input_facts: list[CaseInputFacts] = []
            for inp in definition.inputs:
                group_id = present.get(inp.category)
                is_present = group_id is not None
                integrity_ok = True
                if is_present and integrity_verifier is not None:
                    check: GroupArchiveCheck = await integrity_verifier(
                        group_id, inp.category
                    )
                    integrity_ok = decide_integrity_gate((check,)).ok
                input_facts.append(
                    CaseInputFacts(
                        category=inp.category,
                        required=inp.required,
                        present=is_present,
                        integrity_ok=integrity_ok,
                        source_file_group_id=group_id,
                    )
                )
            decision = decide_case_run(definition.code, tuple(input_facts))
            all_quarantine.update(decision.quarantine_group_ids)
            results.append(_to_result_dto(decision))

        affected = await self._quarantine_and_propagate(
            tuple(sorted(all_quarantine)),
            actor=actor,
            source_match_set_id=source_match_set_id,
        )

        reverted = await self._revert_stale_validator_versions(
            source_match_set_id,
            augment_cases=tuple(d.code for d in augment_cases),
            present=present,
            validator_version=validator_version,
        )
        affected = tuple(sorted(set(affected) | set(reverted.affected_match_set_ids)))

        return ConsistencyRunValidationResponse(
            source_match_set_id=source_match_set_id,
            validator_version=validator_version,
            dataset_snapshot_id=snapshot_id,
            cases=tuple(results),
            revalidated_case_codes=reverted.case_codes,
            quarantined_group_ids=tuple(sorted(all_quarantine)),
            affected_match_set_ids=affected,
            skipped_count=sum(1 for r in results if r.skipped),
            failed_count=sum(1 for r in results if r.failed),
            runnable_count=sum(1 for r in results if r.runnable),
        )

    # --- DB reads ----------------------------------------------------------

    async def _match_set_exists(self, source_match_set_id: str) -> bool:
        async with self.engine.connect() as conn:
            row = await conn.scalar(
                text(
                    "SELECT 1 FROM ops.source_match_sets WHERE source_match_set_id = :id"
                ),
                {"id": source_match_set_id},
            )
        return row is not None

    async def _active_snapshot_id(self, source_match_set_id: str) -> str | None:
        async with self.engine.connect() as conn:
            value = await conn.scalar(
                text(
                    """
SELECT snapshot_id
  FROM ops.dataset_snapshots
 WHERE source_match_set_id = :id
 ORDER BY created_at DESC
 LIMIT 1
"""
                ),
                {"id": source_match_set_id},
            )
        return str(value) if value is not None else None

    async def _present_categories(
        self, source_match_set_id: str
    ) -> dict[str, str]:
        """Map ``category -> source_file_group_id`` for non-omitted items."""
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT category, source_file_group_id
  FROM ops.source_match_set_items
 WHERE source_match_set_id = :id
   AND omitted = false
   AND source_file_group_id IS NOT NULL
"""
                    ),
                    {"id": source_match_set_id},
                )
            ).mappings().all()
        return {str(r["category"]): str(r["source_file_group_id"]) for r in rows}

    # --- integrity-failure propagation -------------------------------------

    async def _quarantine_and_propagate(
        self,
        failed_group_ids: tuple[str, ...],
        *,
        actor: str | None,
        source_match_set_id: str,
    ) -> tuple[str, ...]:
        """Quarantine integrity-failed groups + propagate (doc ~1576).

        Mirrors the rebuild integrity-gate failure path: failing group + its
        non-deleted children → ``quarantined``; ``recompute_group_aggregates``
        propagates (active → ``integrity_alert``, non-active ``validated`` →
        ``invalid``, pre-hash stays). No DB build / snapshot / release.
        """
        if not failed_group_ids:
            return ()
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
                    trigger=RUN_VALIDATION_INTEGRITY_TRIGGER,
                    structure_validation_state="failed",
                )
                affected.update(recompute.affected_match_set_ids)
        return tuple(sorted(affected))

    # --- validator_version change ------------------------------------------

    async def _revert_stale_validator_versions(
        self,
        source_match_set_id: str,
        *,
        augment_cases: tuple[str, ...],
        present: dict[str, str],
        validator_version: str,
    ) -> _RevertResult:
        """Revert prior ``passed`` group validations under a stale validator.

        For each present input group, if its most recent ``passed``/``warning``
        ``ops.source_file_validations`` row was produced by a *different*
        validator version, revert the group's ``validation_state`` to
        ``not_started`` and propagate (doc ~1620). The case is reported in
        ``revalidated_case_codes``.
        """
        # Gather the latest group validation per present group.
        group_ids = tuple(sorted(set(present.values())))
        if not group_ids:
            return _RevertResult(case_codes=(), affected_match_set_ids=())

        reverted_codes: set[str] = set()
        affected: set[str] = set()
        async with self.engine.begin() as conn:
            stale_group_ids: set[str] = set()
            for gid in group_ids:
                prior = (
                    await conn.execute(
                        text(
                            """
SELECT state, validator_version
  FROM ops.source_file_validations
 WHERE source_file_group_id = :gid
   AND scope = 'group'
 ORDER BY started_at DESC
 LIMIT 1
"""
                        ),
                        {"gid": gid},
                    )
                ).mappings().first()
                if prior is None:
                    continue
                decision = decide_validator_version_change(
                    ValidatorVersionFacts(
                        case_code="",
                        prior_state=str(prior["state"]),  # type: ignore[arg-type]
                        prior_validator_version=prior["validator_version"],
                        current_validator_version=validator_version,
                    )
                )
                if decision.needs_revalidation:
                    stale_group_ids.add(gid)

            for gid in stale_group_ids:
                await conn.execute(
                    text(
                        """
UPDATE ops.source_file_groups
   SET validation_state = 'not_started', updated_at = now()
 WHERE source_file_group_id = :gid
   AND state NOT IN ('available')
"""
                    ),
                    {"gid": gid},
                )
                recompute = await recompute_group_aggregates(
                    conn,
                    gid,
                    trigger=VALIDATOR_VERSION_CHANGE_TRIGGER,
                    structure_validation_state="not_started",
                )
                affected.update(recompute.affected_match_set_ids)

            # Map stale groups back to the cases that reference them.
            stale_categories = {
                category for category, g in present.items() if g in stale_group_ids
            }
            registry = await ConsistencyRegistryService(self.engine).list_case_definitions()
            for definition in registry:
                if definition.code not in augment_cases:
                    continue
                if any(inp.category in stale_categories for inp in definition.inputs):
                    reverted_codes.add(definition.code)

        return _RevertResult(
            case_codes=tuple(sorted(reverted_codes)),
            affected_match_set_ids=tuple(sorted(affected)),
        )


def _to_result_dto(decision: CaseRunDecision) -> ConsistencyCaseValidationResult:
    return ConsistencyCaseValidationResult(
        case_code=decision.case_code,
        runnable=decision.runnable,
        skipped=decision.skipped,
        failed=decision.failed,
        inputs=tuple(
            ConsistencyValidationInput(
                category=d.category,
                state=d.state,
                required=d.required,
                failure_reason=d.failure_reason,
                source_file_group_id=d.quarantine_group_id,
            )
            for d in decision.inputs
        ),
        quarantine_group_ids=decision.quarantine_group_ids,
    )
