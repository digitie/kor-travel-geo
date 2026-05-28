"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.api import _jobs
from kraddr.geo.api.responses import error_payload, register_exception_handlers
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.exceptions import RateLimitError
from kraddr.geo.infra.admin_repo import AdminRepository
from kraddr.geo.infra.backup import run_backup_job, run_restore_job
from kraddr.geo.infra.metrics import (
    PROMETHEUS_CONTENT_TYPE,
    refresh_admin_metrics,
    render_prometheus,
)
from kraddr.geo.loaders.bulk_loader import load_bulk_delivery
from kraddr.geo.loaders.consistency import DEFAULT_CASES, run_all_cases
from kraddr.geo.loaders.pobox_loader import load_pobox
from kraddr.geo.loaders.postload import refresh_mv, resolve_text_geometry_links
from kraddr.geo.loaders.shp.polygons_loader import load_shp_polygons
from kraddr.geo.loaders.sppn_makarea_loader import load_sppn_makarea
from kraddr.geo.loaders.text.daily_juso_loader import load_daily_juso_delta
from kraddr.geo.loaders.text.juso_hangul_loader import load_juso_hangul
from kraddr.geo.loaders.text.locsum_loader import load_locsum
from kraddr.geo.loaders.text.navi_loader import load_navi
from kraddr.geo.loaders.text.parcel_link_loader import (
    load_daily_parcel_link_delta,
    load_juso_parcel_link_snapshot,
)
from kraddr.geo.loaders.text.roadaddr_entrance_loader import load_roadaddr_entrances
from kraddr.geo.settings import Settings, get_settings
from kraddr.geo.version import __version__

from .routers import admin, geocode, healthz, pobox, reverse, search, v2, zipcode


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
    try:
        yield
    finally:
        await client.__aexit__(None, None, None)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="kraddr-geo",
        version=__version__,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/v1/docs",
        openapi_url="/v1/openapi.json",
    )
    register_exception_handlers(app)
    _install_admission_control(app, settings)
    app.include_router(healthz.router, prefix="/v1")
    app.include_router(geocode.router, prefix="/v1")
    app.include_router(reverse.router, prefix="/v1")
    app.include_router(search.router, prefix="/v1")
    app.include_router(zipcode.router, prefix="/v1")
    app.include_router(pobox.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1/admin")
    app.include_router(v2.router, prefix="/v2")

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics(request: Request) -> Response:
        client = cast("AsyncAddressClient", request.app.state.client)
        cache = await client.cache_metrics()
        load_jobs = await client.load_job_metric_counts()
        refresh_admin_metrics(cache=cache, load_jobs=load_jobs)
        return Response(render_prometheus(), media_type=PROMETHEUS_CONTENT_TYPE)

    return app


def _install_admission_control(app: FastAPI, settings: Settings) -> None:
    if settings.api_max_concurrency is None:
        return

    semaphore = asyncio.Semaphore(settings.api_max_concurrency)
    timeout_s = settings.api_admission_timeout_ms / 1_000

    @app.middleware("http")
    async def admission_control(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not (request.url.path.startswith("/v1/address/") or request.url.path.startswith("/v2/")):
            return await call_next(request)

        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout_s)
        except TimeoutError:
            error = RateLimitError(
                "too many concurrent address API requests",
                hint=(
                    "increase KRADDR_GEO_API_MAX_CONCURRENCY or retry after current "
                    "requests complete"
                ),
            )
            return ORJSONResponse(error_payload(error), status_code=error.http_status)

        try:
            return await call_next(request)
        finally:
            semaphore.release()


app = create_app()


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
        if report.severity_max == "ERROR":
            msg = f"consistency report failed: {report.report_id}"
            raise RuntimeError(msg)

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
        await repo.ensure_load_batch_release_gate(load_batch_id)
        await refresh_mv(
            engine,
            concurrently=strategy != "swap",
            strategy="swap" if strategy == "swap" else "concurrent",
        )
        snapshot, release = await repo.record_mv_refresh_release(
            job_id=_payload_str(payload, "_job_id"),
            load_batch_id=load_batch_id,
            strategy=strategy,
        )
        await progress(progress=1.0, stage="mv_refresh", message="MV refresh 완료")
        await progress(
            stage="serving_release",
            message=(
                f"serving release 활성화: {release.release_id} "
                f"snapshot={snapshot.snapshot_id}"
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

    queue.register("juso_text_load", juso)
    queue.register("db_backup", db_backup)
    queue.register("db_restore", db_restore)
    queue.register("daily_juso_delta", daily_juso)
    queue.register("juso_parcel_link_load", parcel_links)
    queue.register("juso_parcel_link_delta", daily_parcel_links)
    queue.register("roadaddr_entrance_load", roadaddr_entrances)
    queue.register("locsum_load", locsum)
    queue.register("navi_load", navi)
    queue.register("shp_polygons_load", shp)
    queue.register("sppn_makarea_load", sppn_makarea)
    queue.register("pobox_load", pobox)
    queue.register("bulk_load", bulk)
    queue.register("consistency_check", consistency)
    queue.register("mv_refresh", mv_refresh)


def _payload_path(payload: dict[str, Any]) -> Path:
    value = payload.get("path") or payload.get("source_path")
    if not isinstance(value, str) or not value:
        msg = "load payload requires 'path' or 'source_path'"
        raise ValueError(msg)
    return Path(value)


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
