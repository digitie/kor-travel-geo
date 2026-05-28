"""T-053 consistency case samples

Revision ID: 0012_t053_consistency_samples
Revises: 0011_t047_pg_stat_statements
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op

revision = "0012_t053_consistency_samples"
down_revision = "0011_t047_pg_stat_statements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.consistency_case_samples (
  sample_id            UUID PRIMARY KEY,
  report_id            TEXT NOT NULL REFERENCES load_consistency_reports(report_id)
                       ON DELETE CASCADE,
  case_code            TEXT NOT NULL CHECK (case_code ~ '^C(10|[1-9])$'),
  severity             TEXT NOT NULL CHECK (severity IN ('OK','INFO','WARN','ERROR')),
  sample_rank          INTEGER NOT NULL DEFAULT 0 CHECK (sample_rank >= 0),
  bd_mgt_sn            TEXT,
  rncode_full          TEXT,
  sig_cd               TEXT,
  bjd_cd               TEXT,
  distance_m           DOUBLE PRECISION,
  source_yyyymm        TEXT,
  source_kind          TEXT,
  case_metric          JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_snapshot      JSONB NOT NULL DEFAULT '{}'::jsonb,
  point_4326           geometry(Point, 4326),
  point_5179           geometry(Point, 5179),
  bbox_4326            JSONB NOT NULL DEFAULT '{}'::jsonb,
  has_polygon          BOOLEAN NOT NULL DEFAULT false,
  has_line             BOOLEAN NOT NULL DEFAULT false,
  decision_state       TEXT NOT NULL DEFAULT 'unreviewed'
                       CHECK (decision_state IN ('unreviewed','approved','rejected','deferred')),
  reason_code          TEXT,
  note                 TEXT,
  reviewed_by          TEXT,
  reviewed_at          TIMESTAMPTZ,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_report
  ON ops.consistency_case_samples (report_id, case_code, severity, decision_state)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_case_severity
  ON ops.consistency_case_samples (case_code, severity, distance_m DESC)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_sig
  ON ops.consistency_case_samples (sig_cd, case_code)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_review
  ON ops.consistency_case_samples (report_id, case_code, decision_state, reviewed_at DESC)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_samples_4326
  ON ops.consistency_case_samples USING GIST (point_4326)
"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ops.idx_ops_consistency_case_samples_4326")
    op.execute("DROP INDEX IF EXISTS ops.idx_ops_consistency_case_samples_review")
    op.execute("DROP INDEX IF EXISTS ops.idx_ops_consistency_case_samples_sig")
    op.execute("DROP INDEX IF EXISTS ops.idx_ops_consistency_case_samples_case_severity")
    op.execute("DROP INDEX IF EXISTS ops.idx_ops_consistency_case_samples_report")
    op.execute("DROP TABLE IF EXISTS ops.consistency_case_samples")
