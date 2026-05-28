from __future__ import annotations

from pathlib import Path


def _migration_revision_lines() -> list[str]:
    lines: list[str] = []
    for path in sorted(Path("alembic/versions").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(("revision = ", "down_revision = ")):
                lines.append(line)
    return lines


def test_alembic_revision_ids_fit_default_version_table() -> None:
    for line in _migration_revision_lines():
        if "None" in line:
            continue
        revision_id = line.split("=", 1)[1].strip().strip('"')
        assert len(revision_id) <= 32


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
    assert "down_revision = \"0005_t039_roadaddr_entrc\"" in migration
    assert "CREATE SCHEMA IF NOT EXISTS ops" in migration
    assert "idx_ops_serving_releases_one_active" in migration
    assert "audit_events_append_only" in migration
    assert '"table_stats_snapshots"' in migration


def test_t042_sppn_makarea_migration_covers_table_and_indexes() -> None:
    migration = Path("alembic/versions/0007_t042_sppn_makarea.py").read_text(
        encoding="utf-8"
    )

    assert "revision = \"0007_t042_sppn_makarea\"" in migration
    assert "down_revision = \"0006_t049_ops_metadata_schema\"" in migration
    assert "CREATE TABLE IF NOT EXISTS tl_sppn_makarea" in migration
    assert "geometry(MultiPolygon, 5179) NOT NULL" in migration
    assert "PRIMARY KEY (sig_cd, makarea_id)" in migration
    assert "idx_sppn_makarea_geom" in migration
    assert "DROP TABLE IF EXISTS tl_sppn_makarea" in migration


def test_pr34_review_followups_migration_preserves_audit_job_links() -> None:
    migration = Path("alembic/versions/0008_pr34_review_followups.py").read_text(
        encoding="utf-8"
    )

    assert "revision = \"0008_pr34_review_followups\"" in migration
    assert "down_revision = \"0007_t042_sppn_makarea\"" in migration
    assert "DROP CONSTRAINT IF EXISTS audit_events_job_id_fkey" in migration
    assert "ON DELETE NO ACTION" in migration
    assert "ON DELETE SET NULL" in migration
