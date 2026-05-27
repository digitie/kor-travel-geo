"""T-042 SPPN marking area table

Revision ID: 0007_t042_sppn_makarea
Revises: 0006_t049_ops_metadata_schema
Create Date: 2026-05-27
"""

from __future__ import annotations

from alembic import op

revision = "0007_t042_sppn_makarea"
down_revision = "0006_t049_ops_metadata_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS tl_sppn_makarea (
  sig_cd          TEXT NOT NULL,
  makarea_id      TEXT NOT NULL,
  ntfc_yn         TEXT,
  makarea_nm      TEXT,
  ntfc_de         TEXT,
  mvm_res_cd      TEXT,
  mvmn_resn       TEXT,
  opert_de        TEXT,
  makarea_ar      NUMERIC(12,3),
  mvmn_desc       TEXT,
  geom            geometry(MultiPolygon, 5179) NOT NULL,
  source_file     TEXT NOT NULL,
  source_yyyymm   TEXT,
  loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (sig_cd, makarea_id),
  CHECK (char_length(sig_cd) = 5),
  CHECK (btrim(makarea_id) <> '')
)
"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sppn_makarea_geom "
        "ON tl_sppn_makarea USING GIST (geom)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sppn_makarea_sig "
        "ON tl_sppn_makarea (sig_cd)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sppn_makarea_sig")
    op.execute("DROP INDEX IF EXISTS idx_sppn_makarea_geom")
    op.execute("DROP TABLE IF EXISTS tl_sppn_makarea")
