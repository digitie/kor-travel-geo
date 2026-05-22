"""Async SQLAlchemy engine factory."""

from __future__ import annotations

from typing import Any

import orjson
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kraddr.geo.settings import Settings, get_settings


def _json_serializer(value: Any) -> str:
    return orjson.dumps(value).decode()


def make_async_engine(
    settings: Settings | None = None,
    *,
    pg_dsn: str | None = None,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine from normalized application settings."""

    resolved = settings or get_settings()
    dsn = pg_dsn or resolved.pg_dsn
    return create_async_engine(
        dsn,
        pool_size=resolved.pg_pool_size,
        max_overflow=resolved.pg_max_overflow,
        pool_pre_ping=True,
        pool_recycle=resolved.pg_pool_recycle_s,
        connect_args={"options": f"-c statement_timeout={resolved.pg_statement_timeout_ms}"},
        json_serializer=_json_serializer,
        json_deserializer=orjson.loads,
    )
