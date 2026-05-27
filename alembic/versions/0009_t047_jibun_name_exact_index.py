"""T-047 지번 exact query name-key index

Revision ID: 0009_t047_jibun_name_exact_index
Revises: 0008_pr34_review_followups
Create Date: 2026-05-27
"""

from __future__ import annotations

from alembic import op

revision = "0009_t047_jibun_name_exact_index"
down_revision = "0008_pr34_review_followups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_mv_jibun_name_exact
  ON mv_geocode_target (si_nm, sgg_nm, mntn_yn, lnbr_mnnm, lnbr_slno, emd_nm, li_nm, pt_source, bd_mgt_sn)
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mv_jibun_name_exact")
