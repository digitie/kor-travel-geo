"""T-039 road address direct entrance table

Revision ID: 0005_t039_roadaddr_entrance_table
Revises: 0004_t038_parcel_link_table
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op

revision = "0005_t039_roadaddr_entrance_table"
down_revision = "0004_t038_parcel_link_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute(
        """
CREATE TABLE IF NOT EXISTS tl_roadaddr_entrc (
  bd_mgt_sn       TEXT NOT NULL,
  bjd_cd          TEXT NOT NULL,
  ctp_kor_nm      TEXT,
  sig_kor_nm      TEXT,
  emd_kor_nm      TEXT,
  li_kor_nm       TEXT,
  sig_cd          TEXT NOT NULL,
  rn_cd           TEXT NOT NULL,
  rncode_full     TEXT GENERATED ALWAYS AS (sig_cd || rn_cd) STORED,
  rn              TEXT,
  buld_se_cd      TEXT,
  buld_mnnm       INTEGER,
  buld_slno       INTEGER,
  zip_no          TEXT,
  notice_de       TEXT,
  raw_col_13      TEXT,
  ent_man_no      BIGINT,
  ent_source_cd   TEXT NOT NULL,
  ent_detail_cd   TEXT NOT NULL,
  geom            geometry(Point, 5179) NOT NULL,
  source_file     TEXT,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (bd_mgt_sn),
  CHECK (char_length(bd_mgt_sn) BETWEEN 25 AND 26),
  CHECK (char_length(bjd_cd) = 10),
  CHECK (char_length(sig_cd) = 5),
  CHECK (char_length(rn_cd) = 7),
  CHECK (zip_no IS NULL OR char_length(zip_no) = 5),
  CHECK (notice_de IS NULL OR char_length(notice_de) = 8)
)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_roadaddr_entrc_geom
  ON tl_roadaddr_entrc USING GIST (geom)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_roadaddr_entrc_bd
  ON tl_roadaddr_entrc (bd_mgt_sn, ent_man_no)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_roadaddr_entrc_road
  ON tl_roadaddr_entrc (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd)
"""
    )


def downgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute("DROP INDEX IF EXISTS idx_roadaddr_entrc_road")
    op.execute("DROP INDEX IF EXISTS idx_roadaddr_entrc_bd")
    op.execute("DROP INDEX IF EXISTS idx_roadaddr_entrc_geom")
    op.execute("DROP TABLE IF EXISTS tl_roadaddr_entrc")
