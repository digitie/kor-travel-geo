"""T-049 operational metadata schema

Revision ID: 0006_t049_ops_metadata_schema
Revises: 0005_t039_roadaddr_entrc
Create Date: 2026-05-27
"""

from __future__ import annotations

from alembic import op

from kraddr.geo.infra.sql import INDEX_SQL, SCHEMA_SQL, iter_sql_statements

revision = "0006_t049_ops_metadata_schema"
down_revision = "0005_t039_roadaddr_entrc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for sql in iter_sql_statements(SCHEMA_SQL):
        if "ops." in sql or sql == "CREATE SCHEMA IF NOT EXISTS ops":
            op.execute(sql)
    for sql in iter_sql_statements(INDEX_SQL):
        if "idx_ops_" in sql:
            op.execute(sql)


def downgrade() -> None:
    for index_name in (
        "idx_ops_table_stats_snapshots_captured",
        "idx_ops_maintenance_windows_active",
        "idx_ops_artifacts_type_created",
        "idx_ops_serving_releases_one_active",
        "idx_ops_serving_releases_created",
        "idx_ops_dataset_snapshots_created",
        "idx_ops_audit_events_action",
        "idx_ops_audit_events_occurred",
    ):
        op.execute(f"DROP INDEX IF EXISTS ops.{index_name}")

    op.execute("DROP TRIGGER IF EXISTS trg_ops_audit_events_append_only ON ops.audit_events")
    for table_name in (
        "table_stats_snapshots",
        "maintenance_windows",
        "artifacts",
        "serving_releases",
        "dataset_snapshots",
        "audit_events",
    ):
        op.execute(f"DROP TABLE IF EXISTS ops.{table_name} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS ops.audit_events_append_only()")
    op.execute("DROP SCHEMA IF EXISTS ops")
