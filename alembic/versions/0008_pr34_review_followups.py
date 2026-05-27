"""PR #34 이후 리뷰 후속 스키마 보강

Revision ID: 0008_pr34_review_followups
Revises: 0007_t042_sppn_makarea
Create Date: 2026-05-27
"""

from __future__ import annotations

from alembic import op

revision = "0008_pr34_review_followups"
down_revision = "0007_t042_sppn_makarea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
ALTER TABLE ops.audit_events
  DROP CONSTRAINT IF EXISTS audit_events_job_id_fkey
"""
    )
    op.execute(
        """
ALTER TABLE ops.audit_events
  ADD CONSTRAINT audit_events_job_id_fkey
  FOREIGN KEY (job_id) REFERENCES load_jobs(job_id) ON DELETE NO ACTION
"""
    )


def downgrade() -> None:
    op.execute(
        """
ALTER TABLE ops.audit_events
  DROP CONSTRAINT IF EXISTS audit_events_job_id_fkey
"""
    )
    op.execute(
        """
ALTER TABLE ops.audit_events
  ADD CONSTRAINT audit_events_job_id_fkey
  FOREIGN KEY (job_id) REFERENCES load_jobs(job_id) ON DELETE SET NULL
"""
    )
