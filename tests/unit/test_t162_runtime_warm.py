from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.api import app
from kortravelgeo.loaders import runtime_warm


async def test_t162_plan_mode_is_offline_and_keeps_prewarm_optional() -> None:
    report = await runtime_warm.run_runtime_warm(
        cast("AsyncEngine", object()),
        mode="plan",
        prewarm_enabled=False,
    )
    by_id = {execution.step_id: execution for execution in report.executions}

    assert report.task_id == "T-162"
    assert report.availability is None
    assert by_id["catalog.available"].status == "planned"
    assert by_id["buffer.pg_prewarm"].status == "skipped"
    assert by_id["query.geocode_exact"].status == "planned"
    assert by_id["query.search_text"].status == "planned"
    assert by_id["query.reverse_nearest"].status == "planned"
    assert by_id["query.region_radius"].status == "planned"


def test_t162_plan_covers_runtime_query_and_optional_buffer_warm() -> None:
    steps = runtime_warm.build_runtime_warm_plan(prewarm_enabled=True)
    by_id = {step.step_id: step for step in steps}

    assert list(by_id) == [
        "catalog.available",
        "buffer.pg_prewarm",
        "query.geocode_exact",
        "query.search_text",
        "query.reverse_nearest",
        "query.region_radius",
    ]
    assert by_id["buffer.pg_prewarm"].required is True
    assert "pg_prewarm" in by_id["buffer.pg_prewarm"].command
    assert by_id["query.search_text"].lock_impact == "read-only limited SELECT"


def test_t162_runtime_warm_sql_is_bounded_and_transaction_local() -> None:
    source = inspect.getsource(runtime_warm)

    assert "LIMIT :sample_limit" in source
    assert "to_regclass(:relation_name)::text" in source
    assert "pg_extension" in source
    assert "CREATE EXTENSION" not in source
    assert "set_config('statement_timeout', :timeout_ms, true)" in source
    assert "set_config('pg_trgm.similarity_threshold', :value, true)" in source
    assert "SET pg_trgm.similarity_threshold" not in source


def test_t162_report_metrics_counts_warning_and_failure_separately() -> None:
    report = runtime_warm.RuntimeWarmReport(
        schema_version=1,
        task_id="T-162",
        mode="execute",
        started_at="2026-06-16T00:00:00+00:00",
        finished_at="2026-06-16T00:00:01+00:00",
        settings={},
        steps=(),
        executions=(
            runtime_warm.RuntimeWarmExecution(
                step_id="query.geocode_exact",
                status="succeeded",
                seconds=0.001,
                row_count=3,
            ),
            runtime_warm.RuntimeWarmExecution(
                step_id="buffer.pg_prewarm",
                status="warning",
                seconds=0.002,
            ),
            runtime_warm.RuntimeWarmExecution(
                step_id="query.search_text",
                status="failed",
                seconds=0.003,
            ),
        ),
        availability=None,
    )

    metrics = runtime_warm.runtime_warm_report_metrics(report)

    assert metrics["samples"] == 3
    assert metrics["warning_count"] == 1
    assert metrics["error_count"] == 1
    assert metrics["max_ms"] == 3.0


def test_t162_app_lifespan_has_opt_in_scheduler_and_global_lock() -> None:
    start_source = inspect.getsource(app._start_runtime_warm_scheduler)
    loop_source = inspect.getsource(app._run_runtime_warm_scheduler)
    once_source = inspect.getsource(app._run_runtime_warm_once)
    lifespan_source = inspect.getsource(app.lifespan)

    assert "runtime_warm_on_startup" in start_source
    assert "runtime_warm_interval_minutes <= 0" in start_source
    assert "while interval_s > 0" in loop_source
    assert "AdvisoryLockNamespace.RUNTIME_WARM" in once_source
    assert "run_runtime_warm(" in once_source
    assert "runtime_warm_task" in lifespan_source


def test_t162_script_registers_benchmark_artifact() -> None:
    import scripts.run_t162_runtime_warm as script

    source = inspect.getsource(script)

    assert "BenchmarkArtifactRegisterRequest" in source
    assert 'kind="other"' in source
    assert "runtime_warm" in source
    assert "--register-artifact" in source
    assert "SelectorEventLoop" in source


def test_t162_cold_warm_ratio_gate_flags_regression() -> None:
    import scripts.evaluate_t162_cold_warm_ratio as gate

    warm_payload = {
        "summaries": [
            {
                "group": "Q1_ROAD_EXACT",
                "sql_name": "geocode_road",
                "concurrency": 64,
                "errors": 0,
                "p99_ms": 100.0,
            }
        ]
    }
    cold_payload = {
        "summaries": [
            {
                "group": "Q1_ROAD_EXACT",
                "sql_name": "geocode_road",
                "concurrency": 64,
                "errors": 0,
                "p99_ms": 260.0,
            }
        ]
    }

    report = gate.evaluate_cold_warm_ratio(
        cold_payload=cold_payload,
        warm_payload=warm_payload,
        cold_report="cold/api-report.json",
        warm_report="warm/api-report.json",
        max_ratio=2.0,
        absolute_slack_ms=25.0,
    )

    assert report.passed is False
    assert report.comparisons[0].threshold_ms == 225.0
    assert report.comparisons[0].reason == "p99_ratio_exceeded"
