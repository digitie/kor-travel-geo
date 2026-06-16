"""SQLAlchemy async engine factory."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import orjson
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from kortravelgeo.infra.metrics import install_db_query_metrics
from kortravelgeo.infra.slow_observability import record_slow_query
from kortravelgeo.settings import Settings, get_settings


def _json_serializer(value: Any) -> str:
    return orjson.dumps(value).decode()


def _connect_options(settings: Settings) -> str:
    # x_extension is where PostGIS/pg_trgm/unaccent live. Keeping it in search_path
    # avoids public-schema extension drift while still allowing unqualified ST_* calls.
    return (
        f"-c statement_timeout={settings.pg_statement_timeout_ms} "
        f"-c search_path={settings.pg_search_path}"
    )


def make_async_engine(
    settings: Settings | None = None,
    *,
    pg_dsn: str | None = None,
    connect_args: Mapping[str, Any] | None = None,
) -> AsyncEngine:
    """Create the shared SQLAlchemy 2 async engine.

    ``Settings.pg_dsn`` is already normalized by ``Settings.normalize_pg_dsn``.
    This factory deliberately trusts that value and only wires pool, timeout, and
    JSON serialization settings.
    """

    resolved = settings or get_settings()
    if pg_dsn is not None:
        resolved = resolved.model_copy(update={"pg_dsn": pg_dsn})

    merged_connect_args: dict[str, Any] = {
        "options": _connect_options(resolved),
        "prepare_threshold": resolved.pg_prepare_threshold,
    }
    if connect_args:
        merged_connect_args.update(connect_args)

    engine = create_async_engine(
        resolved.pg_dsn,
        pool_size=resolved.pg_pool_size,
        max_overflow=resolved.pg_max_overflow,
        pool_timeout=resolved.pg_pool_timeout_ms / 1_000,
        pool_pre_ping=True,
        pool_recycle=resolved.pg_pool_recycle_s,
        poolclass=AsyncAdaptedQueuePool,
        connect_args=merged_connect_args,
        json_serializer=_json_serializer,
        json_deserializer=orjson.loads,
    )
    if resolved.pg_query_metrics_enabled:
        install_db_query_metrics(
            engine,
            slow_query_recorder=record_slow_query
            if resolved.ops_slow_samples_enabled
            else None,
        )
    return engine
