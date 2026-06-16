from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from kortravelgeo.api.app import _install_admission_control
from kortravelgeo.settings import Settings


@pytest.mark.asyncio
async def test_admission_control_limits_parallel_address_requests() -> None:
    app = FastAPI()
    _install_admission_control(app, Settings(api_max_concurrency=1))
    active = 0
    max_active = 0

    @app.get("/v1/address/slow")
    async def slow() -> dict[str, str]:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"status": "OK"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(
            client.get("/v1/address/slow"),
            client.get("/v1/address/slow"),
        )

    assert [response.status_code for response in responses] == [200, 200]
    assert max_active == 1


@pytest.mark.asyncio
async def test_admission_control_times_out_with_rate_limit_error() -> None:
    app = FastAPI()
    _install_admission_control(
        app,
        Settings(api_max_concurrency=1, api_admission_timeout_ms=1),
    )
    entered = asyncio.Event()

    @app.get("/v1/address/slow")
    async def slow() -> dict[str, str]:
        entered.set()
        await asyncio.sleep(0.05)
        return {"status": "OK"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = asyncio.create_task(client.get("/v1/address/slow"))
        await entered.wait()
        response = await client.get("/v1/address/slow")
        await first

    assert response.status_code == 429
    assert response.json()["response"]["errorCode"] == "E0200"
    assert response.headers["Retry-After"] == "1"


@pytest.mark.asyncio
async def test_endpoint_admission_control_limits_only_matching_scope() -> None:
    app = FastAPI()
    _install_admission_control(
        app,
        Settings(api_geocode_max_concurrency=1, api_admission_timeout_ms=1),
    )
    entered = asyncio.Event()

    @app.get("/v1/address/geocode")
    async def geocode() -> dict[str, str]:
        entered.set()
        await asyncio.sleep(0.05)
        return {"status": "OK"}

    @app.get("/v1/address/reverse")
    async def reverse() -> dict[str, str]:
        return {"status": "OK"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = asyncio.create_task(client.get("/v1/address/geocode"))
        await entered.wait()
        blocked_geocode = await client.get("/v1/address/geocode")
        reverse_response = await client.get("/v1/address/reverse")
        await first

    assert blocked_geocode.status_code == 429
    assert blocked_geocode.json()["response"]["error"]["code"] == "OVER_REQUEST_LIMIT"
    assert blocked_geocode.headers["Cache-Control"] == "no-store"
    assert reverse_response.status_code == 200


@pytest.mark.asyncio
async def test_admission_control_skips_non_address_paths() -> None:
    app = FastAPI()
    _install_admission_control(
        app,
        Settings(api_max_concurrency=1, api_admission_timeout_ms=1),
    )

    @app.get("/v1/healthz")
    async def healthz() -> dict[str, str]:
        await asyncio.sleep(0.01)
        return {"status": "OK"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(
            client.get("/v1/healthz"),
            client.get("/v1/healthz"),
        )

    assert [response.status_code for response in responses] == [200, 200]


@pytest.mark.asyncio
async def test_admission_control_limits_v2_paths() -> None:
    app = FastAPI()
    _install_admission_control(app, Settings(api_max_concurrency=1))
    active = 0
    max_active = 0

    @app.get("/v2/slow")
    async def slow() -> dict[str, str]:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"status": "OK"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(
            client.get("/v2/slow"),
            client.get("/v2/slow"),
        )

    assert [response.status_code for response in responses] == [200, 200]
    assert max_active == 1
