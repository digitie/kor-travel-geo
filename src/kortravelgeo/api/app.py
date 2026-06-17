"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kortravelgeo.api import _jobs
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

from .routers import admin, geocode, healthz, pobox, reverse, search, v2, zipcode

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
    queue = _jobs.JobQueue(client.engine)
    _register_default_handlers(queue, client.engine)
    app.state.job_queue = queue
    await queue.recover_startup()
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


# Public address endpoints translate request-validation failures into an explicit 400
# error envelope (see :mod:`kortravelgeo.api.responses`): v1 -> VWorld error object,
# v2 -> structured envelope (intended input-safety, T-173/ADR-061). FastAPI's auto-422 is
# therefore never emitted on these paths, so drop it from the published schema.
_VALIDATION_STRUCTURED_400 = (
    ("/v1/address/geocode", "get"),
    ("/v1/address/reverse", "get"),
    ("/v2/geocode", "post"),
    ("/v2/reverse", "post"),
    ("/v2/search", "post"),
    ("/v2/regions/within-radius", "post"),
)


def _install_openapi_customization(app: FastAPI) -> None:
    """Align the published OpenAPI with actual public-address wire behaviour (T-219 M3/M4).

    Each operation in :data:`_VALIDATION_STRUCTURED_400` declares its own ``400`` and never
    emits FastAPI's auto-generated ``422``; remove that ``422`` so the schema matches the wire.
    Wire behaviour is unchanged — this only fixes published-contract drift.
    """
    base_openapi = app.openapi

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = base_openapi()
        for path, method in _VALIDATION_STRUCTURED_400:
            operation = schema.get("paths", {}).get(path, {}).get(method)
            if operation is not None:
                operation.get("responses", {}).pop("422", None)
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


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
        app_task: asyncio.Future[None] = asyncio.ensure_future(
            self.app(scope, queue.get, send)
        )
        receive_task = asyncio.create_task(_pump_disconnect_aware_receive(receive, queue, app_task))
        try:
            done, _pending = await asyncio.wait(
                {app_task, receive_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if app_task in done:
                await app_task
                return

            exc = receive_task.exception()
            if exc is not None:
                app_task.cancel()
                with suppress(asyncio.CancelledError):
                    await app_task
                raise exc

            with suppress(asyncio.CancelledError):
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
) -> None:
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            app_task.cancel()
            await queue.put(message)
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
        )
    except Exception:
        _LOGGER.exception("failed to capture ops.pg_stat_statements_snapshots")
        return

    _LOGGER.info(
        "captured ops.pg_stat_statements_snapshots",
        extra={
            "row_count": len(rows),
            "limit": settings.ops_pg_stat_statements_capture_limit,
        },
    )


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


def _locked_job_handler(
    engine: AsyncEngine,
    namespace: AdvisoryLockNamespace,
    resource: Callable[[dict[str, Any]], object],
    handler: _jobs.JobHandler,
) -> _jobs.JobHandler:
    async def wrapped(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        key = AdvisoryLockKey.for_resource(namespace, resource(payload))
        try:
            async with cross_process_lock(engine, key):
                await handler(payload, cancel_event, progress)
        except ConcurrentExecutionError as exc:
            await progress(stage="lock_conflict", message=f"{exc.code}: {exc.message}")
            raise

    return wrapped


def _locked_global_job_handler(
    engine: AsyncEngine,
    namespace: AdvisoryLockNamespace,
    handler: _jobs.JobHandler,
) -> _jobs.JobHandler:
    async def wrapped(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        _ = payload
        try:
            async with cross_process_lock(engine, AdvisoryLockKey.global_key(namespace)):
                await handler(payload, cancel_event, progress)
        except ConcurrentExecutionError as exc:
            await progress(stage="lock_conflict", message=f"{exc.code}: {exc.message}")
            raise

    return wrapped


def _register_default_handlers(queue: _jobs.JobQueue, engine: AsyncEngine) -> None:
    settings = get_settings()

    async def juso(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="juso_text_load", message="도로명주소 한글 적재 시작")
        count = await load_juso_hangul(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
        await progress(progress=1.0, stage="juso_text_load", message=f"{count} rows loaded")

    async def locsum(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="locsum_load", message="위치정보요약DB 적재 시작")
        count = await load_locsum(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
        await progress(progress=1.0, stage="locsum_load", message=f"{count} rows loaded")

    async def daily_juso(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="daily_juso_delta", message="도로명주소 일변동 적재 시작")
        result = await load_daily_juso_delta(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
        await progress(
            progress=1.0,
            stage="daily_juso_delta",
            message=(
                f"{result.processed_rows} rows processed, "
                f"{result.upserted_rows} upserted, {result.deleted_rows} deleted"
            ),
        )

    async def parcel_links(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="juso_parcel_link_load", message="건물-지번 링크 적재 시작")
        result = await load_juso_parcel_link_snapshot(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            replace=_payload_bool(payload, "replace", default=True),
            cancel_event=cancel_event,
        )
        await progress(
            progress=1.0,
            stage="juso_parcel_link_load",
            message=f"{result.processed_rows} rows processed, {result.upserted_rows} upserted",
        )

    async def daily_parcel_links(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="juso_parcel_link_delta", message="건물-지번 일변동 적재 시작")
        result = await load_daily_parcel_link_delta(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
        await progress(
            progress=1.0,
            stage="juso_parcel_link_delta",
            message=(
                f"{result.processed_rows} rows processed, "
                f"{result.upserted_rows} upserted, {result.deleted_rows} deleted"
            ),
        )

    async def roadaddr_entrances(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="roadaddr_entrance_load", message="도로명주소 출입구 정보 적재 시작")
        result = await load_roadaddr_entrances(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            replace=_payload_bool(payload, "replace", default=True),
            cancel_event=cancel_event,
        )
        await progress(
            progress=1.0,
            stage="roadaddr_entrance_load",
            message=f"{result.processed_rows} rows processed, {result.upserted_rows} upserted",
        )

    async def navi(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="navi_load", message="내비게이션용DB 적재 시작")
        build_count, entrance_count = await load_navi(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
        await progress(
            progress=1.0,
            stage="navi_load",
            message=f"{build_count} centroids, {entrance_count} entrances loaded",
        )

    async def shp(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="shp_polygons_load", message="SHP 보조 레이어 적재 시작")
        count = await load_shp_polygons(
            engine,
            _payload_path(payload),
            mode=_payload_str(payload, "mode") or "full",
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            cancel_event=cancel_event,
        )
        await refresh_region_radius_parts(engine)
        await progress(progress=1.0, stage="shp_polygons_load", message=f"{count} layers loaded")

    async def sppn_makarea(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="sppn_makarea_load", message="국가지점번호 표기 의무지역 적재 시작")
        count = await load_sppn_makarea(
            engine,
            _payload_path(payload),
            mode=_payload_str(payload, "mode") or "full",
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            cancel_event=cancel_event,
        )
        await progress(progress=1.0, stage="sppn_makarea_load", message=f"{count} rows loaded")

    async def pobox(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="pobox_load", message="사서함 우편번호 적재 시작")
        count = await load_pobox(engine, _payload_path(payload), cancel_event=cancel_event)
        await progress(progress=1.0, stage="pobox_load", message=f"{count} rows loaded")

    async def bulk(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await progress(stage="bulk_load", message="대량배달처 우편번호 적재 시작")
        count = await load_bulk_delivery(engine, _payload_path(payload), cancel_event=cancel_event)
        await progress(progress=1.0, stage="bulk_load", message=f"{count} rows loaded")

    async def consistency(
        payload: dict[str, Any],
        _cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        async def case_progress(value: float, code: str) -> None:
            await progress(progress=value, stage=f"consistency:{code}", message=f"{code} checked")

        raw_cases = payload.get("cases")
        cases = tuple(raw_cases) if isinstance(raw_cases, list) and raw_cases else DEFAULT_CASES
        source_set = _source_set(payload)
        report = await run_all_cases(
            engine,
            scope=_payload_str(payload, "scope") or "full",
            cases=cases,
            generated_by="api",
            source_set=source_set,
            on_progress=case_progress,
        )
        await progress(
            progress=1.0,
            stage="consistency_check",
            message=f"{report.report_id} severity={report.severity_max}",
        )
        load_batch_id = _payload_str(payload, "load_batch_id")
        if report.severity_max == "ERROR" and not load_batch_id:
            msg = f"consistency report failed: {report.report_id}"
            raise RuntimeError(msg)
        if report.severity_max == "ERROR":
            await progress(
                stage="consistency_check",
                message="consistency ERROR 기록됨; batch promotion gate에서 처리",
            )

    async def mv_refresh(
        payload: dict[str, Any],
        _cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        strategy = _payload_str(payload, "strategy") or "concurrent"
        await progress(stage="mv_refresh", message=f"MV refresh 시작: {strategy}")
        await resolve_text_geometry_links(engine)
        repo = AdminRepository(engine)
        load_batch_id = _payload_str(payload, "load_batch_id")
        # rebuild-db forced_promotion (T-205b) accepts a known source-quality
        # consistency ERROR — and ONLY that gate. The source-archive integrity
        # gate already ran before any child loader was enqueued.
        forced_promotion = _payload_bool(payload, "forced_promotion", default=False)
        if not forced_promotion:
            await repo.ensure_load_batch_release_gate(load_batch_id)
        await refresh_mv(
            engine,
            concurrently=strategy != "swap",
            strategy="swap" if strategy == "swap" else "concurrent",
        )
        forced_metadata = payload.get("forced_promotion_metadata")
        snapshot, release = await repo.record_mv_refresh_release(
            job_id=_payload_str(payload, "_job_id"),
            load_batch_id=load_batch_id,
            strategy=strategy,
            source_match_set_id=_payload_str(payload, "source_match_set_id"),
            forced_promotion=forced_promotion,
            forced_promotion_metadata=(
                forced_metadata if isinstance(forced_metadata, dict) else None
            ),
        )
        await progress(progress=1.0, stage="mv_refresh", message="MV refresh 완료")
        await progress(
            stage="serving_release",
            message=(
                f"serving release 활성화: {release.serving_release_id} "
                f"snapshot={snapshot.dataset_snapshot_id}"
            ),
        )

    async def db_backup(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await run_backup_job(engine, settings, payload, cancel_event, progress)

    async def db_restore(
        payload: dict[str, Any],
        cancel_event: asyncio.Event,
        progress: _jobs.ProgressCallback,
    ) -> None:
        await run_restore_job(engine, settings, payload, cancel_event, progress)

    queue.register(
        "juso_text_load",
        _locked_job_handler(engine, AdvisoryLockNamespace.LOAD_JUSO_TEXT, _payload_lock_path, juso),
    )
    queue.register(
        "db_backup",
        _locked_global_job_handler(engine, AdvisoryLockNamespace.BACKUP_CREATE, db_backup),
    )
    queue.register(
        "db_restore",
        _locked_job_handler(
            engine,
            AdvisoryLockNamespace.RESTORE_CREATE,
            _restore_lock_resource,
            db_restore,
        ),
    )
    queue.register(
        "daily_juso_delta",
        _locked_job_handler(
            engine,
            AdvisoryLockNamespace.LOAD_DAILY_JUSO,
            _payload_lock_path,
            daily_juso,
        ),
    )
    queue.register(
        "juso_parcel_link_load",
        _locked_job_handler(
            engine,
            AdvisoryLockNamespace.LOAD_PARCEL_LINK,
            _payload_lock_path,
            parcel_links,
        ),
    )
    queue.register(
        "juso_parcel_link_delta",
        _locked_job_handler(
            engine,
            AdvisoryLockNamespace.LOAD_DAILY_PARCEL,
            _payload_lock_path,
            daily_parcel_links,
        ),
    )
    queue.register(
        "roadaddr_entrance_load",
        _locked_job_handler(
            engine,
            AdvisoryLockNamespace.LOAD_ROADADDR_ENTRANCES,
            _payload_lock_path,
            roadaddr_entrances,
        ),
    )
    queue.register(
        "locsum_load",
        _locked_job_handler(engine, AdvisoryLockNamespace.LOAD_LOCSUM, _payload_lock_path, locsum),
    )
    queue.register(
        "navi_load",
        _locked_job_handler(engine, AdvisoryLockNamespace.LOAD_NAVI, _payload_lock_path, navi),
    )
    queue.register(
        "shp_polygons_load",
        _locked_job_handler(
            engine,
            AdvisoryLockNamespace.LOAD_SHP_POLYGONS,
            _payload_lock_path,
            shp,
        ),
    )
    queue.register(
        "sppn_makarea_load",
        _locked_job_handler(
            engine,
            AdvisoryLockNamespace.LOAD_SPPN_MAKAREA,
            _payload_lock_path,
            sppn_makarea,
        ),
    )
    queue.register(
        "pobox_load",
        _locked_job_handler(engine, AdvisoryLockNamespace.LOAD_POBOX, _payload_lock_path, pobox),
    )
    queue.register(
        "bulk_load",
        _locked_job_handler(engine, AdvisoryLockNamespace.LOAD_BULK, _payload_lock_path, bulk),
    )
    queue.register(
        "consistency_check",
        _locked_job_handler(
            engine,
            AdvisoryLockNamespace.CONSISTENCY_RUN,
            _consistency_lock_resource,
            consistency,
        ),
    )
    queue.register(
        "mv_refresh",
        _locked_global_job_handler(engine, AdvisoryLockNamespace.MV_REFRESH, mv_refresh),
    )


def _payload_path(payload: dict[str, Any]) -> Path:
    value = payload.get("path") or payload.get("source_path")
    if not isinstance(value, str) or not value:
        msg = "load payload requires 'path' or 'source_path'"
        raise ValueError(msg)
    return Path(value)


def _payload_lock_path(payload: dict[str, Any]) -> str:
    return str(_payload_path(payload).expanduser().resolve(strict=False))


def _restore_lock_resource(payload: dict[str, Any]) -> object:
    return (
        payload.get("target_database")
        or payload.get("target_dsn")
        or payload.get("artifact_id")
        or payload.get("archive_path")
        or "default"
    )


def _consistency_lock_resource(payload: dict[str, Any]) -> str:
    raw_cases = payload.get("cases")
    cases = ",".join(str(item) for item in raw_cases) if isinstance(raw_cases, list) else "all"
    return f"{payload.get('scope') or 'full'}:{cases}"


def _payload_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _payload_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def _payload_bool(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    return value if isinstance(value, bool) else default


def _source_set(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("source_set")
    result = {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}
    batch_id = payload.get("load_batch_id")
    if isinstance(batch_id, str):
        result["load_batch_id"] = batch_id
    return result
