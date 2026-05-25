"""T-032 performance indexes

Revision ID: 0003_t032_performance_indexes
Revises: 0002_t027_shp_schema_fixups
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op

revision = "0003_t032_performance_indexes"
down_revision = "0002_t027_shp_schema_fixups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_juso_text_resolve
  ON tl_juso_text (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd, zip_no)
"""
    )


def downgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute("DROP INDEX IF EXISTS idx_juso_text_resolve")
