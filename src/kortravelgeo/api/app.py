"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kortravelgeo.api._dagster_recovery import (
    dagster_liveness_probe,
    dagster_orchestrator_cancel,
)
from kortravelgeo.api._full_load_launch import submit_full_load_batch
from kortravelgeo.api._reconciler import DagsterJobReconciler
from kortravelgeo.api.admission import (
    AdmissionController,
    admission_scope_setting_name,
    build_admission_controller,
)
from kortravelgeo.api.middleware.geoip_gate import install_geoip_gate
from kortravelgeo.api.responses import error_payload, register_exception_handlers
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.exceptions import RateLimitError
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import run_backup_job, run_restore_job
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)
from kortravelgeo.infra.load_job_executor import LoadJobExecutor
from kortravelgeo.infra.metrics import (
    PROMETHEUS_CONTENT_TYPE,
    record_api_admission_finished,
    record_api_admission_rejection,
    record_api_admission_started,
    record_api_admission_wait,
    record_api_request,
    record_api_request_cancelled,
    record_api_request_finished,
    record_api_request_started,
    refresh_admin_metrics,
    refresh_db_pool_metrics,
    refresh_pg_stat_statement_metrics,
    refresh_source_registry_metrics,
    render_prometheus,
)
from kortravelgeo.infra.slow_observability import (
    configure_slow_observability,
    record_overload_event,
    record_slow_api_request,
    reset_request_observability_context,
    run_slow_observability_flush_loop,
    set_request_observability_context,
)
from kortravelgeo.loaders.bulk_loader import load_bulk_delivery
from kortravelgeo.loaders.consistency import DEFAULT_CASES, run_all_cases
from kortravelgeo.loaders.pobox_loader import load_pobox
from kortravelgeo.loaders.postload import (
    refresh_mv,
    refresh_region_radius_parts,
    resolve_text_geometry_links,
)
from kortravelgeo.loaders.runtime_warm import run_runtime_warm, runtime_warm_report_metrics
from kortravelgeo.loaders.shp.polygons_loader import load_shp_polygons
from kortravelgeo.loaders.sppn_makarea_loader import load_sppn_makarea
from kortravelgeo.loaders.text.daily_juso_loader import load_daily_juso_delta
from kortravelgeo.loaders.text.juso_hangul_loader import load_juso_hangul
from kortravelgeo.loaders.text.locsum_loader import load_locsum
from kortravelgeo.loaders.text.navi_loader import load_navi
from kortravelgeo.loaders.text.parcel_link_loader import (
    load_daily_parcel_link_delta,
    load_juso_parcel_link_snapshot,
)
from kortravelgeo.loaders.text.roadaddr_entrance_loader import load_roadaddr_entrances
from kortravelgeo.settings import Settings, get_settings
from kortravelgeo.version import __version__

from .routers import admin, dagster, geocode, healthz, pobox, reverse, search, v2, zipcode

_LOGGER = logging.getLogger(__name__)
_PERFORMANCE_LOGGER = logging.getLogger("kortravelgeo.api.performance")
_ADMISSION_RETRY_AFTER_SECONDS = "1"
_CLIENT_CLOSED_STATUS_CODE = 499
_CLIENT_DISCONNECT_CANCEL_PREFIXES = ("/v1/address/", "/v2/")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = AsyncAddressClient()
    await client.__aenter__()
    app.state.client = client
    assert client.engine is not None
    # Executor-aware Dagster reconciler (T-290k §2h/§3) — owns the dagster half of startup
    # recovery (queue.recover_startup now does in-process only) plus a periodic convergence
    # tick, using the REAL GraphQL run-status probe + terminateRun cancel seam.
    reconciler = DagsterJobReconciler(
        client.engine,
        executor=LoadJobExecutor(
            client.engine, lease_ttl_seconds=get_settings().dagster_lease_ttl_seconds
        ),
        liveness_probe=dagster_liveness_probe(get_settings()),
        orchestrator_cancel=dagster_orchestrator_cancel(get_settings()),
    )
    app.state.job_reconciler = reconciler
    if get_settings().dagster_reconcile_on_startup:
        await reconciler.reconcile_once()
    reconciler_task = _start_dagster_reconciler_scheduler(reconciler, get_settings())
    app.state.dagster_reconciler_task = reconciler_task
    table_stats_task = _start_table_stats_capture_scheduler(client.engine, get_settings())
    app.state.table_stats_capture_task = table_stats_task
    pg_stat_task = _start_pg_stat_statements_capture_scheduler(client.engine, get_settings())
    app.state.pg_stat_statements_capture_task = pg_stat_task
    runtime_warm_task = _start_runtime_warm_scheduler(client.engine, get_settings())
    app.state.runtime_warm_task = runtime_warm_task
    slow_observability_task = _start_slow_observability_scheduler(
        client.engine,
        get_settings(),
    )
    app.state.slow_observability_task = slow_observability_task
    janitor_task = _start_source_janitor_scheduler(client, get_settings())
    app.state.source_janitor_task = janitor_task
    try:
        yield
    finally:
        for task in (
            reconciler_task,
            table_stats_task,
            pg_stat_task,
            runtime_warm_task,
            slow_observability_task,
            janitor_task,
        ):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        await client.__aexit__(None, None, None)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_slow_observability(settings)
    app = FastAPI(
        title=settings.api_title,
        version=__version__,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/v1/docs",
        openapi_url="/v1/openapi.json",
    )
    register_exception_handlers(app)
    _install_admission_control(app, settings)
    install_geoip_gate(app, settings)
    _install_performance_monitoring(app, settings)
    _install_client_disconnect_cancellation(app)
    app.include_router(healthz.router, prefix="/v1")
    app.include_router(geocode.router, prefix="/v1")
    app.include_router(reverse.router, prefix="/v1")
    app.include_router(search.router, prefix="/v1")
    app.include_router(zipcode.router, prefix="/v1")
    app.include_router(pobox.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1/admin")
    app.include_router(dagster.router, prefix="/v1")
    app.include_router(v2.router, prefix="/v2")
    _install_openapi_customization(app)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics(request: Request) -> Response:
        client = cast("AsyncAddressClient", request.app.state.client)
        cache = await client.cache_metrics()
        load_jobs = await client.load_job_metric_counts()
        assert client.engine is not None
        refresh_admin_metrics(cache=cache, load_jobs=load_jobs)
        refresh_db_pool_metrics(client.engine)
        capacity = await client.source_storage_capacity()
        session_state_counts = await client.source_upload_session_state_counts()
        refresh_source_registry_metrics(
            capacity=capacity, session_state_counts=session_state_counts
        )
        pg_stat_rows = await client.list_pg_stat_statement_snapshots(
            limit=settings.ops_pg_stat_statements_capture_limit
        )
        refresh_pg_stat_statement_metrics(pg_stat_rows)
        return Response(render_prometheus(), media_type=PROMETHEUS_CONTENT_TYPE)

    return app


# Endpoints translate request-validation failures into explicit 400 error envelopes
# (see :mod:`kortravelgeo.api.responses`): v1 VWorld geocode/reverse -> VWorld error object,
# v2 -> structured envelope, and legacy v1/admin paths -> ``{response:{errorCode,...}}``.
# FastAPI's auto-422 is therefore never emitted on these paths, so drop it from the
# published schema.
_VALIDATION_STRUCTURED_400 = (
    ("/v1/address/geocode", "get"),
    ("/v1/address/reverse", "get"),
    ("/v2/geocode", "post"),
    ("/v2/reverse", "post"),
    ("/v2/search", "post"),
    ("/v2/regions/within-radius", "post"),
)
_VALIDATION_LEGACY_400 = (
    ("/v1/address/search", "get"),
    ("/v1/address/zipcode", "get"),
    ("/v1/address/pobox", "get"),
)
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_LEGACY_ERROR_ENVELOPE_REF = "#/components/schemas/LegacyErrorEnvelope"


def _install_openapi_customization(app: FastAPI) -> None:
    """Align the published OpenAPI with actual validation-error wire behaviour (T-219).

    Operations covered here emit ``400`` through the global validation handler instead of
    FastAPI's auto-generated ``422``. Remove the misleading ``422`` and publish the matching
    ``400`` envelope for legacy v1/admin paths that do not already declare a model.
    """
    base_openapi = app.openapi

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = base_openapi()
        _ensure_legacy_error_schemas(schema)
        for path, method in _VALIDATION_STRUCTURED_400:
            _drop_validation_422(schema, path=path, method=method)
        for path, method in _VALIDATION_LEGACY_400:
            _publish_legacy_validation_400(schema, path=path, method=method)
        for path, path_item in schema.get("paths", {}).items():
            if not path.startswith("/v1/admin/") or not isinstance(path_item, dict):
                continue
            for method in _HTTP_METHODS:
                if method in path_item:
                    _publish_legacy_validation_400(schema, path=path, method=method)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def _drop_validation_422(schema: dict[str, Any], *, path: str, method: str) -> None:
    operation = schema.get("paths", {}).get(path, {}).get(method)
    if isinstance(operation, dict):
        operation.get("responses", {}).pop("422", None)


def _publish_legacy_validation_400(schema: dict[str, Any], *, path: str, method: str) -> None:
    operation = schema.get("paths", {}).get(path, {}).get(method)
    if not isinstance(operation, dict):
        return
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return
    had_validation_422 = responses.pop("422", None) is not None
    if not had_validation_422 or "400" in responses:
        return
    responses["400"] = {
        "description": "Legacy validation error envelope",
        "content": {
            "application/json": {
                "schema": {"$ref": _LEGACY_ERROR_ENVELOPE_REF},
            },
        },
    }


def _ensure_legacy_error_schemas(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components.setdefault(
        "LegacyErrorBody",
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "errorCode", "errorMessage"],
            "properties": {
                "status": {"type": "string", "const": "ERROR"},
                "errorCode": {"type": "string"},
                "errorMessage": {"type": "string"},
                "hint": {"type": "string"},
            },
        },
    )
    components.setdefault(
        "LegacyErrorEnvelope",
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["response"],
            "properties": {
                "response": {"$ref": "#/components/schemas/LegacyErrorBody"},
            },
        },
    )


def _install_performance_monitoring(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def performance_monitoring(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = perf_counter()
        method = request.method
        context_token = set_request_observability_context(method, request.url.path)
        status_code = 500
        cancelled = False
        record_api_request_started(method=method)
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except asyncio.CancelledError:
            cancelled = True
            status_code = _CLIENT_CLOSED_STATUS_CODE
            raise
        finally:
            elapsed_s = perf_counter() - started
            elapsed_ms = elapsed_s * 1_000
            route = _route_template(request)
            if cancelled:
                record_api_request_cancelled(method=method, route=route)
            record_api_request(
                method=method,
                route=route,
                status_code=status_code,
                elapsed_s=elapsed_s,
                slow_threshold_ms=settings.api_slow_request_ms,
            )
            record_api_request_finished(method=method)
            if settings.api_performance_logging_enabled:
                _PERFORMANCE_LOGGER.info(
                    "api_request_cancelled" if cancelled else "api_request",
                    extra={
                        "method": method,
                        "route": route,
                        "status_code": status_code,
                        "elapsed_ms": round(elapsed_ms, 3),
                        "slow": elapsed_ms >= settings.api_slow_request_ms,
                    },
                )
            record_slow_api_request(
                method=method,
                route=route,
                status_code=status_code,
                elapsed_ms=elapsed_ms,
            )
            reset_request_observability_context(context_token)


class ClientDisconnectCancellationMiddleware:
    """Cancel public address API work when the ASGI server reports disconnect."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _cancels_on_client_disconnect(scope):
            await self.app(scope, receive, send)
            return

        queue: asyncio.Queue[Message] = asyncio.Queue()
        response_complete = asyncio.Event()

        async def send_with_response_complete(message: Message) -> None:
            await send(message)
            if message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                response_complete.set()

        app_task: asyncio.Future[None] = asyncio.ensure_future(
            self.app(scope, queue.get, send_with_response_complete)
        )
        receive_task = asyncio.create_task(
            _pump_disconnect_aware_receive(receive, queue, app_task, response_complete)
        )
        try:
            done, _pending = await asyncio.wait(
                {app_task, receive_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if receive_task in done:
                exc = receive_task.exception()
                if exc is not None:
                    app_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await app_task
                    raise exc

                with suppress(asyncio.CancelledError):
                    await app_task
                return

            await app_task
        finally:
            if not app_task.done():
                app_task.cancel()
                with suppress(asyncio.CancelledError):
                    await app_task
            if not receive_task.done():
                receive_task.cancel()
                with suppress(asyncio.CancelledError):
                    await receive_task


async def _pump_disconnect_aware_receive(
    receive: Receive,
    queue: asyncio.Queue[Message],
    app_task: asyncio.Future[None],
    response_complete: asyncio.Event,
) -> None:
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            await queue.put(message)
            if response_complete.is_set():
                return
            app_task.cancel()
            return
        await queue.put(message)


def _install_client_disconnect_cancellation(app: FastAPI) -> None:
    app.add_middleware(ClientDisconnectCancellationMiddleware)


def _cancels_on_client_disconnect(scope: Scope) -> bool:
    path = scope.get("path")
    return isinstance(path, str) and path.startswith(_CLIENT_DISCONNECT_CANCEL_PREFIXES)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else request.url.path


def _install_admission_control(app: FastAPI, settings: Settings) -> None:
    controller = build_admission_controller(settings)
    if controller is None:
        return

    app.state.admission_control = controller
    timeout_s = settings.api_admission_timeout_ms / 1_000

    @app.middleware("http")
    async def admission_control(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        scopes = controller.scopes_for_path(request.url.path)
        if not scopes:
            return await call_next(request)

        method = request.method
        route = _route_template(request)
        acquired_scopes: list[str] = []
        deadline = perf_counter() + timeout_s
        for scope in scopes:
            started = perf_counter()
            remaining_s = deadline - started
            if remaining_s <= 0:
                record_api_admission_wait(
                    method=method,
                    route=route,
                    scope=scope,
                    outcome="rejected",
                    elapsed_s=0.0,
                )
                record_api_admission_rejection(method=method, route=route, scope=scope)
                record_overload_event(method=method, route=route, scope=scope)
                _log_admission_rejection(settings, method=method, route=route, scope=scope)
                _release_admission_scopes(controller, acquired_scopes)
                return _admission_error_response(scope=scope, path=request.url.path)

            try:
                await asyncio.wait_for(controller.acquire(scope), timeout=remaining_s)
            except TimeoutError:
                record_api_admission_wait(
                    method=method,
                    route=route,
                    scope=scope,
                    outcome="rejected",
                    elapsed_s=perf_counter() - started,
                )
                record_api_admission_rejection(method=method, route=route, scope=scope)
                record_overload_event(method=method, route=route, scope=scope)
                _log_admission_rejection(settings, method=method, route=route, scope=scope)
                _release_admission_scopes(controller, acquired_scopes)
                return _admission_error_response(scope=scope, path=request.url.path)

            acquired_scopes.append(scope)
            record_api_admission_started(scope=scope)
            record_api_admission_wait(
                method=method,
                route=route,
                scope=scope,
                outcome="accepted",
                elapsed_s=perf_counter() - started,
            )

        try:
            return await call_next(request)
        finally:
            _release_admission_scopes(controller, acquired_scopes)


def _release_admission_scopes(
    controller: AdmissionController,
    scopes: list[str],
) -> None:
    while scopes:
        scope = scopes.pop()
        controller.release(scope)
        record_api_admission_finished(scope=scope)


def _admission_error_response(*, scope: str, path: str) -> ORJSONResponse:
    setting_name = admission_scope_setting_name(scope)
    error = RateLimitError(
        f"too many concurrent {scope} API requests",
        hint=(
            f"increase {setting_name} or lower caller concurrency after checking "
            "database capacity"
        ),
    )
    return ORJSONResponse(
        error_payload(error, path=path),
        status_code=error.http_status,
        headers={"Retry-After": _ADMISSION_RETRY_AFTER_SECONDS, "Cache-Control": "no-store"},
    )


def _log_admission_rejection(
    settings: Settings,
    *,
    method: str,
    route: str,
    scope: str,
) -> None:
    if not settings.api_performance_logging_enabled:
        return
    _PERFORMANCE_LOGGER.warning(
        "api_admission_rejected",
        extra={"method": method, "route": route, "scope": scope},
    )


app = create_app()


def _start_table_stats_capture_scheduler(
    engine: AsyncEngine,
    settings: Settings,
) -> asyncio.Task[None] | None:
    if settings.ops_table_stats_capture_interval_minutes <= 0:
        return None
    return asyncio.create_task(_run_table_stats_capture_scheduler(engine, settings))


async def _run_table_stats_capture_scheduler(engine: AsyncEngine, settings: Settings) -> None:
    interval_s = settings.ops_table_stats_capture_interval_minutes * 60
    if settings.ops_table_stats_capture_on_startup:
        await _capture_table_stats_once(engine, settings)

    while True:
        await asyncio.sleep(interval_s)
        await _capture_table_stats_once(engine, settings)


async def _capture_table_stats_once(engine: AsyncEngine, settings: Settings) -> None:
    try:
        rows = await AdminRepository(engine).capture_table_stats_snapshots(
            limit=settings.ops_table_stats_capture_limit,
            skip_if_locked=True,
        )
    except Exception:
        _LOGGER.exception("failed to capture ops.table_stats_snapshots")
        return

    _LOGGER.info(
        "captured ops.table_stats_snapshots",
        extra={"row_count": len(rows), "limit": settings.ops_table_stats_capture_limit},
    )


def _start_pg_stat_statements_capture_scheduler(
    engine: AsyncEngine,
    settings: Settings,
) -> asyncio.Task[None] | None:
    if settings.ops_pg_stat_statements_capture_interval_minutes <= 0:
        return None
    return asyncio.create_task(_run_pg_stat_statements_capture_scheduler(engine, settings))


async def _run_pg_stat_statements_capture_scheduler(
    engine: AsyncEngine,
    settings: Settings,
) -> None:
    interval_s = settings.ops_pg_stat_statements_capture_interval_minutes * 60
    if settings.ops_pg_stat_statements_capture_on_startup:
        await _capture_pg_stat_statements_once(engine, settings)

    while True:
        await asyncio.sleep(interval_s)
        await _capture_pg_stat_statements_once(engine, settings)


async def _capture_pg_stat_statements_once(engine: AsyncEngine, settings: Settings) -> None:
    try:
        rows = await AdminRepository(engine).capture_pg_stat_statement_snapshots(
            limit=settings.ops_pg_stat_statements_capture_limit,
            skip_if_locked=True,
            retention_days=settings.ops_pg_stat_statements_retention_days,
        )
    except Exception:
        _LOGGER.exception("failed to capture ops.pg_stat_statements_snapshots")
        return

    _LOGGER.info(
        "captured ops.pg_stat_statements_snapshots",
        extra={
            "row_count": len(rows),
            "limit": settings.ops_pg_stat_statements_capture_limit,
            "retention_days": settings.ops_pg_stat_statements_retention_days,
        },
    )


def _start_dagster_reconciler_scheduler(
    reconciler: DagsterJobReconciler,
    settings: Settings,
) -> asyncio.Task[None] | None:
    """Periodic executor-aware reconciler tick (T-290k §3). ``interval <= 0`` disables it
    (startup-only). Each tick converges ``executor='dagster'`` rows against their real Dagster
    run state so a job whose lease looks alive but whose run died is failed between restarts."""

    if settings.dagster_reconcile_interval_seconds <= 0:
        return None
    return asyncio.create_task(_run_dagster_reconciler_scheduler(reconciler, settings))


async def _run_dagster_reconciler_scheduler(
    reconciler: DagsterJobReconciler,
    settings: Settings,
) -> None:
    interval_s = settings.dagster_reconcile_interval_seconds
    while interval_s > 0:
        await asyncio.sleep(interval_s)
        try:
            await reconciler.reconcile_once()
        except Exception:
            _LOGGER.exception("dagster reconciler tick failed")


def _start_runtime_warm_scheduler(
    engine: AsyncEngine,
    settings: Settings,
) -> asyncio.Task[None] | None:
    if (
        not settings.runtime_warm_on_startup
        and settings.runtime_warm_interval_minutes <= 0
    ):
        return None
    return asyncio.create_task(_run_runtime_warm_scheduler(engine, settings))


async def _run_runtime_warm_scheduler(engine: AsyncEngine, settings: Settings) -> None:
    interval_s = settings.runtime_warm_interval_minutes * 60
    if settings.runtime_warm_on_startup:
        await _run_runtime_warm_once(engine, settings)
    while interval_s > 0:
        await asyncio.sleep(interval_s)
        await _run_runtime_warm_once(engine, settings)


async def _run_runtime_warm_once(engine: AsyncEngine, settings: Settings) -> None:
    key = AdvisoryLockKey.global_key(AdvisoryLockNamespace.RUNTIME_WARM)
    try:
        async with cross_process_lock(engine, key):
            report = await run_runtime_warm(
                engine,
                mode="execute",
                prewarm_enabled=settings.runtime_warm_prewarm_enabled,
                prewarm_relations=settings.runtime_warm_prewarm_relations,
                query_limit=settings.runtime_warm_query_limit,
                statement_timeout_ms=settings.runtime_warm_statement_timeout_ms,
            )
    except ConcurrentExecutionError:
        _LOGGER.info("runtime warm skipped because another worker holds the lock")
        return
    except Exception:
        _LOGGER.exception("runtime warm pass failed")
        return

    metrics = runtime_warm_report_metrics(report)
    _LOGGER.info(
        "runtime warm scheduler pass",
        extra={
            "status": "failed" if metrics["error_count"] else "ok",
            "samples": metrics["samples"],
            "error_count": metrics["error_count"],
            "warning_count": metrics["warning_count"],
            "max_ms": metrics["max_ms"],
        },
    )


def _start_slow_observability_scheduler(
    engine: AsyncEngine,
    settings: Settings,
) -> asyncio.Task[None] | None:
    if not settings.ops_slow_samples_enabled:
        return None
    return asyncio.create_task(run_slow_observability_flush_loop(engine))


def _start_source_janitor_scheduler(
    client: AsyncAddressClient,
    settings: Settings,
) -> asyncio.Task[None] | None:
    """Opt-in upload-session janitor scheduler (T-203c).

    Mirrors the T-050 table-stats scheduler: default interval ``0`` is disabled.
    The janitor itself takes the ``SOURCE_JANITOR`` advisory lock, so multiple
    API processes scheduling it concurrently still run at most one pass.
    """
    if settings.source_janitor_interval_minutes <= 0:
        return None
    return asyncio.create_task(_run_source_janitor_scheduler(client, settings))


async def _run_source_janitor_scheduler(
    client: AsyncAddressClient,
    settings: Settings,
) -> None:
    interval_s = settings.source_janitor_interval_minutes * 60
    if settings.source_janitor_on_startup:
        await _run_source_janitor_once(client)
    while True:
        await asyncio.sleep(interval_s)
        await _run_source_janitor_once(client)


async def _run_source_janitor_once(client: AsyncAddressClient) -> None:
    try:
        summary = await client.run_source_upload_janitor()
    except Exception:
        _LOGGER.exception("source upload janitor pass failed")
        return
    _LOGGER.info("source upload janitor scheduler pass", extra=summary.model_dump())


