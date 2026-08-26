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
from kortravelgeo.settings import Settings


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
        "ops.public_api_keys",
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


def test_load_jobs_executor_lease_metadata_and_reconciler_index_declared() -> None:
    # T-290c schema-drift gate: the executor-boundary columns/index must be declared in
    # the fresh-init DDL (SCHEMA_SQL/INDEX_SQL), kept in lockstep with sql/ddl/001_schema.sql,
    # sql/indexes.sql and alembic 0023 (the 3-place + migration schema-drift rule).
    load_jobs_ddl = SCHEMA_SQL.split("CREATE TABLE IF NOT EXISTS load_jobs", 1)[1].split(
        ");",
        1,
    )[0]
    assert "executor" in load_jobs_ddl
    # T-290k flipped the fresh-init default to 'dagster' (in-process execution retired); the
    # CHECK still allows the historical 'api_in_process' value so converged rows stay valid.
    assert "DEFAULT 'dagster'" in load_jobs_ddl
    assert "CHECK (executor IN ('api_in_process','dagster'))" in load_jobs_ddl
    assert "orchestrator_run_id TEXT" in load_jobs_ddl
    assert "lease_expires_at" in load_jobs_ddl
    # Partial indexes that the reconciler / startup-recovery hot path relies on.
    assert "idx_load_jobs_dagster_running" in INDEX_SQL
    assert "WHERE executor = 'dagster' AND state = 'running'" in INDEX_SQL
    assert "idx_load_jobs_dagster_terminal_orphan" in INDEX_SQL
    assert "state IN ('failed','cancelled')" in INDEX_SQL
    assert "AND orchestrator_run_id IS NOT NULL" in INDEX_SQL


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
    from kortravelgeo.infra import backup
    from kortravelgeo.loaders import batch_dag

    # The mv_refresh serving-release hooks moved to the Dagster-executed batch DAG leaf
    # (T-290j/T-290k retired the in-process mv_refresh handler).
    mv_source = inspect.getsource(batch_dag.run_mv_refresh)
    restore_source = inspect.getsource(backup.run_restore_job)
    backup_source = inspect.getsource(backup)

    assert "ensure_load_batch_release_gate" in mv_source
    assert "record_mv_refresh_release" in mv_source
    assert "load_batch_id" in mv_source
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


def test_direct_serving_loads_record_their_own_release_outside_a_batch() -> None:
    """T-291a (ADR-067 D0 violation class 4): pobox/sppn_makarea/shp/bulk are read directly by
    geocode/reverse/geometry repos, never through mv_geocode_target. A standalone load of one of
    these (``load_batch_id is None``) must record its own release; a batch child must not — the
    batch's own consistency gate hasn't run yet when the child loader finishes, and the batch's
    final ``run_mv_refresh`` step already records the consolidated release once the gate passes.
    """
    from kortravelgeo.loaders import batch_dag

    source = inspect.getsource(batch_dag.run_source_loader)
    leaf_source = inspect.getsource(batch_dag._source_leaf)
    run_batch_source = inspect.getsource(batch_dag.run_full_load_batch)

    assert frozenset(
        {"pobox_load", "sppn_makarea_load", "shp_polygons_load", "bulk_load"}
    ) == batch_dag._DIRECT_SERVING_KINDS
    assert "load_batch_id is None" in source
    assert "record_mv_refresh_release" in source
    assert "load_batch_id=load_batch_id" in leaf_source
    assert "load_batch_id=batch_id" in run_batch_source
    # ADR-067 D0's delta-lineage enumeration is daily_juso_delta/juso_parcel_link_delta/
    # shp_polygons_delta only — sppn_makarea/pobox/bulk have no daily_delta lineage, so the
    # mode=="delta" check must be scoped to shp_polygons_load specifically, not any direct-
    # serving kind (a broader check would mislabel a delta-mode sppn_makarea/pobox/bulk load).
    assert 'kind == "shp_polygons_load" and payload.get("mode") == "delta"' in source


def test_postload_maintenance_execute_safe_records_serving_release() -> None:
    """T-291a (violation class 2): ``execute_safe`` mode runs a real ``refresh_mv`` swap against
    the configured engine but never recorded a release."""
    from kortravelgeo.loaders import postload_maintenance

    source = inspect.getsource(postload_maintenance.run_postload_maintenance)
    assert "record_mv_refresh_release" in source


def test_restore_replace_current_activates_instead_of_leaving_pending() -> None:
    """T-291a (violation class 3): ``db_restore mode=replace_current`` overwrites the database
    this app is already serving in place — there is no later hot-swap to promote it, so it must
    be recorded as the active release directly instead of a `pending` candidate nothing ever
    promotes."""
    from kortravelgeo.infra import backup

    restore_source = inspect.getsource(backup.run_restore_job)
    record_source = inspect.getsource(admin_repo.AdminRepository.record_restore_candidate)

    assert 'activate=req.mode == "replace_current"' in restore_source
    assert '"active" if activate else "pending"' in record_source
    assert '"released" if activate else "validated"' in record_source
    assert "activated_by_job_id=job_id if activate else None" in record_source


def test_generic_refresh_paths_can_label_daily_delta_and_batch_children_cannot() -> None:
    """T-291a follow-up: the documented daily-delta operator workflow
    (docs/t028-daily-juso-delta.md) is apply-deltas-then-refresh-separately via the *generic*
    `ktgctl refresh mv` / REST `POST /maintenance/refresh-mv` — not a per-load-command flag.
    Both must be able to label the resulting release daily_delta, and a full_load_batch's own
    mv_refresh child must never honor it (a batch always means full_load lineage)."""
    from kortravelgeo.api.routers import admin as admin_router
    from kortravelgeo.cli.main import refresh_materialized_view
    from kortravelgeo.loaders import batch_dag

    cli_source = inspect.getsource(refresh_materialized_view)
    assert "--daily-delta" in cli_source
    assert 'release_kind="daily_delta" if daily_delta else None' in cli_source

    rest_source = inspect.getsource(admin_router.refresh_mv)
    assert "daily_delta: bool = False" in rest_source
    assert 'payload["release_kind"] = "daily_delta"' in rest_source

    mv_refresh_source = inspect.getsource(batch_dag.run_mv_refresh)
    assert 'payload_release_kind = _payload_str(payload, "release_kind")' in mv_refresh_source
    assert 'release_kind = "daily_delta" if payload_release_kind ==' in mv_refresh_source
    assert "release_kind=None if load_batch_id else release_kind" in mv_refresh_source


def test_record_mv_refresh_release_release_kind_can_be_overridden() -> None:
    """T-291a: the derived full_load/manual_rebuild release_kind can be overridden — used to
    label delta-lineage refreshes (daily_juso_delta/juso_parcel_link_delta/shp delta mode) as
    ``daily_delta`` instead of the enum value sitting unreachable.

    Checks both the fallback derivation *and* that the resulting variable — not a fresh
    re-derivation that would silently discard the override — is what reaches the SQL insert:
    a mutation that inlines ``"full_load" if load_batch_id else "manual_rebuild"`` directly at
    the ``_insert_dataset_snapshot_and_release`` call site (bypassing the override-aware local)
    passes the first assertion alone while making ``daily_delta`` permanently unreachable again.
    """
    source = inspect.getsource(admin_repo.AdminRepository.record_mv_refresh_release)
    assert "release_kind = release_kind or (" in source
    assert "release_kind=release_kind," in source


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


def test_slow_observability_prune_scheduler_uses_retention_settings() -> None:
    """T-158 후속(#302 M1): ops.slow_observability_samples 보존 정책이 자동으로 도는지."""
    from kortravelgeo.api import app

    module_source = inspect.getsource(app)
    slow_observability_source = inspect.getsource(slow_observability)
    scheduler_source = inspect.getsource(app._start_slow_observability_prune_scheduler)
    loop_source = inspect.getsource(app._run_slow_observability_prune_scheduler)
    once_source = inspect.getsource(app._prune_slow_observability_samples_once)

    assert "DELETE FROM ops.slow_observability_samples" in slow_observability_source
    assert (
        "captured_at < now() - (:retention_days * interval '1 day')"
        in slow_observability_source
    )
    assert "prune_slow_observability_samples" in module_source
    assert "ops_slow_sample_retention_days" in module_source
    assert "ops_slow_samples_enabled" in scheduler_source
    assert "ops_slow_sample_prune_interval_minutes <= 0" in scheduler_source
    assert "ops_slow_sample_prune_interval_minutes" in loop_source
    assert "retention_days=settings.ops_slow_sample_retention_days" in once_source


async def test_slow_observability_prune_once_swallows_errors(monkeypatch) -> None:
    """T-158 후속(#302): 보존 프루닝도 형제 스케줄러처럼 실패해도 루프를 죽이지 않아야 한다."""
    from kortravelgeo.api import app

    calls: list[int] = []

    async def fake_prune(engine: object, retention_days: int) -> int:
        calls.append(retention_days)
        raise RuntimeError("simulated DB error")

    monkeypatch.setattr(app, "prune_slow_observability_samples", fake_prune)

    # Must not raise.
    await app._prune_slow_observability_samples_once(
        object(), Settings(ops_slow_sample_retention_days=3)
    )

    assert calls == [3]
