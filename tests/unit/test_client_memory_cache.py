from __future__ import annotations

import asyncio
import math
from unittest.mock import AsyncMock

import pytest

import kortravelgeo.client as client_module
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.common import Point, ServiceMeta
from kortravelgeo.dto.search import SearchInput, SearchResponse, SearchResultItem
from kortravelgeo.dto.v2 import BBoxV2, DatasetRef
from kortravelgeo.exceptions import GeometryTimeoutError
from kortravelgeo.infra.geometry_repo import GeometryRepository
from kortravelgeo.settings import Settings
from tests.unit.test_geometry_enrichment_resilience import polygon
from tests.unit.test_t156_geo_cache import (
    FakeGeoCacheRepository,
    _geocode_response,
    _reset_fake_cache,
    _reverse_response,
)

_STAMP = DatasetRef(version_token="dv1-" + "a" * 32, data_token="dd1-" + "b" * 32)
_ADDRESS = "서울특별시 강남구 테헤란로 152"


@pytest.fixture
def cached_client(monkeypatch):
    _reset_fake_cache()
    monkeypatch.setattr(client_module, "GeoCacheRepository", FakeGeoCacheRepository)
    state = {"stamp": _STAMP, "geocode_calls": 0, "reverse_calls": 0, "search_calls": 0}

    async def stamp(self):
        return state["stamp"]

    async def geocode(repo, inp, **kwargs):
        state["geocode_calls"] += 1
        return _geocode_response(inp)

    async def reverse(repo, inp, **kwargs):
        state["reverse_calls"] += 1
        return _reverse_response(inp)

    async def search(self, query, **kwargs):
        state["search_calls"] += 1
        return SearchResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="search"), status="OK",
            input=SearchInput(query=query, page=kwargs["page"], size=kwargs["size"]),
            result=(SearchResultItem(type="address", title=_ADDRESS, address=_ADDRESS,
                                     point=Point(x=127.036, y=37.501), score=1),),
            total=123,
        )

    monkeypatch.setattr(AsyncAddressClient, "dataset_ref", stamp)
    monkeypatch.setattr(client_module, "core_geocode", geocode)
    monkeypatch.setattr(client_module, "core_reverse_geocode", reverse)
    monkeypatch.setattr(AsyncAddressClient, "_search_v1", search)
    client = AsyncAddressClient(engine=object(), settings=Settings(_env_file=None))
    return client, state


@pytest.mark.asyncio
async def test_v1_memory_hits_skip_postgres_cache_and_preserve_cache_source(cached_client):
    client, state = cached_client
    first = await client._geocode_v1(_ADDRESS)
    second = await client._geocode_v1(_ADDRESS)
    assert first.x_extension.source == "local"
    assert second.x_extension.source == "cache"
    assert state["geocode_calls"] == 1
    assert len(FakeGeoCacheRepository.gets) == len(FakeGeoCacheRepository.sets) == 1
    await client._reverse_geocode_v1(127.036, 37.501)
    cached = await client._reverse_geocode_v1(127.036, 37.501)
    assert cached.result[0].source == "cache"
    assert state["reverse_calls"] == 1
    await client.close()


@pytest.mark.asyncio
async def test_v2_response_hits_skip_conversion_and_search_preserves_exact_total(cached_client):
    client, state = cached_client
    first = await client.geocode(_ADDRESS, limit=1)
    second = await client.geocode(_ADDRESS, limit=1)
    assert first.model_dump(exclude={"query_id"}) == second.model_dump(exclude={"query_id"})
    assert first.query_id != second.query_id and second.dataset == _STAMP
    assert state["geocode_calls"] == 1
    first = await client.reverse(127.036, 37.501)
    second = await client.reverse(127.036, 37.501)
    assert first.model_dump(exclude={"query_id"}) == second.model_dump(exclude={"query_id"})
    assert first.query_id != second.query_id and state["reverse_calls"] == 1
    first = await client.search("테헤란로", size=10)
    second = await client.search("테헤란로", size=10)
    assert first.model_dump(exclude={"query_id"}) == second.model_dump(exclude={"query_id"})
    assert first.query_id != second.query_id and second.total == 123
    assert state["search_calls"] == 1
    await client.search("테헤란로", size=20)
    assert state["search_calls"] == 2
    await client.close()


@pytest.mark.asyncio
async def test_release_and_query_options_are_part_of_result_cache_keys(cached_client):
    client, state = cached_client
    await client.geocode(_ADDRESS, limit=1)
    state["stamp"] = DatasetRef(version_token="dv1-" + "c" * 32,
                                data_token="dd1-" + "d" * 32)
    response = await client.geocode(_ADDRESS, limit=1)
    assert response.dataset == state["stamp"] and state["geocode_calls"] == 2
    await client.reverse(127.036, 37.501, radius_m=100)
    await client.reverse(127.036, 37.501, radius_m=200)
    await client.reverse(127.0361, 37.501, radius_m=200)
    assert state["reverse_calls"] == 3
    await client.close()


@pytest.mark.asyncio
async def test_no_stamp_or_external_fallback_bypasses_memory_cache(cached_client):
    client, state = cached_client
    state["stamp"] = None
    await client.geocode(_ADDRESS, limit=1)
    await client.geocode(_ADDRESS, limit=1)
    assert state["geocode_calls"] == 2 and client._memory_result_cache.size_bytes == 0
    state["stamp"] = _STAMP
    await client.geocode(_ADDRESS, limit=1, fallback="api")
    await client.geocode(_ADDRESS, limit=1, fallback="api")
    assert state["geocode_calls"] == 4 and client._memory_result_cache.size_bytes == 0
    assert FakeGeoCacheRepository.gets == []
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,max_bytes", [(False, 4096), (True, 0)])
async def test_disable_settings_keep_the_existing_lookup_path(cached_client, enabled, max_bytes):
    _, state = cached_client
    client = AsyncAddressClient(engine=object(), settings=Settings(
        _env_file=None, cache_enabled=enabled, cache_memory_max_bytes=max_bytes,
    ))
    await client.geocode(_ADDRESS, limit=1)
    await client.geocode(_ADDRESS, limit=1)
    assert state["geocode_calls"] == 2 and client._memory_result_cache.size_bytes == 0
    assert len(FakeGeoCacheRepository.gets) == (2 if enabled else 0)
    await client.close()


@pytest.mark.asyncio
async def test_concurrent_v2_calls_share_the_complete_query_path(cached_client, monkeypatch):
    client, state = cached_client
    started = asyncio.Event()
    release = asyncio.Event()

    async def geocode(repo, inp, **kwargs):
        state["geocode_calls"] += 1
        started.set()
        await release.wait()
        return _geocode_response(inp)

    monkeypatch.setattr(client_module, "core_geocode", geocode)
    requests = [asyncio.create_task(client.geocode(_ADDRESS, limit=1)) for _ in range(16)]
    await started.wait()
    release.set()
    results = await asyncio.gather(*requests)
    assert len(results) == 16
    assert len({x.query_id for x in results}) == 16
    assert all(x.model_dump(exclude={"query_id"}) ==
               results[0].model_dump(exclude={"query_id"}) for x in results)
    assert state["geocode_calls"] == 1 and len(FakeGeoCacheRepository.gets) == 1
    await client.close()


@pytest.mark.asyncio
async def test_geometry_option_has_its_own_key_and_failed_geometry_is_retried(
    cached_client, monkeypatch,
):
    client, state = cached_client
    calls = 0

    async def lookup(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise GeometryTimeoutError("injected optional geometry timeout")
        return polygon()

    monkeypatch.setattr(GeometryRepository, "building_geometry", lookup)
    plain = await client.geocode(_ADDRESS, limit=1)
    assert plain.candidates[0].geometry is None and calls == 0
    degraded = await client.geocode(_ADDRESS, limit=1, include_geometry=True)
    assert degraded.candidates[0].geometry_error is not None and calls == 1
    recovered = await client.geocode(_ADDRESS, limit=1, include_geometry=True)
    assert recovered.candidates[0].geometry is not None and calls == 2
    recovered.candidates[0].geometry.geojson["coordinates"].append([[1, 2]])
    cached = await client.geocode(_ADDRESS, limit=1, include_geometry=True)
    assert cached.candidates[0].geometry.geojson["coordinates"] == []
    assert calls == 2 and state["geocode_calls"] == 1
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("service", ["geocode", "search"])
@pytest.mark.parametrize("as_mapping", [False, True])
@pytest.mark.parametrize("minimum,maximum", [
    (float("-inf"), float("inf")), (float("nan"), 130.0),
])
async def test_nonfinite_bbox_preserves_the_cache_disabled_response(
    cached_client, service, minimum, maximum, as_mapping,
):
    client, _ = cached_client
    bbox = BBoxV2(min_lon=minimum, min_lat=32, max_lon=maximum, max_lat=39)
    if as_mapping:
        bbox = bbox.model_dump()
    call = client.geocode if service == "geocode" else client.search
    client.settings = client.settings.model_copy(update={"cache_memory_max_bytes": 0})
    expected = await call(_ADDRESS, bbox=bbox)
    client.settings = client.settings.model_copy(update={"cache_memory_max_bytes": 67108864})
    for _ in range(2):
        actual = await call(_ADDRESS, bbox=bbox)
        assert actual.status == expected.status and actual.candidates == expected.candidates
        if service == "search":
            assert actual.total == expected.total
        echoed = actual.input.bbox
        assert echoed is not None
        assert (math.isnan(echoed.min_lon) if math.isnan(minimum) else echoed.min_lon == minimum)
        assert echoed.max_lon == maximum
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("as_mapping", [False, True])
async def test_finite_bbox_keeps_complete_response_caching(cached_client, monkeypatch, as_mapping):
    client, state = cached_client
    bbox = BBoxV2(min_lon=126, min_lat=36, max_lon=128, max_lat=38)
    if as_mapping:
        bbox = bbox.model_dump()
    geocode = AsyncMock(wraps=client._geocode_v2)
    monkeypatch.setattr(client, "_geocode_v2", geocode)
    await client.geocode(_ADDRESS, bbox=bbox, limit=1)
    await client.geocode(_ADDRESS, bbox=bbox, limit=1)
    await client.search(_ADDRESS, bbox=bbox)
    await client.search(_ADDRESS, bbox=bbox)
    assert geocode.await_count == 1 and state["search_calls"] == 1
    await client.close()


@pytest.mark.asyncio
async def test_bbox_key_and_loader_share_the_validated_snapshot(cached_client, monkeypatch):
    client, _ = cached_client
    bounds = {"min_lon": 126, "min_lat": 36, "max_lon": 128, "max_lat": 38}

    async def stamp():
        bounds["max_lon"] = 130
        return _STAMP

    monkeypatch.setattr(client, "dataset_ref", stamp)
    result = await client.geocode(_ADDRESS, bbox=bounds, limit=1)
    assert bounds["max_lon"] == 130
    assert result.input.bbox.max_lon == 128
    await client.close()
