from __future__ import annotations

from typing import Any

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.confidence import SPPN_GRID_CONFIDENCE
from kortravelgeo.core.v2 import (
    geocode_v2_from_geometry_lookups,
    geocode_v2_from_v1,
    reverse_v2_from_v1,
    search_v2_from_v1,
)
from kortravelgeo.dto.address import AddressStructure, RefinedAddress
from kortravelgeo.dto.common import Point, ServiceMeta
from kortravelgeo.dto.geocode import (
    GeocodeExtension,
    GeocodeInput,
    GeocodeResponse,
    GeocodeResult,
    SppnMakareaContext,
)
from kortravelgeo.dto.reverse import (
    ReverseExtension,
    ReverseInput,
    ReverseResponse,
    ReverseResultItem,
)
from kortravelgeo.dto.search import SearchInput, SearchResponse, SearchResultItem
from kortravelgeo.dto.v2 import (
    BBoxV2,
    CandidateV2,
    GeocodeV2Input,
    GeocodeV2Response,
    GeometryV2,
    RegionsWithinRadiusInput,
    RegionsWithinRadiusResponse,
    RegionV2,
    RegionWithinRadiusItem,
    ReverseV2Input,
    SearchV2Input,
    SearchV2Response,
)
from kortravelgeo.exceptions import InvalidAddressError


def _v1_geocode_response(inp: GeocodeInput) -> GeocodeResponse:
    return GeocodeResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="geocode"),
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
async def test_async_client_geocode_can_add_geometry_without_replacing_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kortravelgeo.core.protocols import GeometryLookup
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_geocode(self: AsyncAddressClient, address: str, **_: Any) -> GeocodeResponse:
        return _v1_geocode_response(GeocodeInput(address=address))

    async def fake_building_geometry(self: GeometryRepository, **kwargs: Any) -> GeometryLookup:
        assert kwargs["bd_mgt_sn"] == "1168010100108250000028924"
        assert kwargs["rncode_full"] == "116803122001"
        return GeometryLookup(
            kind="building",
            geometry=GeometryV2(
                kind="building",
                source_table="tl_spbd_buld_polygon",
                geojson={
                    "type": "MultiPolygon",
                    "coordinates": [[[[127.0, 37.0], [127.1, 37.0], [127.1, 37.1], [127.0, 37.0]]]],
                },
            ),
            bbox=BBoxV2(min_lon=127.0, min_lat=37.0, max_lon=127.1, max_lat=37.1),
        )

    monkeypatch.setattr(AsyncAddressClient, "_geocode_v1", fake_geocode)
    monkeypatch.setattr(GeometryRepository, "building_geometry", fake_building_geometry)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.geocode(
        query="서울특별시 강남구 테헤란로 152",
        include_geometry=True,
    )

    candidate = response.candidates[0]
    assert candidate.point == Point(x=127.036, y=37.501)
    assert candidate.geometry is not None
    assert candidate.geometry.kind == "building"
    assert candidate.bbox is not None


@pytest.mark.asyncio
async def test_async_client_geocode_promotes_region_only_input_to_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_geocode(self: AsyncAddressClient, address: str, **_: Any) -> GeocodeResponse:
        raise InvalidAddressError("address number could not be parsed")

    async def fake_road_geometries(self: GeometryRepository, *_: Any, **__: Any) -> list[Any]:
        return []

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
    monkeypatch.setattr(GeometryRepository, "road_geometries", fake_road_geometries)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.geocode(road_address="수지구")

    assert response.status == "OK"
    assert response.candidates[0].match_kind == "region"
    assert response.candidates[0].region is not None
    assert response.candidates[0].region.sig_cd == "41465"


@pytest.mark.asyncio
async def test_async_client_geocode_promotes_road_name_only_to_line_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kortravelgeo.core.protocols import GeometryLookup
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_geocode(self: AsyncAddressClient, address: str, **_: Any) -> GeocodeResponse:
        raise InvalidAddressError("address number could not be parsed")

    async def fake_road_geometries(
        self: GeometryRepository,
        query: str,
        **_: Any,
    ) -> list[GeometryLookup]:
        assert query == "성복1로"
        return [
            GeometryLookup(
                kind="road",
                title="경기도 용인시 수지구 성복1로",
                road_name="성복1로",
                rncode_full="414653205009",
                sig_cd="41465",
                sido="경기도",
                sigungu="용인시 수지구",
                point=Point(x=127.0743, y=37.3134),
                score=1.0,
                geometry=GeometryV2(
                    kind="road",
                    source_table="tl_sprd_manage",
                    geojson={
                        "type": "MultiLineString",
                        "coordinates": [[[127.07, 37.31], [127.08, 37.32]]],
                    },
                ),
                bbox=BBoxV2(min_lon=127.07, min_lat=37.31, max_lon=127.08, max_lat=37.32),
            )
        ]

    async def fail_search(self: AsyncAddressClient, **_: Any) -> SearchV2Response:
        raise AssertionError("road geometry candidates should be tried before district search")

    monkeypatch.setattr(AsyncAddressClient, "_geocode_v1", fake_geocode)
    monkeypatch.setattr(AsyncAddressClient, "search", fail_search)
    monkeypatch.setattr(GeometryRepository, "road_geometries", fake_road_geometries)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.geocode(road_address="성복1로", include_geometry=True)

    candidate = response.candidates[0]
    assert candidate.point == Point(x=127.0743, y=37.3134)
    assert candidate.geometry is not None
    assert candidate.geometry.kind == "road"
    assert candidate.address is not None
    assert candidate.address.road_name == "성복1로"


@pytest.mark.asyncio
async def test_async_client_geocode_merges_local_primary_and_supplemental_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kortravelgeo.core.protocols import GeometryLookup
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_geocode(self: AsyncAddressClient, address: str, **_: Any) -> GeocodeResponse:
        assert address == "테헤란로"
        return _v1_geocode_response(GeocodeInput(address=address))

    async def fake_road_geometries(
        self: GeometryRepository,
        query: str,
        **kwargs: Any,
    ) -> list[GeometryLookup]:
        assert query == "테헤란로"
        assert kwargs["limit"] == 3
        return [
            GeometryLookup(
                kind="building",
                title="서울특별시 강남구 테헤란로 152",
                rncode_full="116803122001",
                bd_mgt_sn="1168010100108250000028924",
                point=Point(x=127.036, y=37.501),
                geometry=GeometryV2(
                    kind="building",
                    source_table="tl_spbd_buld_polygon",
                    geojson={"type": "MultiPolygon", "coordinates": []},
                ),
            ),
            GeometryLookup(
                kind="road",
                title="서울특별시 강남구 테헤란로",
                road_name="테헤란로",
                rncode_full="116803122000",
                sig_cd="11680",
                point=Point(x=127.04, y=37.5),
                score=0.91,
                geometry=GeometryV2(
                    kind="road",
                    source_table="tl_sprd_manage",
                    geojson={"type": "MultiLineString", "coordinates": []},
                ),
            ),
        ]

    monkeypatch.setattr(AsyncAddressClient, "_geocode_v1", fake_geocode)
    monkeypatch.setattr(GeometryRepository, "road_geometries", fake_road_geometries)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.geocode(query="테헤란로", limit=3)

    assert response.status == "OK"
    assert [candidate.match_kind for candidate in response.candidates] == ["road", "road"]
    assert response.candidates[0].address is not None
    assert response.candidates[0].address.full == "서울특별시 강남구 테헤란로 152"
    assert response.candidates[1].address is not None
    assert response.candidates[1].address.road_name == "테헤란로"
    assert response.candidates[1].metadata["rncode_full"] == "116803122000"


@pytest.mark.asyncio
async def test_v2_geocode_route_uses_client_dependency() -> None:
    class FakeClient:
        async def geocode(self, **kwargs: Any) -> GeocodeV2Response:
            assert kwargs["bbox"] is not None
            assert kwargs["include_geometry"] is True
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
                "include_geometry": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OK"
    assert body["input"]["bbox"]["min_lon"] == pytest.approx(127.0)
    assert body["candidates"][0]["match_kind"] == "road"


@pytest.mark.asyncio
async def test_async_client_regions_within_radius_wraps_geometry_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_regions_within_radius(
        self: GeometryRepository,
        **kwargs: Any,
    ) -> dict[str, tuple[RegionWithinRadiusItem, ...]]:
        assert kwargs == {
            "lon": 126.978,
            "lat": 37.5665,
            "radius_km": 3.0,
            "levels": ("sigungu", "emd"),
        }
        return {
            "sigungu": (
                RegionWithinRadiusItem(
                    code="11110",
                    name="종로구",
                    relation="contains",
                ),
                RegionWithinRadiusItem(
                    code="11140",
                    name="중구",
                    relation="overlaps",
                ),
            ),
            "emd": (
                RegionWithinRadiusItem(
                    code="11110119",
                    name="세종로",
                    relation="contains",
                ),
            ),
        }

    monkeypatch.setattr(GeometryRepository, "regions_within_radius", fake_regions_within_radius)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.regions_within_radius(
        lon=126.978,
        lat=37.5665,
        radius_km=3.0,
        levels=("sigungu", "emd"),
    )

    assert response.center.lon == pytest.approx(126.978)
    assert response.radius_km == pytest.approx(3.0)
    assert [item.code for item in response.sigungu] == ["11110", "11140"]
    assert response.sigungu[0].relation == "contains"
    assert response.emd[0].code == "11110119"
    assert response.sido == ()


@pytest.mark.asyncio
async def test_v2_regions_within_radius_route_uses_client_dependency() -> None:
    class FakeClient:
        async def regions_within_radius(self, **kwargs: Any) -> RegionsWithinRadiusResponse:
            assert kwargs == {
                "lon": 126.978,
                "lat": 37.5665,
                "radius_km": 3.0,
                "levels": ("sigungu",),
            }
            return RegionsWithinRadiusResponse(
                center={"lon": kwargs["lon"], "lat": kwargs["lat"]},
                radius_km=kwargs["radius_km"],
                sigungu=(
                    RegionWithinRadiusItem(
                        code="11110",
                        name="종로구",
                        relation="contains",
                    ),
                ),
            )

    app = create_app()
    app.dependency_overrides[get_client] = lambda: FakeClient()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(
            "/v2/regions/within-radius",
            json={
                "lon": 126.978,
                "lat": 37.5665,
                "radius_km": 3.0,
                "levels": ["sigungu", "sigungu"],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["center"] == {"lon": 126.978, "lat": 37.5665}
    assert body["radius_km"] == pytest.approx(3.0)
    assert body["sigungu"] == [
        {"code": "11110", "name": "종로구", "relation": "contains"}
    ]
    assert body["emd"] == []


def test_async_client_has_unsuffixed_v2_python_api() -> None:
    assert hasattr(AsyncAddressClient, "geocode")
    assert hasattr(AsyncAddressClient, "reverse")
    assert hasattr(AsyncAddressClient, "search")
    assert hasattr(AsyncAddressClient, "regions_within_radius")
    assert not hasattr(AsyncAddressClient, "geocode_v2")
    assert not hasattr(AsyncAddressClient, "reverse_v2")
    assert not hasattr(AsyncAddressClient, "search_v2")
    assert not hasattr(AsyncAddressClient, "regions_within_radius_v2")
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


def test_geocode_v2_geometry_candidates_dedupe_before_limit() -> None:
    from kortravelgeo.core.protocols import GeometryLookup

    inp = GeocodeV2Input(query="성복1로", limit=2)
    rows = [
        GeometryLookup(
            kind="road",
            title="경기도 용인시 수지구 성복1로",
            road_name="성복1로",
            rncode_full="414653205009",
            point=Point(x=127.0743, y=37.3134),
            geometry=GeometryV2(
                kind="road",
                source_table="tl_sprd_manage",
                geojson={"type": "MultiLineString", "coordinates": []},
            ),
        ),
        GeometryLookup(
            kind="road",
            title="경기도 용인시 수지구 성복1로",
            road_name="성복1로",
            rncode_full="414653205009",
            point=Point(x=127.0743, y=37.3134),
            geometry=GeometryV2(
                kind="road",
                source_table="tl_sprd_manage",
                geojson={"type": "MultiLineString", "coordinates": []},
            ),
        ),
        GeometryLookup(
            kind="road",
            title="경기도 용인시 수지구 성복2로",
            road_name="성복2로",
            rncode_full="414653205010",
            point=Point(x=127.076, y=37.315),
            geometry=GeometryV2(
                kind="road",
                source_table="tl_sprd_manage",
                geojson={"type": "MultiLineString", "coordinates": []},
            ),
        ),
    ]

    converted = geocode_v2_from_geometry_lookups(inp, rows)

    assert converted.status == "OK"
    road_names = [
        candidate.address.road_name for candidate in converted.candidates if candidate.address
    ]
    assert road_names == [
        "성복1로",
        "성복2로",
    ]


def test_regions_within_radius_input_defaults_and_dedupes_levels() -> None:
    defaulted = RegionsWithinRadiusInput(lon=126.978, lat=37.5665)
    explicit = RegionsWithinRadiusInput(
        lon=126.978,
        lat=37.5665,
        radius_km=5.0,
        levels=["sigungu", "emd", "sigungu"],
    )

    assert defaulted.radius_km == pytest.approx(3.0)
    assert defaulted.levels == ("sigungu", "emd")
    assert explicit.levels == ("sigungu", "emd")
    assert explicit.center.lon == pytest.approx(126.978)


def test_regions_within_radius_input_rejects_empty_levels() -> None:
    with pytest.raises(ValueError, match="levels must include"):
        RegionsWithinRadiusInput(lon=126.978, lat=37.5665, levels=[])


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


def test_geocode_v2_marks_sppn_precision_as_grid_cell() -> None:
    inp = GeocodeV2Input(query="다사 6925 4045")
    response = GeocodeResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="geocode"),
        status="OK",
        input=GeocodeInput(address="다사 6925 4045"),
        refined=RefinedAddress(text="국가지점번호 다사 6925 4045", structure=AddressStructure()),
        result=GeocodeResult(point=Point(x=127.1, y=36.6)),
        x_extension=GeocodeExtension(
            source="local",
            confidence=0.72,
            national_point_number="다사 6925 4045",
        ),
    )

    converted = geocode_v2_from_v1(inp, response)

    assert converted.candidates[0].match_kind == "sppn"
    assert converted.candidates[0].point_precision == "grid_cell"


def test_geocode_v2_collapses_v1_cache_source_to_local_source() -> None:
    inp = GeocodeV2Input(road_address="서울특별시 강남구 테헤란로 152")
    v1_response = _v1_geocode_response(GeocodeInput(address="서울특별시 강남구 테헤란로 152"))
    response = v1_response.model_copy(
        update={
            "x_extension": GeocodeExtension(
                source="cache",
                confidence=0.97,
            )
        }
    )

    assert geocode_v2_from_v1(inp, response).candidates[0].source == "local"


def test_v2_candidate_enum_accepts_current_and_planned_values_only() -> None:
    CandidateV2(confidence=1.0, match_kind="detail", point_precision="approximate")
    CandidateV2(confidence=1.0, match_kind="poi", point_precision="grid_cell")

    with pytest.raises(ValueError):
        CandidateV2(confidence=1.0, match_kind="postal")
    with pytest.raises(ValueError):
        CandidateV2(confidence=1.0, match_kind="category")
    with pytest.raises(ValueError):
        CandidateV2(confidence=1.0, match_kind="road", source="cache")


def test_search_v2_maps_place_results_to_poi_candidates() -> None:
    inp = SearchV2Input(query="카페", type="category", category_group_code="FD6")
    response = SearchResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="search"),
        status="OK",
        input=SearchInput(query="카페", type="place"),
        result=(
            SearchResultItem(
                type="place",
                title="근처 카페",
                point=Point(x=127.036, y=37.501),
                score=0.81,
            ),
        ),
        total=1,
    )

    converted = search_v2_from_v1(inp, response)

    assert converted.candidates[0].match_kind == "poi"
    assert converted.candidates[0].place is not None
    assert converted.candidates[0].place.name == "근처 카페"


def test_reverse_v2_promotes_distance_and_uses_distance_confidence() -> None:
    inp = ReverseInput(point=Point(x=127.036, y=37.501), radius_m=200)
    response = ReverseResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
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


def test_reverse_v2_promotes_sppn_extension_to_candidate() -> None:
    inp = ReverseInput(point=Point(x=127.1, y=36.6), radius_m=200)
    response = ReverseResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
        status="OK",
        input=inp,
        x_extension=ReverseExtension(
            national_point_number="다사 6925 4045",
            sppn_makarea=(
                SppnMakareaContext(
                    sig_cd="36110",
                    makarea_id="17",
                    makarea_nm="운주산",
                    source_yyyymm="202605",
                    area_m2=10124000.0,
                ),
            )
        ),
    )

    converted = reverse_v2_from_v1(
        inp=ReverseV2Input(lon=127.1, lat=36.6, radius_m=200),
        response=response,
    )

    assert converted.status == "OK"
    assert converted.candidates[0].match_kind == "sppn"
    assert converted.candidates[0].confidence == pytest.approx(SPPN_GRID_CONFIDENCE)
    assert converted.candidates[0].region is not None
    assert converted.candidates[0].region.sig_cd == "36110"
    assert converted.candidates[0].metadata["national_point_number"] == "다사 6925 4045"
    assert converted.candidates[0].metadata["makarea_nm"] == "운주산"


def test_reverse_v2_promotes_sppn_number_without_makarea_to_candidate() -> None:
    inp = ReverseInput(point=Point(x=127.1, y=36.6), radius_m=200)
    response = ReverseResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
        status="OK",
        input=inp,
        x_extension=ReverseExtension(national_point_number="다사 6925 4045"),
    )

    converted = reverse_v2_from_v1(
        inp=ReverseV2Input(lon=127.1, lat=36.6, radius_m=200),
        response=response,
    )

    assert converted.status == "OK"
    assert converted.candidates[0].match_kind == "sppn"
    assert converted.candidates[0].confidence == pytest.approx(SPPN_GRID_CONFIDENCE)
    assert converted.candidates[0].point == Point(x=127.1, y=36.6)
    assert converted.candidates[0].point_precision == "grid_cell"
    assert converted.candidates[0].metadata == {"national_point_number": "다사 6925 4045"}
