"""T-200 source file registry, match sets, and consistency case definitions

Revision ID: 0016_t200_source_registry
Revises: 0015_t075_region_radius_parts
Create Date: 2026-06-14
"""

from __future__ import annotations

from alembic import op

revision = "0016_t200_source_registry"
down_revision = "0015_t075_region_radius_parts"
branch_labels = None
depends_on = None


_NEW_TABLES = (
    "consistency_case_inputs",
    "consistency_case_definitions",
    "source_storage_reconcile_items",
    "source_storage_reconcile_runs",
    "source_match_set_items",
    "source_match_sets",
    "source_upload_session_parts",
    "source_upload_sessions",
    "source_file_validations",
    "source_file_members",
    "source_files",
    "source_file_groups",
)

_NEW_INDEXES = (
    "idx_ops_source_match_sets_one_active",
    "idx_ops_source_file_groups_category_state",
    "idx_ops_source_files_group",
    "idx_ops_source_files_object",
    "idx_ops_source_file_members_file",
    "idx_ops_source_file_validations_group",
    "idx_ops_source_upload_sessions_category",
    "idx_ops_source_storage_reconcile_items_run",
    "idx_ops_source_match_set_items_group",
    "idx_ops_consistency_case_definitions_order",
    "idx_ops_dataset_snapshots_source_match_set_id",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_file_groups (
  source_file_group_id  UUID PRIMARY KEY,
  category              TEXT NOT NULL,
  group_kind            TEXT NOT NULL,
  display_name          TEXT NOT NULL,
  state                 TEXT NOT NULL,
  validation_state      TEXT NOT NULL,
  user_yyyymm           TEXT NOT NULL,
  inferred_yyyymm       TEXT,
  inferred_yyyymm_basis TEXT,
  yyyymm_mismatch       BOOLEAN NOT NULL DEFAULT false,
  expected_file_count   INTEGER NOT NULL DEFAULT 1 CHECK (expected_file_count >= 1),
  actual_file_count     INTEGER NOT NULL DEFAULT 0 CHECK (actual_file_count >= 0),
  coverage              JSONB NOT NULL DEFAULT '{}'::jsonb,
  group_sha256          TEXT,
  uploaded_by           TEXT,
  uploaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at          TIMESTAMPTZ,
  deleted_at            TIMESTAMPTZ,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_summary    JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_file_groups_group_kind
    CHECK (group_kind IN ('single_file', 'multi_part')),
  CONSTRAINT chk_ops_source_file_groups_user_yyyymm
    CHECK (user_yyyymm ~ '^\\d{6}$'),
  CONSTRAINT chk_ops_source_file_groups_inferred_yyyymm
    CHECK (inferred_yyyymm IS NULL OR inferred_yyyymm ~ '^\\d{6}$'),
  CONSTRAINT chk_ops_source_file_groups_group_sha256
    CHECK (group_sha256 IS NULL OR char_length(group_sha256) = 64),
  CONSTRAINT chk_ops_source_file_groups_state CHECK (state IN (
    'validating',
    'available',
    'quarantined',
    'missing',
    'soft_deleted',
    'hard_deleted',
    'delete_failed'
  )),
  CONSTRAINT chk_ops_source_file_groups_validation_state CHECK (validation_state IN (
    'unknown',
    'not_started',
    'running',
    'passed',
    'warning',
    'failed',
    'skipped'
  )),
  CONSTRAINT chk_ops_source_file_groups_available_validation
    CHECK (state <> 'available' OR validation_state IN ('passed','warning'))
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_files (
  source_file_id        UUID PRIMARY KEY,
  source_file_group_id  UUID NOT NULL REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  original_filename     TEXT NOT NULL,
  part_kind             TEXT NOT NULL DEFAULT 'single',
  part_key              TEXT NOT NULL DEFAULT 'archive',
  part_label            TEXT,
  file_role             TEXT,
  content_type          TEXT,
  compression_format    TEXT NOT NULL,
  state                 TEXT NOT NULL,
  validation_state      TEXT NOT NULL,
  size_bytes            BIGINT NOT NULL CHECK (size_bytes >= 0),
  sha256                TEXT NOT NULL,
  duplicate_of_file_id  UUID REFERENCES ops.source_files(source_file_id) ON DELETE SET NULL,
  storage_kind          TEXT NOT NULL,
  storage_uri           TEXT NOT NULL,
  bucket                TEXT,
  object_key            TEXT,
  object_etag           TEXT,
  object_version_id     TEXT,
  last_verified_etag    TEXT,
  last_verified_size_bytes BIGINT,
  last_verified_at      TIMESTAMPTZ,
  last_deep_verified_at TIMESTAMPTZ,
  rustfs_endpoint_hash  TEXT,
  uploaded_by           TEXT,
  uploaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at          TIMESTAMPTZ,
  deleted_at            TIMESTAMPTZ,
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb,
  validation_summary    JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_files_part_kind
    CHECK (part_kind IN ('single', 'sido', 'grid_layer', 'custom')),
  CONSTRAINT chk_ops_source_files_sha256
    CHECK (char_length(sha256) = 64),
  CONSTRAINT chk_ops_source_files_last_verified_size
    CHECK (last_verified_size_bytes IS NULL OR last_verified_size_bytes >= 0),
  CONSTRAINT chk_ops_source_files_state CHECK (state IN (
    'validating',
    'available',
    'quarantined',
    'missing',
    'soft_deleted',
    'hard_deleted',
    'delete_failed'
  )),
  CONSTRAINT chk_ops_source_files_validation_state CHECK (validation_state IN (
    'unknown',
    'not_started',
    'running',
    'passed',
    'warning',
    'failed',
    'skipped'
  )),
  CONSTRAINT chk_ops_source_files_available_validation
    CHECK (state <> 'available' OR validation_state IN ('passed','warning'))
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_file_members (
  source_file_member_id UUID PRIMARY KEY,
  source_file_id     UUID NOT NULL REFERENCES ops.source_files(source_file_id) ON DELETE RESTRICT,
  member_path        TEXT NOT NULL,
  member_kind        TEXT NOT NULL,
  part_kind          TEXT,
  part_key           TEXT,
  part_label         TEXT,
  layer_name         TEXT,
  geometry_type      TEXT,
  record_count       BIGINT,
  size_bytes         BIGINT,
  sha256             TEXT,
  dbf_fields         JSONB,
  detected_yyyymm    TEXT,
  validation_notes   JSONB NOT NULL DEFAULT '{}'::jsonb
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_file_validations (
  source_file_validation_id UUID PRIMARY KEY,
  source_file_group_id UUID NOT NULL REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  source_file_id      UUID REFERENCES ops.source_files(source_file_id) ON DELETE RESTRICT,
  scope               TEXT NOT NULL CHECK (scope IN ('group', 'file')),
  validator_version   TEXT NOT NULL,
  state               TEXT NOT NULL,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  stage               TEXT,
  progress            DOUBLE PRECISION NOT NULL DEFAULT 0,
  error_code          TEXT,
  error_message       TEXT,
  log_tail            TEXT,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (
    (scope = 'group' AND source_file_id IS NULL)
    OR (scope = 'file' AND source_file_id IS NOT NULL)
  )
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_upload_sessions (
  source_upload_session_id TEXT PRIMARY KEY,
  source_file_group_id     UUID NOT NULL,
  category                 TEXT NOT NULL,
  group_kind               TEXT NOT NULL,
  user_yyyymm              TEXT NOT NULL,
  display_name             TEXT NOT NULL,
  state                    TEXT NOT NULL,
  expected_file_count      INTEGER NOT NULL CHECK (expected_file_count >= 1),
  uploaded_file_count      INTEGER NOT NULL DEFAULT 0 CHECK (uploaded_file_count >= 0),
  upload_strategy          TEXT NOT NULL CHECK (upload_strategy IN ('multipart')),
  storage_kind             TEXT NOT NULL,
  bucket                   TEXT,
  prefix                   TEXT,
  created_by               TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at               TIMESTAMPTZ,
  registration_deadline_at TIMESTAMPTZ,
  completed_at             TIMESTAMPTZ,
  registered_at            TIMESTAMPTZ,
  error_message            TEXT,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_upload_sessions_user_yyyymm
    CHECK (user_yyyymm ~ '^\\d{6}$')
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_upload_session_parts (
  source_upload_session_id TEXT NOT NULL REFERENCES ops.source_upload_sessions(source_upload_session_id) ON DELETE CASCADE,
  part_key                 TEXT NOT NULL,
  multipart_upload_id      TEXT,
  part_number              INTEGER NOT NULL CHECK (part_number >= 1),
  part_etag                TEXT,
  part_sha256              TEXT CHECK (part_sha256 IS NULL OR char_length(part_sha256) = 64),
  received_bytes           BIGINT NOT NULL DEFAULT 0 CHECK (received_bytes >= 0),
  completed_at             TIMESTAMPTZ,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (source_upload_session_id, part_key, part_number)
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_match_sets (
  source_match_set_id      UUID PRIMARY KEY,
  name                     TEXT NOT NULL,
  description              TEXT,
  profile                  TEXT NOT NULL,
  state                    TEXT NOT NULL,
  source_set_hash          TEXT,
  mixed_yyyymm             BOOLEAN NOT NULL DEFAULT false,
  yyyymm_by_category       JSONB NOT NULL DEFAULT '{}'::jsonb,
  omitted_optional         JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by               TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  validated_at             TIMESTAMPTZ,
  last_load_job_id         TEXT REFERENCES load_jobs(job_id) ON DELETE SET NULL,
  last_consistency_report_id TEXT REFERENCES load_consistency_reports(report_id) ON DELETE SET NULL,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  integrity_alert          BOOLEAN NOT NULL DEFAULT false,
  integrity_alert_at       TIMESTAMPTZ,
  integrity_alert_detail   JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_match_sets_state
    CHECK (state IN ('draft', 'validated', 'active', 'retired', 'invalid', 'revalidatable', 'restored_from_backup')),
  CONSTRAINT chk_ops_source_match_sets_source_set_hash
    CHECK (
      (state = 'draft' AND source_set_hash IS NULL)
      OR (state = 'restored_from_backup' AND (source_set_hash IS NULL OR char_length(source_set_hash) = 64))
      OR (state NOT IN ('draft', 'restored_from_backup') AND source_set_hash IS NOT NULL AND char_length(source_set_hash) = 64)
    )
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_match_set_items (
  source_match_set_item_id UUID PRIMARY KEY,
  source_match_set_id      UUID NOT NULL REFERENCES ops.source_match_sets(source_match_set_id) ON DELETE CASCADE,
  category                 TEXT NOT NULL,
  role                     TEXT NOT NULL,
  source_file_group_id     UUID REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE RESTRICT,
  required                 BOOLEAN NOT NULL DEFAULT false,
  omitted                  BOOLEAN NOT NULL DEFAULT false,
  omitted_reason           TEXT,
  effective_yyyymm         TEXT,
  validation_enabled       BOOLEAN NOT NULL DEFAULT true,
  load_order               INTEGER,
  metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT chk_ops_source_match_set_items_role
    CHECK (role IN ('build_required', 'build_recommended', 'validation_optional', 'enrichment_candidate')),
  CONSTRAINT chk_ops_source_match_set_items_omitted
    CHECK (
    (omitted = false AND source_file_group_id IS NOT NULL)
    OR (omitted = true AND source_file_group_id IS NULL)
  ),
  UNIQUE (source_match_set_id, category)
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_storage_reconcile_runs (
  source_storage_reconcile_run_id UUID PRIMARY KEY,
  prefix              TEXT NOT NULL,
  mode                TEXT NOT NULL DEFAULT 'quick' CHECK (mode IN ('quick', 'deep')),
  state               TEXT NOT NULL,
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at         TIMESTAMPTZ,
  scanned_objects     BIGINT NOT NULL DEFAULT 0,
  scanned_db_files    BIGINT NOT NULL DEFAULT 0,
  rehashed_objects    BIGINT NOT NULL DEFAULT 0,
  skipped_rehash_objects BIGINT NOT NULL DEFAULT 0,
  cursor              JSONB NOT NULL DEFAULT '{}'::jsonb,
  mismatch_count      BIGINT NOT NULL DEFAULT 0,
  resolved_count      BIGINT NOT NULL DEFAULT 0,
  log_tail            TEXT,
  summary             JSONB NOT NULL DEFAULT '{}'::jsonb
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.source_storage_reconcile_items (
  source_storage_reconcile_item_id UUID PRIMARY KEY,
  source_storage_reconcile_run_id UUID NOT NULL REFERENCES ops.source_storage_reconcile_runs(source_storage_reconcile_run_id) ON DELETE CASCADE,
  issue_type          TEXT NOT NULL,
  source_file_group_id UUID REFERENCES ops.source_file_groups(source_file_group_id) ON DELETE SET NULL,
  source_file_id      UUID REFERENCES ops.source_files(source_file_id) ON DELETE SET NULL,
  object_key          TEXT,
  db_sha256           TEXT,
  object_sha256       TEXT,
  db_size_bytes       BIGINT,
  object_size_bytes   BIGINT,
  db_etag             TEXT,
  object_etag         TEXT,
  severity            TEXT NOT NULL,
  state               TEXT NOT NULL DEFAULT 'open',
  resolution_action   TEXT,
  resolved_by         TEXT,
  resolved_at         TIMESTAMPTZ,
  details             JSONB NOT NULL DEFAULT '{}'::jsonb
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.consistency_case_definitions (
  consistency_case_code TEXT PRIMARY KEY CHECK (consistency_case_code ~ '^C\\d+$'),
  display_order         INTEGER NOT NULL,
  name                  TEXT NOT NULL,
  compares              TEXT NOT NULL,
  abnormal_criteria     TEXT NOT NULL,
  evidence              JSONB NOT NULL DEFAULT '[]'::jsonb,
  likely_causes         JSONB NOT NULL DEFAULT '[]'::jsonb,
  decision_guide        TEXT NOT NULL,
  threshold             TEXT,
  default_severity      TEXT,
  state                 TEXT NOT NULL CHECK (state IN ('enabled', 'disabled', 'retired')),
  skip_policy           JSONB NOT NULL DEFAULT '{}'::jsonb,
  sample_schema         JSONB NOT NULL DEFAULT '{}'::jsonb,
  introduced_by         TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata              JSONB NOT NULL DEFAULT '{}'::jsonb
)
"""
    )

    op.execute(
        """
CREATE TABLE IF NOT EXISTS ops.consistency_case_inputs (
  consistency_case_code TEXT NOT NULL REFERENCES ops.consistency_case_definitions(consistency_case_code) ON DELETE RESTRICT,
  category              TEXT NOT NULL,
  required              BOOLEAN NOT NULL DEFAULT true,
  PRIMARY KEY (consistency_case_code, category)
)
"""
    )

    # dataset_snapshots gains a nullable link to the source match set registry.
    op.execute("ALTER TABLE ops.dataset_snapshots ADD COLUMN IF NOT EXISTS source_match_set_id UUID")
    op.execute(
        """
ALTER TABLE ops.dataset_snapshots
  ADD CONSTRAINT fk_ops_dataset_snapshots_source_match_set
  FOREIGN KEY (source_match_set_id)
  REFERENCES ops.source_match_sets(source_match_set_id) ON DELETE SET NULL
"""
    )

    op.execute(
        """
CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_source_match_sets_one_active
  ON ops.source_match_sets (state) WHERE state = 'active'
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_source_file_groups_category_state
  ON ops.source_file_groups (category, state)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_source_files_group
  ON ops.source_files (source_file_group_id)
"""
    )
    op.execute(
        """
CREATE UNIQUE INDEX IF NOT EXISTS idx_ops_source_files_object
  ON ops.source_files (bucket, object_key)
  WHERE bucket IS NOT NULL AND object_key IS NOT NULL
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_source_file_members_file
  ON ops.source_file_members (source_file_id)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_source_file_validations_group
  ON ops.source_file_validations (source_file_group_id, started_at DESC)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_source_upload_sessions_category
  ON ops.source_upload_sessions (category, user_yyyymm, state)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_source_storage_reconcile_items_run
  ON ops.source_storage_reconcile_items (source_storage_reconcile_run_id, issue_type)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_source_match_set_items_group
  ON ops.source_match_set_items (source_file_group_id) WHERE source_file_group_id IS NOT NULL
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_consistency_case_definitions_order
  ON ops.consistency_case_definitions (display_order)
"""
    )
    op.execute(
        """
CREATE INDEX IF NOT EXISTS idx_ops_dataset_snapshots_source_match_set_id
  ON ops.dataset_snapshots (source_match_set_id) WHERE source_match_set_id IS NOT NULL
"""
    )

    # Relax the C1~C10 case_code CHECK on the existing samples table so that
    # C11+ cases registered in ops.consistency_case_definitions are allowed.
    # The auto-generated constraint name pattern is <table>_<column>_check.
    op.execute(
        "ALTER TABLE ops.consistency_case_samples "
        "DROP CONSTRAINT IF EXISTS consistency_case_samples_case_code_check"
    )
    op.execute(
        "ALTER TABLE ops.consistency_case_samples "
        "ADD CONSTRAINT consistency_case_samples_case_code_check "
        "CHECK (case_code ~ '^C\\d+$')"
    )


def downgrade() -> None:
    # Restore the original C1~C10 case_code CHECK.
    op.execute(
        "ALTER TABLE ops.consistency_case_samples "
        "DROP CONSTRAINT IF EXISTS consistency_case_samples_case_code_check"
    )
    op.execute(
        "ALTER TABLE ops.consistency_case_samples "
        "ADD CONSTRAINT consistency_case_samples_case_code_check "
        "CHECK (case_code ~ '^C(10|[1-9])$')"
    )

    for index_name in _NEW_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS ops.{index_name}")

    op.execute(
        "ALTER TABLE ops.dataset_snapshots "
        "DROP CONSTRAINT IF EXISTS fk_ops_dataset_snapshots_source_match_set"
    )
    op.execute("ALTER TABLE ops.dataset_snapshots DROP COLUMN IF EXISTS source_match_set_id")

    for table_name in _NEW_TABLES:
        op.execute(f"DROP TABLE IF EXISTS ops.{table_name} CASCADE")
