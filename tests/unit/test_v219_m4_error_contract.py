"""T-219 M4 / T-268: v2 error envelope contract (ADR-060 §4).

v2 API validation/domain errors use ``{status, query_id, error:{code, message, hint?, field?}}``,
sharing the success trace key ``query_id``. The structured 4xx is intended input-safety (T-173).
The ``hint`` is sanitized — no raw pydantic repr, no echoed input value, no extra-key reflection.
"""

from __future__ import annotations

import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.client import AsyncAddressClient

_V2_PATHS = ("/v2/geocode", "/v2/reverse", "/v2/search", "/v2/regions/within-radius")


def _app_with_dummy_client() -> object:
    app = create_app()
    # validation fails before the client is touched, so a dummy engine is enough.
    app.dependency_overrides[get_client] = lambda: AsyncAddressClient(
        engine=object()  # type: ignore[arg-type]
    )
    return app


def test_v2_paths_advertise_v2_error_envelope_and_drop_422() -> None:
    schema = create_app().openapi()
    for path in _V2_PATHS:
        responses = schema["paths"][path]["post"]["responses"]
        assert "422" not in responses, f"{path} should not advertise the auto-422"
        ref = responses["400"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/V2ErrorEnvelope")


def test_v2_error_schema_shares_trace_key_and_detail() -> None:
    comps = create_app().openapi()["components"]["schemas"]
    env = comps["V2ErrorEnvelope"]
    assert {"status", "error"} <= set(env["required"])  # query_id has a default factory
    assert set(env["properties"]) == {"status", "query_id", "error"}
    detail = comps["V2ErrorDetail"]
    assert {"code", "message"} <= set(detail["required"])
    assert set(detail["properties"]) == {"code", "message", "hint", "field"}
    # the legacy {response:{errorCode}} envelope is gone for v2 (superseded by V2ErrorEnvelope).
    assert "StructuredErrorEnvelope" not in comps


@pytest.mark.asyncio
async def test_v2_validation_error_uses_envelope_with_trace_and_field() -> None:
    import httpx

    app = _app_with_dummy_client()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v2/reverse", json={"lon": 127.0, "lat": 37.5, "radius_m": 0})

    assert response.status_code == 400
    payload = response.json()
    assert "response" not in payload  # not the legacy wrapper
    assert payload["status"] == "ERROR"
    assert payload["query_id"]
    assert payload["error"]["code"] == "E0100"
    assert payload["error"]["message"]
    assert payload["error"]["field"] == "radius_m"  # container 'body' stripped


@pytest.mark.asyncio
async def test_v2_coordinate_bounds_error_code() -> None:
    import httpx

    app = _app_with_dummy_client()
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v2/reverse", json={"lon": 0.0, "lat": 0.0, "radius_m": 200})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "E0102"


@pytest.mark.asyncio
async def test_v2_validation_hint_is_sanitized_and_does_not_leak_input() -> None:
    import httpx

    app = _app_with_dummy_client()
    secret = "x" * 250  # over the 200-char limit -> a validation error
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v2/geocode", json={"query": secret})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "E0100"
    hint = error["hint"]
    # sanitized "loc: msg" form, not the raw pydantic errors repr.
    assert hint
    assert "query" in hint
    assert secret not in hint  # the user-supplied value must not be echoed back
    for leak in ("'input'", "'url'", "'ctx'", "'type'", "[{"):
        assert leak not in hint, f"hint leaks raw pydantic repr fragment {leak!r}: {hint!r}"


@pytest.mark.asyncio
async def test_v2_extra_key_name_is_not_reflected_in_hint() -> None:
    # extra='forbid' makes the bad-key name the loc leaf; it must not be echoed (ADR-061 §3).
    import httpx

    app = _app_with_dummy_client()
    marker = "leaked__${jndi:ldap://evil}__key"
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v2/geocode", json={"query": "x", marker: 1})

    assert response.status_code == 400
    hint = response.json()["error"]["hint"]
    assert hint and marker not in hint
    assert "unexpected field" in hint  # still informative without reflecting the key


@pytest.mark.asyncio
async def test_v2_validation_hint_is_length_bounded() -> None:
    # a request stuffed with bogus keys must not amplify the response.
    import httpx

    app = _app_with_dummy_client()
    body: dict[str, object] = {"query": "x"}
    body.update({f"junk_{i}_{'z' * 200}": 1 for i in range(500)})
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v2/geocode", json=body)

    assert response.status_code == 400
    hint = response.json()["error"]["hint"]
    assert hint is not None and len(hint) <= 600
