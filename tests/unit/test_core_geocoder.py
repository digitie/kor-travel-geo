from __future__ import annotations

import pytest

from kraddr.geo.core.geocoder import geocode
from kraddr.geo.core.normalize import parse_address
from kraddr.geo.core.protocols import AddressLookup, FakeGeocodeRepo
from kraddr.geo.dto.common import Point
from kraddr.geo.dto.geocode import GeocodeInput
from kraddr.geo.dto.region import RegionHint


def _lookup(*, confidence: float = 1.0, pt_source: str = "entrance") -> AddressLookup:
    return AddressLookup(
        bd_mgt_sn="1111010100101440003031291",
        text="서울특별시 종로구 자하문로 94",
        address_type="road",
        point=Point(x=126.969, y=37.586),
        si_nm="서울특별시",
        sgg_nm="종로구",
        emd_nm="청운동",
        road_nm="자하문로",
        detail="94",
        rncode_full="111103100012",
        bjd_cd="1111010100",
        adm_cd="1111051500",
        adm_nm="청운효자동",
        zip_no="03047",
        pt_source=pt_source,  # type: ignore[arg-type]
        confidence=confidence,
    )


def test_parse_road_address_normalizes_alias_and_numbers() -> None:
    parts = parse_address("서울 종로구 청운동 자하문로 94 (청운동)")

    assert parts.si == "서울특별시"
    assert parts.sgg == "종로구"
    assert parts.road == "자하문로"
    assert parts.road_nrm == "자하문로"
    assert parts.mnnm == 94
    assert parts.slno == 0
    assert parts.is_road is True


def test_parse_parcel_address_tracks_mountain_flag() -> None:
    parts = parse_address("강원특별자치도 춘천시 신북읍 산 12-3")

    assert parts.mt is True
    assert parts.mntn_yn == "1"
    assert parts.mnnm == 12
    assert parts.slno == 3


@pytest.mark.asyncio
async def test_geocode_uses_fake_repo_and_builds_vworld_compatible_response() -> None:
    response = await geocode(
        FakeGeocodeRepo(road_result=_lookup()),
        GeocodeInput(address="서울특별시 종로구 자하문로 94"),
    )

    assert response.status == "OK"
    assert response.result is not None
    assert response.result.point.x == pytest.approx(126.969)
    assert response.refined is not None
    assert response.refined.structure.level4AC == "1111051500"
    assert response.x_extension is not None
    assert response.x_extension.bd_mgt_sn == "1111010100101440003031291"


@pytest.mark.asyncio
async def test_geocode_lowers_confidence_for_centroid_fallback() -> None:
    response = await geocode(
        FakeGeocodeRepo(road_result=_lookup(confidence=1.0, pt_source="centroid")),
        GeocodeInput(address="서울특별시 종로구 자하문로 94"),
    )

    assert response.x_extension is not None
    assert response.x_extension.confidence == pytest.approx(0.82)


@pytest.mark.asyncio
async def test_geocode_forwards_region_hint_to_repository() -> None:
    repo = FakeGeocodeRepo(road_result=_lookup())
    hint = RegionHint(sig_cd="11110")

    response = await geocode(
        repo,
        GeocodeInput(address="자하문로 94"),
        region_hint=hint,
    )

    assert response.status == "OK"
    assert repo.last_region_hint == hint
