from __future__ import annotations

import pytest

from kortravelgeo.core.geocoder import geocode
from kortravelgeo.core.protocols import SppnAreaLookup
from kortravelgeo.core.reverse_geocoder import reverse_geocode
from kortravelgeo.core.sppn import (
    format_national_point_number_from_5179,
    parse_national_point_number,
)
from kortravelgeo.dto.common import Point
from kortravelgeo.dto.geocode import GeocodeInput
from kortravelgeo.dto.reverse import ReverseInput


def test_parse_national_point_number_returns_epsg5179_cell_center() -> None:
    parsed = parse_national_point_number("다사 6925 4045")

    assert parsed is not None
    assert parsed.compact == "다사69254045"
    assert parsed.point_5179.x == pytest.approx(969255)
    assert parsed.point_5179.y == pytest.approx(1940455)


def test_parse_national_point_number_rejects_embedded_address_text() -> None:
    assert parse_national_point_number("세종시 다사 6925 4045 부근") is None
    assert parse_national_point_number("다사 692 4045") is None


def test_parse_national_point_number_rejects_outside_korea_grid_envelope() -> None:
    assert parse_national_point_number("가가 0000 0000") is None
    assert parse_national_point_number("하하 9999 9999") is None


def test_format_national_point_number_from_epsg5179_round_trips_cell() -> None:
    formatted = format_national_point_number_from_5179(Point(x=969258.1, y=1940457.9))

    assert formatted is not None
    assert formatted.text == "다사 6925 4045"
    assert formatted.point_5179.x == pytest.approx(969255)
    assert formatted.point_5179.y == pytest.approx(1940455)
    assert format_national_point_number_from_5179(Point(x=1, y=1)) is None


class _SppnGeocodeRepo:
    async def lookup_by_road(self, parts, *, region_hint=None):
        _ = region_hint
        return None

    async def lookup_by_jibun(self, parts, *, region_hint=None):
        _ = region_hint
        return None

    async def fuzzy_roads(self, parts, *, limit: int = 5, region_hint=None):
        _ = region_hint
        return []

    async def lookup_sppn_area(self, point_5179: Point) -> SppnAreaLookup | None:
        assert point_5179.x == pytest.approx(969255)
        return SppnAreaLookup(
            sig_cd="36110",
            makarea_id="17",
            makarea_nm="운주산",
            ntfc_yn="Y",
            ntfc_de="20231212",
            mvm_res_cd="11",
            source_file="구역의도형_전체분_세종특별자치시.zip:36110/TL_SPPN_MAKAREA.shp",
            source_yyyymm="202605",
            area_m2=10124000.0,
            point=Point(x=127.1, y=36.6),
        )

    async def project_sppn_point_4326(self, point_5179: Point) -> Point | None:
        _ = point_5179
        return Point(x=127.1, y=36.6)


async def test_geocode_enriches_national_point_number_with_makarea_context() -> None:
    response = await geocode(_SppnGeocodeRepo(), GeocodeInput(address="다사 6925 4045"))

    assert response.status == "OK"
    assert response.result is not None
    assert response.result.point.x == pytest.approx(127.1)
    assert response.x_extension is not None
    assert response.x_extension.national_point_number == "다사 6925 4045"
    assert response.x_extension.sppn_makarea is not None
    assert response.x_extension.sppn_makarea.makarea_nm == "운주산"


class _SppnNoMakareaGeocodeRepo(_SppnGeocodeRepo):
    async def lookup_sppn_area(self, point_5179: Point) -> SppnAreaLookup | None:
        _ = point_5179
        return None

    async def project_sppn_point_4326(self, point_5179: Point) -> Point | None:
        assert point_5179.x == pytest.approx(969255)
        return Point(x=127.101, y=36.601)


async def test_geocode_returns_calculated_national_point_without_makarea_gate() -> None:
    response = await geocode(_SppnNoMakareaGeocodeRepo(), GeocodeInput(address="다사 6925 4045"))

    assert response.status == "OK"
    assert response.result is not None
    assert response.result.point == Point(x=127.101, y=36.601)
    assert response.x_extension is not None
    assert response.x_extension.national_point_number == "다사 6925 4045"
    assert response.x_extension.sppn_makarea is None


class _SppnReverseRepo:
    async def nearest(
        self,
        point: Point,
        *,
        crs: str,
        address_type: str,
        radius_m: int,
        limit: int = 5,
        region_hint=None,
    ):
        _ = (point, crs, address_type, radius_m, limit, region_hint)
        return []

    async def sppn_areas(
        self,
        point: Point,
        *,
        crs: str,
        limit: int = 5,
    ) -> list[SppnAreaLookup]:
        _ = (point, crs, limit)
        return [
            SppnAreaLookup(
                sig_cd="36110",
                makarea_id="17",
                makarea_nm="운주산",
                area_m2=10124000.0,
            )
        ]

    async def project_reverse_point_5179(self, point: Point, *, crs: str) -> Point | None:
        _ = (point, crs)
        return Point(x=969255, y=1940455)


async def test_reverse_returns_ok_when_only_sppn_area_matches() -> None:
    response = await reverse_geocode(
        _SppnReverseRepo(),
        ReverseInput(point=Point(x=127.1, y=36.6)),
    )

    assert response.status == "OK"
    assert response.result == ()
    assert response.x_extension is not None
    assert response.x_extension.national_point_number == "다사 6925 4045"
    assert response.x_extension.sppn_makarea[0].makarea_id == "17"


class _SppnNoMakareaReverseRepo(_SppnReverseRepo):
    async def sppn_areas(
        self,
        point: Point,
        *,
        crs: str,
        limit: int = 5,
    ) -> list[SppnAreaLookup]:
        _ = (point, crs, limit)
        return []


async def test_reverse_returns_national_point_number_without_makarea_context() -> None:
    response = await reverse_geocode(
        _SppnNoMakareaReverseRepo(),
        ReverseInput(point=Point(x=127.1, y=36.6)),
    )

    assert response.status == "OK"
    assert response.result == ()
    assert response.x_extension is not None
    assert response.x_extension.national_point_number == "다사 6925 4045"
    assert response.x_extension.sppn_makarea == ()
