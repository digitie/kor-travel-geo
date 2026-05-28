from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from kraddr.geo.dto.geocode import GeocodeInput
from kraddr.geo.infra.external_api import ExternalGeocodeClient
from kraddr.geo.settings import Settings


@pytest.mark.asyncio
async def test_external_geocode_client_maps_vworld_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["request"] == "getcoord"
        return httpx.Response(
            200,
            json={
                "response": {
                    "status": "OK",
                    "result": {
                        "text": "서울특별시 강남구 테헤란로 152",
                        "point": {"x": "127.036", "y": "37.501"},
                        "structure": {"level1": "서울특별시", "level2": "강남구"},
                    },
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ExternalGeocodeClient(
            Settings(vworld_api_key=SecretStr("vworld-key")),
            http_client=http_client,
        )
        response = await client.geocode(GeocodeInput(address="서울특별시 강남구 테헤란로 152"))

    assert response is not None
    assert response.status == "OK"
    assert response.result is not None
    assert response.result.point.x == pytest.approx(127.036)
    assert response.x_extension is not None
    assert response.x_extension.source == "api_vworld"


@pytest.mark.asyncio
async def test_external_geocode_client_maps_juso_search_and_coord_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if "addrLinkApi" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "results": {
                        "juso": [
                            {
                                "roadAddr": "서울특별시 강남구 테헤란로 152",
                                "admCd": "1168010100",
                                "rnMgtSn": "116803122001",
                                "udrtYn": "0",
                                "buldMnnm": "152",
                                "buldSlno": "0",
                                "bdMgtSn": "1168010100108250000028924",
                                "zipNo": "06236",
                            }
                        ]
                    }
                },
            )
        assert request.url.params["admCd"] == "1168010100"
        assert request.url.params["rnMgtSn"] == "116803122001"
        assert request.url.params["udrtYn"] == "0"
        assert request.url.params["buldMnnm"] == "152"
        assert request.url.params["buldSlno"] == "0"
        return httpx.Response(
            200,
            json={"results": {"juso": [{"entX": "127.036", "entY": "37.501"}]}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ExternalGeocodeClient(
            Settings(
                juso_api_key=SecretStr("juso-key"),
                juso_search_url="https://business.juso.go.kr/addrlink/addrLinkApi.do",
                juso_coord_url="https://business.juso.go.kr/addrlink/addrCoordApi.do",
            ),
            http_client=http_client,
        )
        response = await client.geocode(GeocodeInput(address="테헤란로 152"))

    assert response is not None
    assert response.x_extension is not None
    assert response.x_extension.source == "api_juso"
    assert response.x_extension.bd_mgt_sn == "1168010100108250000028924"
    assert response.x_extension.zip_no == "06236"


@pytest.mark.asyncio
async def test_external_geocode_client_skips_juso_coord_when_code_parts_are_missing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if "addrLinkApi" not in str(request.url):
            pytest.fail("coord API must not be called without admCd/rnMgtSn code parts")
        return httpx.Response(
            200,
            json={
                "results": {
                    "juso": [
                        {
                            "roadAddr": "서울특별시 강남구 테헤란로 152",
                            "buldMnnm": "152",
                            "buldSlno": "0",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ExternalGeocodeClient(
            Settings(
                juso_api_key=SecretStr("juso-key"),
                juso_search_url="https://business.juso.go.kr/addrlink/addrLinkApi.do",
                juso_coord_url="https://business.juso.go.kr/addrlink/addrCoordApi.do",
            ),
            http_client=http_client,
        )
        response = await client.geocode(GeocodeInput(address="테헤란로 152"))

    assert response is None
