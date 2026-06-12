"""T-065 navi sigungu building name search

Revision ID: 0014_t065_navi_name_search
Revises: 0013_t061_text_search_mv
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op

from kortravelgeo.infra.sql import MV_SQL, TEXT_SEARCH_MV_SQL, iter_sql_statements

revision = "0014_t065_navi_name_search"
down_revision = "0013_t061_text_search_mv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute("SET LOCAL statement_timeout = 0")
    op.execute(
        """
ALTER TABLE tl_navi_buld_centroid
  ADD COLUMN IF NOT EXISTS sigungu_buld_nm TEXT
"""
    )
    op.execute(
        """
ALTER TABLE tl_navi_buld_centroid
  ADD COLUMN IF NOT EXISTS sigungu_buld_nm_nrm TEXT
  GENERATED ALWAYS AS (
    regexp_replace(COALESCE(sigungu_buld_nm, ''), '\\s+', '', 'g')
  ) STORED
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_navi_centroid_sigungu_buld_nm_trgm
  ON tl_navi_buld_centroid USING GIN (sigungu_buld_nm_nrm gin_trgm_ops)
  WHERE sigungu_buld_nm_nrm IS NOT NULL AND sigungu_buld_nm_nrm <> ''
"""
    )
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search")
    for sql in iter_sql_statements(MV_SQL):
        op.execute(sql)
    for sql in iter_sql_statements(TEXT_SEARCH_MV_SQL):
        op.execute(sql)
    op.execute("ANALYZE tl_navi_buld_centroid")
    op.execute("ANALYZE mv_geocode_target")
    op.execute("ANALYZE mv_geocode_text_search")


def downgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute("SET LOCAL statement_timeout = 0")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target")
    op.execute("DROP INDEX IF EXISTS idx_navi_centroid_sigungu_buld_nm_trgm")
    op.execute(
        """
ALTER TABLE tl_navi_buld_centroid
  DROP COLUMN IF EXISTS sigungu_buld_nm_nrm,
  DROP COLUMN IF EXISTS sigungu_buld_nm
"""
    )
