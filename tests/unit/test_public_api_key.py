from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from pydantic import SecretStr

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.api.responses import register_exception_handlers
from kortravelgeo.dto.v2 import GeocodeV2Input, GeocodeV2Response
from kortravelgeo.infra import public_api_keys
from kortravelgeo.settings import Settings, get_settings, reset_settings, set_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

_VWORLD_DEFAULT_KEY = "vworld-default-key"
_TRUSTED_HEADERS = {"X-KTG-Actor": "ui-admin", "X-KTG-Roles": "source_file_viewer"}


@pytest.fixture(autouse=True)
def _settings() -> Iterator[None]:
    set_settings(
        Settings(
            _env_file=None,
            admin_trusted_proxy_cidrs="127.0.0.0/8",
            geoip_gate_mode="off",
            vworld_api_key=SecretStr(_VWORLD_DEFAULT_KEY),
        )
    )
    try:
        yield
    finally:
        reset_settings()
        public_api_keys.invalidate_public_api_key_cache()


class _FakeV2Client:
    async def geocode(self, **kwargs: Any) -> GeocodeV2Response:
        return GeocodeV2Response(status="OK", input=GeocodeV2Input(query=kwargs["query"]))


@pytest.mark.asyncio
async def test_v1_requires_key_query_parameter() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/address/geocode", params={"address": "서울시청"})

    payload = response.json()["response"]
    assert response.status_code == 400
    assert payload["status"] == "ERROR"
    assert payload["error"]["code"] == "PARAM_REQUIRED"
    assert "<key>" in payload["error"]["text"]


@pytest.mark.asyncio
async def test_v1_rejects_invalid_key_against_vworld_default() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/address/geocode",
            params={"address": "서울시청", "key": "wrong"},
        )

    payload = response.json()["response"]
    assert response.status_code == 401
    assert payload["error"]["code"] == "INVALID_KEY"


@pytest.mark.asyncio
async def test_v2_requires_key_query_parameter() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = lambda: _FakeV2Client()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v2/geocode", json={"query": "서울시청"})

    payload = response.json()
    assert response.status_code == 400
    assert payload["status"] == "ERROR"
    assert payload["error"]["code"] == "E0100"
    assert payload["error"]["field"] == "key"


@pytest.mark.asyncio
async def test_v2_accepts_vworld_default_key_when_no_db_key_exists() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = lambda: _FakeV2Client()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v2/geocode",
            params={"key": _VWORLD_DEFAULT_KEY},
            json={"query": "서울시청"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "OK"


@pytest.mark.asyncio
async def test_trusted_proxy_identity_bypasses_public_key_for_v2() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = lambda: _FakeV2Client()
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing_key = await client.post(
            "/v2/geocode",
            headers=_TRUSTED_HEADERS,
            json={"query": "서울시청"},
        )
        wrong_key = await client.post(
            "/v2/geocode",
            headers=_TRUSTED_HEADERS,
            params={"key": "wrong"},
            json={"query": "서울시청"},
        )

    assert missing_key.status_code == 200
    assert wrong_key.status_code == 200


@pytest.mark.asyncio
async def test_trusted_proxy_identity_bypasses_public_key_for_v1_dependency() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        vworld_api_key=SecretStr(_VWORLD_DEFAULT_KEY),
    )

    @app.get("/v1/address/geocode")
    async def protected(_api_key: None = Depends(require_public_api_key)) -> dict[str, bool]:
        return {"ok": True}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/address/geocode", headers=_TRUSTED_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_db_active_key_overrides_vworld_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_hashes(*_args: Any, **_kwargs: Any) -> frozenset[str]:
        return frozenset({public_api_keys.hash_public_api_key("db-generated-key")})

    monkeypatch.setattr(
        "kortravelgeo.api.public_api_key._engine_from_request",
        lambda _req: object(),
    )
    monkeypatch.setattr(
        "kortravelgeo.api.public_api_key.cached_active_public_api_key_hashes",
        fake_hashes,
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        vworld_api_key=SecretStr(_VWORLD_DEFAULT_KEY),
    )

    @app.get("/v1/address/geocode")
    async def protected(_api_key: None = Depends(require_public_api_key)) -> dict[str, bool]:
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        fallback = await client.get(
            "/v1/address/geocode",
            params={"key": _VWORLD_DEFAULT_KEY},
        )
        generated = await client.get(
            "/v1/address/geocode",
            params={"key": "db-generated-key"},
        )

    assert fallback.status_code == 401
    assert fallback.json()["response"]["error"]["code"] == "INVALID_KEY"
    assert generated.status_code == 200
    assert generated.json() == {"ok": True}
