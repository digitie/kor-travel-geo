"""T-047 pg_stat_statements extension

Revision ID: 0011_t047_pg_stat_statements
Revises: 0010_t047_search_exact_indexes
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op

revision = "0011_t047_pg_stat_statements"
down_revision = "0010_t047_search_exact_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS x_extension")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA x_extension")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
