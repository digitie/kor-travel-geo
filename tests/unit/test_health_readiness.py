from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from kortravelgeo.api.admission import AdmissionScopeSnapshot
from kortravelgeo.api.routers import healthz
from kortravelgeo.settings import Settings, reset_settings, set_settings


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
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeResult:
        return self

    def one(self) -> dict[str, Any]:
        return self._rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self._rows


_SERVING_OK = {"mv_geocode_target": "ok", "mv_geocode_text_search": "ok"}


class _FakeConnection:
    def __init__(self, engine: _FakeEngine) -> None:
        self.engine = engine

    async def execute(self, statement: object, _params: object = None) -> _FakeResult:
        if self.engine.mode == "fail":
            raise RuntimeError("database unavailable")
        if self.engine.mode == "slow":
            await asyncio.sleep(1.0)
        sql = str(statement)
        self.engine.statements.append(sql)
        serving = self.engine.serving
        if "pg_class" in sql:
            if self.engine.serving_fail:
                raise RuntimeError("catalog unavailable")
            # 실제 SQL처럼 missing → NULL, not_populated → false.
            return _FakeResult(
                [
                    {
                        "relation_name": name,
                        "relispopulated": None if state == "missing" else state != "not_populated",
                    }
                    for name, state in serving.items()
                ]
            )
        if "EXISTS" in sql:
            return _FakeResult([{name: state == "ok" for name, state in serving.items()}])
        return _FakeResult([{"current_database": "kor_travel_geo", "postgres_version": "16.4"}])


class _FakeConnectionContext:
    def __init__(self, engine: _FakeEngine) -> None:
        self.engine = engine

    async def __aenter__(self) -> _FakeConnection:
        self.engine.connect_count += 1
        return _FakeConnection(self.engine)

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FakeEngine:
    def __init__(
        self,
        *,
        pool: _FakePool | None = None,
        fail: bool = False,
        mode: str = "ok",
        serving: dict[str, str] | None = None,
        serving_fail: bool = False,
    ) -> None:
        self.sync_engine = _FakeSyncEngine(pool or _FakePool())
        self.mode = "fail" if fail else mode
        self.serving = dict(serving or _SERVING_OK)
        self.serving_fail = serving_fail
        self.statements: list[str] = []
        self.connect_count = 0

    def connect(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self)


class _FakeClient:
    def __init__(self, engine: _FakeEngine | None) -> None:
        self.engine = engine


class _FakeAdmissionController:
    def __init__(self, snapshots: tuple[AdmissionScopeSnapshot, ...]) -> None:
        self._snapshots = snapshots

    def snapshots(self) -> tuple[AdmissionScopeSnapshot, ...]:
        return self._snapshots


def _app(
    client: Any | None = None,
    admission: _FakeAdmissionController | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(healthz.router, prefix="/v1")
    if client is not None:
        app.state.client = client
    if admission is not None:
        app.state.admission_control = admission
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
    assert payload["components"]["pool"]["detail"]["timeout_ms"] == 1000
    assert payload["components"]["serving"]["status"] == "ok"
    assert payload["components"]["serving"]["detail"]["relations"] == _SERVING_OK
    # DB probe 1회 + serving probe 1회(순차) — 동시에 두 connection을 잡지 않는다.
    assert engine.connect_count == 2


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
    assert payload["components"]["serving"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_readyz_times_out_slow_database_probe_and_recovers() -> None:
    set_settings(Settings(api_readiness_timeout_ms=10))
    engine = _FakeEngine(mode="slow")
    transport = httpx.ASGITransport(app=_app(_FakeClient(engine)))

    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = perf_counter()
            unavailable = await client.get("/v1/readyz")
            elapsed = perf_counter() - started

            engine.mode = "ok"
            recovered = await client.get("/v1/readyz")
    finally:
        reset_settings()

    unavailable_payload = unavailable.json()
    recovered_payload = recovered.json()
    assert elapsed < 0.5
    assert unavailable.status_code == 503
    assert unavailable_payload["ready"] is False
    assert unavailable_payload["degraded"] is True
    assert unavailable_payload["components"]["database"]["status"] == "unavailable"
    assert unavailable_payload["components"]["database"]["error_type"] == "TimeoutError"
    assert recovered.status_code == 200
    assert recovered_payload["ready"] is True
    assert recovered_payload["degraded"] is False
    assert recovered_payload["components"]["database"]["status"] == "ok"
    # slow: DB probe만(serving은 skipped) 1회, 회복: DB + serving 2회.
    assert engine.connect_count == 3


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


@pytest.mark.asyncio
async def test_readyz_reports_degraded_when_admission_scope_is_saturated() -> None:
    admission = _FakeAdmissionController(
        (
            AdmissionScopeSnapshot(
                scope="geocode",
                limit=1,
                in_use=1,
                available=0,
                utilization=1.0,
            ),
        )
    )
    transport = httpx.ASGITransport(app=_app(_FakeClient(_FakeEngine()), admission))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/readyz")

    payload = response.json()
    assert response.status_code == 200
    assert payload["ready"] is True
    assert payload["degraded"] is True
    assert payload["status"] == "degraded"
    assert payload["components"]["admission"]["status"] == "saturated"
    assert payload["components"]["admission"]["detail"]["scopes"][0]["scope"] == "geocode"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "serving",
    [
        # 최초 적재 전(행 없음)과 데이터 없이 복원된 MV(unpopulated) — 2026-09-28 장애 형태.
        {"mv_geocode_target": "empty", "mv_geocode_text_search": "not_populated"},
        # migration 전 빈 DB: relation 자체가 없다.
        {"mv_geocode_target": "missing", "mv_geocode_text_search": "missing"},
        # 한쪽만 비어도 degraded다.
        {"mv_geocode_target": "ok", "mv_geocode_text_search": "empty"},
    ],
)
async def test_readyz_reports_degraded_but_ready_when_serving_mvs_are_not_ok(
    serving: dict[str, str],
) -> None:
    engine = _FakeEngine(serving=serving)
    transport = httpx.ASGITransport(app=_app(_FakeClient(engine)))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/readyz")

    payload = response.json()
    # 빈 DB는 정상 상태일 수 있으므로 503(not ready)이 아니라 200 + degraded로 알린다.
    assert response.status_code == 200
    assert payload["ready"] is True
    assert payload["degraded"] is True
    assert payload["status"] == "degraded"
    assert payload["components"]["database"]["status"] == "ok"
    assert payload["components"]["serving"]["status"] == "degraded"
    assert payload["components"]["serving"]["detail"]["relations"] == serving


@pytest.mark.asyncio
async def test_readyz_serving_probe_never_counts_rows_and_skips_unpopulated_mvs() -> None:
    engine = _FakeEngine(
        serving={"mv_geocode_target": "ok", "mv_geocode_text_search": "not_populated"}
    )
    transport = httpx.ASGITransport(app=_app(_FakeClient(engine)))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/v1/readyz")

    probes = " ".join(engine.statements).lower()
    assert "count(" not in probes
    exists = [sql for sql in engine.statements if "EXISTS" in sql]
    assert len(exists) == 1
    # unpopulated MV를 SELECT하면 오류가 나므로 EXISTS 대상에서 뺀다.
    assert "mv_geocode_target" in exists[0]
    assert "mv_geocode_text_search" not in exists[0]


@pytest.mark.asyncio
async def test_readyz_serving_probe_failure_is_unknown_and_not_degraded() -> None:
    engine = _FakeEngine(serving_fail=True)
    transport = httpx.ASGITransport(app=_app(_FakeClient(engine)))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/readyz")

    payload = response.json()
    assert response.status_code == 200
    assert payload["ready"] is True
    assert payload["degraded"] is False
    assert payload["components"]["serving"]["status"] == "unknown"
    assert payload["components"]["serving"]["error_type"] == "RuntimeError"
