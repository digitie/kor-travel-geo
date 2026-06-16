from __future__ import annotations

import inspect
from typing import Any, ClassVar

import pytest

import kortravelgeo.client as client_module
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.address import AddressStructure, RefinedAddress
from kortravelgeo.dto.common import Point, ServiceMeta
from kortravelgeo.dto.geocode import (
    GeocodeExtension,
    GeocodeInput,
    GeocodeResponse,
    GeocodeResult,
)
from kortravelgeo.dto.reverse import ReverseInput, ReverseResponse, ReverseResultItem
from kortravelgeo.infra.cache import GeoCacheRepository, make_cache_key
from kortravelgeo.settings import Settings


class FakeGeoCacheRepository:
    get_payload: ClassVar[dict[str, Any] | None] = None
    gets: ClassVar[list[str]] = []
    sets: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, engine: object) -> None:
        self.engine = engine

    async def get_json(self, cache_key: str) -> dict[str, Any] | None:
        self.gets.append(cache_key)
        return self.get_payload

    async def set_json(
        self,
        *,
        cache_key: str,
        service: str,
        payload: dict[str, Any],
        ttl_days: int,
    ) -> None:
        self.sets.append(
            {
                "cache_key": cache_key,
                "service": service,
                "payload": payload,
                "ttl_days": ttl_days,
            }
        )


def _reset_fake_cache(payload: dict[str, Any] | None = None) -> None:
    FakeGeoCacheRepository.get_payload = payload
    FakeGeoCacheRepository.gets = []
    FakeGeoCacheRepository.sets = []


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def _geocode_response(inp: GeocodeInput | None = None) -> GeocodeResponse:
    input_model = inp or GeocodeInput(address="서울특별시 강남구 테헤란로 152")
    return GeocodeResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="geocode"),
        status="OK",
        input=input_model,
        refined=RefinedAddress(
            text=input_model.address,
            structure=AddressStructure(
                level1="서울특별시",
                level2="강남구",
                level4L="테헤란로",
                level5="152",
            ),
        ),
        result=GeocodeResult(point=Point(x=127.036, y=37.501)),
        x_extension=GeocodeExtension(
            source="local",
            confidence=0.98,
            bd_mgt_sn="1168010100108250000028924",
        ),
    )


def _reverse_response(inp: ReverseInput | None = None) -> ReverseResponse:
    input_model = inp or ReverseInput(point=Point(x=127.036, y=37.501), radius_m=200)
    return ReverseResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
        status="OK",
        input=input_model,
        result=(
            ReverseResultItem(
                type="road",
                text="서울특별시 강남구 테헤란로 152",
                structure=AddressStructure(
                    level1="서울특별시",
                    level2="강남구",
                    level4L="테헤란로",
                    level5="152",
                ),
                point=Point(x=127.036, y=37.501),
                source="local",
                distance_m=1.2,
            ),
        ),
    )


def test_make_cache_key_is_stable_and_opaque() -> None:
    left = make_cache_key("geocode", {"address": "서울", "type": "road"})
    right = make_cache_key("geocode", {"type": "road", "address": "서울"})

    assert left == right
    assert left.startswith("geocode:v1:")
    assert "서울" not in left


def test_geo_cache_repository_sql_contract() -> None:
    get_source = inspect.getsource(GeoCacheRepository.get_json)
    set_source = inspect.getsource(GeoCacheRepository.set_json)
    clear_source = inspect.getsource(GeoCacheRepository.clear)

    assert "hit_count = hit_count + 1" in get_source
    assert "expires_at > now()" in get_source
    assert "ON CONFLICT (cache_key) DO UPDATE" in set_source
    assert "JSONB" in set_source
    assert "DELETE FROM geo_cache" in clear_source


@pytest.mark.asyncio
async def test_geocode_v1_returns_cache_hit_without_repo_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = client_module._geocode_cache_payload(_geocode_response())
    GeocodeResponse.model_validate(payload)
    _reset_fake_cache(payload)
    monkeypatch.setattr(client_module, "GeoCacheRepository", FakeGeoCacheRepository)

    async def fail_core(*_args: Any, **_kwargs: Any) -> GeocodeResponse:
        raise AssertionError("core geocode must not run on cache hit")

    monkeypatch.setattr(client_module, "core_geocode", fail_core)
    client = AsyncAddressClient(engine=object(), settings=_settings())

    response = await client._geocode_v1("서울특별시 강남구 테헤란로 152")

    assert response.x_extension is not None
    assert response.x_extension.source == "cache"
    assert FakeGeoCacheRepository.gets
    assert FakeGeoCacheRepository.sets == []


@pytest.mark.asyncio
async def test_geocode_v1_stores_local_ok_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_cache()
    monkeypatch.setattr(client_module, "GeoCacheRepository", FakeGeoCacheRepository)

    async def fake_core(_repo: object, inp: GeocodeInput, **_kwargs: Any) -> GeocodeResponse:
        return _geocode_response(inp)

    monkeypatch.setattr(client_module, "core_geocode", fake_core)
    client = AsyncAddressClient(engine=object(), settings=_settings(cache_ttl_days=7))

    response = await client._geocode_v1("서울특별시 강남구 테헤란로 152")

    assert response.status == "OK"
    assert len(FakeGeoCacheRepository.sets) == 1
    cached = FakeGeoCacheRepository.sets[0]
    assert cached["service"] == "geocode"
    assert cached["ttl_days"] == 7
    assert cached["payload"]["input"]["type"] == "road"
    GeocodeResponse.model_validate(cached["payload"])


@pytest.mark.asyncio
async def test_reverse_v1_returns_cache_hit_without_repo_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = client_module._reverse_cache_payload(_reverse_response())
    ReverseResponse.model_validate(payload)
    _reset_fake_cache(payload)
    monkeypatch.setattr(client_module, "GeoCacheRepository", FakeGeoCacheRepository)

    async def fail_core(*_args: Any, **_kwargs: Any) -> ReverseResponse:
        raise AssertionError("core reverse must not run on cache hit")

    monkeypatch.setattr(client_module, "core_reverse_geocode", fail_core)
    client = AsyncAddressClient(engine=object(), settings=_settings())

    response = await client._reverse_geocode_v1(127.036, 37.501)

    assert response.result
    assert {item.source for item in response.result} == {"cache"}
    assert FakeGeoCacheRepository.gets
    assert FakeGeoCacheRepository.sets == []


@pytest.mark.asyncio
async def test_cache_disabled_bypasses_geo_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_cache()
    monkeypatch.setattr(client_module, "GeoCacheRepository", FakeGeoCacheRepository)

    async def fake_core(_repo: object, inp: GeocodeInput, **_kwargs: Any) -> GeocodeResponse:
        return _geocode_response(inp)

    monkeypatch.setattr(client_module, "core_geocode", fake_core)
    client = AsyncAddressClient(engine=object(), settings=_settings(cache_enabled=False))

    response = await client._geocode_v1("서울특별시 강남구 테헤란로 152")

    assert response.status == "OK"
    assert FakeGeoCacheRepository.gets == []
    assert FakeGeoCacheRepository.sets == []
