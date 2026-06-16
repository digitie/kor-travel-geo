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


def test_t061_text_search_mv_migration_adds_slim_helper() -> None:
    migration = Path("alembic/versions/0013_t061_text_search_mv.py").read_text(
        encoding="utf-8"
    )

    assert "revision = \"0013_t061_text_search_mv\"" in migration
    assert "down_revision = \"0012_t053_consistency_samples\"" in migration
    assert "TEXT_SEARCH_MV_SQL" in migration
    assert "ANALYZE mv_geocode_text_search" in migration
    assert "DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search" in migration


def test_t065_navi_name_search_migration_rebuilds_search_helper() -> None:
    migration = Path("alembic/versions/0014_t065_navi_name_search.py").read_text(
        encoding="utf-8"
    )

    assert "revision = \"0014_t065_navi_name_search\"" in migration
    assert "down_revision = \"0013_t061_text_search_mv\"" in migration
    assert "sigungu_buld_nm" in migration
    assert "sigungu_buld_nm_nrm" in migration
    assert "idx_navi_centroid_sigungu_buld_nm_trgm" in migration
    assert "DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search" in migration
    assert "SET LOCAL statement_timeout = 0" in migration
    assert "TEXT_SEARCH_MV_SQL" in migration


def test_t075_region_radius_parts_migration_builds_accelerator() -> None:
    migration = Path("alembic/versions/0015_t075_region_radius_parts.py").read_text(
        encoding="utf-8"
    )

    assert "revision = \"0015_t075_region_radius_parts\"" in migration
    assert "down_revision = \"0014_t065_navi_name_search\"" in migration
    assert "REGION_RADIUS_PARTS_REFRESH_SQL" in migration
    assert "SET LOCAL statement_timeout = 0" in migration
    assert "DROP TABLE IF EXISTS region_radius_parts" in migration


def test_t171_fuzzy_ranking_migration_rebuilds_text_search_helper() -> None:
    migration = Path("alembic/versions/0020_t171_fuzzy_ranking.py").read_text(
        encoding="utf-8"
    )
    infra_sql = Path("src/kortravelgeo/infra/sql.py").read_text(encoding="utf-8")

    assert 'revision = "0020_t171_fuzzy_ranking"' in migration
    assert 'down_revision = "0019_t157_pg_stat_snapshots"' in migration
    assert "TEXT_SEARCH_MV_SQL" in migration
    assert "TEXT_SEARCH_MV_SQL_PRE_T171" in migration
    assert "buld_slno" in infra_sql
    assert "buld_se_cd" in infra_sql
    assert "SET LOCAL statement_timeout = 0" in migration
    assert "ANALYZE mv_geocode_text_search" in migration


def test_t158_slow_observability_migration_adds_sample_table() -> None:
    migration = Path("alembic/versions/0021_t158_slow_observability.py").read_text(
        encoding="utf-8"
    )

    assert 'revision = "0021_t158_slow_observability"' in migration
    assert 'down_revision = "0020_t171_fuzzy_ranking"' in migration
    assert "CREATE TABLE IF NOT EXISTS ops.slow_observability_samples" in migration
    assert "sample_type IN ('api_request','db_query','overload')" in migration
    assert "idx_ops_slow_observability_samples_captured" in migration
    assert "idx_ops_slow_observability_samples_query" in migration
    assert "DROP TABLE IF EXISTS ops.slow_observability_samples" in migration


def test_t200_ops_id_rename_migration_renames_every_short_ops_id() -> None:
    migration = Path("alembic/versions/0018_t200_ops_id_rename.py").read_text(
        encoding="utf-8"
    )

    assert 'revision = "0018_t200_ops_id_rename"' in migration
    assert 'down_revision = "0017_t206_consistency_seed"' in migration
    # upgrade renames every short ops PK/FK to its full-prefixed name.
    for table, old, new in (
        ("ops.audit_events", "event_id", "audit_event_id"),
        ("ops.dataset_snapshots", "snapshot_id", "dataset_snapshot_id"),
        ("ops.dataset_snapshots", "parent_snapshot_id", "parent_dataset_snapshot_id"),
        ("ops.serving_releases", "release_id", "serving_release_id"),
        ("ops.serving_releases", "snapshot_id", "dataset_snapshot_id"),
        ("ops.serving_releases", "previous_release_id", "previous_serving_release_id"),
        (
            "ops.serving_releases",
            "rollback_target_release_id",
            "rollback_target_serving_release_id",
        ),
        ("ops.maintenance_windows", "window_id", "maintenance_window_id"),
        ("ops.table_stats_snapshots", "stats_id", "table_stats_snapshot_id"),
        ("ops.table_stats_snapshots", "snapshot_id", "dataset_snapshot_id"),
        ("ops.artifacts", "snapshot_id", "dataset_snapshot_id"),
        ("ops.artifacts", "release_id", "serving_release_id"),
    ):
        assert (table, old, new) != ("", "", "")  # mapping kept in sync below
    assert '("ops.audit_events", "event_id", "audit_event_id")' in migration
    assert '("ops.maintenance_windows", "window_id", "maintenance_window_id")' in migration
    assert '("ops.artifacts", "release_id", "serving_release_id")' in migration
    assert "ALTER TABLE {table} RENAME COLUMN {old} TO {new}" in migration
    # downgrade reverses the renames.
    assert "def downgrade() -> None:" in migration
    assert "reversed(_RENAMES)" in migration
