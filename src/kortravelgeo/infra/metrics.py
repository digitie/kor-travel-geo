"""Prometheus metric helpers with a no-op fallback for library-only installs."""

from __future__ import annotations

import asyncio
import hashlib
import re
from time import perf_counter
from typing import TYPE_CHECKING, Any, Final

from kortravelgeo.core.source_reconcile import (
    CapacityUsage,
    CategoryCapacity,
    build_source_registry_metric_facts,
)
from kortravelgeo.dto.admin import CacheMetrics, PgStatStatementSnapshot

if TYPE_CHECKING:
    from collections.abc import Mapping

    from kortravelgeo.dto.source import SourceCapacityUsage

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
API_REQUEST_CANCELLATIONS = _counter(
    "kor_travel_geo_api_request_cancellations_total",
    "HTTP requests cancelled by client disconnect or server-side task cancellation.",
    ("method", "route"),
)
API_REQUEST_DURATION = _histogram(
    "kor_travel_geo_api_request_duration_seconds",
    "HTTP request duration by route template, method, and status code.",
    ("method", "route", "status_code"),
    (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
API_ADMISSION_WAIT = _histogram(
    "kor_travel_geo_api_admission_wait_seconds",
    "Admission-control wait time by route template, method, scope, and outcome.",
    ("method", "route", "scope", "outcome"),
    (0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)
API_ADMISSION_REJECTIONS = _counter(
    "kor_travel_geo_api_admission_rejections_total",
    "Admission-control rejected requests by route template, method, and scope.",
    ("method", "route", "scope"),
)
API_ADMISSION_IN_PROGRESS = _gauge(
    "kor_travel_geo_api_admission_in_progress",
    "HTTP requests currently holding an admission-control slot by scope.",
    ("scope",),
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
PG_POOL_CHECKOUT_TIMEOUTS = _counter(
    "kor_travel_geo_pg_pool_checkout_timeouts_total",
    "SQLAlchemy DB pool checkout timeouts by route template and method.",
    ("method", "route"),
)
DB_QUERIES = _counter(
    "kor_travel_geo_db_queries_total",
    "SQL queries executed by this API process by operation, fingerprint, and status.",
    ("operation", "query_fingerprint", "status"),
)
DB_QUERY_CANCELLATIONS = _counter(
    "kor_travel_geo_db_query_cancellations_total",
    "SQL queries cancelled by asyncio cancellation or PostgreSQL user cancellation.",
    ("operation", "query_fingerprint"),
)
SOURCE_JANITOR_RUNS = _counter(
    "kor_travel_geo_source_janitor_runs_total",
    "Upload-session janitor passes by outcome (ran or skipped on lock conflict).",
    ("outcome",),
)
SOURCE_JANITOR_SESSIONS = _counter(
    "kor_travel_geo_source_janitor_sessions_total",
    "Upload sessions processed by the janitor by transition action.",
    ("action",),
)
SOURCE_JANITOR_ABORTS = _counter(
    "kor_travel_geo_source_janitor_multipart_aborts_total",
    "Multipart upload abort attempts by the janitor by outcome.",
    ("outcome",),
)
SOURCE_RECONCILE_RUNS = _counter(
    "kor_travel_geo_source_reconcile_runs_total",
    "RustFS reconciliation passes by mode and outcome.",
    ("mode", "outcome"),
)
SOURCE_RECONCILE_ITEMS = _counter(
    "kor_travel_geo_source_reconcile_items_total",
    "Reconciliation issue items emitted by issue_type and severity.",
    ("issue_type", "severity"),
)
SOURCE_RECONCILE_RESOLVES = _counter(
    "kor_travel_geo_source_reconcile_resolves_total",
    "Reconciliation resolve attempts by action and outcome.",
    ("action", "outcome"),
)
SOURCE_HARD_DELETES = _counter(
    "kor_travel_geo_source_hard_deletes_total",
    "Manual bulk source-object hard-delete outcomes (T-212/ADR-052).",
    ("outcome",),
)
DB_QUERY_DURATION = _histogram(
    "kor_travel_geo_db_query_duration_seconds",
    "SQL query duration by operation, fingerprint, and status.",
    ("operation", "query_fingerprint", "status"),
    (0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
PG_STAT_STATEMENTS_TOTAL_EXEC_MS = _gauge(
    "kor_travel_geo_pg_stat_statements_total_exec_time_ms",
    "Latest persisted pg_stat_statements top query total execution time in milliseconds.",
    ("rank", "operation", "query_fingerprint"),
)
PG_STAT_STATEMENTS_CALLS = _gauge(
    "kor_travel_geo_pg_stat_statements_calls",
    "Latest persisted pg_stat_statements top query call count.",
    ("rank", "operation", "query_fingerprint"),
)
PG_STAT_STATEMENTS_MEAN_EXEC_MS = _gauge(
    "kor_travel_geo_pg_stat_statements_mean_exec_time_ms",
    "Latest persisted pg_stat_statements top query mean execution time in milliseconds.",
    ("rank", "operation", "query_fingerprint"),
)
PG_STAT_STATEMENTS_MAX_EXEC_MS = _gauge(
    "kor_travel_geo_pg_stat_statements_max_exec_time_ms",
    "Latest persisted pg_stat_statements top query max execution time in milliseconds.",
    ("rank", "operation", "query_fingerprint"),
)
# --- source-registry observability gauges (T-211) --------------------------
# T-203c janitor (3 counters) and T-204 reconcile (3 counters) metrics already
# exist above; T-211 adds the upload-session state gauge and the storage
# capacity gauges (doc line ~2107) — per-category object count / bytes, the
# 30-day growth, and the quarantined / soft_deleted / unregistered byte
# breakdown — fed from ``compute_source_capacity`` on each /metrics scrape.
SOURCE_UPLOAD_SESSIONS = _gauge(
    "kor_travel_geo_source_upload_sessions",
    "Upload sessions by lifecycle state.",
    ("state",),
)
SOURCE_STORAGE_OBJECTS = _gauge(
    "kor_travel_geo_source_storage_objects",
    "Live source-registry objects by category.",
    ("category",),
)
SOURCE_STORAGE_BYTES = _gauge(
    "kor_travel_geo_source_storage_bytes",
    "Live source-registry bytes by category.",
    ("category",),
)
SOURCE_STORAGE_TOTAL_OBJECTS = _gauge(
    "kor_travel_geo_source_storage_total_objects",
    "Total live source-registry objects across all categories.",
)
SOURCE_STORAGE_TOTAL_BYTES = _gauge(
    "kor_travel_geo_source_storage_total_bytes",
    "Total live source-registry bytes across all categories.",
)
SOURCE_STORAGE_QUARANTINED_BYTES = _gauge(
    "kor_travel_geo_source_storage_quarantined_bytes",
    "Source-registry bytes in quarantined files.",
)
SOURCE_STORAGE_SOFT_DELETED_BYTES = _gauge(
    "kor_travel_geo_source_storage_soft_deleted_bytes",
    "Source-registry bytes in soft-deleted files.",
)
SOURCE_STORAGE_UNREGISTERED_BYTES = _gauge(
    "kor_travel_geo_source_storage_unregistered_bytes",
    "Stored-but-unregistered object bytes the latest reconcile run found.",
)
SOURCE_STORAGE_GROWTH_30D_BYTES = _gauge(
    "kor_travel_geo_source_storage_growth_30d_bytes",
    "Source-registry bytes uploaded within the last 30 days.",
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


def record_api_request_cancelled(*, method: str, route: str) -> None:
    API_REQUEST_CANCELLATIONS.labels(method=method, route=route).inc()


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


def record_api_admission_started(*, scope: str) -> None:
    API_ADMISSION_IN_PROGRESS.labels(scope=scope).inc()


def record_api_admission_finished(*, scope: str) -> None:
    API_ADMISSION_IN_PROGRESS.labels(scope=scope).dec()


def record_api_admission_wait(
    *,
    method: str,
    route: str,
    scope: str,
    outcome: str,
    elapsed_s: float,
) -> None:
    API_ADMISSION_WAIT.labels(
        method=method,
        route=route,
        scope=scope,
        outcome=outcome,
    ).observe(max(0.0, elapsed_s))


def record_api_admission_rejection(*, method: str, route: str, scope: str) -> None:
    API_ADMISSION_REJECTIONS.labels(method=method, route=route, scope=scope).inc()


def record_db_pool_checkout_timeout(*, method: str, route: str) -> None:
    PG_POOL_CHECKOUT_TIMEOUTS.labels(method=method, route=route).inc()


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
    operation = sql_operation(statement)
    fingerprint = sql_fingerprint(statement)
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
    if status == "cancelled":
        DB_QUERY_CANCELLATIONS.labels(
            operation=operation,
            query_fingerprint=fingerprint,
        ).inc()


def record_source_janitor_run(*, outcome: str) -> None:
    """Count one janitor pass: ``ran`` or ``skipped_locked``."""
    SOURCE_JANITOR_RUNS.labels(outcome=outcome).inc()


def record_source_janitor_session(*, action: str) -> None:
    """Count one session the janitor acted on by transition action."""
    SOURCE_JANITOR_SESSIONS.labels(action=action).inc()


def record_source_janitor_abort(*, outcome: str) -> None:
    """Count one multipart abort attempt: ``succeeded`` or ``failed``."""
    SOURCE_JANITOR_ABORTS.labels(outcome=outcome).inc()


def record_source_reconcile_run(*, mode: str, outcome: str) -> None:
    """Count one reconciliation pass by mode (quick/deep) and outcome."""
    SOURCE_RECONCILE_RUNS.labels(mode=mode, outcome=outcome).inc()


def record_source_reconcile_item(*, issue_type: str, severity: str) -> None:
    """Count one reconciliation issue item by issue_type and severity."""
    SOURCE_RECONCILE_ITEMS.labels(issue_type=issue_type, severity=severity).inc()


def record_source_reconcile_resolve(*, action: str, outcome: str) -> None:
    """Count one reconciliation resolve attempt by action and outcome."""
    SOURCE_RECONCILE_RESOLVES.labels(action=action, outcome=outcome).inc()


def record_source_hard_delete(*, outcome: str) -> None:
    """Count one manual bulk source-object hard-delete outcome (T-212)."""
    SOURCE_HARD_DELETES.labels(outcome=outcome).inc()


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


def refresh_pg_stat_statement_metrics(rows: list[PgStatStatementSnapshot]) -> None:
    for metric in (
        PG_STAT_STATEMENTS_TOTAL_EXEC_MS,
        PG_STAT_STATEMENTS_CALLS,
        PG_STAT_STATEMENTS_MEAN_EXEC_MS,
        PG_STAT_STATEMENTS_MAX_EXEC_MS,
    ):
        _clear_metric(metric)
    for row in rows:
        labels = {
            "rank": str(row.rank),
            "operation": row.operation,
            "query_fingerprint": row.query_fingerprint,
        }
        PG_STAT_STATEMENTS_TOTAL_EXEC_MS.labels(**labels).set(row.total_exec_time_ms)
        PG_STAT_STATEMENTS_CALLS.labels(**labels).set(row.calls)
        PG_STAT_STATEMENTS_MEAN_EXEC_MS.labels(**labels).set(row.mean_exec_time_ms)
        PG_STAT_STATEMENTS_MAX_EXEC_MS.labels(**labels).set(row.max_exec_time_ms)


def _clear_metric(metric: Any) -> None:
    clear = getattr(metric, "clear", None)
    if not callable(clear):
        return
    try:
        clear()
    except Exception:  # pragma: no cover - defensive for alternate metric backends.
        return


def refresh_source_registry_metrics(
    *,
    capacity: SourceCapacityUsage,
    session_state_counts: Mapping[str, int] | None = None,
) -> None:
    """Set the source-registry observability gauges from a capacity snapshot (T-211).

    Reuses :func:`compute_source_capacity`'s DTO (per-category counts/bytes, the
    quarantined / soft_deleted / unregistered breakdown, and the 30-day growth)
    plus an upload-session ``GROUP BY state`` count, wired into the same
    ``/metrics`` scrape path as :func:`refresh_admin_metrics`. The projection is
    pure (``build_source_registry_metric_facts``) so it is unit-tested DB-free.
    """
    facts = build_source_registry_metric_facts(
        _capacity_usage_from_dto(capacity),
        session_state_counts=session_state_counts,
    )
    for category, count in facts.category_objects:
        SOURCE_STORAGE_OBJECTS.labels(category=category).set(count)
    for category, byte_count in facts.category_bytes:
        SOURCE_STORAGE_BYTES.labels(category=category).set(byte_count)
    SOURCE_STORAGE_TOTAL_OBJECTS.set(facts.total_objects)
    SOURCE_STORAGE_TOTAL_BYTES.set(facts.total_bytes)
    SOURCE_STORAGE_QUARANTINED_BYTES.set(facts.quarantined_bytes)
    SOURCE_STORAGE_SOFT_DELETED_BYTES.set(facts.soft_deleted_bytes)
    SOURCE_STORAGE_UNREGISTERED_BYTES.set(facts.unregistered_bytes)
    SOURCE_STORAGE_GROWTH_30D_BYTES.set(facts.growth_30d_bytes)
    for state, count in facts.session_states:
        SOURCE_UPLOAD_SESSIONS.labels(state=state).set(count)


def _capacity_usage_from_dto(capacity: SourceCapacityUsage) -> CapacityUsage:
    """Map the API capacity DTO back to the core dataclass for the pure builder.

    ``core`` cannot import ``dto`` (downward layer hop), so this infra-layer
    adapter bridges the identical-field DTO into :class:`CapacityUsage`.
    """
    return CapacityUsage(
        categories=tuple(
            CategoryCapacity(
                category=c.category,
                object_count=c.object_count,
                total_bytes=c.total_bytes,
                quarantined_bytes=c.quarantined_bytes,
                soft_deleted_bytes=c.soft_deleted_bytes,
            )
            for c in capacity.categories
        ),
        total_object_count=capacity.total_object_count,
        total_bytes=capacity.total_bytes,
        quarantined_bytes=capacity.quarantined_bytes,
        soft_deleted_bytes=capacity.soft_deleted_bytes,
        unregistered_bytes=capacity.unregistered_bytes,
        growth_30d_bytes=capacity.growth_30d_bytes,
        capacity_limit_bytes=capacity.capacity_limit_bytes,
        over_threshold=capacity.over_threshold,
    )


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
            status=_db_query_status_from_exception(exception_context),
        )


def _record_db_query_from_context(statement: str, context: Any, *, status: str) -> None:
    started_at = getattr(context, _QUERY_START_ATTR, None)
    if not isinstance(started_at, float):
        return
    record_db_query(statement=statement, elapsed_s=perf_counter() - started_at, status=status)


def _db_query_status_from_exception(exception_context: Any) -> str:
    for attr in ("original_exception", "sqlalchemy_exception"):
        exc = getattr(exception_context, attr, None)
        if isinstance(exc, BaseException) and _is_cancelled_exception(exc):
            return "cancelled"
    return "error"


def _is_cancelled_exception(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return True
    exceptions = getattr(exc, "exceptions", None)
    if isinstance(exceptions, tuple) and any(
        isinstance(child, BaseException) and _is_cancelled_exception(child)
        for child in exceptions
    ):
        return True
    exc_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    return exc_name == "querycanceled" and "user request" in message


def _normalize_stage_label(stage: str) -> str:
    return stage.split(":", 1)[0]


def sql_operation(statement: str) -> str:
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


def sql_fingerprint(statement: str) -> str:
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
