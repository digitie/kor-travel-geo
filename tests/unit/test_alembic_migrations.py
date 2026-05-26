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
    assert "GeometryType(geom) NOT IN ('POLYGON', 'MULTIPOLYGON')" in migration
    assert "TRUNCATE TABLE tl_sprd_rw" in migration
    assert "ALTER COLUMN geom TYPE geometry(MultiPolygon, 5179)" in migration


def test_t032_performance_index_migration_covers_resolve_key() -> None:
    migration = Path("alembic/versions/0003_t032_performance_indexes.py").read_text(
        encoding="utf-8"
    )

    assert "revision = \"0003_t032_performance_indexes\"" in migration
    assert "down_revision = \"0002_t027_shp_schema_fixups\"" in migration
    assert "CREATE INDEX IF NOT EXISTS idx_juso_text_resolve" in migration
    assert "rncode_full, buld_se_cd, buld_mnnm, buld_slno, bjd_cd, zip_no" in migration
    assert "DROP INDEX IF EXISTS idx_juso_text_resolve" in migration


def test_t049_ops_metadata_migration_covers_ops_schema() -> None:
    migration = Path("alembic/versions/0006_t049_ops_metadata_schema.py").read_text(
        encoding="utf-8"
    )

    assert "revision = \"0006_t049_ops_metadata_schema\"" in migration
    assert "down_revision = \"0005_t039_roadaddr_entrance_table\"" in migration
    assert "CREATE SCHEMA IF NOT EXISTS ops" in migration
    assert "idx_ops_serving_releases_one_active" in migration
    assert "audit_events_append_only" in migration
    assert '"table_stats_snapshots"' in migration
