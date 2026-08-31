from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi import FastAPI, Request

from kortravelgeo.api import app as app_module
from kortravelgeo.api.app import (
    ClientDisconnectCancellationMiddleware,
    _install_client_disconnect_cancellation,
    _install_performance_monitoring,
    create_app,
)
from kortravelgeo.infra import metrics, slow_observability
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from starlette.types import Receive, Scope, Send


def test_create_app_exposes_expected_routes_without_starting_lifespan() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    paths.update(
        path
        for route in app.routes
        if isinstance((path := getattr(route, "path", None)), str)
    )

    assert "/v1/address/geocode" in paths
    assert "/v1/address/reverse" in paths
    assert "/v1/address/search" in paths
    assert "/v1/address/zipcode" in paths
    assert "/v1/address/pobox" in paths
    assert "/v1/readyz" in paths
    assert "/v2/geocode" in paths
    assert "/v2/reverse" in paths
    assert "/v2/search" in paths
    assert "/v1/admin/loads" in paths
    assert "/v1/admin/jobs" in paths
    assert "/v1/admin/jobs/{job_id}/events" in paths
    assert "/v1/admin/tables" in paths
    assert "/v1/admin/explain" in paths
    assert "/v1/admin/cache/metrics" in paths
    assert "/v1/admin/logs" in paths
    assert "/v1/admin/upload/sido-zip" in paths
    assert "/v1/admin/source-file-categories" in paths
    assert "/v1/admin/storage/rustfs/config" in paths
    assert "/v1/admin/storage/rustfs/check" in paths
    assert "/v1/admin/storage/rustfs/import-prefix" in paths
    assert "/v1/admin/storage/rustfs/sync-local" in paths
    # T-201 removed the legacy auto-detection upload-SET + load-source surface.
    assert "/v1/admin/uploads" not in paths
    assert "/v1/admin/uploads/{upload_set_id}" not in paths
    assert "/v1/admin/uploads/{upload_set_id}/files" not in paths
    assert "/v1/admin/uploads/{upload_set_id}/cancel" not in paths
    assert "/v1/admin/load-sources/discover" not in paths
    assert "/v1/admin/load-sources/plan" not in paths
    assert "/v1/admin/backups" in paths
    assert "/v1/admin/backups/{artifact_id}" in paths
    assert "/v1/admin/backups/{artifact_id}/download" in paths
    assert "/v1/admin/backups/{artifact_id}/delete" in paths
    assert "/v1/admin/restores" in paths
    assert "/v1/admin/maintenance/refresh-mv" in paths
    assert "/v1/admin/consistency/run" in paths
    assert "/v1/admin/consistency/case-definitions" in paths
    assert "/v1/admin/source-match-sets/{source_match_set_id}/run-validation" in paths
    assert "/v1/admin/consistency/{report_id}/cases/{case_code}/samples" in paths
    assert "/v1/admin/consistency/{report_id}/cases/{case_code}/summary" in paths
    assert (
        "/v1/admin/consistency/{report_id}/cases/{case_code}/samples/{sample_id}/decision"
        in paths
    )
    assert "/v1/admin/consistency/{report_id}/cases/{case_code}/samples/bulk-decision" in paths
    assert (
        "/v1/admin/consistency/{report_id}/cases/{case_code}/samples/{sample_id}/recheck"
        in paths
    )
    assert "/v1/admin/ops/audit-events" in paths
    assert "/v1/admin/ops/snapshots" in paths
    assert "/v1/admin/ops/releases" in paths
    assert "/v1/admin/ops/releases/{serving_release_id}/rollback-plan" in paths
    assert "/v1/admin/ops/artifacts" in paths
    assert "/v1/admin/ops/maintenance-windows" in paths
    assert "/v1/admin/ops/maintenance-windows/{maintenance_window_id}/end" in paths
    assert "/v1/admin/ops/table-stats" in paths
    assert "/v1/admin/ops/table-stats/capture" in paths
    assert "/v1/admin/ops/pg-stat-statements" in paths
    assert "/v1/admin/ops/pg-stat-statements/capture" in paths
    assert "/v1/ops/dagster/summary" in paths
    assert "/v1/ops/dagster/runs/{run_id}" in paths
    assert "/metrics" in paths


def test_batch_dag_dispatches_sppn_makarea_loader() -> None:
    # The sppn_makarea loader (like all source loaders) is now dispatched by the Dagster-executed
    # batch DAG leaf, not the retired in-process JobQueue handler registry (T-290k).
    from kortravelgeo.loaders import batch_dag

    source = inspect.getsource(batch_dag)

    assert "load_sppn_makarea(" in source
    assert '"sppn_makarea_load"' in source
    assert "AdvisoryLockNamespace.LOAD_SPPN_MAKAREA" in source


@pytest.mark.asyncio
async def test_loader_thread_wrapper_keeps_api_event_loop_responsive() -> None:
    from kortravelgeo.loaders import batch_dag

    main_thread_id = threading.get_ident()
    worker_thread_ids: list[int] = []
    blocker = threading.Event()

    async def blocking_loader() -> str:
        worker_thread_ids.append(threading.get_ident())
        blocker.wait(0.2)
        return "loaded"

    task = asyncio.create_task(batch_dag._run_off_event_loop(blocking_loader))

    await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.05)
    assert not task.done()

    assert await task == "loaded"
    assert worker_thread_ids
    assert worker_thread_ids[0] != main_thread_id


@pytest.mark.asyncio
async def test_performance_logging_uses_route_template_without_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, Any]:
        return {"item_id": item_id}

    _install_performance_monitoring(
        app,
        Settings(api_performance_logging_enabled=True),
    )

    caplog.set_level(logging.INFO, logger="kortravelgeo.api.performance")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/items/123?address=서울특별시 종로구 인사동")

    assert response.status_code == 200
    records = [
        record for record in caplog.records if record.name == "kortravelgeo.api.performance"
    ]
    assert records
    record = records[-1]
    assert record.__dict__["route"] == "/items/{item_id}"
    assert record.__dict__["status_code"] == 200
    assert "address" not in record.getMessage()
    assert "서울특별시" not in record.getMessage()


@pytest.mark.asyncio
async def test_performance_monitoring_enqueues_slow_request_sample() -> None:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, Any]:
        await asyncio.sleep(0.002)
        return {"item_id": item_id}

    settings = Settings(
        ops_slow_samples_enabled=True,
        api_slow_request_ms=1,
        ops_slow_sample_min_interval_ms=0,
    )
    slow_observability.configure_slow_observability(settings)
    _install_performance_monitoring(app, settings)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/items/123?address=서울특별시 종로구 인사동")

        samples = slow_observability.pop_slow_samples_for_tests()
    finally:
        slow_observability.reset_slow_observability_for_tests()

    assert response.status_code == 200
    assert len(samples) == 1
    assert samples[0].sample_type == "api_request"
    assert samples[0].route == "/items/{item_id}"
    assert "서울특별시" not in str(slow_observability.sample_record(samples[0]))


@pytest.mark.asyncio
async def test_db_query_sample_route_is_templated_not_raw_path_with_param(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T-158 후속(#302 M2): db_query 표본의 route는 handler 실행 중 request.url.path가
    아니라 라우트 템플릿이어야 한다 — 그렇지 않으면 throttle key/저장 row가
    path-param(id 등) 카디널리티만큼 무한 증가한다."""
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, Any]:
        slow_observability.record_slow_query(
            statement="SELECT 1",
            parameters=None,
            elapsed_s=1.0,
            status="success",
        )
        return {"item_id": item_id}

    settings = Settings(
        ops_slow_samples_enabled=True,
        ops_slow_query_ms=1,
        ops_slow_sample_min_interval_ms=0,
    )
    slow_observability.configure_slow_observability(settings)
    _install_performance_monitoring(app, settings)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/items/507f191e810c19729de860ea")

        samples = slow_observability.pop_slow_samples_for_tests()
    finally:
        slow_observability.reset_slow_observability_for_tests()

    assert response.status_code == 200
    db_samples = [sample for sample in samples if sample.sample_type == "db_query"]
    assert len(db_samples) == 1
    assert db_samples[0].route == "/items/{item_id}"
    assert "507f191e810c19729de860ea" not in (db_samples[0].route or "")


def _synthetic_request(app: FastAPI, path: str) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "app": app,
    }
    return Request(scope)


def test_resolve_route_template_before_dispatch_matches_and_falls_back() -> None:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, Any]:
        return {"item_id": item_id}

    matched = app_module._resolve_route_template_before_dispatch(
        _synthetic_request(app, "/items/507f191e810c19729de860ea")
    )
    unmatched = app_module._resolve_route_template_before_dispatch(
        _synthetic_request(app, "/no-such-route")
    )

    assert matched == "/items/{item_id}"
    # A raw 404 path would let arbitrary URLs create unbounded Prometheus label
    # cardinality. Matched routes still use their Starlette route template.
    assert unmatched == "/<unmatched>"


def test_observability_route_template_gated_by_enabled_flag() -> None:
    """T-158 후속(#302, 리뷰 should-fix): 기능이 꺼져 있으면(기본값) route-matching 스캔
    자체를 하지 않고 저렴한 request.url.path를 그대로 써야 한다."""
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, Any]:
        return {"item_id": item_id}

    request = _synthetic_request(app, "/items/507f191e810c19729de860ea")
    try:
        slow_observability.configure_slow_observability(
            Settings(ops_slow_samples_enabled=False)
        )
        assert (
            app_module._observability_route_template(request)
            == "/items/507f191e810c19729de860ea"
        )

        slow_observability.configure_slow_observability(Settings(ops_slow_samples_enabled=True))
        assert app_module._observability_route_template(request) == "/items/{item_id}"
    finally:
        slow_observability.reset_slow_observability_for_tests()


@pytest.mark.asyncio
async def test_client_disconnect_cancels_public_address_request_while_body_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    started = asyncio.Event()
    cancelled = asyncio.Event()
    original_wait = asyncio.wait

    async def wait_with_cancel_race(
        futures: set[asyncio.Future[Any]],
        **kwargs: Any,
    ) -> tuple[set[asyncio.Future[Any]], set[asyncio.Future[Any]]]:
        done, pending = await original_wait(futures, **kwargs)
        return_when = kwargs.get("return_when", asyncio.ALL_COMPLETED)
        if return_when == asyncio.FIRST_COMPLETED:
            for _ in range(20):
                if all(future.done() for future in futures):
                    break
                await asyncio.sleep(0)
            done = {future for future in futures if future.done()}
            pending = futures - done
        return done, pending

    monkeypatch.setattr(app_module.asyncio, "wait", wait_with_cancel_race)

    @app.post("/v1/address/slow")
    async def slow() -> dict[str, str]:
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"status": "OK"}

    _install_performance_monitoring(app, Settings())
    _install_client_disconnect_cancellation(app)

    receive_messages: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
    await receive_messages.put({"type": "http.request", "body": b"{", "more_body": True})
    sent_messages: list[dict[str, Any]] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/address/slow",
        "raw_path": b"/v1/address/slow",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    async def receive() -> MutableMapping[str, Any]:
        return await receive_messages.get()

    async def send(message: MutableMapping[str, Any]) -> None:
        sent_messages.append(dict(message))

    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(started.wait(), timeout=1)
    await receive_messages.put({"type": "http.disconnect"})
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    await asyncio.wait_for(task, timeout=1)

    body = metrics.render_prometheus().decode()

    assert sent_messages == []
    assert "kor_travel_geo_api_request_cancellations_total" in body
    assert 'route="/v1/address/slow"' in body
    assert 'status_code="499"' in body


@pytest.mark.asyncio
async def test_client_disconnect_after_empty_body_cancels_public_get() -> None:
    app = FastAPI()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    @app.get("/v1/address/slow")
    async def slow() -> dict[str, str]:
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {"status": "OK"}

    _install_performance_monitoring(app, Settings())
    _install_client_disconnect_cancellation(app)

    receive_messages: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
    await receive_messages.put({"type": "http.request", "body": b"", "more_body": False})
    sent_messages: list[dict[str, Any]] = []
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/v1/address/slow",
        "raw_path": b"/v1/address/slow",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    async def receive() -> MutableMapping[str, Any]:
        return await receive_messages.get()

    async def send(message: MutableMapping[str, Any]) -> None:
        sent_messages.append(dict(message))

    task = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(started.wait(), timeout=1)
    await receive_messages.put({"type": "http.disconnect"})
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    await asyncio.wait_for(task, timeout=1)

    assert sent_messages == []


@pytest.mark.asyncio
async def test_disconnect_after_response_complete_does_not_cancel_public_request() -> None:
    response_sent = asyncio.Event()
    finish = asyncio.Event()
    cancelled = asyncio.Event()
    sent_messages: list[dict[str, Any]] = []

    async def asgi_app(_scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", b"2")],
            }
        )
        await send({"type": "http.response.body", "body": b"OK", "more_body": False})
        response_sent.set()
        try:
            await finish.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    middleware = ClientDisconnectCancellationMiddleware(asgi_app)
    receive_messages: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
    await receive_messages.put({"type": "http.request", "body": b"", "more_body": False})
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/v1/address/slow",
        "raw_path": b"/v1/address/slow",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    async def receive() -> MutableMapping[str, Any]:
        return await receive_messages.get()

    async def send(message: MutableMapping[str, Any]) -> None:
        sent_messages.append(dict(message))

    task = asyncio.create_task(middleware(scope, receive, send))
    await asyncio.wait_for(response_sent.wait(), timeout=1)
    await receive_messages.put({"type": "http.disconnect"})
    await asyncio.sleep(0)

    assert not cancelled.is_set()

    finish.set()
    await asyncio.wait_for(task, timeout=1)
    assert sent_messages[0] == {
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-length", b"2")],
    }
    body = b"".join(
        message.get("body", b"")
        for message in sent_messages
        if message["type"] == "http.response.body"
    )
    assert body == b"OK"
