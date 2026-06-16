"""Sampled slow-request and slow-query persistence."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.metrics import sql_fingerprint, sql_operation
from kortravelgeo.settings import Settings

SlowSampleType = Literal["api_request", "db_query", "overload"]

_LOGGER = logging.getLogger("kortravelgeo.observability.slow")
_SQL_LITERAL_RE = re.compile(
    r"\$([A-Za-z_][A-Za-z_0-9]*)\$.*?\$\1\$|\$\$.*?\$\$|"
    r"[eE]?'(?:''|[^'])*'|\b\d+(?:\.\d+)?\b",
    re.DOTALL,
)
_SQL_SPACE_RE = re.compile(r"\s+")
_SLOW_OBSERVABILITY_TABLE = "ops.slow_observability_samples"
_SLOW_SAMPLE_INSERT_SQL = text(
    """
INSERT INTO ops.slow_observability_samples
  (slow_sample_id, captured_at, sample_type, method, route, status_code,
   elapsed_ms, threshold_ms, sample_rate, operation, query_fingerprint,
   query_preview, plan, context)
VALUES
  (:slow_sample_id, :captured_at, :sample_type, :method, :route, :status_code,
   :elapsed_ms, :threshold_ms, :sample_rate, :operation, :query_fingerprint,
   :query_preview, :plan, :context)
"""
).bindparams(bindparam("plan", type_=JSONB), bindparam("context", type_=JSONB))


@dataclass(frozen=True, slots=True)
class _RequestContext:
    method: str
    route: str


@dataclass(frozen=True, slots=True)
class _SlowObservabilityConfig:
    enabled: bool = False
    slow_query_ms: int = 250
    slow_request_ms: int = 500
    sample_rate: float = 1.0
    min_interval_ms: int = 1_000
    queue_size: int = 1_000
    flush_interval_ms: int = 1_000
    flush_batch_size: int = 50
    explain_enabled: bool = False
    explain_timeout_ms: int = 3_000


@dataclass(slots=True)
class SlowObservabilitySample:
    slow_sample_id: str
    captured_at: datetime
    sample_type: SlowSampleType
    elapsed_ms: float
    sample_rate: float
    method: str | None = None
    route: str | None = None
    status_code: int | None = None
    threshold_ms: int | None = None
    operation: str | None = None
    query_fingerprint: str | None = None
    query_preview: str | None = None
    plan: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    _statement: str | None = field(default=None, repr=False)
    _parameters: Any = field(default=None, repr=False)
    _executemany: bool = field(default=False, repr=False)


_REQUEST_CONTEXT: ContextVar[_RequestContext | None] = ContextVar(
    "ktg_slow_observability_request",
    default=None,
)
_SUPPRESS_SAMPLING: ContextVar[bool] = ContextVar(
    "ktg_slow_observability_suppressed",
    default=False,
)
_config = _SlowObservabilityConfig()
_queue: deque[SlowObservabilitySample] = deque()
_last_sample_at: dict[tuple[str, str, str], float] = {}
_dropped_samples = 0


def configure_slow_observability(settings: Settings) -> None:
    """Configure the process-local sampler from runtime settings."""

    global _config
    _config = _SlowObservabilityConfig(
        enabled=settings.ops_slow_samples_enabled,
        slow_query_ms=settings.ops_slow_query_ms,
        slow_request_ms=settings.api_slow_request_ms,
        sample_rate=settings.ops_slow_sample_rate,
        min_interval_ms=settings.ops_slow_sample_min_interval_ms,
        queue_size=settings.ops_slow_sample_queue_size,
        flush_interval_ms=settings.ops_slow_sample_flush_interval_ms,
        flush_batch_size=settings.ops_slow_sample_flush_batch_size,
        explain_enabled=settings.ops_slow_query_explain_enabled,
        explain_timeout_ms=settings.ops_slow_query_explain_timeout_ms,
    )
    if not _config.enabled:
        _queue.clear()
        _last_sample_at.clear()


def slow_observability_enabled() -> bool:
    return _config.enabled


def set_request_observability_context(method: str, route: str) -> Token[_RequestContext | None]:
    return _REQUEST_CONTEXT.set(_RequestContext(method=method, route=route))


def reset_request_observability_context(token: Token[_RequestContext | None]) -> None:
    _REQUEST_CONTEXT.reset(token)


@contextmanager
def suppress_slow_observability() -> Any:
    token = _SUPPRESS_SAMPLING.set(True)
    try:
        yield
    finally:
        _SUPPRESS_SAMPLING.reset(token)


def record_slow_api_request(
    *,
    method: str,
    route: str,
    status_code: int,
    elapsed_ms: float,
) -> None:
    if not _config.enabled or _SUPPRESS_SAMPLING.get():
        return
    if elapsed_ms < _config.slow_request_ms:
        return
    _enqueue(
        SlowObservabilitySample(
            slow_sample_id=str(uuid4()),
            captured_at=datetime.now(UTC),
            sample_type="api_request",
            method=method,
            route=route,
            status_code=status_code,
            elapsed_ms=round(elapsed_ms, 3),
            threshold_ms=_config.slow_request_ms,
            sample_rate=_config.sample_rate,
            context={"source": "api_middleware", "slow": True},
        )
    )


def record_overload_event(*, method: str, route: str, scope: str) -> None:
    if not _config.enabled or _SUPPRESS_SAMPLING.get():
        return
    _enqueue(
        SlowObservabilitySample(
            slow_sample_id=str(uuid4()),
            captured_at=datetime.now(UTC),
            sample_type="overload",
            method=method,
            route=route,
            status_code=429,
            elapsed_ms=0.0,
            threshold_ms=None,
            sample_rate=_config.sample_rate,
            context={"source": "admission_control", "scope": scope},
        )
    )


def record_slow_query(
    statement: str,
    parameters: Any,
    elapsed_s: float,
    status: str,
    executemany: bool = False,
) -> None:
    if not _config.enabled or _SUPPRESS_SAMPLING.get():
        return
    elapsed_ms = elapsed_s * 1_000
    if elapsed_ms < _config.slow_query_ms:
        return
    if _SLOW_OBSERVABILITY_TABLE in statement:
        return
    context = _REQUEST_CONTEXT.get()
    fingerprint = sql_fingerprint(statement)
    _enqueue(
        SlowObservabilitySample(
            slow_sample_id=str(uuid4()),
            captured_at=datetime.now(UTC),
            sample_type="db_query",
            method=context.method if context is not None else None,
            route=context.route if context is not None else None,
            elapsed_ms=round(elapsed_ms, 3),
            threshold_ms=_config.slow_query_ms,
            sample_rate=_config.sample_rate,
            operation=sql_operation(statement),
            query_fingerprint=fingerprint,
            query_preview=slow_query_preview(statement),
            context={
                "source": "sqlalchemy_event",
                "status": status,
                "explain_requested": _config.explain_enabled,
                "executemany": executemany,
            },
            _statement=statement,
            _parameters=parameters,
            _executemany=executemany,
        )
    )


async def run_slow_observability_flush_loop(engine: AsyncEngine) -> None:
    """Persist queued samples until cancelled."""

    while True:
        await flush_slow_observability_samples(engine)
        await asyncio.sleep(_config.flush_interval_ms / 1_000)


async def flush_slow_observability_samples(engine: AsyncEngine) -> int:
    if not _config.enabled:
        return 0
    samples = _pop_samples(_config.flush_batch_size)
    if not samples:
        return 0
    records: list[dict[str, Any]] = []
    for sample in samples:
        if sample.sample_type == "db_query" and _config.explain_enabled:
            sample.plan = await _safe_explain_sample(engine, sample)
        records.append(sample_record(sample))
    with suppress_slow_observability():
        async with engine.begin() as conn:
            await conn.execute(_SLOW_SAMPLE_INSERT_SQL, records)
    return len(records)


def sample_record(sample: SlowObservabilitySample) -> dict[str, Any]:
    return {
        "slow_sample_id": sample.slow_sample_id,
        "captured_at": sample.captured_at,
        "sample_type": sample.sample_type,
        "method": sample.method,
        "route": sample.route,
        "status_code": sample.status_code,
        "elapsed_ms": sample.elapsed_ms,
        "threshold_ms": sample.threshold_ms,
        "sample_rate": sample.sample_rate,
        "operation": sample.operation,
        "query_fingerprint": sample.query_fingerprint,
        "query_preview": sample.query_preview,
        "plan": sample.plan,
        "context": sample.context,
    }


def slow_query_preview(statement: str) -> str:
    normalized = _SQL_SPACE_RE.sub(" ", statement).strip()
    masked = _SQL_LITERAL_RE.sub("?", normalized)
    return (masked[:500] or "empty")


def queued_slow_sample_count() -> int:
    return len(_queue)


def dropped_slow_sample_count() -> int:
    return _dropped_samples


def pop_slow_samples_for_tests() -> list[SlowObservabilitySample]:
    return _pop_samples(len(_queue) or 1_000)


def reset_slow_observability_for_tests() -> None:
    global _config, _dropped_samples
    _config = _SlowObservabilityConfig()
    _queue.clear()
    _last_sample_at.clear()
    _dropped_samples = 0


def _enqueue(sample: SlowObservabilitySample) -> None:
    global _dropped_samples
    if not _config.enabled or _SUPPRESS_SAMPLING.get():
        return
    if _config.sample_rate <= 0.0:
        return
    if _config.sample_rate < 1.0 and random.random() > _config.sample_rate:
        return
    now = monotonic()
    key = _sample_throttle_key(sample)
    last = _last_sample_at.get(key)
    if last is not None and (now - last) * 1_000 < _config.min_interval_ms:
        return
    if len(_queue) >= _config.queue_size:
        _dropped_samples += 1
        return
    _last_sample_at[key] = now
    _queue.append(sample)
    _LOGGER.info(
        f"{sample.sample_type}_sampled",
        extra={
            "sample_type": sample.sample_type,
            "method": sample.method,
            "route": sample.route,
            "status_code": sample.status_code,
            "elapsed_ms": sample.elapsed_ms,
            "threshold_ms": sample.threshold_ms,
            "operation": sample.operation,
            "query_fingerprint": sample.query_fingerprint,
            "sample_queue_size": len(_queue),
        },
    )


def _sample_throttle_key(sample: SlowObservabilitySample) -> tuple[str, str, str]:
    if sample.sample_type == "db_query":
        return (
            sample.sample_type,
            sample.route or "unknown",
            sample.query_fingerprint or "unknown",
        )
    return (
        sample.sample_type,
        sample.route or "unknown",
        str(sample.context.get("scope") or sample.status_code or "unknown"),
    )


def _pop_samples(limit: int) -> list[SlowObservabilitySample]:
    batch: list[SlowObservabilitySample] = []
    while _queue and len(batch) < limit:
        batch.append(_queue.popleft())
    return batch


async def _safe_explain_sample(
    engine: AsyncEngine,
    sample: SlowObservabilitySample,
) -> dict[str, Any]:
    statement = sample._statement
    if statement is None:
        return {"skipped": "missing_statement"}
    if sample._executemany:
        return {"skipped": "executemany"}
    query = statement.strip()
    if not _is_explainable_query(query):
        return {"skipped": "not_select_or_with"}
    try:
        with suppress_slow_observability():
            async with engine.begin() as conn:
                await conn.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": f"{_config.explain_timeout_ms}ms"},
                )
                result = await conn.exec_driver_sql(
                    f"EXPLAIN (FORMAT JSON) {query}",
                    sample._parameters,
                )
                plan = result.scalar()
    except Exception as exc:  # pragma: no cover - defensive around driver-specific SQL.
        return {"error_type": exc.__class__.__name__, "error": str(exc)[:500]}
    return {"format": "json", "plan": _redact_plan(plan)}


def _is_explainable_query(query: str) -> bool:
    lowered = query.lower()
    if ";" in query:
        return False
    if lowered.startswith("explain"):
        return False
    if _SLOW_OBSERVABILITY_TABLE in lowered:
        return False
    return lowered.startswith(("select", "with"))


def _redact_plan(value: Any) -> Any:
    if isinstance(value, str):
        return slow_query_preview(value)
    if isinstance(value, list):
        return [_redact_plan(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact_plan(item) for key, item in value.items()}
    return value
