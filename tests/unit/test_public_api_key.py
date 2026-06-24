from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import httpx
import pytest
from fastapi import Depends, FastAPI
from pydantic import SecretStr

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.api.responses import register_exception_handlers
from kortravelgeo.api.security import ROLE_SOURCE_FILE_VIEWER, require_role
from kortravelgeo.dto.v2 import GeocodeV2Input, GeocodeV2Response
from kortravelgeo.exceptions import NotFoundError
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
    calls = 0

    async def fake_hashes(_repo: Any) -> frozenset[str]:
        nonlocal calls
        calls += 1
        return frozenset({public_api_keys.hash_public_api_key("db-generated-key")})

    monkeypatch.setattr(
        "kortravelgeo.api.public_api_key._engine_from_request",
        lambda _req: object(),
    )
    monkeypatch.setattr(
        "kortravelgeo.api.public_api_key.PublicApiKeyRepository.active_key_hashes",
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
    assert calls == 2


@pytest.mark.asyncio
async def test_revoke_key_rejects_malformed_uuid_as_not_found() -> None:
    # A non-UUID id must surface as NotFound (→ 404), not reach the UUID column and 500.
    repo = public_api_keys.PublicApiKeyRepository(cast("Any", object()))
    with pytest.raises(NotFoundError):
        await repo.revoke_key("not-a-uuid", revoked_by="admin")


def _proxy_secret_settings() -> Settings:
    return Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        admin_proxy_secret=SecretStr("proxy-secret"),
        vworld_api_key=SecretStr(_VWORLD_DEFAULT_KEY),
    )


@pytest.mark.asyncio
async def test_admin_proxy_secret_required_for_admin_route_when_configured() -> None:
    # When admin_proxy_secret is set, a trusted-peer request with the admin identity headers is
    # still denied (403) unless it also carries the matching X-KTG-Admin-Proxy-Secret.
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = _proxy_secret_settings
    # Hoist the parameterized dependency out of the argument default (ruff B008).
    viewer_dep = Depends(require_role(ROLE_SOURCE_FILE_VIEWER))

    @app.get("/v1/admin/probe")
    async def probe(_ctx: Any = viewer_dep) -> dict[str, bool]:
        return {"ok": True}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/v1/admin/probe", headers=_TRUSTED_HEADERS)
        wrong = await client.get(
            "/v1/admin/probe",
            headers={**_TRUSTED_HEADERS, "X-KTG-Admin-Proxy-Secret": "nope"},
        )
        ok = await client.get(
            "/v1/admin/probe",
            headers={**_TRUSTED_HEADERS, "X-KTG-Admin-Proxy-Secret": "proxy-secret"},
        )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}


@pytest.mark.asyncio
async def test_admin_proxy_secret_gates_public_key_bypass() -> None:
    # The trusted-proxy public-key bypass is gated by the same secret: correct secret bypasses
    # the key requirement (200); a missing secret falls through to the normal key check (400).
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = _proxy_secret_settings

    @app.get("/v1/address/geocode")
    async def protected(_api_key: None = Depends(require_public_api_key)) -> dict[str, bool]:
        return {"ok": True}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        bypassed = await client.get(
            "/v1/address/geocode",
            headers={**_TRUSTED_HEADERS, "X-KTG-Admin-Proxy-Secret": "proxy-secret"},
        )
        denied = await client.get("/v1/address/geocode", headers=_TRUSTED_HEADERS)

    assert bypassed.status_code == 200
    assert bypassed.json() == {"ok": True}
    # No secret → no bypass → the normal public-key requirement applies (client error, not 200).
    assert denied.status_code == 400
