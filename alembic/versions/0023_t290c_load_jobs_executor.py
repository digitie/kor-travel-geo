"""load_jobs executor / orchestrator_run_id / lease metadata (T-290c)

Adds the executor-boundary columns that let ``JobQueue`` become executor-aware
*before* Dagster is wired in as an actual executor (ADR-066 §5, dagster-boundary §6):

* ``executor``            — execution owner (``api_in_process`` | ``dagster``).
* ``orchestrator_run_id`` — Dagster run id backing a ``dagster``-executed job.
* ``lease_expires_at``    — worker/lease heartbeat expiry for executor-aware recovery.

Backward compatible: every existing row defaults to ``api_in_process`` so startup
recovery keeps force-failing interrupted in-process jobs exactly as before. Mirrors the
fresh-init DDL in ``src/kortravelgeo/infra/sql.py`` (SCHEMA_SQL / INDEX_SQL),
``sql/ddl/001_schema.sql`` and ``sql/indexes.sql`` (schema-drift 3-place rule).

Revision ID: 0023_t290c_load_jobs_executor
Revises: 0022_public_api_keys
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op

revision = "0023_t290c_load_jobs_executor"
down_revision = "0022_public_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE load_jobs
  ADD COLUMN IF NOT EXISTS executor TEXT NOT NULL DEFAULT 'api_in_process',
  ADD COLUMN IF NOT EXISTS orchestrator_run_id TEXT,
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
"""
    )
    # ADD CONSTRAINT has no IF NOT EXISTS in Postgres; guard so re-apply is idempotent.
    op.execute(
        """
DO $$
BEGIN
  ALTER TABLE load_jobs
    ADD CONSTRAINT load_jobs_executor_check
    CHECK (executor IN ('api_in_process','dagster'));
EXCEPTION WHEN duplicate_object THEN
  NULL;
END;
$$;
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_load_jobs_dagster_running
  ON load_jobs (lease_expires_at)
  WHERE executor = 'dagster' AND state = 'running';
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_load_jobs_dagster_running")
    op.execute("ALTER TABLE load_jobs DROP CONSTRAINT IF EXISTS load_jobs_executor_check")
    op.execute(
        """
ALTER TABLE load_jobs
  DROP COLUMN IF EXISTS lease_expires_at,
  DROP COLUMN IF EXISTS orchestrator_run_id,
  DROP COLUMN IF EXISTS executor;
"""
    )
