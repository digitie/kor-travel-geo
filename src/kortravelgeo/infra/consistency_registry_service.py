"""Consistency case registry seed + read service (T-206).

Upserts ``ops.consistency_case_definitions`` + ``ops.consistency_case_inputs``
from the pure seed authority (``core/consistency_registry_seed.py``) and reads
the registry rows back as DTOs for ``GET .../consistency/case-definitions``.

The seed is **data-driven and idempotent** (upsert + input reconcile), so it is
safe to run on every ``init-db`` / deploy. It imports only ``core`` (the seed
rows) and ``dto`` — no loader imports — so the ``infra`` layer stays clean.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.consistency_registry_seed import (
    REGISTRY_SEED_ROWS,
    CaseRegistryRow,
)
from kortravelgeo.dto.admin import ConsistencyCaseDefinition, ConsistencyCaseInput

_UPSERT_DEFINITION_SQL = text(
    """
INSERT INTO ops.consistency_case_definitions (
  consistency_case_code, display_order, name, compares, abnormal_criteria,
  evidence, likely_causes, decision_guide, threshold, default_severity,
  state, skip_policy, sample_schema, introduced_by, metadata
) VALUES (
  :code, :display_order, :name, :compares, :abnormal_criteria,
  :evidence, :likely_causes, :decision_guide, :threshold, :default_severity,
  :state, :skip_policy, :sample_schema, :introduced_by, :metadata
)
ON CONFLICT (consistency_case_code) DO UPDATE SET
  display_order     = EXCLUDED.display_order,
  name              = EXCLUDED.name,
  compares          = EXCLUDED.compares,
  abnormal_criteria = EXCLUDED.abnormal_criteria,
  evidence          = EXCLUDED.evidence,
  likely_causes     = EXCLUDED.likely_causes,
  decision_guide    = EXCLUDED.decision_guide,
  threshold         = EXCLUDED.threshold,
  default_severity  = EXCLUDED.default_severity,
  state             = EXCLUDED.state,
  skip_policy       = EXCLUDED.skip_policy,
  sample_schema     = EXCLUDED.sample_schema,
  introduced_by     = EXCLUDED.introduced_by,
  metadata          = EXCLUDED.metadata,
  updated_at        = now()
"""
).bindparams(
    bindparam("evidence", type_=JSONB),
    bindparam("likely_causes", type_=JSONB),
    bindparam("skip_policy", type_=JSONB),
    bindparam("sample_schema", type_=JSONB),
    bindparam("metadata", type_=JSONB),
)


async def _seed_one(conn: AsyncConnection, row: CaseRegistryRow) -> None:
    await conn.execute(
        _UPSERT_DEFINITION_SQL,
        {
            "code": row.consistency_case_code,
            "display_order": row.display_order,
            "name": row.name,
            "compares": row.compares,
            "abnormal_criteria": row.abnormal_criteria,
            "evidence": list(row.evidence),
            "likely_causes": list(row.likely_causes),
            "decision_guide": row.decision_guide,
            "threshold": row.threshold,
            "default_severity": row.default_severity,
            "state": row.state,
            "skip_policy": row.skip_policy,
            "sample_schema": row.sample_schema,
            "introduced_by": row.introduced_by,
            "metadata": row.metadata,
        },
    )
    # Reconcile inputs: delete rows no longer in the seed, then upsert the seed.
    seed_categories = [i.category for i in row.inputs]
    await conn.execute(
        text(
            """
DELETE FROM ops.consistency_case_inputs
 WHERE consistency_case_code = :code
   AND (:has_inputs = false OR category <> ALL(:keep))
"""
        ),
        {
            "code": row.consistency_case_code,
            "has_inputs": bool(seed_categories),
            "keep": seed_categories or [""],
        },
    )
    for spec in row.inputs:
        await conn.execute(
            text(
                """
INSERT INTO ops.consistency_case_inputs (consistency_case_code, category, required)
VALUES (:code, :category, :required)
ON CONFLICT (consistency_case_code, category) DO UPDATE SET
  required = EXCLUDED.required
"""
            ),
            {
                "code": row.consistency_case_code,
                "category": spec.category,
                "required": spec.required,
            },
        )


class ConsistencyRegistryService:
    """Seed + read ``ops.consistency_case_definitions``/``..._inputs`` (T-206)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def seed_registry(
        self, rows: Sequence[CaseRegistryRow] = REGISTRY_SEED_ROWS
    ) -> int:
        """Idempotently upsert the C1~C17 seed. Returns the row count seeded."""
        async with self.engine.begin() as conn:
            for row in rows:
                await _seed_one(conn, row)
        return len(rows)

    async def list_case_definitions(self) -> tuple[ConsistencyCaseDefinition, ...]:
        """Read the registry rows (+ their inputs) ordered by ``display_order``."""
        async with self.engine.connect() as conn:
            def_rows = (
                await conn.execute(
                    text(
                        """
SELECT consistency_case_code, display_order, name, compares, abnormal_criteria,
       evidence, likely_causes, decision_guide, threshold, default_severity,
       state, skip_policy, sample_schema, introduced_by, metadata
  FROM ops.consistency_case_definitions
 ORDER BY display_order, consistency_case_code
"""
                    )
                )
            ).mappings().all()
            input_rows = (
                await conn.execute(
                    text(
                        """
SELECT consistency_case_code, category, required
  FROM ops.consistency_case_inputs
 ORDER BY consistency_case_code, category
"""
                    )
                )
            ).mappings().all()

        inputs_by_code: dict[str, list[ConsistencyCaseInput]] = {}
        for r in input_rows:
            inputs_by_code.setdefault(str(r["consistency_case_code"]), []).append(
                ConsistencyCaseInput(category=str(r["category"]), required=bool(r["required"]))
            )

        return tuple(
            ConsistencyCaseDefinition(
                code=str(r["consistency_case_code"]),
                name=str(r["name"]),
                compares=str(r["compares"]),
                abnormal_criteria=str(r["abnormal_criteria"]),
                evidence=tuple(r["evidence"] or ()),
                likely_causes=tuple(r["likely_causes"] or ()),
                decision_guide=str(r["decision_guide"]),
                threshold=r["threshold"],
                display_order=int(r["display_order"]),
                default_severity=r["default_severity"],
                state=str(r["state"]),
                inputs=tuple(inputs_by_code.get(str(r["consistency_case_code"]), ())),
                skip_policy=dict(r["skip_policy"] or {}),
                sample_schema=dict(r["sample_schema"] or {}),
                introduced_by=r["introduced_by"],
                metadata=dict(r["metadata"] or {}),
            )
            for r in def_rows
        )
