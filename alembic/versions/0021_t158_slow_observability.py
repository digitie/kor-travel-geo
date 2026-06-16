"""T-158 sampled slow observability persistence

Revision ID: 0021_t158_slow_observability
Revises: 0020_t171_fuzzy_ranking
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op

revision = "0021_t158_slow_observability"
down_revision = "0020_t171_fuzzy_ranking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.slow_observability_samples (
  slow_sample_id              UUID PRIMARY KEY,
  captured_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  sample_type                 TEXT NOT NULL CHECK (
                                sample_type IN ('api_request','db_query','overload')
                              ),
  method                      TEXT,
  route                       TEXT,
  status_code                 INTEGER,
  elapsed_ms                  DOUBLE PRECISION NOT NULL CHECK (elapsed_ms >= 0),
  threshold_ms                INTEGER CHECK (threshold_ms IS NULL OR threshold_ms >= 0),
  sample_rate                 DOUBLE PRECISION NOT NULL CHECK (
                                sample_rate >= 0 AND sample_rate <= 1
                              ),
  operation                   TEXT CHECK (
                                operation IS NULL
                                OR char_length(operation) BETWEEN 1 AND 32
                              ),
  query_fingerprint           TEXT CHECK (
                                query_fingerprint IS NULL
                                OR char_length(query_fingerprint) BETWEEN 1 AND 64
                              ),
  query_preview               TEXT CHECK (
                                query_preview IS NULL
                                OR char_length(query_preview) BETWEEN 1 AND 500
                              ),
  plan                        JSONB NOT NULL DEFAULT '{}'::jsonb,
  context                     JSONB NOT NULL DEFAULT '{}'::jsonb
);
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_slow_observability_samples_captured
  ON ops.slow_observability_samples (captured_at DESC, sample_type);
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_slow_observability_samples_route
  ON ops.slow_observability_samples (route, captured_at DESC)
  WHERE route IS NOT NULL;
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_slow_observability_samples_query
  ON ops.slow_observability_samples (query_fingerprint, captured_at DESC)
  WHERE query_fingerprint IS NOT NULL;
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.slow_observability_samples")
