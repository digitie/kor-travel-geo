"""T-200 follow-up: full-prefix ops ID rename (breaking)

Renames the ``ops`` schema PK/FK columns that still carried short, ambiguous
names to fully-prefixed names so every cross-table reference is unambiguous
(the deferred breaking change from T-200). PostgreSQL keeps the PRIMARY KEY,
FOREIGN KEY, and self-referencing FK constraints attached to a column across a
``RENAME COLUMN`` (the constraint follows the column), so no constraint/index
re-creation is required — only the column names change.

Full mapping (old -> new):
  ops.audit_events.event_id                          -> audit_event_id
  ops.dataset_snapshots.snapshot_id                  -> dataset_snapshot_id (PK)
  ops.dataset_snapshots.parent_snapshot_id           -> parent_dataset_snapshot_id
  ops.serving_releases.release_id                    -> serving_release_id (PK)
  ops.serving_releases.snapshot_id                   -> dataset_snapshot_id (FK)
  ops.serving_releases.previous_release_id           -> previous_serving_release_id
  ops.serving_releases.rollback_target_release_id    -> rollback_target_serving_release_id
  ops.maintenance_windows.window_id                  -> maintenance_window_id
  ops.table_stats_snapshots.stats_id                 -> table_stats_snapshot_id
  ops.table_stats_snapshots.snapshot_id              -> dataset_snapshot_id (FK)
  ops.artifacts.snapshot_id                          -> dataset_snapshot_id (FK)
  ops.artifacts.release_id                           -> serving_release_id (FK)

Revision ID: 0018_t200_ops_id_rename
Revises: 0017_t206_consistency_seed
Create Date: 2026-06-15
"""

from __future__ import annotations

from alembic import op

revision = "0018_t200_ops_id_rename"
down_revision = "0017_t206_consistency_seed"
branch_labels = None
depends_on = None


#: (table, old_column, new_column). Order matters only for readability — a
#: RENAME COLUMN on a referenced PK transparently updates dependent FK
#: definitions, and dependent FK columns are renamed independently below.
_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("ops.audit_events", "event_id", "audit_event_id"),
    ("ops.dataset_snapshots", "snapshot_id", "dataset_snapshot_id"),
    ("ops.dataset_snapshots", "parent_snapshot_id", "parent_dataset_snapshot_id"),
    ("ops.serving_releases", "release_id", "serving_release_id"),
    ("ops.serving_releases", "snapshot_id", "dataset_snapshot_id"),
    ("ops.serving_releases", "previous_release_id", "previous_serving_release_id"),
    (
        "ops.serving_releases",
        "rollback_target_release_id",
        "rollback_target_serving_release_id",
    ),
    ("ops.maintenance_windows", "window_id", "maintenance_window_id"),
    ("ops.table_stats_snapshots", "stats_id", "table_stats_snapshot_id"),
    ("ops.table_stats_snapshots", "snapshot_id", "dataset_snapshot_id"),
    ("ops.artifacts", "snapshot_id", "dataset_snapshot_id"),
    ("ops.artifacts", "release_id", "serving_release_id"),
)


def _rename_column(table: str, old: str, new: str) -> None:
    """Idempotent RENAME COLUMN: only rename when the old column still exists
    and the new one does not (so a partially-applied upgrade is recoverable)."""

    schema, _, name = table.partition(".")
    op.execute(
        f"""
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
     WHERE table_schema = '{schema}' AND table_name = '{name}'
       AND column_name = '{old}'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
     WHERE table_schema = '{schema}' AND table_name = '{name}'
       AND column_name = '{new}'
  ) THEN
    ALTER TABLE {table} RENAME COLUMN {old} TO {new};
  END IF;
END
$$;
"""
    )


def upgrade() -> None:
    for table, old, new in _RENAMES:
        _rename_column(table, old, new)


def downgrade() -> None:
    for table, old, new in reversed(_RENAMES):
        _rename_column(table, new, old)
