from __future__ import annotations

import inspect

from kortravelgeo.loaders import postload_maintenance as maintenance


def test_t146_plan_separates_automatic_and_manual_steps() -> None:
    steps = maintenance.build_postload_maintenance_plan(strategy="swap", vacuum_analyze=True)
    by_id = {step.step_id: step for step in steps}

    assert list(by_id)[:5] == [
        "catalog.before",
        "source.vacuum_analyze",
        "links.resolve",
        "serving.refresh",
        "stats.capture",
    ]
    assert by_id["source.vacuum_analyze"].required is True
    assert "VACUUM (ANALYZE)" in by_id["source.vacuum_analyze"].command
    assert 'public."tl_juso_text"' in by_id["source.vacuum_analyze"].command
    assert by_id["serving.refresh"].command == "refresh_mv(strategy='swap')"
    assert by_id["manual.reindex_concurrently"].mode == "manual"
    assert by_id["manual.cluster_or_repack"].mode == "manual"
    assert by_id["manual.pg_prewarm"].notes.startswith("automation belongs to T-162")


def test_t146_warnings_cover_budget_bloat_analyze_and_invalid_index() -> None:
    stats = (
        maintenance.MaintenanceObjectStat(
            schema_name="public",
            object_name="tl_juso_text",
            object_kind="table",
            parent_object_name=None,
            estimated_rows=100,
            total_bytes=100,
            table_bytes=80,
            index_bytes=20,
            toast_bytes=0,
            live_tuples=100,
            dead_tuples=50,
            dead_tuple_ratio=50 / 150,
            last_vacuum=None,
            last_analyze=None,
            index_valid=None,
            index_ready=None,
        ),
        maintenance.MaintenanceObjectStat(
            schema_name="public",
            object_name="idx_bad",
            object_kind="index",
            parent_object_name="tl_juso_text",
            estimated_rows=None,
            total_bytes=200,
            table_bytes=None,
            index_bytes=200,
            toast_bytes=None,
            live_tuples=None,
            dead_tuples=None,
            dead_tuple_ratio=None,
            last_vacuum=None,
            last_analyze=None,
            index_valid=False,
            index_ready=True,
        ),
    )

    warnings = maintenance.build_postload_maintenance_warnings(
        stats,
        index_budget_bytes=100,
        dead_tuple_count_warn=10,
        dead_tuple_ratio_warn=0.10,
    )
    codes = {warning.code for warning in warnings}

    assert codes == {
        "index_budget_exceeded",
        "missing_analyze",
        "dead_tuple_ratio_high",
        "index_invalid",
    }


def test_t146_catalog_query_uses_stats_and_index_catalogs() -> None:
    source = inspect.getsource(maintenance.collect_postload_object_stats)

    assert "pg_stat_user_tables" in source
    assert "pg_index" in source
    assert "pg_total_relation_size" in source
    assert "bindparam" in source
    assert "REFRESH MATERIALIZED VIEW" not in source


def test_t146_execute_safe_does_not_automate_reindex_or_cluster() -> None:
    source = inspect.getsource(maintenance.run_postload_maintenance)

    assert "resolve_text_geometry_links(engine)" in source
    assert "refresh_mv(engine" in source
    assert "capture_table_stats_snapshots()" in source
    assert "REINDEX" not in source
    assert "CLUSTER" not in source


def test_t146_script_registers_benchmark_artifact() -> None:
    import scripts.run_t146_postload_maintenance as script

    source = inspect.getsource(script)

    assert "BenchmarkArtifactRegisterRequest" in source
    assert 'kind="other"' in source
    assert "postload_maintenance" in source
    assert "--register-artifact" in source
