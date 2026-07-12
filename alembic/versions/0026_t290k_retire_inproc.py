"""Retire in-process load execution — converge stranded rows + default executor 'dagster' (T-290k)

T-290k deletes the in-process ``JobQueue`` drain: after the PR3 routing cutover no code path
inserts ``executor='api_in_process'`` any more, and there is no drain left to run such a row.
This migration closes the transition:

1. **Convergence** — any ``load_jobs`` row still ``queued``/``running`` under
   ``executor='api_in_process'`` (a pre-cutover leftover) can never make progress now, so it is
   force-failed once, at deploy. This replaces the runtime ``JobQueue.recover_startup`` /
   ``_recover_in_process_running`` behaviour that used to fail such rows on API startup.
2. **Default** — the ``load_jobs.executor`` column default flips ``api_in_process`` → ``dagster``
   so a bare insert (belt-and-suspenders behind ``AdminRepository.insert_load_job``'s
   ``executor='dagster'`` default) records the only executor that still runs work.

The ``CHECK (executor IN ('api_in_process','dagster'))`` is intentionally KEPT (not narrowed to
``= 'dagster'``): historical/converged ``api_in_process`` rows stay in ``load_jobs`` as an audit
trail and must remain valid. The ``load_jobs`` table + the Dagster run store 2-record boundary
(ADR-066 §5/§6) are untouched.

Mirrors the fresh-init default in ``src/kortravelgeo/infra/sql.py`` (SCHEMA_SQL) and
``sql/ddl/001_schema.sql`` (schema-drift 3-place rule).

Revision ID: 0026_t290k_retire_inproc
Revises: 0025_t290h_run_failure_alerts
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op

revision = "0026_t290k_retire_inproc"
down_revision = "0025_t290h_run_failure_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
UPDATE load_jobs
   SET state = 'failed',
       error_message = 'converged: in-process execution retired (T-290k)',
       finished_at = COALESCE(finished_at, now())
 WHERE executor = 'api_in_process'
   AND state IN ('queued', 'running');
"""
    )
    op.execute("ALTER TABLE load_jobs ALTER COLUMN executor SET DEFAULT 'dagster'")


def downgrade() -> None:
    # The one-time convergence is not reversible (the rows are terminal); only the column
    # default is restored.
    op.execute("ALTER TABLE load_jobs ALTER COLUMN executor SET DEFAULT 'api_in_process'")
