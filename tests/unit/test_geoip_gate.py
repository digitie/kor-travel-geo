from __future__ import annotations

import asyncio
from ipaddress import ip_network

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kortravelgeo.api.app import _install_admission_control
from kortravelgeo.api.middleware.geoip_gate import install_geoip_gate
from kortravelgeo.infra.geoip import classify_ip, client_ip_from_forwarded, is_open_path
from kortravelgeo.settings import Settings


class FakeReader:
    def __init__(self, countries: dict[str, str | None]) -> None:
        self.countries = countries

    def country_code(self, ip: str) -> str | None:
        return self.countries.get(ip)


def test_classify_ip_allows_internal_and_kr_public_ip() -> None:
    reader = FakeReader({"1.201.1.1": "KR"})

    assert classify_ip("10.1.2.3", reader=reader, mode="strict").reason == "internal_ip"
    decision = classify_ip("1.201.1.1", reader=reader, mode="strict")

    assert decision.allowed is True
    assert decision.country_code == "KR"
    assert decision.reason == "kr_public_ip"


def test_classify_ip_honors_deny_and_allow_cidrs() -> None:
    reader = FakeReader({})

    denied = classify_ip(
        "10.1.2.3",
        reader=reader,
        mode="strict",
        deny_cidrs=(ip_network("10.0.0.0/8"),),
    )
    allowed = classify_ip(
        "8.8.8.8",
        reader=reader,
        mode="strict",
        allow_cidrs=(ip_network("8.8.8.0/24"),),
    )

    assert denied.allowed is False
    assert denied.reason == "denylist"
    assert allowed.allowed is True
    assert allowed.reason == "allowlist"


def test_classify_ip_denies_non_kr_or_missing_db_in_strict_mode() -> None:
    reader = FakeReader({"8.8.8.8": "US"})

    assert classify_ip("8.8.8.8", reader=reader, mode="strict").reason == "non_kr_public_ip"
    assert classify_ip("8.8.4.4", reader=None, mode="strict").reason == "geoip_db_unavailable"
    assert classify_ip("testclient", reader=reader, mode="strict").reason == "invalid_client_ip"


def test_classify_ip_permissive_allows_non_kr_public_ip() -> None:
    decision = classify_ip("8.8.8.8", reader=FakeReader({"8.8.8.8": "US"}), mode="permissive")

    assert decision.allowed is True
    assert decision.reason == "permissive_non_kr"


def test_client_ip_from_forwarded_trusts_only_configured_proxy() -> None:
    trusted = (ip_network("127.0.0.1/32"),)

    assert client_ip_from_forwarded("8.8.8.8", "1.1.1.1", trusted) == "8.8.8.8"
    assert client_ip_from_forwarded("127.0.0.1", "1.1.1.1, 127.0.0.1", trusted) == "1.1.1.1"
    assert (
        client_ip_from_forwarded("127.0.0.1", "1.1.1.1:5678, 127.0.0.1", trusted)
        == "1.1.1.1"
    )
    assert (
        client_ip_from_forwarded("127.0.0.1", "[2001:4860:4860::8888]:443, 127.0.0.1", trusted)
        == "2001:4860:4860::8888"
    )


def test_open_paths_match_exact_and_child_paths() -> None:
    assert is_open_path("/v1/healthz", ("/v1/healthz",))
    assert is_open_path("/metrics/prometheus", ("/metrics",))
    assert not is_open_path("/v1/address/geocode", ("/v1/healthz",))


def test_geoip_middleware_denies_public_non_kr_ip_and_keeps_health_open() -> None:
    app = FastAPI()
    settings = Settings(geoip_gate_mode="strict", geoip_audit_denials=False)
    install_geoip_gate(app, settings, reader=FakeReader({"8.8.8.8": "US"}))

    @app.get("/v1/address/geocode")
    def geocode() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/v1/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app, client=("8.8.8.8", 12345))

    denied = client.get("/v1/address/geocode")
    open_response = client.get("/v1/healthz")

    assert denied.status_code == 403
    assert denied.json()["response"]["errorCode"] == "E0403"
    assert denied.json()["response"]["client_country"] == "US"
    assert open_response.status_code == 200


@pytest.mark.asyncio
async def test_geoip_gate_runs_before_admission_control_for_denied_clients() -> None:
    app = FastAPI()
    settings = Settings(
        api_max_concurrency=1,
        api_admission_timeout_ms=1,
        geoip_gate_mode="strict",
        geoip_audit_denials=False,
    )
    _install_admission_control(app, settings)
    install_geoip_gate(
        app,
        settings,
        reader=FakeReader({"1.201.1.1": "KR", "8.8.8.8": "US"}),
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    @app.get("/v1/address/slow")
    async def slow() -> dict[str, str]:
        entered.set()
        await release.wait()
        return {"status": "OK"}

    kr_transport = httpx.ASGITransport(app=app, client=("1.201.1.1", 10001))
    us_transport = httpx.ASGITransport(app=app, client=("8.8.8.8", 10002))
    async with (
        httpx.AsyncClient(transport=kr_transport, base_url="http://test") as kr_client,
        httpx.AsyncClient(transport=us_transport, base_url="http://test") as us_client,
    ):
        first = asyncio.create_task(kr_client.get("/v1/address/slow"))
        await entered.wait()
        denied = await us_client.get("/v1/address/slow")
        release.set()
        await first

    assert denied.status_code == 403
    assert denied.json()["response"]["errorCode"] == "E0403"
