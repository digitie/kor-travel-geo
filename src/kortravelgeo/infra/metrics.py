"""Prometheus metric helpers with a no-op fallback for library-only installs."""

from __future__ import annotations

import hashlib
import re
from time import perf_counter
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

    def dec(self, _amount: float = 1.0) -> None:
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
API_REQUESTS = _counter(
    "kor_travel_geo_api_requests_total",
    "HTTP requests by route template, method, and status code.",
    ("method", "route", "status_code"),
)
API_SLOW_REQUESTS = _counter(
    "kor_travel_geo_api_slow_requests_total",
    "HTTP requests slower than KTG_API_SLOW_REQUEST_MS by route template, method, and status code.",
    ("method", "route", "status_code"),
)
API_REQUESTS_IN_PROGRESS = _gauge(
    "kor_travel_geo_api_requests_in_progress",
    "HTTP requests currently being handled by this API process.",
    ("method",),
)
API_REQUEST_DURATION = _histogram(
    "kor_travel_geo_api_request_duration_seconds",
    "HTTP request duration by route template, method, and status code.",
    ("method", "route", "status_code"),
    (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
LOAD_JOB_DURATION = _histogram(
    "kor_travel_geo_load_job_duration_seconds",
    "Load job wall-clock duration by job kind and final state.",
    ("kind", "state"),
    (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0, 1800.0, 3600.0, 7200.0),
)
LOAD_JOB_STAGE_DURATION = _histogram(
    "kor_travel_geo_load_job_stage_duration_seconds",
    "Load job stage duration by job kind, stage, and outcome.",
    ("kind", "stage", "outcome"),
    (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0, 1800.0, 3600.0),
)
PG_POOL_SIZE = _gauge(
    "kor_travel_geo_pg_pool_size",
    "Configured SQLAlchemy DB pool size for this API process.",
)
PG_POOL_CHECKED_IN = _gauge(
    "kor_travel_geo_pg_pool_checked_in",
    "SQLAlchemy DB pool connections currently idle in this API process.",
)
PG_POOL_CHECKED_OUT = _gauge(
    "kor_travel_geo_pg_pool_checked_out",
    "SQLAlchemy DB pool connections currently checked out by this API process.",
)
PG_POOL_OVERFLOW = _gauge(
    "kor_travel_geo_pg_pool_overflow",
    "SQLAlchemy DB pool overflow connections currently opened by this API process.",
)
DB_QUERIES = _counter(
    "kor_travel_geo_db_queries_total",
    "SQL queries executed by this API process by operation, fingerprint, and status.",
    ("operation", "query_fingerprint", "status"),
)
DB_QUERY_DURATION = _histogram(
    "kor_travel_geo_db_query_duration_seconds",
    "SQL query duration by operation, fingerprint, and status.",
    ("operation", "query_fingerprint", "status"),
    (0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

_QUERY_START_ATTR: Final[str] = "_ktg_query_started_at"
_SQL_COMMENT_RE: Final[re.Pattern[str]] = re.compile(r"/\*.*?\*/|--[^\n\r]*", re.DOTALL)
_SQL_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")


def record_external_api_call(provider: str, outcome: str) -> None:
    EXTERNAL_API_CALLS.labels(provider=provider, outcome=outcome).inc()


def record_api_request_started(*, method: str) -> None:
    API_REQUESTS_IN_PROGRESS.labels(method=method).inc()


def record_api_request_finished(*, method: str) -> None:
    API_REQUESTS_IN_PROGRESS.labels(method=method).dec()


def record_api_request(
    *,
    method: str,
    route: str,
    status_code: int,
    elapsed_s: float,
    slow_threshold_ms: int | None = None,
) -> None:
    API_REQUESTS.labels(
        method=method,
        route=route,
        status_code=str(status_code),
    ).inc()
    API_REQUEST_DURATION.labels(
        method=method,
        route=route,
        status_code=str(status_code),
    ).observe(elapsed_s)
    if slow_threshold_ms is not None and elapsed_s * 1_000 >= slow_threshold_ms:
        API_SLOW_REQUESTS.labels(
            method=method,
            route=route,
            status_code=str(status_code),
        ).inc()


def record_load_job_duration(*, kind: str, state: str, elapsed_s: float) -> None:
    LOAD_JOB_DURATION.labels(kind=kind, state=state).observe(max(0.0, elapsed_s))


def record_load_job_stage_duration(
    *,
    kind: str,
    stage: str,
    outcome: str,
    elapsed_s: float,
) -> None:
    LOAD_JOB_STAGE_DURATION.labels(
        kind=kind,
        stage=_normalize_stage_label(stage),
        outcome=outcome,
    ).observe(max(0.0, elapsed_s))


def record_db_query(*, statement: str, elapsed_s: float, status: str) -> None:
    operation = _sql_operation(statement)
    fingerprint = _sql_fingerprint(statement)
    DB_QUERIES.labels(
        operation=operation,
        query_fingerprint=fingerprint,
        status=status,
    ).inc()
    DB_QUERY_DURATION.labels(
        operation=operation,
        query_fingerprint=fingerprint,
        status=status,
    ).observe(max(0.0, elapsed_s))


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


def refresh_db_pool_metrics(engine: Any) -> None:
    pool = getattr(getattr(engine, "sync_engine", engine), "pool", None)
    if pool is None:
        return

    _set_pool_metric(PG_POOL_SIZE, pool, "size")
    _set_pool_metric(PG_POOL_CHECKED_IN, pool, "checkedin")
    _set_pool_metric(PG_POOL_CHECKED_OUT, pool, "checkedout")
    _set_pool_metric(PG_POOL_OVERFLOW, pool, "overflow")


def _set_pool_metric(metric: Any, pool: object, method_name: str) -> None:
    method = getattr(pool, method_name, None)
    if not callable(method):
        return
    try:
        value = method()
    except Exception:  # pragma: no cover - defensive for alternate SQLAlchemy pool classes.
        return
    if isinstance(value, (int, float)):
        metric.set(float(value))


def install_db_query_metrics(engine: Any) -> None:
    if _prometheus_client is None:
        return

    sync_engine = getattr(engine, "sync_engine", engine)
    try:
        from sqlalchemy import event
    except ModuleNotFoundError:  # pragma: no cover - SQLAlchemy is a runtime dependency.
        return

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_cursor_execute(
        _conn: Any,
        _cursor: Any,
        _statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        setattr(context, _QUERY_START_ATTR, perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_cursor_execute(
        _conn: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        context: Any,
        _executemany: bool,
    ) -> None:
        _record_db_query_from_context(statement, context, status="success")

    @event.listens_for(sync_engine, "handle_error")
    def _handle_error(exception_context: Any) -> None:
        _record_db_query_from_context(
            str(getattr(exception_context, "statement", "") or ""),
            getattr(exception_context, "execution_context", None),
            status="error",
        )


def _record_db_query_from_context(statement: str, context: Any, *, status: str) -> None:
    started_at = getattr(context, _QUERY_START_ATTR, None)
    if not isinstance(started_at, float):
        return
    record_db_query(statement=statement, elapsed_s=perf_counter() - started_at, status=status)


def _normalize_stage_label(stage: str) -> str:
    return stage.split(":", 1)[0]


def _sql_operation(statement: str) -> str:
    stripped = statement.lstrip()
    if not stripped:
        return "unknown"
    token = stripped.split(None, 1)[0].upper()
    if token in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return token.lower()
    if token == "WITH":
        return "with"
    if token in {"CREATE", "ALTER", "DROP", "TRUNCATE"}:
        return "ddl"
    return "other"


def _sql_fingerprint(statement: str) -> str:
    normalized = _SQL_COMMENT_RE.sub(" ", statement).strip().lower()
    normalized = _SQL_WHITESPACE_RE.sub(" ", normalized)
    if not normalized:
        return "empty"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def render_prometheus() -> bytes:
    if _prometheus_client is None:
        return b""
    body = _prometheus_client.generate_latest()
    return body if isinstance(body, bytes) else bytes(body)
