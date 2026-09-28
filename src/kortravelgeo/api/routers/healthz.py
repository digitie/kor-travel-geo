"""Health endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from time import perf_counter
from typing import Any, cast

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from kortravelgeo.api.admission import AdmissionScopeSnapshot
from kortravelgeo.dto.health import (
    ComponentStatus,
    ReadinessComponent,
    ReadinessResponse,
    ReadinessStatus,
)
from kortravelgeo.settings import Settings, get_settings

router = APIRouter(tags=["health"])

# Relations geocode/search read directly. When they are missing, unpopulated or empty (before
# the first load, after a restore without MV data, mid refresh) requests return nothing or fall
# into slow fallbacks that hit statement_timeout (2026-09-28). An empty DB before the first
# load is a legitimate state, so this only marks readiness degraded (HTTP 200), never 503.
_SERVING_RELATIONS = ("mv_geocode_target", "mv_geocode_text_search")
_SERVING_CATALOG_SQL = """
SELECT r.relation_name, c.relispopulated
  FROM unnest(CAST(:names AS text[])) AS r(relation_name)
  LEFT JOIN pg_class c ON c.oid = to_regclass(r.relation_name)
"""


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
        components = {
            "database": ReadinessComponent(
                status="unavailable",
                detail={"reason": "client_not_started"},
            ),
            "pool": ReadinessComponent(status="unknown"),
        }
        admission = _admission_component(request, settings)
        if admission is not None:
            components["admission"] = admission
        return ReadinessResponse(
            status="unavailable",
            ready=False,
            degraded=True,
            components=components,
        )

    pool = _pool_component(engine, settings)
    if pool.status == "saturated":
        response.status_code = 503
        components = {
            "database": ReadinessComponent(
                status="skipped",
                detail={"reason": "pool_saturated"},
            ),
            "pool": pool,
        }
        admission = _admission_component(request, settings)
        if admission is not None:
            components["admission"] = admission
        return ReadinessResponse(
            status="unavailable",
            ready=False,
            degraded=True,
            components=components,
        )

    database = await _database_component(engine, settings.api_readiness_timeout_ms)
    serving = (
        await _serving_component(engine, settings.api_readiness_timeout_ms)
        if database.status == "ok"
        else ReadinessComponent(status="skipped", detail={"reason": "database_unavailable"})
    )
    admission = _admission_component(request, settings)
    ready = database.status == "ok"
    degraded = (
        database.status != "ok"
        or pool.status == "degraded"
        or serving.status == "degraded"
        or (admission is not None and admission.status in {"degraded", "saturated"})
    )
    if not ready:
        response.status_code = 503
    components = {"database": database, "pool": pool, "serving": serving}
    if admission is not None:
        components["admission"] = admission
    return ReadinessResponse(
        status=_readiness_status(ready=ready, degraded=degraded),
        ready=ready,
        degraded=degraded,
        components=components,
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


async def _serving_component(engine: Any, timeout_ms: int) -> ReadinessComponent:
    """Serving MV state: ``ok``, ``degraded`` (a relation is not ok) or ``unknown``.

    A failed or slow probe reports ``unknown`` and does not flip ``degraded`` (same as the pool
    component): the database probe alone decides readiness.
    """
    started = perf_counter()
    try:
        relations = await asyncio.wait_for(
            _probe_serving_relations(engine),
            timeout=timeout_ms / 1_000,
        )
    except TimeoutError:
        return ReadinessComponent(
            status="unknown",
            latency_ms=_elapsed_ms(started),
            error_type="TimeoutError",
        )
    except Exception as exc:
        return ReadinessComponent(
            status="unknown",
            latency_ms=_elapsed_ms(started),
            error_type=type(exc).__name__,
        )
    ok = all(state == "ok" for state in relations.values())
    return ReadinessComponent(
        status="ok" if ok else "degraded",
        latency_ms=_elapsed_ms(started),
        detail={"relations": relations},
    )


async def _probe_serving_relations(engine: Any) -> dict[str, str]:
    """Per relation ``ok``/``empty``/``not_populated``/``missing``.

    Never ``count(*)`` (6.4M rows each). The catalog lookup settles missing/unpopulated
    relations (selecting from an unpopulated MV raises), then one ``EXISTS (SELECT 1 ...)``
    per populated relation stops at the first row.
    """
    async with engine.connect() as conn:
        catalog = (
            await conn.execute(
                text(_SERVING_CATALOG_SQL),
                {"names": list(_SERVING_RELATIONS)},
            )
        ).mappings().all()
        states: dict[str, str] = {}
        populated: list[str] = []
        for row in catalog:
            name = str(row["relation_name"])
            if row["relispopulated"] is None:
                states[name] = "missing"
            elif not row["relispopulated"]:
                states[name] = "not_populated"
            else:
                populated.append(name)
        if populated:
            # Names come from the fixed _SERVING_RELATIONS allowlist, never from input.
            exists_sql = "SELECT " + ", ".join(
                f"EXISTS (SELECT 1 FROM {name}) AS {name}" for name in populated
            )
            found = (await conn.execute(text(exists_sql))).mappings().one()
            for name in populated:
                states[name] = "ok" if found[name] else "empty"
    return {name: states.get(name, "missing") for name in _SERVING_RELATIONS}


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
        "timeout_ms": settings.pg_pool_timeout_ms,
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


def _admission_component(request: Request, settings: Settings) -> ReadinessComponent | None:
    controller = getattr(request.app.state, "admission_control", None)
    snapshots_method = getattr(controller, "snapshots", None)
    if not callable(snapshots_method):
        return None

    snapshots = tuple(cast("Sequence[AdmissionScopeSnapshot]", snapshots_method()))
    if not snapshots:
        return None

    max_utilization = max(snapshot.utilization for snapshot in snapshots)
    status: ComponentStatus = "ok"
    if any(snapshot.available <= 0 for snapshot in snapshots):
        status = "saturated"
    elif max_utilization >= 0.8:
        status = "degraded"
    return ReadinessComponent(
        status=status,
        detail={
            "timeout_ms": settings.api_admission_timeout_ms,
            "max_utilization": round(max_utilization, 4),
            "scopes": [
                {
                    "scope": snapshot.scope,
                    "limit": snapshot.limit,
                    "in_use": snapshot.in_use,
                    "available": snapshot.available,
                    "utilization": snapshot.utilization,
                }
                for snapshot in snapshots
            ],
        },
    )


def _readiness_status(*, ready: bool, degraded: bool) -> ReadinessStatus:
    if not ready:
        return "unavailable"
    return "degraded" if degraded else "ok"


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1_000, 3)
