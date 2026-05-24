"""T-027 SHP schema fixups

Revision ID: 0002_t027_shp_schema_fixups
Revises: 0001_text_primary_postgis
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op

revision = "0002_t027_shp_schema_fixups"
down_revision = "0001_text_primary_postgis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path = public, x_extension")

    op.execute("DROP INDEX IF EXISTS idx_spbd_buld_polygon_resolve")
    op.execute("DROP INDEX IF EXISTS idx_sprd_manage_rn")
    op.execute("DROP INDEX IF EXISTS idx_sprd_manage_geom")
    op.execute("DROP INDEX IF EXISTS idx_sprd_rw_geom")

    for column in (
        "sig_cd TEXT",
        "emd_cd TEXT",
        "li_cd TEXT",
        "rds_sig_cd TEXT",
        "rn_cd TEXT",
        "buld_se_cd TEXT",
        "buld_mnnm INTEGER",
        "buld_slno INTEGER",
    ):
        op.execute(f"ALTER TABLE IF EXISTS tl_spbd_buld_polygon ADD COLUMN IF NOT EXISTS {column}")

    op.execute("ALTER TABLE IF EXISTS tl_spbd_buld_polygon DROP COLUMN IF EXISTS bjd_cd")
    op.execute("ALTER TABLE IF EXISTS tl_spbd_buld_polygon DROP COLUMN IF EXISTS rncode_full")
    op.execute(
        """
ALTER TABLE IF EXISTS tl_spbd_buld_polygon
  ADD COLUMN bjd_cd TEXT GENERATED ALWAYS AS (
    CASE
      WHEN NULLIF(sig_cd, '') IS NULL OR NULLIF(emd_cd, '') IS NULL THEN NULL
      ELSE sig_cd || emd_cd || COALESCE(NULLIF(li_cd, ''), '00')
    END
  ) STORED
"""
    )
    op.execute(
        """
ALTER TABLE IF EXISTS tl_spbd_buld_polygon
  ADD COLUMN rncode_full TEXT GENERATED ALWAYS AS (
    CASE
      WHEN NULLIF(rds_sig_cd, '') IS NULL OR NULLIF(rn_cd, '') IS NULL THEN NULL
      ELSE rds_sig_cd || rn_cd
    END
  ) STORED
"""
    )

    op.execute("ALTER TABLE IF EXISTS tl_sprd_manage ADD COLUMN IF NOT EXISTS geom geometry(MultiLineString, 5179)")
    op.execute("ALTER TABLE IF EXISTS tl_sprd_manage DROP COLUMN IF EXISTS rncode_full")
    op.execute(
        """
ALTER TABLE IF EXISTS tl_sprd_manage
  ADD COLUMN rncode_full TEXT GENERATED ALWAYS AS (
    CASE
      WHEN NULLIF(sig_cd, '') IS NULL OR NULLIF(rn_cd, '') IS NULL THEN NULL
      ELSE sig_cd || rn_cd
    END
  ) STORED
"""
    )

    op.execute(
        """
ALTER TABLE IF EXISTS tl_sprd_rw
  ALTER COLUMN geom TYPE geometry(MultiPolygon, 5179)
  USING ST_Multi(geom)::geometry(MultiPolygon, 5179)
"""
    )

    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_spbd_buld_polygon_resolve
  ON tl_spbd_buld_polygon (rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd)
"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_sprd_manage_geom ON tl_sprd_manage USING GIST (geom)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sprd_rw_geom ON tl_sprd_rw USING GIST (geom)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sprd_manage_rn ON tl_sprd_manage (rncode_full)")


def downgrade() -> None:
    op.execute("SET search_path = public, x_extension")

    op.execute("DROP INDEX IF EXISTS idx_spbd_buld_polygon_resolve")
    op.execute("DROP INDEX IF EXISTS idx_sprd_manage_rn")
    op.execute("DROP INDEX IF EXISTS idx_sprd_manage_geom")
    op.execute("DROP INDEX IF EXISTS idx_sprd_rw_geom")

    op.execute("ALTER TABLE IF EXISTS tl_spbd_buld_polygon DROP COLUMN IF EXISTS rncode_full")
    op.execute("ALTER TABLE IF EXISTS tl_spbd_buld_polygon DROP COLUMN IF EXISTS bjd_cd")
    for column in (
        "sig_cd",
        "emd_cd",
        "li_cd",
        "rds_sig_cd",
        "rn_cd",
        "buld_se_cd",
        "buld_mnnm",
        "buld_slno",
    ):
        op.execute(f"ALTER TABLE IF EXISTS tl_spbd_buld_polygon DROP COLUMN IF EXISTS {column}")

    op.execute("ALTER TABLE IF EXISTS tl_sprd_manage DROP COLUMN IF EXISTS rncode_full")
    op.execute("ALTER TABLE IF EXISTS tl_sprd_manage DROP COLUMN IF EXISTS geom")

    op.execute(
        """
ALTER TABLE IF EXISTS tl_sprd_rw
  ALTER COLUMN geom TYPE geometry(MultiLineString, 5179)
  USING ST_Multi(ST_Boundary(geom))::geometry(MultiLineString, 5179)
"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_sprd_rw_geom ON tl_sprd_rw USING GIST (geom)")
