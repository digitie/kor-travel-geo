"""Prometheus metric helpers with a no-op fallback for library-only installs."""

from __future__ import annotations

from typing import Any, Final

from kortravelgeo.dto.admin import CacheMetrics

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

    def observe(self, _value: float) -> None:
        return None


def _counter(name: str, documentation: str, labelnames: tuple[str, ...]) -> Any:
    if _prometheus_client is None:
        return _NoopMetric()
    return _prometheus_client.Counter(name, documentation, labelnames)


def _gauge(name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Any:
    if _prometheus_client is None:
        return _NoopMetric()
    return _prometheus_client.Gauge(name, documentation, labelnames)


def _histogram(
    name: str,
    documentation: str,
    labelnames: tuple[str, ...],
    buckets: tuple[float, ...],
) -> Any:
    if _prometheus_client is None:
        return _NoopMetric()
    return _prometheus_client.Histogram(name, documentation, labelnames, buckets=buckets)


EXTERNAL_API_CALLS = _counter(
    "kor_travel_geo_external_api_calls_total",
    "External geocoding API calls by provider and outcome.",
    ("provider", "outcome"),
)
CACHE_ENTRIES = _gauge("kor_travel_geo_cache_entries", "Rows currently stored in geo_cache.")
CACHE_HITS = _gauge("kor_travel_geo_cache_hits", "Accumulated geo_cache hit count.")
CACHE_EXPIRED = _gauge(
    "kor_travel_geo_cache_expired_entries",
    "Expired rows currently in geo_cache.",
)
LOAD_JOBS = _gauge(
    "kor_travel_geo_load_jobs",
    "Load jobs by kind and persistent state.",
    ("kind", "state"),
)
API_REQUEST_DURATION = _histogram(
    "kor_travel_geo_api_request_duration_seconds",
    "HTTP request duration by route template, method, and status code.",
    ("method", "route", "status_code"),
    (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def record_external_api_call(provider: str, outcome: str) -> None:
    EXTERNAL_API_CALLS.labels(provider=provider, outcome=outcome).inc()


def record_api_request(
    *,
    method: str,
    route: str,
    status_code: int,
    elapsed_s: float,
) -> None:
    API_REQUEST_DURATION.labels(
        method=method,
        route=route,
        status_code=str(status_code),
    ).observe(elapsed_s)


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
