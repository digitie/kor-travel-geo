from __future__ import annotations

from typing import Any

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.confidence import SPPN_GRID_CONFIDENCE
from kortravelgeo.core.v2 import (
    geocode_v2_from_geometry_lookups,
    geocode_v2_from_v1,
    merge_geocode_v2_responses,
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
    AddressV2,
    BBoxV2,
    CandidateV2,
    GeocodeV2Input,
    GeocodeV2Response,
    GeometryV2,
    PointV2,
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
    assert candidate.point == PointV2(lon=127.036, lat=37.501)
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
                    point=PointV2(lon=127.0887, lat=37.3328),
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
    assert candidate.point == PointV2(lon=127.0743, lat=37.3134)
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


def test_merge_geocode_v2_responses_dedupes_same_building_across_differing_match_kind() -> None:
    # Regression guard for the reverse-geocode dedupe fix (T-176 follow-up, road-address
    # display): dedupe_candidates() gained an opt-in split_building_by_match_kind flag so
    # reverse's legitimate road+parcel-same-building pair survives dedup. Forward-geocode
    # merge must NOT opt in — _geocode_match_kind() returns "keyword" whenever
    # GeocodeV2Input.keyword is set regardless of the actual lookup surface, so a primary
    # candidate (match_kind="keyword") and a supplemental candidate (match_kind="road") for
    # the SAME building must still collapse to one, or a duplicate leaks into the response.
    inp = GeocodeV2Input(keyword="테헤란로", road_address="테헤란로 152", limit=10)
    same_building = AddressV2(type="road", full="서울특별시 강남구 테헤란로 152")
    primary = GeocodeV2Response(
        status="OK",
        input=inp,
        candidates=(
            CandidateV2(
                confidence=1.0,
                match_kind="keyword",
                address=same_building,
                metadata={"bd_mgt_sn": "1168010100108250000028924"},
            ),
        ),
    )
    supplemental = GeocodeV2Response(
        status="OK",
        input=inp,
        candidates=(
            CandidateV2(
                confidence=0.9,
                match_kind="road",
                address=same_building,
                metadata={"bd_mgt_sn": "1168010100108250000028924"},
            ),
        ),
    )

    merged = merge_geocode_v2_responses(inp, primary, supplemental)

    assert len(merged.candidates) == 1
    assert merged.candidates[0].match_kind == "keyword"


@pytest.mark.asyncio
async def test_async_client_geocode_keeps_primary_when_supplemental_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_geocode(self: AsyncAddressClient, address: str, **_: Any) -> GeocodeResponse:
        assert address == "테헤란로"
        return _v1_geocode_response(GeocodeInput(address=address))

    async def fail_road_geometries(self: GeometryRepository, *_: Any, **__: Any) -> list[Any]:
        raise RuntimeError("geometry repository unavailable")

    monkeypatch.setattr(AsyncAddressClient, "_geocode_v1", fake_geocode)
    monkeypatch.setattr(GeometryRepository, "road_geometries", fail_road_geometries)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.geocode(query="테헤란로", limit=3)

    assert response.status == "OK"
    assert len(response.candidates) == 1
    assert response.candidates[0].address is not None
    assert response.candidates[0].address.full == "서울특별시 강남구 테헤란로 152"


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
                        point=PointV2(lon=127.036, lat=37.501),
                    ),
                ),
            )

    app = create_app()
    app.dependency_overrides[get_client] = lambda: FakeClient()
    app.dependency_overrides[require_public_api_key] = lambda: None
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
                status="OK",
                input=RegionsWithinRadiusInput(
                    lon=kwargs["lon"],
                    lat=kwargs["lat"],
                    radius_km=kwargs["radius_km"],
                    levels=kwargs["levels"],
                ),
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
    app.dependency_overrides[require_public_api_key] = lambda: None
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


def test_v2_candidate_enum_accepts_only_emitted_values() -> None:
    # current emitted values are accepted.
    CandidateV2(confidence=1.0, match_kind="poi", point_precision="grid_cell")
    CandidateV2(confidence=1.0, match_kind="region", point_precision="centroid")

    # reserved/unemitted values were removed from the published enums (ADR-060 §2, T-268).
    with pytest.raises(ValueError):
        CandidateV2(confidence=1.0, match_kind="detail")
    for reserved_precision in ("exact", "interpolated", "approximate"):
        with pytest.raises(ValueError):
            CandidateV2(confidence=1.0, match_kind="poi", point_precision=reserved_precision)

    # previously-removed values stay rejected.
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
    assert converted.candidates[0].point == PointV2(lon=127.1, lat=36.6)
    assert converted.candidates[0].point_precision == "grid_cell"
    assert converted.candidates[0].metadata == {"national_point_number": "다사 6925 4045"}


# --- T-105/§5 (#308): include_geometry symmetry on reverse/search (ADR-060) -----------------


def _district_search_v1_response(
    query: str,
    *,
    region_code: str = "41465",
    title: str = "용인시 수지구",
) -> SearchResponse:
    # map_region_search() puts the resolved region code in level4LC (2-digit 시도, 5-digit
    # 시군구, 8/10-digit 법정동); _region_from_structure reads it into RegionV2.
    return SearchResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="search"),
        status="OK",
        input=SearchInput(query=query),
        result=(
            SearchResultItem(
                type="district",
                title=title,
                structure=AddressStructure(
                    level1="경기도", level2="용인시 수지구", level4LC=region_code
                ),
                point=Point(x=127.0887, y=37.3328),
                score=0.95,
            ),
        ),
        total=1,
    )


def _fake_region_geometry_recorder(
    queried: list[dict[str, object]],
) -> Any:
    from kortravelgeo.core.protocols import GeometryLookup

    async def fake_region_geometry(self: Any, **kwargs: Any) -> GeometryLookup:
        queried.append(kwargs)
        return GeometryLookup(
            kind="region",
            geometry=GeometryV2(
                kind="region",
                source_table="tl_scco_sig",
                geojson={
                    "type": "MultiPolygon",
                    "coordinates": [[[[127.0, 37.0], [127.1, 37.0], [127.1, 37.1], [127.0, 37.0]]]],
                },
            ),
            bbox=BBoxV2(min_lon=127.0, min_lat=37.0, max_lon=127.1, max_lat=37.1),
        )

    return fake_region_geometry


@pytest.mark.asyncio
async def test_search_sigungu_district_include_geometry_enriches_with_resolved_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_search_v1(self: AsyncAddressClient, query: str, **_: Any) -> SearchResponse:
        return _district_search_v1_response(query, region_code="41465")  # 5-digit 시군구

    queried: list[dict[str, object]] = []
    monkeypatch.setattr(AsyncAddressClient, "_search_v1", fake_search_v1)
    monkeypatch.setattr(
        GeometryRepository, "region_geometry", _fake_region_geometry_recorder(queried)
    )
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.search(query="수지구", type="district", include_geometry=True)

    candidate = response.candidates[0]
    assert candidate.match_kind == "region"
    assert candidate.region is not None and candidate.region.sig_cd == "41465"
    assert candidate.geometry is not None and candidate.geometry.kind == "region"
    assert candidate.bbox is not None
    # rigorous: the lookup uses the resolved region code, not a blind call.
    assert queried == [{"sig_cd": "41465", "bjd_cd": None}]


@pytest.mark.asyncio
async def test_search_sido_district_include_geometry_resolves_via_ctprvn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 시도(2-digit ctprvn) district candidates must also enrich (#317 review): the 2-digit code
    # is preserved as sig_cd and region_geometry resolves it through the ctprvn query.
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_search_v1(self: AsyncAddressClient, query: str, **_: Any) -> SearchResponse:
        return _district_search_v1_response(query, region_code="41", title="경기도")

    queried: list[dict[str, object]] = []
    monkeypatch.setattr(AsyncAddressClient, "_search_v1", fake_search_v1)
    monkeypatch.setattr(
        GeometryRepository, "region_geometry", _fake_region_geometry_recorder(queried)
    )
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.search(query="경기도", type="district", include_geometry=True)

    candidate = response.candidates[0]
    assert candidate.region is not None and candidate.region.sig_cd == "41"
    assert candidate.geometry is not None and candidate.geometry.kind == "region"
    assert queried == [{"sig_cd": "41", "bjd_cd": None}]


@pytest.mark.asyncio
async def test_search_road_candidate_geometry_is_null_pending_key_preservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #317 review: search road/address candidates lose bd_mgt_sn/rncode_full/bjd_cd/detail in the
    # v1->v2 conversion (metadata={"score"} only), so building_geometry short-circuits to None and
    # include_geometry yields null today. Pin that so docs and behaviour stay honest.
    async def fake_search_v1(self: AsyncAddressClient, query: str, **_: Any) -> SearchResponse:
        return SearchResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="search"),
            status="OK",
            input=SearchInput(query=query),
            result=(
                SearchResultItem(
                    type="road",
                    title="테헤란로",
                    address="서울특별시 강남구 테헤란로",
                    structure=AddressStructure(level1="서울특별시", level2="강남구"),
                    point=Point(x=127.036, y=37.501),
                    score=0.9,
                ),
            ),
            total=1,
        )

    monkeypatch.setattr(AsyncAddressClient, "_search_v1", fake_search_v1)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.search(query="테헤란로", type="road", include_geometry=True)

    candidate = response.candidates[0]
    assert candidate.match_kind != "region"
    assert candidate.geometry is None


@pytest.mark.asyncio
async def test_search_without_include_geometry_does_not_query_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kortravelgeo.infra.geometry_repo import GeometryRepository

    async def fake_search_v1(self: AsyncAddressClient, query: str, **_: Any) -> SearchResponse:
        return _district_search_v1_response(query)

    async def forbidden(self: GeometryRepository, **_: Any) -> None:
        raise AssertionError("geometry must not be queried when include_geometry is false")

    monkeypatch.setattr(AsyncAddressClient, "_search_v1", fake_search_v1)
    monkeypatch.setattr(GeometryRepository, "region_geometry", forbidden)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.search(query="수지구", type="district")

    assert response.input.include_geometry is False
    assert response.candidates[0].geometry is None


@pytest.mark.asyncio
async def test_reverse_accepts_include_geometry_symmetric_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_reverse_v1(
        self: AsyncAddressClient,
        lon: float,
        lat: float,
        **_: Any,
    ) -> ReverseResponse:
        return ReverseResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
            status="OK",
            input=ReverseInput(point=Point(x=lon, y=lat), radius_m=200),
            result=(
                ReverseResultItem(
                    type="road",
                    text="서울특별시 강남구 테헤란로 152",
                    structure=AddressStructure(level1="서울특별시", level2="강남구"),
                    point=Point(x=lon, y=lat),
                    distance_m=12.0,
                ),
            ),
        )

    monkeypatch.setattr(AsyncAddressClient, "_reverse_geocode_v1", fake_reverse_v1)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]

    response = await client.reverse(127.036, 37.501, include_geometry=True)

    # include_geometry is accepted symmetrically (ADR-060 §5). reverse road/parcel candidates
    # carry no building keys, so geometry stays None today (documented; building_geometry
    # short-circuits before any DB access).
    assert response.input.include_geometry is True
    assert response.candidates[0].geometry is None


def test_v2_reverse_search_inputs_publish_include_geometry() -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    for path in ("/v2/reverse", "/v2/search"):
        ref = schema["paths"][path]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        name = ref.rsplit("/", maxsplit=1)[-1]
        assert "include_geometry" in components[name]["properties"], name
        # additive optional field -> not required.
        assert "include_geometry" not in components[name].get("required", [])
