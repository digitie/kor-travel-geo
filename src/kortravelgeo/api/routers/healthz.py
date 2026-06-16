"""Health endpoints."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from kortravelgeo.dto.health import (
    ReadinessComponent,
    ReadinessResponse,
    ReadinessStatus,
)
from kortravelgeo.settings import Settings, get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    response_model_exclude_none=True,
)
async def readyz(request: Request, response: Response) -> ReadinessResponse:
    client = getattr(request.app.state, "client", None)
    engine = getattr(client, "engine", None)
    settings = get_settings()

    if engine is None:
        response.status_code = 503
        return ReadinessResponse(
            status="unavailable",
            ready=False,
            degraded=True,
            components={
                "database": ReadinessComponent(
                    status="unavailable",
                    detail={"reason": "client_not_started"},
                ),
                "pool": ReadinessComponent(status="unknown"),
            },
        )

    pool = _pool_component(engine, settings)
    if pool.status == "saturated":
        response.status_code = 503
        return ReadinessResponse(
            status="unavailable",
            ready=False,
            degraded=True,
            components={
                "database": ReadinessComponent(
                    status="skipped",
                    detail={"reason": "pool_saturated"},
                ),
                "pool": pool,
            },
        )

    database = await _database_component(engine, settings.api_readiness_timeout_ms)
    ready = database.status == "ok"
    degraded = database.status != "ok" or pool.status == "degraded"
    if not ready:
        response.status_code = 503
    return ReadinessResponse(
        status=_readiness_status(ready=ready, degraded=degraded),
        ready=ready,
        degraded=degraded,
        components={"database": database, "pool": pool},
    )


async def _database_component(engine: Any, timeout_ms: int) -> ReadinessComponent:
    started = perf_counter()
    try:
        row = await asyncio.wait_for(
            _probe_database(engine),
            timeout=timeout_ms / 1_000,
        )
    except TimeoutError:
        return ReadinessComponent(
            status="unavailable",
            latency_ms=_elapsed_ms(started),
            error_type="TimeoutError",
        )
    except Exception as exc:
        return ReadinessComponent(
            status="unavailable",
            latency_ms=_elapsed_ms(started),
            error_type=type(exc).__name__,
        )

    return ReadinessComponent(
        status="ok",
        latency_ms=_elapsed_ms(started),
        detail={
            "current_database": str(row.get("current_database") or ""),
            "postgres_version": str(row.get("postgres_version") or ""),
        },
    )


async def _probe_database(engine: Any) -> dict[str, Any]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
SELECT current_database() AS current_database,
       current_setting('server_version') AS postgres_version
"""
                )
            )
        ).mappings().one()
    return dict(row)


def _pool_component(engine: Any, settings: Settings) -> ReadinessComponent:
    pool = getattr(getattr(engine, "sync_engine", engine), "pool", None)
    if pool is None:
        return ReadinessComponent(status="unknown")

    size = _pool_value(pool, "size")
    checked_in = _pool_value(pool, "checkedin")
    checked_out = _pool_value(pool, "checkedout")
    overflow = _pool_value(pool, "overflow")
    if size is None or checked_in is None or checked_out is None:
        return ReadinessComponent(status="unknown")

    capacity = int(settings.pg_pool_size) + int(settings.pg_max_overflow)
    utilization = checked_out / capacity if capacity > 0 else 1.0
    detail = {
        "size": size,
        "checked_in": checked_in,
        "checked_out": checked_out,
        "overflow": overflow,
        "capacity": capacity,
        "utilization": round(utilization, 4),
    }
    if checked_out >= capacity and checked_in <= 0:
        return ReadinessComponent(status="saturated", detail=detail)
    if utilization >= 0.8:
        return ReadinessComponent(status="degraded", detail=detail)
    return ReadinessComponent(status="ok", detail=detail)


def _pool_value(pool: object, method_name: str) -> int | None:
    method = getattr(pool, method_name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:
        return None
    return int(value) if isinstance(value, (int, float)) else None


def _readiness_status(*, ready: bool, degraded: bool) -> ReadinessStatus:
    if not ready:
        return "unavailable"
    return "degraded" if degraded else "ok"


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1_000, 3)
