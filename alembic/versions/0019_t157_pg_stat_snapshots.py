"""T-157 pg_stat_statements snapshot persistence

Revision ID: 0019_t157_pg_stat_snapshots
Revises: 0018_t200_ops_id_rename
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op

revision = "0019_t157_pg_stat_snapshots"
down_revision = "0018_t200_ops_id_rename"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.pg_stat_statements_snapshots (
  pg_stat_snapshot_id         UUID PRIMARY KEY,
  captured_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  rank                        INTEGER NOT NULL CHECK (rank >= 1),
  queryid                     TEXT,
  query_fingerprint           TEXT NOT NULL CHECK (
                                char_length(query_fingerprint) BETWEEN 1 AND 64
                              ),
  operation                   TEXT NOT NULL CHECK (char_length(operation) BETWEEN 1 AND 32),
  calls                       BIGINT NOT NULL CHECK (calls >= 0),
  total_exec_time_ms          DOUBLE PRECISION NOT NULL CHECK (total_exec_time_ms >= 0),
  mean_exec_time_ms           DOUBLE PRECISION NOT NULL CHECK (mean_exec_time_ms >= 0),
  max_exec_time_ms            DOUBLE PRECISION NOT NULL CHECK (max_exec_time_ms >= 0),
  rows_returned               BIGINT NOT NULL CHECK (rows_returned >= 0),
  shared_blks_hit             BIGINT NOT NULL DEFAULT 0 CHECK (shared_blks_hit >= 0),
  shared_blks_read            BIGINT NOT NULL DEFAULT 0 CHECK (shared_blks_read >= 0),
  temp_blks_read              BIGINT NOT NULL DEFAULT 0 CHECK (temp_blks_read >= 0),
  temp_blks_written           BIGINT NOT NULL DEFAULT 0 CHECK (temp_blks_written >= 0),
  query_preview               TEXT NOT NULL CHECK (
                                char_length(query_preview) BETWEEN 1 AND 500
                              ),
  stats                       JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_pg_stat_statements_snapshots_captured
  ON ops.pg_stat_statements_snapshots (captured_at DESC, rank);
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_pg_stat_statements_snapshots_fingerprint
  ON ops.pg_stat_statements_snapshots (query_fingerprint, captured_at DESC);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.pg_stat_statements_snapshots")
