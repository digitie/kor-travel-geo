"""T-171 fuzzy road ranking determinism

Revision ID: 0020_t171_fuzzy_ranking
Revises: 0019_t157_pg_stat_snapshots
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op

from kortravelgeo.infra.sql import TEXT_SEARCH_MV_SQL, iter_sql_statements

revision = "0020_t171_fuzzy_ranking"
down_revision = "0019_t157_pg_stat_snapshots"
branch_labels = None
depends_on = None


TEXT_SEARCH_MV_SQL_PRE_T171 = """
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
  sigungu_buld_nm_nrm,
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
CREATE INDEX idx_mv_text_search_sigungu_buld_nm_trgm
  ON mv_geocode_text_search USING GIN (sigungu_buld_nm_nrm gin_trgm_ops)
  WHERE sigungu_buld_nm_nrm IS NOT NULL;
"""


def upgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    for sql in iter_sql_statements(TEXT_SEARCH_MV_SQL):
        op.execute(sql)
    op.execute("ANALYZE mv_geocode_text_search")


def downgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    for sql in iter_sql_statements(TEXT_SEARCH_MV_SQL_PRE_T171):
        op.execute(sql)
    op.execute("ANALYZE mv_geocode_text_search")
