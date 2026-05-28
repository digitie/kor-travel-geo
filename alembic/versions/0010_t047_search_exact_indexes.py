"""T-047 search exact preflight indexes

Revision ID: 0010_t047_search_exact_indexes
Revises: 0009_t047_jibun_name_exact_index
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op

revision = "0010_t047_search_exact_indexes"
down_revision = "0009_t047_jibun_name_exact_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_mv_rn_nrm_exact
  ON mv_geocode_target (rn_nrm, bd_mgt_sn)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_mv_buld_nm_nrm_exact
  ON mv_geocode_target (buld_nm_nrm, bd_mgt_sn)
  WHERE buld_nm_nrm IS NOT NULL
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mv_buld_nm_nrm_exact")
    op.execute("DROP INDEX IF EXISTS idx_mv_rn_nrm_exact")
