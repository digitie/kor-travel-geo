from __future__ import annotations

from typing import Any

import httpx
import pytest

from kraddr.geo.api.app import create_app
from kraddr.geo.api.deps import get_client
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.core.v2 import geocode_v2_from_v1, reverse_v2_from_v1
from kraddr.geo.dto.address import AddressStructure, RefinedAddress
from kraddr.geo.dto.common import Point, ServiceMeta
from kraddr.geo.dto.geocode import GeocodeExtension, GeocodeInput, GeocodeResponse, GeocodeResult
from kraddr.geo.dto.reverse import ReverseInput, ReverseResponse, ReverseResultItem
from kraddr.geo.dto.v2 import (
    CandidateV2,
    GeocodeV2Input,
    GeocodeV2Response,
    RegionV2,
    ReverseV2Input,
    SearchV2Input,
    SearchV2Response,
)
from kraddr.geo.exceptions import InvalidAddressError


def _v1_geocode_response(inp: GeocodeInput) -> GeocodeResponse:
    return GeocodeResponse(
        service=ServiceMeta(name="kraddr-geo", operation="geocode"),
        status="OK",
        input=inp,
        refined=RefinedAddress(
            text="서울특별시 강남구 테헤란로 152",
            structure=AddressStructure(
                level1="서울특별시",
                level2="강남구",
                level4L="역삼동",
                level4LC="1168010100",
                level5="테헤란로",
            ),
        ),
        result=GeocodeResult(point=Point(x=127.036, y=37.501)),
        x_extension=GeocodeExtension(
            source="local",
            confidence=0.97,
            bd_mgt_sn="1168010100108250000028924",
            rncode_full="116803122001",
            bjd_cd="1168010100",
            zip_no="06236",
            zip_source="building_bsi_zon_no",
        ),
    )


@pytest.mark.asyncio
async def test_async_client_geocode_wraps_internal_v1_geocode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_geocode(self: AsyncAddressClient, address: str, **_: Any) -> GeocodeResponse:
        return _v1_geocode_response(GeocodeInput(address=address))

    monkeypatch.setattr(AsyncAddressClient, "_geocode_v1", fake_geocode)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.geocode(query="서울특별시 강남구 테헤란로 152", sig_cd="11680")

    assert response.status == "OK"
    assert response.region_hint_applied is not None
    assert response.candidates[0].source == "local"
    assert response.candidates[0].address is not None
    assert response.candidates[0].address.road_name_code == "116803122001"
    assert response.candidates[0].region is not None
    assert response.candidates[0].region.sig_cd == "11680"


@pytest.mark.asyncio
async def test_async_client_geocode_promotes_region_only_input_to_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_geocode(self: AsyncAddressClient, address: str, **_: Any) -> GeocodeResponse:
        raise InvalidAddressError("address number could not be parsed")

    async def fake_search(self: AsyncAddressClient, **kwargs: Any) -> SearchV2Response:
        assert kwargs["query"] == "수지구"
        assert kwargs["type"] == "district"
        return SearchV2Response(
            status="OK",
            input=SearchV2Input(query="수지구", type="district"),
            candidates=(
                CandidateV2(
                    confidence=0.95,
                    match_kind="region",
                    point=Point(x=127.0887, y=37.3328),
                    region=RegionV2(sig_cd="41465", sido="경기도", sigungu="용인시 수지구"),
                ),
            ),
            total=1,
        )

    monkeypatch.setattr(AsyncAddressClient, "_geocode_v1", fake_geocode)
    monkeypatch.setattr(AsyncAddressClient, "search", fake_search)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.geocode(road_address="수지구")

    assert response.status == "OK"
    assert response.candidates[0].match_kind == "region"
    assert response.candidates[0].region is not None
    assert response.candidates[0].region.sig_cd == "41465"


@pytest.mark.asyncio
async def test_v2_geocode_route_uses_client_dependency() -> None:
    class FakeClient:
        async def geocode(self, **kwargs: Any) -> GeocodeV2Response:
            assert kwargs["bbox"] is not None
            inp = GeocodeV2Input(query=kwargs["query"], bbox=kwargs["bbox"])
            return GeocodeV2Response(
                status="OK",
                input=inp,
                candidates=(
                    CandidateV2(
                        confidence=0.9,
                        match_kind="road",
                        point=Point(x=127.036, y=37.501),
                    ),
                ),
            )

    app = create_app()
    app.dependency_overrides[get_client] = lambda: FakeClient()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(
            "/v2/geocode",
            json={
                "query": "테헤란로 152",
                "bbox": {
                    "min_lon": 127.0,
                    "min_lat": 37.4,
                    "max_lon": 127.1,
                    "max_lat": 37.6,
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["input"]["bbox"]["min_lon"] == pytest.approx(127.0)
    assert body["candidates"][0]["match_kind"] == "road"


def test_async_client_has_unsuffixed_v2_python_api() -> None:
    assert hasattr(AsyncAddressClient, "geocode")
    assert hasattr(AsyncAddressClient, "reverse")
    assert hasattr(AsyncAddressClient, "search")
    assert not hasattr(AsyncAddressClient, "geocode_v2")
    assert not hasattr(AsyncAddressClient, "reverse_v2")
    assert not hasattr(AsyncAddressClient, "search_v2")
    assert not hasattr(AsyncAddressClient, "reverse_geocode")


def test_geocode_v2_input_requires_query_surface() -> None:
    with pytest.raises(ValueError, match="one of query"):
        GeocodeV2Input()


def test_v2_input_preserves_bbox() -> None:
    geocode = GeocodeV2Input(
        query="테헤란로 152",
        bbox={"min_lon": 127.0, "min_lat": 37.4, "max_lon": 127.1, "max_lat": 37.6},
    )
    search = SearchV2Input(
        query="테헤란로",
        bbox={"min_lon": 127.0, "min_lat": 37.4, "max_lon": 127.1, "max_lat": 37.6},
    )

    assert geocode.bbox is not None
    assert geocode.bbox.min_lon == pytest.approx(127.0)
    assert search.bbox is not None
    assert search.bbox.max_lat == pytest.approx(37.6)


def test_geocode_v2_maps_external_provider_sources() -> None:
    inp = GeocodeV2Input(road_address="서울특별시 중구 세종대로 110", fallback="api")
    response = _v1_geocode_response(
        GeocodeInput(address="서울특별시 중구 세종대로 110", fallback="api")
    ).model_copy(
        update={
            "x_extension": GeocodeExtension(
                source="api_vworld",
                confidence=0.7,
            )
        }
    )

    assert geocode_v2_from_v1(inp, response).candidates[0].source == "vworld"


def test_reverse_v2_promotes_distance_and_uses_distance_confidence() -> None:
    inp = ReverseInput(point=Point(x=127.036, y=37.501), radius_m=200)
    response = ReverseResponse(
        service=ServiceMeta(name="kraddr-geo", operation="reverse_geocode"),
        status="OK",
        input=inp,
        result=(
            ReverseResultItem(
                type="road",
                text="서울특별시 강남구 테헤란로 152",
                structure=AddressStructure(level1="서울특별시", level2="강남구"),
                point=Point(x=127.036, y=37.501),
                distance_m=50.0,
            ),
        ),
    )

    converted_input = ReverseV2Input(
        lon=127.036,
        lat=37.501,
        radius_m=200,
    )
    converted = reverse_v2_from_v1(inp=converted_input, response=response)

    assert converted.input is converted_input
    assert converted.candidates[0].distance_m == pytest.approx(50.0)
    assert converted.candidates[0].confidence == pytest.approx(0.75)
