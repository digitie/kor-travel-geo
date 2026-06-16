from __future__ import annotations

from typing import Any

import pytest

from kortravelgeo.core.reverse_geocoder import reverse_geocode
from kortravelgeo.core.v2 import reverse_v2_from_v1
from kortravelgeo.dto.address import AddressStructure
from kortravelgeo.dto.common import Point, ServiceMeta
from kortravelgeo.dto.reverse import ReverseInput, ReverseResponse, ReverseResultItem
from kortravelgeo.dto.v2 import ReverseV2Input
from kortravelgeo.infra import reverse_repo
from kortravelgeo.infra.reverse_repo import ReverseRepository


def _reverse_row(
    bd_mgt_sn: str,
    *,
    distance_m: float,
    pt_source: str = "entrance",
) -> dict[str, Any]:
    return {
        "bd_mgt_sn": bd_mgt_sn,
        "rncode_full": "112303005001",
        "road_nm": "왕산로",
        "buld_mnnm": 189,
        "buld_slno": 4,
        "buld_se_cd": "0",
        "buld_nm": None,
        "bjd_cd": "1123010700",
        "adm_cd": "1123071000",
        "adm_kor_nm": "청량리동",
        "mntn_yn": "0",
        "lnbr_mnnm": 819,
        "lnbr_slno": 1,
        "zip_no": "02559",
        "si_nm": "서울특별시",
        "sgg_nm": "동대문구",
        "emd_nm": "청량리동",
        "li_nm": None,
        "pnu": "1123010700108190001",
        "pt_source": pt_source,
        "lon": 127.044,
        "lat": 37.58,
        "distance_m": distance_m,
    }


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.params: dict[str, Any] | None = None

    async def execute(self, statement: object, params: dict[str, Any]) -> _FakeResult:
        self.params = dict(params)
        return _FakeResult(self._rows)


class _FakeConnect:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _FakeEngine:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.conn = _FakeConn(rows)

    def connect(self) -> _FakeConnect:
        return _FakeConnect(self.conn)


def test_t176_reverse_nearest_sql_defines_inclusive_radius_and_tie_breaks() -> None:
    sql = str(reverse_repo._NEAREST_SQL)

    assert "knn_candidates AS MATERIALIZED" in sql
    assert "WHERE distance_m <= :radius_m" in sql
    assert "ORDER BY t.pt_5179 <-> p.geom" in sql
    assert "distance_m ASC" in sql
    assert "CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END" in sql
    assert "bd_mgt_sn ASC" in sql
    assert "rncode_full ASC" in sql
    assert "bjd_cd ASC" in sql


@pytest.mark.asyncio
async def test_t176_reverse_both_fans_out_after_base_row_limit() -> None:
    engine = _FakeEngine([_reverse_row("1123010700108190001000001", distance_m=12.5)])
    repo = ReverseRepository(engine)  # type: ignore[arg-type]

    rows = await repo.nearest(
        Point(x=127.044, y=37.58),
        crs="EPSG:4326",
        address_type="both",
        radius_m=200,
        limit=1,
    )

    assert engine.conn.params is not None
    assert engine.conn.params["limit"] == 1
    assert [row.address_type for row in rows] == ["road", "parcel"]
    assert [row.distance_m for row in rows] == [pytest.approx(12.5), pytest.approx(12.5)]
    assert "왕산로 189-4" in rows[0].text
    assert "청량리동 819-1" in rows[1].text


class _ContextOnlyReverseRepo:
    def __init__(self, projected_point: Point | None) -> None:
        self.projected_point = projected_point

    async def nearest(self, *_args: object, **_kwargs: object) -> list[Any]:
        return []

    async def sppn_areas(self, *_args: object, **_kwargs: object) -> list[Any]:
        return []

    async def project_reverse_point_5179(self, *_args: object, **_kwargs: object) -> Point | None:
        return self.projected_point


@pytest.mark.asyncio
async def test_t176_far_reverse_inside_sppn_envelope_is_ok_context_only() -> None:
    response = await reverse_geocode(
        _ContextOnlyReverseRepo(Point(x=969255, y=1940455)),
        ReverseInput(point=Point(x=127.1, y=36.6), radius_m=200),
    )

    assert response.status == "OK"
    assert response.result == ()
    assert response.x_extension is not None
    assert response.x_extension.national_point_number == "다사 6925 4045"

    converted = reverse_v2_from_v1(
        ReverseV2Input(lon=127.1, lat=36.6, radius_m=200),
        response,
    )

    assert converted.status == "OK"
    assert len(converted.candidates) == 1
    assert converted.candidates[0].match_kind == "sppn"
    assert converted.candidates[0].distance_m is None


@pytest.mark.asyncio
async def test_t176_far_reverse_without_address_or_sppn_context_is_not_found() -> None:
    response = await reverse_geocode(
        _ContextOnlyReverseRepo(Point(x=1, y=1)),
        ReverseInput(point=Point(x=127.1, y=36.6), radius_m=200),
    )

    assert response.status == "NOT_FOUND"
    assert response.result == ()
    assert response.x_extension is None

    converted = reverse_v2_from_v1(
        ReverseV2Input(lon=127.1, lat=36.6, radius_m=200),
        response,
    )

    assert converted.status == "NOT_FOUND"
    assert converted.candidates == ()


def test_t176_reverse_radius_edge_candidate_has_zero_confidence() -> None:
    input_v2 = ReverseV2Input(lon=127.036, lat=37.501, radius_m=200)
    response = ReverseResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
        status="OK",
        input=ReverseInput(point=Point(x=127.036, y=37.501), radius_m=200),
        result=(
            ReverseResultItem(
                type="road",
                text="서울특별시 강남구 테헤란로 152",
                structure=AddressStructure(level1="서울특별시", level2="강남구"),
                point=Point(x=127.036, y=37.501),
                distance_m=200.0,
            ),
        ),
    )

    converted = reverse_v2_from_v1(input_v2, response)

    assert converted.candidates[0].distance_m == pytest.approx(200.0)
    assert converted.candidates[0].confidence == pytest.approx(0.0)
