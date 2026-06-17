from __future__ import annotations

from typing import Any, Literal

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.reverse_geocoder import reverse_geocode as core_reverse_geocode
from kortravelgeo.core.searcher import search as core_search
from kortravelgeo.dto.common import Point
from kortravelgeo.dto.region import RegionHint
from kortravelgeo.dto.reverse import ReverseInput
from kortravelgeo.dto.search import SearchInput
from kortravelgeo.dto.v2 import GeocodeV2Input, ReverseV2Input, SearchV2Input

HttpMethod = Literal["get", "post"]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: GeocodeV2Input(query="왕산로 189-4", sig_cd="11680", bjd_cd="1123010700"),
        lambda: ReverseV2Input(
            lon=127.04416880226447,
            lat=37.579995940386155,
            sig_cd="11680",
            bjd_cd="1123010700",
        ),
        lambda: SearchV2Input(query="왕산로", sig_cd="11680", bjd_cd="1123010700"),
    ],
)
def test_t175_v2_inputs_reject_contradictory_region_hints(
    factory: Any,
) -> None:
    with pytest.raises(ValueError, match="bjd_cd must start with sig_cd"):
        factory()


@pytest.mark.parametrize(
    ("method", "path", "kwargs", "expected_shape", "expected_code"),
    [
        (
            "get",
            "/v1/address/geocode",
            {
                "params": {
                    "address": "왕산로 189-4",
                    "sig_cd": "11680",
                    "bjd_cd": "1123010700",
                }
            },
            "vworld",
            "INVALID_TYPE",
        ),
        (
            "get",
            "/v1/address/reverse",
            {
                "params": {
                    "x": 127.04416880226447,
                    "y": 37.579995940386155,
                    "sig_cd": "11680",
                    "bjd_cd": "1123010700",
                }
            },
            "vworld",
            "INVALID_TYPE",
        ),
        (
            "get",
            "/v1/address/search",
            {"params": {"query": "왕산로", "sig_cd": "11680", "bjd_cd": "1123010700"}},
            "legacy",
            "E0100",
        ),
        (
            "post",
            "/v2/geocode",
            {"json": {"query": "왕산로 189-4", "sig_cd": "11680", "bjd_cd": "1123010700"}},
            "v2",
            "E0100",
        ),
        (
            "post",
            "/v2/reverse",
            {
                "json": {
                    "lon": 127.04416880226447,
                    "lat": 37.579995940386155,
                    "sig_cd": "11680",
                    "bjd_cd": "1123010700",
                }
            },
            "v2",
            "E0100",
        ),
        (
            "post",
            "/v2/search",
            {"json": {"query": "왕산로", "sig_cd": "11680", "bjd_cd": "1123010700"}},
            "v2",
            "E0100",
        ),
    ],
)
@pytest.mark.asyncio
async def test_t175_public_api_rejects_contradictory_region_hints(
    method: HttpMethod,
    path: str,
    kwargs: dict[str, Any],
    expected_shape: Literal["v2", "vworld", "legacy"],
    expected_code: str,
) -> None:
    app = create_app()
    app.dependency_overrides[get_client] = lambda: AsyncAddressClient(
        engine=object()  # type: ignore[arg-type]
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await getattr(client, method)(path, **kwargs)

    assert response.status_code == 400
    payload = response.json()
    if expected_shape == "vworld":
        assert payload["response"]["status"] == "ERROR"
        assert payload["response"]["error"]["code"] == expected_code
        assert payload["response"]["error"]["text"] == "invalid request data"
    elif expected_shape == "v2":
        # v2 error envelope (ADR-060 §4)
        assert payload["status"] == "ERROR"
        assert payload["error"]["code"] == expected_code
        assert "bjd_cd" in response.text
    else:
        # legacy {response:{errorCode}} for non-vworld, non-v2 paths (e.g. /v1/address/search)
        assert payload["response"]["status"] == "ERROR"
        assert payload["response"]["errorCode"] == expected_code
        assert "bjd_cd" in response.text


class _FakeSearchRepo:
    last_region_hint: RegionHint | None = None

    async def search(
        self,
        _query: str,
        *,
        search_type: Literal["address", "place", "district", "road"],
        page: int,
        size: int,
        region_hint: RegionHint | None = None,
    ) -> tuple[list[Any], int]:
        assert search_type == "road"
        assert page == 1
        assert size == 10
        self.last_region_hint = region_hint
        return ([], 0)


class _FakeReverseRepo:
    last_region_hint: RegionHint | None = None

    async def nearest(
        self,
        _point: Point,
        *,
        crs: str,
        address_type: Literal["both", "road", "parcel"],
        radius_m: int,
        limit: int = 5,
        region_hint: RegionHint | None = None,
    ) -> list[Any]:
        assert crs == "EPSG:4326"
        assert address_type == "both"
        assert radius_m == 200
        assert limit == 5
        self.last_region_hint = region_hint
        return []

    async def sppn_areas(
        self,
        _point: Point,
        *,
        crs: str,
        limit: int = 5,
    ) -> list[Any]:
        assert crs == "EPSG:4326"
        assert limit == 5
        return []

    async def project_reverse_point_5179(self, _point: Point, *, crs: str) -> None:
        assert crs == "EPSG:4326"
        return None


@pytest.mark.asyncio
async def test_t175_core_search_and_reverse_forward_consistent_region_hint() -> None:
    hint = RegionHint(sig_cd="11230", bjd_cd="1123010700")
    search_repo = _FakeSearchRepo()
    reverse_repo = _FakeReverseRepo()

    search_response = await core_search(
        search_repo,
        SearchInput(query="왕산로", type="road"),
        region_hint=hint,
    )
    reverse_response = await core_reverse_geocode(
        reverse_repo,
        ReverseInput(point=Point(x=127.04416880226447, y=37.579995940386155)),
        region_hint=hint,
    )

    assert search_response.status == "NOT_FOUND"
    assert reverse_response.status == "NOT_FOUND"
    assert search_repo.last_region_hint == hint
    assert reverse_repo.last_region_hint == hint
