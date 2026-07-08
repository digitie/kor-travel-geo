"""Dagster terminal orphan reconciler index (T-290c)

Revision ID: 0024_t290c_orphan_idx
Revises: 0023_t290c_load_jobs_executor
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op

revision = "0024_t290c_orphan_idx"
down_revision = "0023_t290c_load_jobs_executor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_load_jobs_dagster_terminal_orphan
  ON load_jobs (created_at)
  WHERE executor = 'dagster'
    AND state IN ('failed','cancelled')
    AND orchestrator_run_id IS NOT NULL;
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_load_jobs_dagster_terminal_orphan")
