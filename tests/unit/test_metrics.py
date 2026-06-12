from __future__ import annotations

from kortravelgeo.dto.admin import CacheMetrics
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
    metrics.record_api_request(
        method="GET",
        route="/v1/healthz",
        status_code=200,
        elapsed_s=0.012,
    )

    body = metrics.render_prometheus().decode()

    assert "kor_travel_geo_api_request_duration_seconds_bucket" in body
    assert 'route="/v1/healthz"' in body
