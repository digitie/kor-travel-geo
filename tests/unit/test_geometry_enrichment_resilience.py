"""요청 내부 geometry 조회 공유와 보조 단계 실패 격리 회귀."""

from __future__ import annotations

from typing import Any

import pytest

from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.core.protocols import GeometryLookup
from kortravelgeo.dto.v2 import CandidateV2, GeometryV2, PointV2
from kortravelgeo.infra.geometry_repo import GeometryRepository


def candidate(**updates: Any) -> CandidateV2:
    return CandidateV2(
        confidence=0.97,
        match_kind="road",
        point=PointV2(lon=127.036, lat=37.501),
        metadata={
            "bd_mgt_sn": "building-1", "rncode_full": "road-1",
            "bjd_cd": "dong-1", "detail": "152",
        },
    ).model_copy(update=updates)


def polygon() -> GeometryLookup:
    return GeometryLookup(kind="building", geometry=GeometryV2(
        kind="building", geojson={"type": "Polygon", "coordinates": []},
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("found", [True, False])
async def test_identical_building_query_is_shared_only_within_one_request(
    monkeypatch: pytest.MonkeyPatch, found: bool,
) -> None:
    calls: list[dict[str, Any]] = []

    async def lookup(self: GeometryRepository, **kwargs: Any) -> GeometryLookup | None:
        calls.append(kwargs)
        return polygon() if found else None

    monkeypatch.setattr(GeometryRepository, "building_geometry", lookup)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    road = candidate()
    parcel = candidate(match_kind="parcel")
    first = await client._enrich_candidates_with_geometry((road, parcel), include_geometry=True)
    assert len(calls) == 1
    assert len(first) == 2
    assert first[0].point == road.point and first[1].point == parcel.point
    assert (first[0].geometry is not None) is found
    await client._enrich_candidates_with_geometry((road, parcel), include_geometry=True)
    assert len(calls) == 2  # 별도 요청은 miss와 geometry 객체를 전역 보존하지 않는다.


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["bd_mgt_sn", "rncode_full", "bjd_cd", "detail"])
async def test_every_actual_lookup_argument_participates_in_memo_key(
    monkeypatch: pytest.MonkeyPatch, field: str,
) -> None:
    calls: list[dict[str, Any]] = []

    async def lookup(self: GeometryRepository, **kwargs: Any) -> GeometryLookup:
        calls.append(kwargs)
        return polygon()

    monkeypatch.setattr(GeometryRepository, "building_geometry", lookup)
    first = candidate()
    second = candidate(metadata={**first.metadata, field: "different"})
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    await client._enrich_candidates_with_geometry((first, second), include_geometry=True)
    assert len(calls) == 2
    assert calls[0][field] != calls[1][field]


@pytest.mark.asyncio
async def test_existing_geometry_is_kept_without_requery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden(self: GeometryRepository, **kwargs: Any) -> None:
        raise AssertionError("이미 확보한 geometry를 다시 조회하면 안 된다")

    monkeypatch.setattr(GeometryRepository, "building_geometry", forbidden)
    existing = candidate(geometry=polygon().geometry)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    result = await client._enrich_candidates_with_geometry((existing,), include_geometry=True)
    assert result[0] is existing


@pytest.mark.asyncio
async def test_no_geometry_option_does_not_query_or_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden(self: GeometryRepository, **kwargs: Any) -> None:
        raise AssertionError("geometry 미선택 요청에서 조회하면 안 된다")

    monkeypatch.setattr(GeometryRepository, "building_geometry", forbidden)
    candidates = (candidate(),)
    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    result = await client._enrich_candidates_with_geometry(candidates, include_geometry=False)
    assert result is candidates
