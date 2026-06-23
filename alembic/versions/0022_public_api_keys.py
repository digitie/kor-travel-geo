"""Public API key registry

Revision ID: 0022_public_api_keys
Revises: 0021_t158_slow_observability
Create Date: 2026-06-23
"""

from __future__ import annotations

from alembic import op

revision = "0022_public_api_keys"
down_revision = "0021_t158_slow_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.public_api_keys (
  public_api_key_id UUID PRIMARY KEY,
  key_hash          TEXT NOT NULL UNIQUE CHECK (key_hash ~ '^[0-9a-f]{64}$'),
  key_hint          TEXT NOT NULL CHECK (char_length(key_hint) BETWEEN 6 AND 12),
  label             TEXT CHECK (label IS NULL OR char_length(label) BETWEEN 1 AND 80),
  state             TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','revoked')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by        TEXT,
  revoked_at        TIMESTAMPTZ,
  revoked_by        TEXT,
  CHECK (
    (state = 'active' AND revoked_at IS NULL AND revoked_by IS NULL)
    OR (state = 'revoked' AND revoked_at IS NOT NULL)
  )
);
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_public_api_keys_active_hash
  ON ops.public_api_keys (key_hash)
  WHERE state = 'active';
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_public_api_keys_created_at
  ON ops.public_api_keys (created_at DESC);
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.public_api_keys")
