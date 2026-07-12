"""ops.run_failure_alerts — Dagster run-failure alert ledger (T-290h)

Cross-run persistent history of Dagster run failures. Written by the Dagster
``run_failure_sensor`` through the ``client`` resource (dagster-boundary §3/§6),
read back by the admin observe API (run detail ``failure_alert`` + the recent
``run-failures`` list). Only bounded fields are stored — ``error_code`` is the
failure error *class* name, never the raw failure message (dagster-boundary §5).

``run_id`` (the Dagster run id) is the PK, so re-firing the sensor for the same
failed run is idempotent. ``acknowledged_at`` is UPDATE-able (unlike the
append-only ``ops.audit_events``), so the table carries no immutability trigger.
``job_id``/``job_kind`` are nullable: a run may fail without a
``kor_travel_geo.job_id`` tag (e.g. ``mv_refresh``).

Mirrors the fresh-init DDL in ``src/kortravelgeo/infra/sql.py`` (SCHEMA_SQL /
INDEX_SQL), ``sql/ddl/001_schema.sql`` and ``sql/indexes.sql`` (schema-drift
3-place rule).

Revision ID: 0025_t290h_run_failure_alerts
Revises: 0024_t290c_orphan_idx
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op

revision = "0025_t290h_run_failure_alerts"
down_revision = "0024_t290c_orphan_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.run_failure_alerts (
  run_id          TEXT PRIMARY KEY,
  job_id          TEXT,
  job_name        TEXT,
  job_kind        TEXT,
  status          TEXT NOT NULL,
  error_code      TEXT,
  run_failed_at   TIMESTAMPTZ NOT NULL,
  recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  acknowledged_at TIMESTAMPTZ
);
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_run_failure_alerts_unacked_recent
  ON ops.run_failure_alerts (run_failed_at DESC)
  WHERE acknowledged_at IS NULL;
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ops.idx_ops_run_failure_alerts_unacked_recent")
    op.execute("DROP TABLE IF EXISTS ops.run_failure_alerts")
