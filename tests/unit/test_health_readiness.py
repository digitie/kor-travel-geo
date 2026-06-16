from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from kortravelgeo.api.routers import healthz


class _FakePool:
    def __init__(self, *, checked_in: int = 10, checked_out: int = 0) -> None:
        self._checked_in = checked_in
        self._checked_out = checked_out

    def size(self) -> int:
        return 10

    def checkedin(self) -> int:
        return self._checked_in

    def checkedout(self) -> int:
        return self._checked_out

    def overflow(self) -> int:
        return 0


class _FakeSyncEngine:
    def __init__(self, pool: _FakePool) -> None:
        self.pool = pool


class _FakeResult:
    def mappings(self) -> _FakeResult:
        return self

    def one(self) -> dict[str, str]:
        return {"current_database": "kor_travel_geo", "postgres_version": "16.4"}


class _FakeConnection:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def execute(self, _statement: object) -> _FakeResult:
        if self.fail:
            raise RuntimeError("database unavailable")
        return _FakeResult()


class _FakeConnectionContext:
    def __init__(self, engine: _FakeEngine) -> None:
        self.engine = engine

    async def __aenter__(self) -> _FakeConnection:
        self.engine.connect_count += 1
        return _FakeConnection(fail=self.engine.fail)

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FakeEngine:
    def __init__(
        self,
        *,
        pool: _FakePool | None = None,
        fail: bool = False,
    ) -> None:
        self.sync_engine = _FakeSyncEngine(pool or _FakePool())
        self.fail = fail
        self.connect_count = 0

    def connect(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self)


class _FakeClient:
    def __init__(self, engine: _FakeEngine | None) -> None:
        self.engine = engine


def _app(client: Any | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(healthz.router, prefix="/v1")
    if client is not None:
        app.state.client = client
    return app


@pytest.mark.asyncio
async def test_healthz_stays_liveness_without_db_client() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_returns_ready_when_database_ping_and_pool_are_ok() -> None:
    engine = _FakeEngine()
    transport = httpx.ASGITransport(app=_app(_FakeClient(engine)))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/readyz")

    payload = response.json()
    assert response.status_code == 200
    assert payload["ready"] is True
    assert payload["degraded"] is False
    assert payload["components"]["database"]["status"] == "ok"
    assert payload["components"]["pool"]["status"] == "ok"
    assert engine.connect_count == 1


@pytest.mark.asyncio
async def test_readyz_returns_unavailable_when_database_ping_fails() -> None:
    transport = httpx.ASGITransport(app=_app(_FakeClient(_FakeEngine(fail=True))))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/readyz")

    payload = response.json()
    assert response.status_code == 503
    assert payload["ready"] is False
    assert payload["degraded"] is True
    assert payload["components"]["database"]["status"] == "unavailable"
    assert payload["components"]["database"]["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_readyz_fast_fails_without_db_checkout_when_pool_is_saturated() -> None:
    engine = _FakeEngine(pool=_FakePool(checked_in=0, checked_out=15))
    transport = httpx.ASGITransport(app=_app(_FakeClient(engine)))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/readyz")

    payload = response.json()
    assert response.status_code == 503
    assert payload["ready"] is False
    assert payload["degraded"] is True
    assert payload["components"]["database"]["status"] == "skipped"
    assert payload["components"]["pool"]["status"] == "saturated"
    assert engine.connect_count == 0


@pytest.mark.asyncio
async def test_readyz_reports_degraded_when_pool_utilization_is_high() -> None:
    transport = httpx.ASGITransport(
        app=_app(_FakeClient(_FakeEngine(pool=_FakePool(checked_in=1, checked_out=12))))
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/readyz")

    payload = response.json()
    assert response.status_code == 200
    assert payload["ready"] is True
    assert payload["degraded"] is True
    assert payload["status"] == "degraded"
    assert payload["components"]["pool"]["status"] == "degraded"
