"""T-061 slim text-search materialized view

Revision ID: 0013_t061_text_search_mv
Revises: 0012_t053_consistency_samples
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op

from kraddr.geo.infra.sql import TEXT_SEARCH_MV_SQL, iter_sql_statements

revision = "0013_t061_text_search_mv"
down_revision = "0012_t053_consistency_samples"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for sql in iter_sql_statements(TEXT_SEARCH_MV_SQL):
        op.execute(sql)
    op.execute("ANALYZE mv_geocode_text_search")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search")
