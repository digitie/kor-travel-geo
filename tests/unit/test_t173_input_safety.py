from __future__ import annotations

from typing import Any, Literal

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.geocoder import geocode as core_geocode
from kortravelgeo.core.protocols import FakeGeocodeRepo
from kortravelgeo.core.sppn import parse_national_point_number
from kortravelgeo.dto.geocode import GeocodeInput
from kortravelgeo.dto.v2 import GeocodeV2Input, ReverseV2Input

HttpMethod = Literal["get", "post"]


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "expected_shape", "expected_code"),
    [
        ("post", "/v2/geocode", {"json": {}}, "v2", "E0100"),
        (
            "post",
            "/v2/geocode",
            {"json": {"query": "서울특별시\x00강남구 1"}},
            "v2",
            "E0100",
        ),
        (
            "post",
            "/v2/geocode",
            {"json": {"query": "라사 2670 8512\x00"}},
            "v2",
            "E0100",
        ),
        (
            "post",
            "/v2/reverse",
            {"json": {"lon": 0.0, "lat": 0.0, "radius_m": 200}},
            "v2",
            "E0102",
        ),
        (
            "post",
            "/v2/reverse",
            {"json": {"lon": "NaN", "lat": 37.5, "radius_m": 200}},
            "v2",
            "E0100",
        ),
        (
            "post",
            "/v2/reverse",
            {"json": {"lon": 127.0, "lat": 37.5, "radius_m": 0}},
            "v2",
            "E0100",
        ),
        ("get", "/v1/address/geocode", {"params": {}}, "vworld", "PARAM_REQUIRED"),
        (
            "get",
            "/v1/address/geocode",
            {"params": {"address": "서울특별시\x00강남구 1"}},
            "vworld",
            "INVALID_TYPE",
        ),
        (
            "get",
            "/v1/address/reverse",
            {"params": {"x": 0.0, "y": 0.0}},
            "vworld",
            "INVALID_RANGE",
        ),
    ],
)
@pytest.mark.asyncio
async def test_t173_public_address_inputs_return_structured_4xx(
    method: HttpMethod,
    path: str,
    kwargs: dict[str, Any],
    expected_shape: Literal["v2", "vworld"],
    expected_code: str,
) -> None:
    app = create_app()
    app.dependency_overrides[get_client] = lambda: AsyncAddressClient(
        engine=object()  # type: ignore[arg-type]
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await getattr(client, method)(path, **kwargs)

    assert 400 <= response.status_code < 500
    payload = response.json()
    assert set(payload) == {"response"}
    assert payload["response"]["status"] == "ERROR"
    if expected_shape == "vworld":
        assert payload["response"]["service"]["name"] == "address"
        assert payload["response"]["error"]["code"] == expected_code
    else:
        assert payload["response"]["errorCode"] == expected_code
        assert payload["response"]["errorMessage"]


def test_t173_geocode_text_inputs_reject_control_characters() -> None:
    with pytest.raises(ValueError, match="control characters"):
        GeocodeInput(address="서울특별시\x00강남구 1")
    with pytest.raises(ValueError, match="control characters"):
        GeocodeV2Input(query="라사 2670 8512\x00")


def test_t173_reverse_v2_rejects_non_finite_and_outside_korea_coordinates() -> None:
    with pytest.raises(ValueError, match="finite"):
        ReverseV2Input(lon=float("nan"), lat=37.5)
    with pytest.raises(ValueError, match="coordinate_bounds"):
        ReverseV2Input(lon=0.0, lat=0.0)


@pytest.mark.parametrize(
    "address",
    [
        "가가 0000 0000",
        "라사 2670 8512 trailing",
        "라사 2670 851200",
    ],
)
@pytest.mark.asyncio
async def test_t173_malformed_sppn_inputs_do_not_crash_core_geocode(address: str) -> None:
    response = await core_geocode(FakeGeocodeRepo(), GeocodeInput(address=address))

    assert response.status == "NOT_FOUND"
    assert response.result is None


def test_t173_sppn_parser_rejects_extra_control_text_without_crashing() -> None:
    assert parse_national_point_number("라사 2670 8512\x00") is None
