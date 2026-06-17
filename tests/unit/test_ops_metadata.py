from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime

from kortravelgeo.core.redaction import REDACTED, canonical_payload_hash, redact_audit_payload
from kortravelgeo.dto.admin import (
    AuditEvent,
    MaintenanceWindowCreate,
    OpsArtifact,
    PgStatStatementSnapshot,
    TableStatsSnapshot,
)
from kortravelgeo.infra import admin_repo, slow_observability
from kortravelgeo.infra.sql import INDEX_SQL, SCHEMA_SQL, iter_sql_statements


def test_ops_schema_tables_indexes_and_append_only_trigger_are_declared() -> None:
    assert "CREATE SCHEMA IF NOT EXISTS ops" in SCHEMA_SQL
    for table_name in (
        "ops.audit_events",
        "ops.consistency_case_samples",
        "ops.dataset_snapshots",
        "ops.serving_releases",
        "ops.artifacts",
        "ops.maintenance_windows",
        "ops.table_stats_snapshots",
        "ops.pg_stat_statements_snapshots",
        "ops.slow_observability_samples",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in SCHEMA_SQL

    audit_sql = SCHEMA_SQL.split("CREATE TABLE IF NOT EXISTS ops.audit_events", 1)[1].split(
        "CREATE OR REPLACE FUNCTION",
        1,
    )[0]

    assert "ops.audit_events_append_only" in SCHEMA_SQL
    assert "trg_ops_audit_events_append_only" in SCHEMA_SQL
    assert "job_id            TEXT REFERENCES load_jobs(job_id) ON DELETE NO ACTION" in audit_sql
    assert "ON DELETE SET NULL" not in audit_sql
    assert "idx_ops_serving_releases_one_active" in INDEX_SQL
    assert "idx_ops_consistency_case_samples_report" in INDEX_SQL
    assert "idx_ops_consistency_case_samples_4326" in INDEX_SQL
    assert "idx_ops_pg_stat_statements_snapshots_captured" in INDEX_SQL
    assert "idx_ops_pg_stat_statements_snapshots_fingerprint" in INDEX_SQL
    assert "idx_ops_slow_observability_samples_captured" in INDEX_SQL
    assert "idx_ops_slow_observability_samples_query" in INDEX_SQL
    assert "WHERE state = 'active'" in INDEX_SQL
    assert any("ops.table_stats_snapshots" in sql for sql in iter_sql_statements(SCHEMA_SQL))
    assert any(
        "ops.pg_stat_statements_snapshots" in sql for sql in iter_sql_statements(SCHEMA_SQL)
    )
    assert any(
        "ops.slow_observability_samples" in sql for sql in iter_sql_statements(SCHEMA_SQL)
    )


def test_audit_redaction_never_keeps_secrets_dsn_tokens_or_raw_address() -> None:
    payload = {
        "api_key": "secret-key",
        "pg_dsn": "postgresql://user:password@localhost/kor_travel_geo",
        "download_token": "token-value",
        "address": "서울특별시 강남구 테헤란로 152",
        "nested": {"query": "부산광역시 해운대구 우동", "callback_secret": "hook"},
    }

    redacted, digest = redact_audit_payload(payload)
    dumped = json.dumps(redacted, ensure_ascii=False, sort_keys=True)

    assert redacted["api_key"] == REDACTED
    assert redacted["pg_dsn"] == REDACTED
    assert redacted["download_token"] == REDACTED
    assert str(redacted["address"]).startswith("[ADDRESS_SHA256:")
    assert "secret-key" not in dumped
    assert "password" not in dumped
    assert "token-value" not in dumped
    assert "서울특별시" not in dumped
    assert "부산광역시" not in dumped
    assert digest == canonical_payload_hash(payload)


def test_ops_dtos_validate_core_contracts() -> None:
    now = datetime.now(UTC)

    event = AuditEvent(
        audit_event_id="event-1",
        occurred_at=now,
        actor_type="api",
        action="load.submit",
        outcome="started",
        payload_hash="a" * 64,
    )
    assert event.payload_redacted == {}

    maintenance = MaintenanceWindowCreate(
        kind="restore",
        reason="복원 dry-run 검증",
        confirmation="RESTORE kor_travel_geo",
    )
    assert maintenance.blocks == {}

    artifact = OpsArtifact(
        artifact_id="artifact-1",
        artifact_type="db_backup",
        state="available",
        storage_kind="local_file",
        sha256="b" * 64,
        created_at=now,
    )
    assert artifact.manifest == {}

    stats = TableStatsSnapshot(
        table_stats_snapshot_id="stats-1",
        captured_at=now,
        schema_name="public",
        object_name="tl_juso_text",
        object_kind="table",
        estimated_rows=10,
    )
    assert stats.estimated_rows == 10

    pg_stat = PgStatStatementSnapshot(
        pg_stat_snapshot_id="pg-stat-1",
        captured_at=now,
        rank=1,
        query_fingerprint="abc123",
        operation="select",
        calls=3,
        total_exec_time_ms=15.0,
        mean_exec_time_ms=5.0,
        max_exec_time_ms=7.5,
        rows_returned=30,
        query_preview="SELECT * FROM mv_geocode_target WHERE road_address = ?",
    )
    assert pg_stat.stats == {}


def test_admin_repo_ops_methods_redact_and_hash_confirmation() -> None:
    source = inspect.getsource(admin_repo.AdminRepository)
    module_source = inspect.getsource(admin_repo)

    assert "record_audit_event" in source
    assert "redact_audit_payload" in source
    assert "hash_identifier(client_ip)" in source
    assert "hash_confirmation(req.confirmation)" in source
    assert "require_active_maintenance_window" in source
    assert "starts_at <= now()" in source
    assert "confirmation_hash = :confirmation_hash" in source
    assert "capture_table_stats_snapshots" in source
    assert "_active_release_snapshot_id_for_conn" in module_source
    assert "active_serving_release" in module_source
    assert "snapshot_link" in module_source
    assert "_OPS_TABLE_STATS_ADVISORY_LOCK = 0x4B47_00A0" in module_source
    assert "pg_try_advisory_xact_lock" in module_source
    assert "TABLE_STATS_CAPTURE_LOCKED_MESSAGE" in module_source
    assert "capture_pg_stat_statement_snapshots" in source
    assert "retention_days" in source
    assert "DELETE FROM ops.pg_stat_statements_snapshots" in source
    assert "captured_at < now() - (:retention_days * interval '1 day')" in source
    assert "retention_days must be greater than or equal to 1" in source
    assert "ops.slow_observability_samples" in inspect.getsource(slow_observability)
    assert "_OPS_PG_STAT_STATEMENTS_ADVISORY_LOCK = 0x4B47_00A1" in module_source
    assert "PG_STAT_STATEMENTS_CAPTURE_LOCKED_MESSAGE" in module_source
    assert "x_extension.pg_stat_statements" in module_source
    assert "_pg_stat_query_preview" in module_source
    assert "skip_if_locked" in source
    assert "http_status=409" in source
    assert "insert_artifact" in source
    assert "update_artifact" in source
    assert "mark_artifact_deleted" in source
    assert "pg_class" in source
    assert "record_mv_refresh_release" in source
    assert "record_restore_candidate" in source
    assert "ensure_load_batch_release_gate" in source
    assert "canonical_payload_hash" in module_source
    assert "source_set_hash" in module_source
    assert "UPDATE ops.serving_releases" in module_source
    assert "mv_hash=mv_hash" in module_source
    assert "CAST(:mv_row_count AS text)" in module_source
    assert "serving_release.activate" in module_source


def test_pg_stat_query_preview_masks_literals_and_limits_length() -> None:
    query = (
        "SELECT $$서울특별시 강남구$$, E'비밀', 123 "
        "FROM mv_geocode_target WHERE road_address = '테헤란로 152'"
    )

    preview = admin_repo._pg_stat_query_preview(query * 20)

    assert "서울특별시" not in preview
    assert "비밀" not in preview
    assert "테헤란로" not in preview
    assert "123" not in preview
    assert len(preview) <= 500


def test_mv_refresh_and_restore_paths_record_ops_release_hooks() -> None:
    from kortravelgeo.api import app
    from kortravelgeo.infra import backup

    app_source = inspect.getsource(app._register_default_handlers)
    restore_source = inspect.getsource(backup.run_restore_job)
    backup_source = inspect.getsource(backup)

    assert "ensure_load_batch_release_gate" in app_source
    assert "record_mv_refresh_release" in app_source
    assert "load_batch_id" in app_source
    assert "record_restore_candidate" in restore_source
    assert "validate_replace_current_restore_request" in restore_source
    assert "require_active_maintenance_window" in restore_source
    assert "maintenance_window.authorize" in restore_source
    assert 'actor_type="system"' in restore_source
    assert 'actor_type="job"' not in restore_source
    assert "hash_confirmation(confirmation)" in restore_source
    assert "confirmation_hash" in restore_source
    assert "replace_current target_database must match" in backup_source
    assert "release_state" in restore_source
    assert "dataset_snapshot_id" in restore_source


def test_ops_capture_schedulers_use_settings_and_advisory_locks() -> None:
    from kortravelgeo.api import app

    module_source = inspect.getsource(app)
    scheduler_source = inspect.getsource(app._start_table_stats_capture_scheduler)
    loop_source = inspect.getsource(app._run_table_stats_capture_scheduler)
    pg_scheduler_source = inspect.getsource(app._start_pg_stat_statements_capture_scheduler)
    pg_loop_source = inspect.getsource(app._run_pg_stat_statements_capture_scheduler)

    assert "ops_table_stats_capture_interval_minutes <= 0" in scheduler_source
    assert "asyncio.create_task" in scheduler_source
    assert "ops_table_stats_capture_on_startup" in loop_source
    assert "ops_table_stats_capture_limit" in module_source
    assert "capture_table_stats_snapshots(" in module_source
    assert "ops_pg_stat_statements_capture_interval_minutes <= 0" in pg_scheduler_source
    assert "ops_pg_stat_statements_capture_on_startup" in pg_loop_source
    assert "ops_pg_stat_statements_capture_limit" in module_source
    assert "ops_pg_stat_statements_retention_days" in module_source
    assert "capture_pg_stat_statement_snapshots(" in module_source
    assert "refresh_pg_stat_statement_metrics" in module_source
    assert "skip_if_locked=True" in module_source
