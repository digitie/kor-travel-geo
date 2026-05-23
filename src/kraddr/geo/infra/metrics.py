"""Prometheus metric helpers with a no-op fallback for library-only installs."""

from __future__ import annotations

from typing import Any, Final

from kraddr.geo.dto.admin import CacheMetrics

_prometheus_client: Any
try:  # pragma: no cover - exercised in environments with api extra installed.
    import prometheus_client as _prometheus_client
except ModuleNotFoundError:  # pragma: no cover - library-only extra keeps metrics no-op.
    _prometheus_client = None

PROMETHEUS_CONTENT_TYPE: Final[str] = (
    _prometheus_client.CONTENT_TYPE_LATEST
    if _prometheus_client is not None
    else "text/plain; version=0.0.4; charset=utf-8"
)


class _NoopMetric:
    def labels(self, *_args: object, **_kwargs: object) -> _NoopMetric:
        return self

    def inc(self, _amount: float = 1.0) -> None:
        return None

    def set(self, _value: float) -> None:
        return None


def _counter(name: str, documentation: str, labelnames: tuple[str, ...]) -> Any:
    if _prometheus_client is None:
        return _NoopMetric()
    return _prometheus_client.Counter(name, documentation, labelnames)


def _gauge(name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Any:
    if _prometheus_client is None:
        return _NoopMetric()
    return _prometheus_client.Gauge(name, documentation, labelnames)


EXTERNAL_API_CALLS = _counter(
    "kraddr_geo_external_api_calls_total",
    "External geocoding API calls by provider and outcome.",
    ("provider", "outcome"),
)
CACHE_ENTRIES = _gauge("kraddr_geo_cache_entries", "Rows currently stored in geo_cache.")
CACHE_HITS = _gauge("kraddr_geo_cache_hits_total", "Accumulated geo_cache hit count.")
CACHE_EXPIRED = _gauge("kraddr_geo_cache_expired_entries", "Expired rows currently in geo_cache.")
LOAD_JOBS = _gauge(
    "kraddr_geo_load_jobs",
    "Load jobs by kind and persistent state.",
    ("kind", "state"),
)


def record_external_api_call(provider: str, outcome: str) -> None:
    EXTERNAL_API_CALLS.labels(provider=provider, outcome=outcome).inc()


def refresh_admin_metrics(
    *,
    cache: CacheMetrics,
    load_jobs: list[tuple[str, str, int]],
) -> None:
    CACHE_ENTRIES.set(cache.entries)
    CACHE_HITS.set(cache.hits)
    CACHE_EXPIRED.set(cache.expired)
    for kind, state, count in load_jobs:
        LOAD_JOBS.labels(kind=kind, state=state).set(count)


def render_prometheus() -> bytes:
    if _prometheus_client is None:
        return b""
    body = _prometheus_client.generate_latest()
    return body if isinstance(body, bytes) else bytes(body)
