"""T-038 parcel link table

Revision ID: 0004_t038_parcel_link_table
Revises: 0003_t032_performance_indexes
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op

revision = "0004_t038_parcel_link_table"
down_revision = "0003_t032_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute(
        """
CREATE TABLE IF NOT EXISTS tl_juso_parcel_link (
  bd_mgt_sn       TEXT NOT NULL REFERENCES tl_juso_text(bd_mgt_sn) ON DELETE CASCADE,
  pnu             TEXT NOT NULL,
  bjd_cd          TEXT NOT NULL,
  mntn_yn         CHAR(1) NOT NULL,
  lnbr_mnnm       INTEGER NOT NULL,
  lnbr_slno       INTEGER NOT NULL DEFAULT 0,
  sig_cd          TEXT NOT NULL,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  source_kind     TEXT NOT NULL CHECK (source_kind IN ('jibun_full','daily_lnbr')),
  source_file     TEXT,
  source_yyyymm   TEXT,
  last_mvmn_de    TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (bd_mgt_sn, pnu),
  CHECK (char_length(bd_mgt_sn) BETWEEN 25 AND 26),
  CHECK (char_length(pnu) = 19),
  CHECK (char_length(bjd_cd) = 10),
  CHECK (mntn_yn IN ('0', '1')),
  CHECK (lnbr_mnnm >= 0),
  CHECK (lnbr_slno >= 0),
  CHECK (char_length(sig_cd) = 5),
  CHECK (char_length(rn_cd) = 7)
)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_juso_parcel_link_pnu
  ON tl_juso_parcel_link (pnu)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_juso_parcel_link_road
  ON tl_juso_parcel_link (rncode_full, buld_se_cd, buld_mnnm, buld_slno)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_juso_parcel_link_bjd
  ON tl_juso_parcel_link (bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno)
"""
    )


def downgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute("DROP INDEX IF EXISTS idx_juso_parcel_link_bjd")
    op.execute("DROP INDEX IF EXISTS idx_juso_parcel_link_road")
    op.execute("DROP INDEX IF EXISTS idx_juso_parcel_link_pnu")
    op.execute("DROP TABLE IF EXISTS tl_juso_parcel_link")
