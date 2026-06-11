"""T-061 slim text-search materialized view

Revision ID: 0013_t061_text_search_mv
Revises: 0012_t053_consistency_samples
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op

from kraddr.geo.infra.sql import iter_sql_statements

revision = "0013_t061_text_search_mv"
down_revision = "0012_t053_consistency_samples"
branch_labels = None
depends_on = None

TEXT_SEARCH_MV_SQL_T061 = """
SET search_path = public, x_extension;

DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search;
CREATE MATERIALIZED VIEW mv_geocode_text_search AS
SELECT
  bd_mgt_sn,
  left(bjd_cd, 2) AS sido_cd,
  left(bjd_cd, 5) AS sig_cd,
  bjd_cd,
  si_nm,
  sgg_nm,
  rn_nrm,
  buld_nm_nrm,
  buld_mnnm,
  pt_source
FROM mv_geocode_target
WHERE rn_nrm IS NOT NULL
  AND rn_nrm <> ''
WITH DATA;

CREATE UNIQUE INDEX idx_mv_text_search_pk
  ON mv_geocode_text_search (bd_mgt_sn);
CREATE INDEX idx_mv_text_search_sig_buld
  ON mv_geocode_text_search (sig_cd, buld_mnnm, bd_mgt_sn);
CREATE INDEX idx_mv_text_search_sido_buld
  ON mv_geocode_text_search (sido_cd, buld_mnnm, bd_mgt_sn);
CREATE INDEX idx_mv_text_search_bjd_prefix_buld
  ON mv_geocode_text_search (bjd_cd text_pattern_ops, buld_mnnm, bd_mgt_sn);
CREATE INDEX idx_mv_text_search_rn_trgm
  ON mv_geocode_text_search USING GIN (rn_nrm gin_trgm_ops);
CREATE INDEX idx_mv_text_search_buld_nm_trgm
  ON mv_geocode_text_search USING GIN (buld_nm_nrm gin_trgm_ops)
  WHERE buld_nm_nrm IS NOT NULL;
"""


def upgrade() -> None:
    for sql in iter_sql_statements(TEXT_SEARCH_MV_SQL_T061):
        op.execute(sql)
    op.execute("ANALYZE mv_geocode_text_search")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search")
