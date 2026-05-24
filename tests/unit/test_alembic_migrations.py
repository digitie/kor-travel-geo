from __future__ import annotations

from pathlib import Path


def test_t027_shp_schema_fixups_migration_covers_reviewed_changes() -> None:
    migration = Path("alembic/versions/0002_t027_shp_schema_fixups.py").read_text(
        encoding="utf-8"
    )

    assert "revision = \"0002_t027_shp_schema_fixups\"" in migration
    assert "sig_cd TEXT" in migration
    assert "ADD COLUMN IF NOT EXISTS {column}" in migration
    assert "COALESCE(NULLIF(li_cd, ''), '00')" in migration
    assert "ADD COLUMN IF NOT EXISTS geom geometry(MultiLineString, 5179)" in migration
    assert "ALTER COLUMN geom TYPE geometry(MultiPolygon, 5179)" in migration
