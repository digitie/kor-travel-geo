from __future__ import annotations

from typing import Any

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.dto.address import AddressStructure, RefinedAddress
from kortravelgeo.dto.common import Point, ServiceMeta
from kortravelgeo.dto.geocode import GeocodeExtension, GeocodeInput, GeocodeResponse, GeocodeResult
from kortravelgeo.dto.reverse import ReverseInput, ReverseResponse, ReverseResultItem


class _FakeV1Client:
    async def _geocode_v1(
        self,
        address: str,
        **kwargs: Any,
    ) -> GeocodeResponse:
        kwargs.pop("sig_cd", None)
        kwargs.pop("bjd_cd", None)
        inp = GeocodeInput(address=address, **kwargs)
        return GeocodeResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="geocode"),
            status="OK",
            input=inp,
            refined=RefinedAddress(
                text=address,
                structure=AddressStructure(level1="서울특별시", level2="강남구"),
            ),
            result=GeocodeResult(point=Point(x=127.036, y=37.501)),
            x_extension=GeocodeExtension(
                source="local",
                confidence=0.98,
                bd_mgt_sn="1168010100108250000028924",
            ),
        )

    async def _reverse_geocode_v1(
        self,
        x: float,
        y: float,
        **kwargs: Any,
    ) -> ReverseResponse:
        kwargs.pop("sig_cd", None)
        kwargs.pop("bjd_cd", None)
        radius_m = kwargs.pop("radius_m") or 200
        inp = ReverseInput(point=Point(x=x, y=y), radius_m=radius_m, **kwargs)
        return ReverseResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
            status="OK",
            input=inp,
            result=(
                ReverseResultItem(
                    type="road",
                    text="서울특별시 강남구 테헤란로 152",
                    structure=AddressStructure(level1="서울특별시", level2="강남구"),
                    point=Point(x=x, y=y),
                    zipcode="06236",
                    distance_m=3.2,
                ),
            ),
        )


@pytest.mark.asyncio
async def test_v1_geocode_http_response_uses_vworld_envelope() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = _FakeV1Client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/address/geocode",
            params={
                "address": "서울특별시 강남구 테헤란로 152",
                "type": "road",
                "fallback": "local_only",
            },
        )

    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"response"}
    assert body["response"]["service"]["name"] == "address"
    assert body["response"]["service"]["operation"] == "getCoord"
    assert body["response"]["input"]["type"] == "ROAD"
    assert body["response"]["result"]["point"] == {"x": 127.036, "y": 37.501}
    assert body["response"]["x_extension"]["bd_mgt_sn"] == "1168010100108250000028924"


@pytest.mark.asyncio
async def test_v1_geocode_simple_omits_input_and_refined() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = _FakeV1Client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/address/geocode",
            params={
                "address": "서울특별시 강남구 테헤란로 152",
                "simple": "true",
            },
        )

    payload = response.json()["response"]

    assert response.status_code == 200
    assert "input" not in payload
    assert "refined" not in payload
    assert payload["result"]["point"]["x"] == 127.036


@pytest.mark.asyncio
async def test_v1_reverse_http_response_uses_vworld_envelope() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = _FakeV1Client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/address/reverse",
            params={"x": 127.036, "y": 37.501, "type": "both"},
        )

    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"response"}
    assert body["response"]["service"]["name"] == "address"
    assert body["response"]["service"]["operation"] == "getAddress"
    assert body["response"]["input"]["type"] == "BOTH"
    assert body["response"]["result"][0]["type"] == "ROAD"
    assert body["response"]["result"][0]["zipcode"] == "06236"


@pytest.mark.asyncio
async def test_v1_geocode_request_validation_uses_vworld_error_object() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = _FakeV1Client
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/address/geocode")

    body = response.json()

    assert response.status_code == 400
    assert set(body) == {"response"}
    assert body["response"]["service"]["operation"] == "getCoord"
    assert body["response"]["status"] == "ERROR"
    assert body["response"]["error"] == {
        "level": 1,
        "code": "PARAM_REQUIRED",
        "text": "필수 파라미터인 <address>가 없어서 요청을 처리할수 없습니다.",
    }
