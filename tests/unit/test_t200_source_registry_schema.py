from __future__ import annotations

from pathlib import Path

from kortravelgeo.infra.sql import INDEX_SQL, SCHEMA_SQL

_NEW_TABLES = (
    "ops.source_file_groups",
    "ops.source_files",
    "ops.source_file_members",
    "ops.source_file_validations",
    "ops.source_upload_sessions",
    "ops.source_upload_session_parts",
    "ops.source_match_sets",
    "ops.source_match_set_items",
    "ops.source_storage_reconcile_runs",
    "ops.source_storage_reconcile_items",
    "ops.consistency_case_definitions",
    "ops.consistency_case_inputs",
)


def test_new_source_registry_tables_are_declared_in_schema_sql() -> None:
    for table_name in _NEW_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {table_name} (" in SCHEMA_SQL


def test_one_active_match_set_and_snapshot_link_indexes_exist() -> None:
    assert "idx_ops_source_match_sets_one_active" in INDEX_SQL
    assert "ON ops.source_match_sets (state) WHERE state = 'active'" in INDEX_SQL
    assert "idx_ops_dataset_snapshots_source_match_set_id" in INDEX_SQL
    assert (
        "ON ops.dataset_snapshots (source_match_set_id) WHERE source_match_set_id IS NOT NULL"
        in INDEX_SQL
    )


def test_case_code_check_is_relaxed_to_generic_c_pattern() -> None:
    assert "case_code ~ '^C\\d+$'" in SCHEMA_SQL
    assert "case_code ~ '^C(10|[1-9])$'" not in SCHEMA_SQL


def test_dataset_snapshots_gains_source_match_set_id_column_and_fk() -> None:
    assert "source_match_set_id         UUID," in SCHEMA_SQL
    assert "fk_ops_dataset_snapshots_source_match_set" in SCHEMA_SQL


def test_available_validation_cross_check_on_groups_and_files() -> None:
    assert "chk_ops_source_file_groups_available_validation" in SCHEMA_SQL
    assert "chk_ops_source_files_available_validation" in SCHEMA_SQL


def test_migration_0016_exists_with_expected_revisions() -> None:
    migration = Path("alembic/versions/0016_t200_source_registry.py").read_text(
        encoding="utf-8"
    )

    assert 'revision = "0016_t200_source_registry"' in migration
    assert 'down_revision = "0015_t075_region_radius_parts"' in migration
    assert "CREATE TABLE IF NOT EXISTS ops.source_match_sets" in migration
    assert "idx_ops_source_match_sets_one_active" in migration
    assert "fk_ops_dataset_snapshots_source_match_set" in migration
    assert "consistency_case_samples_case_code_check" in migration
