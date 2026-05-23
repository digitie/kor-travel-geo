"""Initial PostgreSQL and PostGIS schema."""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001_initial_postgis_schema"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILES: tuple[str, ...] = (
    "sql/ddl/001_extensions.sql",
    "sql/ddl/010_master_tables.sql",
    "sql/ddl/020_auxiliary_tables.sql",
    "sql/ddl/030_meta_tables.sql",
    "sql/indexes.sql",
    "sql/mv.sql",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_sql(relative_path: str) -> str:
    return (_repo_root() / relative_path).read_text(encoding="utf-8")


def upgrade() -> None:
    connection = op.get_bind()
    for relative_path in SQL_FILES:
        connection.exec_driver_sql(_read_sql(relative_path))


def downgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target")
    for table_name in (
        "geo_cache",
        "load_codes",
        "load_jobs",
        "load_manifest",
        "postal_bulk_delivery",
        "postal_pobox",
        "tl_spbd_entrc",
        "tl_spbd_buld",
        "tl_spbd_eqb",
        "tl_sprd_rw",
        "tl_sprd_intrvl",
        "tl_sprd_manage",
        "tl_kodis_bas",
        "tl_scco_li",
        "tl_scco_emd",
        "tl_scco_sig",
        "tl_scco_ctprvn",
    ):
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table_name} CASCADE")
