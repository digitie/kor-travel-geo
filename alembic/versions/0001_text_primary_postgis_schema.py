"""text primary PostGIS schema

Revision ID: 0001_text_primary_postgis
Revises:
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op

from kraddr.geo.infra.sql import INDEX_SQL, MV_SQL, POSTLOAD_SQL, SCHEMA_SQL, iter_sql_statements

revision = "0001_text_primary_postgis"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for sql in iter_sql_statements(SCHEMA_SQL):
        op.execute(sql)
    for sql in iter_sql_statements(INDEX_SQL):
        op.execute(sql)
    for sql in iter_sql_statements(POSTLOAD_SQL):
        op.execute(sql)
    for sql in iter_sql_statements(MV_SQL):
        op.execute(sql)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target")
    op.execute("DROP SCHEMA IF EXISTS ops CASCADE")
    for table in (
        "geo_cache",
        "load_consistency_reports",
        "load_jobs",
        "load_codes",
        "load_manifest",
        "postal_bulk_delivery",
        "postal_pobox",
        "tl_sprd_rw",
        "tl_sprd_intrvl",
        "tl_sprd_manage",
        "tl_spbd_buld_polygon",
        "tl_kodis_bas",
        "tl_scco_li",
        "tl_scco_emd",
        "tl_scco_sig",
        "tl_scco_ctprvn",
        "tl_navi_entrc",
        "tl_navi_buld_centroid",
        "tl_roadaddr_entrc",
        "tl_locsum_entrc",
        "tl_juso_parcel_link",
        "tl_juso_text",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
