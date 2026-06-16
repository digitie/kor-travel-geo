from __future__ import annotations

from datetime import UTC, datetime

from kortravelgeo.dto.admin import CacheMetrics, PgStatStatementSnapshot
from kortravelgeo.infra import metrics


def test_metrics_render_includes_external_api_and_admin_gauges() -> None:
    metrics.record_external_api_call("vworld", "success")
    metrics.refresh_admin_metrics(
        cache=CacheMetrics(enabled=True, entries=3, hits=7, expired=1),
        load_jobs=[("full_load_batch", "running", 1)],
    )

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_external_api_calls_total" in body
    assert "kor_travel_geo_cache_entries" in body
    assert "kor_travel_geo_cache_hits " in body
    assert "kor_travel_geo_cache_hits_total" not in body
    assert "kor_travel_geo_load_jobs" in body


def test_metrics_render_includes_api_request_duration_histogram() -> None:
    metrics.record_api_request_started(method="GET")
    metrics.record_api_request_finished(method="GET")
    metrics.record_api_request(
        method="GET",
        route="/v1/healthz",
        status_code=200,
        elapsed_s=0.012,
        slow_threshold_ms=10,
    )

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_api_requests_total" in body
    assert "kor_travel_geo_api_slow_requests_total" in body
    assert "kor_travel_geo_api_requests_in_progress" in body
    assert "kor_travel_geo_api_request_duration_seconds_bucket" in body
    assert 'route="/v1/healthz"' in body


def test_metrics_render_includes_db_pool_gauges() -> None:
    class FakePool:
        def size(self) -> int:
            return 10

        def checkedin(self) -> int:
            return 8

        def checkedout(self) -> int:
            return 2

        def overflow(self) -> int:
            return 0

    class FakeSyncEngine:
        pool = FakePool()

    class FakeEngine:
        sync_engine = FakeSyncEngine()

    metrics.refresh_db_pool_metrics(FakeEngine())

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_pg_pool_size" in body
    assert "kor_travel_geo_pg_pool_checked_in" in body
    assert "kor_travel_geo_pg_pool_checked_out" in body
    assert "kor_travel_geo_pg_pool_overflow" in body


def test_metrics_render_includes_db_pool_checkout_timeout_counter() -> None:
    metrics.record_db_pool_checkout_timeout(method="GET", route="/v1/address/geocode")

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_pg_pool_checkout_timeouts_total" in body
    assert 'route="/v1/address/geocode"' in body


def test_metrics_render_includes_api_admission_counters_and_histograms() -> None:
    metrics.record_api_admission_started(scope="geocode")
    metrics.record_api_admission_finished(scope="geocode")
    metrics.record_api_admission_wait(
        method="GET",
        route="/v1/address/geocode",
        scope="geocode",
        outcome="accepted",
        elapsed_s=0.001,
    )
    metrics.record_api_admission_rejection(
        method="GET",
        route="/v1/address/geocode",
        scope="geocode",
    )

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_api_admission_wait_seconds_bucket" in body
    assert "kor_travel_geo_api_admission_rejections_total" in body
    assert "kor_travel_geo_api_admission_in_progress" in body
    assert 'scope="geocode"' in body


def test_metrics_render_includes_load_job_duration_histograms() -> None:
    metrics.record_load_job_duration(kind="full_load_batch", state="done", elapsed_s=1.25)
    metrics.record_load_job_stage_duration(
        kind="full_load_batch",
        stage="source_loads:202605",
        outcome="completed",
        elapsed_s=0.5,
    )

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_load_job_duration_seconds_bucket" in body
    assert "kor_travel_geo_load_job_stage_duration_seconds_bucket" in body
    assert 'kind="full_load_batch"' in body
    assert 'stage="source_loads"' in body
    assert 'outcome="completed"' in body


def test_metrics_render_includes_db_query_duration_histogram() -> None:
    metrics.record_db_query(
        statement="SELECT *\n  FROM mv_geocode_target\n WHERE road_address = :query",
        elapsed_s=0.007,
        status="success",
    )

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_db_queries_total" in body
    assert "kor_travel_geo_db_query_duration_seconds_bucket" in body
    assert 'operation="select"' in body
    assert 'status="success"' in body
    assert "query_fingerprint=" in body


def test_metrics_render_includes_pg_stat_statement_snapshot_without_query_text() -> None:
    metrics.refresh_pg_stat_statement_metrics(
        [
            PgStatStatementSnapshot(
                pg_stat_snapshot_id="pg-stat-1",
                captured_at=datetime.now(UTC),
                rank=1,
                query_fingerprint="abcdef123456",
                operation="select",
                calls=12,
                total_exec_time_ms=120.5,
                mean_exec_time_ms=10.0,
                max_exec_time_ms=40.25,
                rows_returned=24,
                query_preview="SELECT * FROM mv_geocode_target WHERE road_address = ?",
            )
        ]
    )

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_pg_stat_statements_total_exec_time_ms" in body
    assert "kor_travel_geo_pg_stat_statements_calls" in body
    assert 'operation="select"' in body
    assert 'query_fingerprint="abcdef123456"' in body
    assert "mv_geocode_target" not in body
    assert "road_address" not in body
