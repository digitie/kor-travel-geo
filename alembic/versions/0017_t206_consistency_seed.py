"""T-206 seed the consistency case registry (C1~C17)

Idempotently upserts ``ops.consistency_case_definitions`` +
``ops.consistency_case_inputs`` from the pure seed authority
(``kortravelgeo.core.consistency_registry_seed``) so existing deployed DBs get
the C1~C17 registry without an ``init-db`` re-run. C1~C10 are derived from the
in-code ``CASE_DEFINITIONS``; C11~C17 from the T-118 confirmed spec.

Revision ID: 0017_t206_consistency_seed
Revises: 0016_t200_source_registry
Create Date: 2026-06-14
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from kortravelgeo.core.consistency_registry_seed import REGISTRY_SEED_ROWS

revision = "0017_t206_consistency_seed"
down_revision = "0016_t200_source_registry"
branch_labels = None
depends_on = None


_UPSERT_DEFINITION = text(
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

_UPSERT_INPUT = text(
    """
INSERT INTO ops.consistency_case_inputs (consistency_case_code, category, required)
VALUES (:code, :category, :required)
ON CONFLICT (consistency_case_code, category) DO UPDATE SET
  required = EXCLUDED.required
"""
)


def upgrade() -> None:
    conn = op.get_bind()
    for row in REGISTRY_SEED_ROWS:
        conn.execute(
            _UPSERT_DEFINITION,
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
        seed_categories = [i.category for i in row.inputs]
        conn.execute(
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
            conn.execute(
                _UPSERT_INPUT,
                {
                    "code": row.consistency_case_code,
                    "category": spec.category,
                    "required": spec.required,
                },
            )


def downgrade() -> None:
    codes = [row.consistency_case_code for row in REGISTRY_SEED_ROWS]
    conn = op.get_bind()
    conn.execute(
        text(
            "DELETE FROM ops.consistency_case_inputs "
            "WHERE consistency_case_code = ANY(:codes)"
        ),
        {"codes": codes},
    )
    conn.execute(
        text(
            "DELETE FROM ops.consistency_case_definitions "
            "WHERE consistency_case_code = ANY(:codes)"
        ),
        {"codes": codes},
    )
