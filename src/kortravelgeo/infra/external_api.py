"""External geocoding API adapters used only as explicit fallback."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import SecretStr
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from kortravelgeo.core.address import address_code_set_from_mapping
from kortravelgeo.core.confidence import external_geocode_confidence
from kortravelgeo.dto.address import AddressStructure, RefinedAddress
from kortravelgeo.dto.common import Point, ServiceMeta
from kortravelgeo.dto.geocode import GeocodeExtension, GeocodeInput, GeocodeResponse, GeocodeResult
from kortravelgeo.exceptions import ConfigError, ExternalApiError
from kortravelgeo.infra.metrics import record_external_api_call
from kortravelgeo.settings import Settings


class ExternalGeocodeClient:
    """Call approved provider APIs for ``fallback='api'`` geocoding."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._http_client = http_client

    async def geocode(self, inp: GeocodeInput) -> GeocodeResponse | None:
        if self.settings.vworld_api_key is None and self.settings.juso_api_key is None:
            msg = "external API fallback is enabled but no provider API key is configured"
            raise ConfigError(
                msg,
                hint=(
                    "Set KTG_VWORLD_API_KEY or KTG_JUSO_API_KEY "
                    "for fallback='api'. NEXT_PUBLIC_VWORLD_API_KEY is only for the UI map."
                ),
            )
        if self.settings.vworld_api_key is not None:
            response = await self._vworld_geocode(inp)
            if response is not None:
                return response
        if self.settings.juso_api_key is not None:
            return await self._juso_coord_geocode(inp)
        return None

    async def _vworld_geocode(self, inp: GeocodeInput) -> GeocodeResponse | None:
        assert self.settings.vworld_api_key is not None
        payload = await self._get_json(
            self.settings.vworld_url,
            params={
                "service": "address",
                "request": "getcoord",
                "version": "2.0",
                "crs": inp.crs,
                "address": inp.address,
                "type": "road" if inp.type == "road" else "parcel",
                "format": "json",
                "errorformat": "json",
                "key": self.settings.vworld_api_key.get_secret_value(),
            },
        )
        _raise_for_vworld_error(payload)
        return _vworld_response(inp, payload)

    async def _juso_coord_geocode(self, inp: GeocodeInput) -> GeocodeResponse | None:
        assert self.settings.juso_api_key is not None
        search_payload = await self._get_json(
            self.settings.juso_search_url,
            params={
                "confmKey": self.settings.juso_api_key.get_secret_value(),
                "currentPage": 1,
                "countPerPage": 1,
                "keyword": inp.address,
                "resultType": "json",
            },
        )
        _raise_for_juso_error(search_payload, provider="juso search")
        item = _first_juso_item(search_payload)
        if item is None:
            return None
        try:
            codes = address_code_set_from_mapping(item)
        except ValueError:
            return None
        if codes.legal_dong_code is None or codes.road_name_address_code is None:
            return None
        coord_key = self.settings.juso_coord_api_key or self.settings.juso_api_key
        road_address = codes.road_name_address_code
        coord_payload = await self._get_json(
            self.settings.juso_coord_url,
            params={
                "confmKey": coord_key.get_secret_value(),
                "admCd": codes.legal_dong_code.code,
                "rnMgtSn": road_address.road_name_code.code,
                "udrtYn": road_address.underground_flag,
                "buldMnnm": str(road_address.building_main_number),
                "buldSlno": str(road_address.building_sub_number),
                "resultType": "json",
            },
        )
        _raise_for_juso_error(coord_payload, provider="juso coord")
        coord_item = _first_juso_item(coord_payload)
        if coord_item is None:
            return None
        return _juso_response(inp, item, coord_item)

    async def _get_json(self, url: str, *, params: Mapping[str, Any]) -> dict[str, Any]:
        provider = _provider_from_url(url)

        async def fetch(client: httpx.AsyncClient) -> dict[str, Any]:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.2, max=2.0),
                retry=retry_if_exception_type(
                    (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError)
                ),
                reraise=True,
            ):
                with attempt:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        msg = f"external API returned non-object JSON: {url}"
                        raise ExternalApiError(msg)
                    record_external_api_call(provider, "success")
                    return data
            msg = f"external API retry loop did not return: {url}"
            raise ExternalApiError(msg)

        try:
            if self._http_client is not None:
                return await fetch(self._http_client)
            async with httpx.AsyncClient(timeout=5.0) as client:
                return await fetch(client)
        except httpx.HTTPError as exc:
            record_external_api_call(provider, "failure")
            msg = f"external API request failed: {url}"
            raise ExternalApiError(msg) from exc


def _provider_from_url(url: str) -> str:
    lowered = url.lower()
    if "vworld" in lowered:
        return "vworld"
    if "juso" in lowered:
        return "juso"
    if "epost" in lowered:
        return "epost"
    return "unknown"


def _vworld_response(inp: GeocodeInput, payload: Mapping[str, Any]) -> GeocodeResponse | None:
    response = _mapping(payload.get("response"))
    if str(response.get("status", "")).upper() != "OK":
        return None
    result = response.get("result")
    if isinstance(result, list):
        result = result[0] if result else None
    result_map = _mapping(result)
    point = _point(_mapping(result_map.get("point")))
    if point is None:
        return None
    text = str(result_map.get("text") or inp.address)
    structure = _mapping(result_map.get("structure"))
    return GeocodeResponse(
        service=_service(inp),
        status="OK",
        input=inp,
        refined=RefinedAddress(text=text, structure=_structure(structure)),
        result=GeocodeResult(crs=inp.crs, point=point),
        x_extension=GeocodeExtension(
            source="api_vworld",
            confidence=external_geocode_confidence("api_vworld"),
        ),
    )


def _raise_for_vworld_error(payload: Mapping[str, Any]) -> None:
    response = _mapping(payload.get("response"))
    if str(response.get("status", "")).upper() != "ERROR":
        return
    error = _mapping(response.get("error"))
    code = str(error.get("code") or "UNKNOWN")
    text = str(error.get("text") or "VWorld API request failed")
    if code.upper() in {"INVALID_KEY", "INVALIDKEY", "AUTH_ERROR"}:
        msg = "VWorld API authentication failed"
        raise ExternalApiError(msg, hint=f"{code}: {text}")
    msg = "VWorld API returned an error"
    raise ExternalApiError(msg, hint=f"{code}: {text}")


def _raise_for_juso_error(payload: Mapping[str, Any], *, provider: str) -> None:
    common = _mapping(_mapping(payload.get("results")).get("common"))
    code = str(common.get("errorCode") or "0")
    if code in {"0", "00"}:
        return
    message = str(common.get("errorMessage") or "Juso API request failed")
    if code in {"E0001", "E0005"} or "KEY" in message.upper():
        msg = f"{provider} API authentication failed"
        raise ExternalApiError(msg, hint=f"{code}: {message}")
    msg = f"{provider} API returned an error"
    raise ExternalApiError(msg, hint=f"{code}: {message}")


def _juso_response(
    inp: GeocodeInput,
    search_item: Mapping[str, Any],
    coord_item: Mapping[str, Any],
) -> GeocodeResponse | None:
    point = _point_from_keys(coord_item, x_keys=("entX", "x", "X"), y_keys=("entY", "y", "Y"))
    if point is None:
        return None
    text = str(search_item.get("roadAddr") or search_item.get("jibunAddr") or inp.address)
    return GeocodeResponse(
        service=_service(inp),
        status="OK",
        input=inp,
        refined=RefinedAddress(
            text=text,
            structure=AddressStructure(
                level4AC=_str_or_none(search_item.get("admCd")),
                level5=_str_or_none(search_item.get("rn")),
                detail=_str_or_none(search_item.get("buldMnnm")),
            ),
        ),
        result=GeocodeResult(crs="EPSG:4326", point=point),
        x_extension=GeocodeExtension(
            source="api_juso",
            confidence=external_geocode_confidence("api_juso"),
            bd_mgt_sn=_str_or_none(search_item.get("bdMgtSn")),
            rncode_full=_str_or_none(search_item.get("rnMgtSn")),
            zip_no=_str_or_none(search_item.get("zipNo")),
            zip_source="building_bsi_zon_no" if search_item.get("zipNo") else None,
            buld_nm=_str_or_none(search_item.get("bdNm")),
        ),
    )


def _service(_inp: GeocodeInput) -> ServiceMeta:
    return ServiceMeta(
        name="kor-travel-geo",
        operation="geocode",
        time=datetime.now(UTC).isoformat(),
    )


def _first_juso_item(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    results = _mapping(payload.get("results"))
    items = results.get("juso")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    return first if isinstance(first, Mapping) else None


def _point(raw: Mapping[str, Any]) -> Point | None:
    return _point_from_keys(raw, x_keys=("x", "X"), y_keys=("y", "Y"))


def _point_from_keys(
    raw: Mapping[str, Any],
    *,
    x_keys: tuple[str, ...],
    y_keys: tuple[str, ...],
) -> Point | None:
    x = next((raw[key] for key in x_keys if raw.get(key) not in (None, "")), None)
    y = next((raw[key] for key in y_keys if raw.get(key) not in (None, "")), None)
    if x is None or y is None:
        return None
    return Point(x=float(x), y=float(y))


def _structure(raw: Mapping[str, Any]) -> AddressStructure:
    return AddressStructure(
        level1=_str_or_none(raw.get("level1")),
        level2=_str_or_none(raw.get("level2")),
        level4L=_str_or_none(raw.get("level4L")),
        level4LC=_str_or_none(raw.get("level4LC")),
        level4A=_str_or_none(raw.get("level4A")),
        level4AC=_str_or_none(raw.get("level4AC")),
        level5=_str_or_none(raw.get("level5")),
        detail=_str_or_none(raw.get("detail")),
    )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _str_or_none(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value)
