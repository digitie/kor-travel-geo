from __future__ import annotations

from kraddr.geo.dto.admin import CacheMetrics
from kraddr.geo.infra import metrics


def test_metrics_render_includes_external_api_and_admin_gauges() -> None:
    metrics.record_external_api_call("vworld", "success")
    metrics.refresh_admin_metrics(
        cache=CacheMetrics(enabled=True, entries=3, hits=7, expired=1),
        load_jobs=[("full_load_batch", "running", 1)],
    )

    body = metrics.render_prometheus().decode()

    assert "kraddr_geo_external_api_calls_total" in body
    assert "kraddr_geo_cache_entries" in body
    assert "kraddr_geo_cache_hits " in body
    assert "kraddr_geo_cache_hits_total" not in body
    assert "kraddr_geo_load_jobs" in body
