"""T-075 region radius lookup accelerator

Revision ID: 0015_t075_region_radius_parts
Revises: 0014_t065_navi_name_search
Create Date: 2026-06-02
"""

from __future__ import annotations

from alembic import op

from kraddr.geo.infra.sql import REGION_RADIUS_PARTS_REFRESH_SQL, iter_sql_statements

revision = "0015_t075_region_radius_parts"
down_revision = "0014_t065_navi_name_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute("SET LOCAL statement_timeout = 0")
    for sql in iter_sql_statements(REGION_RADIUS_PARTS_REFRESH_SQL):
        op.execute(sql)


def downgrade() -> None:
    op.execute("SET search_path = public, x_extension")
    op.execute("DROP TABLE IF EXISTS region_radius_parts")
