"""Navigation DB parsing and VWorld fallback reverse-geocoding helpers."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from .data import _content_bytes, _iter_decoded_lines, _iter_text_members, _split_line
from .exceptions import KrAddrParseError, KrAddrRequestError

NAVIGATION_BUILDING_COLUMNS = (
    "jurisdiction_emd_code",
    "sido_name",
    "sigungu_name",
    "eup_myeon_dong_name",
    "road_name_code",
    "road_name",
    "underground_yn",
    "building_main_no",
    "building_sub_no",
    "postal_code",
    "building_management_number",
    "sigungu_building_name",
    "building_use",
    "administrative_dong_code",
    "administrative_dong_name",
    "ground_floor_count",
    "underground_floor_count",
    "apartment_kind_code",
    "building_count",
    "detail_building_name",
    "building_name_history",
    "detail_building_name_history",
    "residential_yn",
    "building_center_x",
    "building_center_y",
    "entrance_x",
    "entrance_y",
    "sido_name_en",
    "sigungu_name_en",
    "eup_myeon_dong_name_en",
    "road_name_en",
    "eup_myeon_dong_type",
    "change_reason_code",
)


class OfflineReverseStore(Protocol):
    def nearest_road_address(
        self,
        *,
        lon: float,
        lat: float,
        max_distance_m: float | None,
    ) -> ReverseGeocodeResult | None: ...


def _freeze(raw: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(raw or {}))


@dataclass(frozen=True, slots=True)
class ReverseGeocodeResult:
    """One normalized reverse-geocoding result."""

    address_type: str
    road_address: str | None = None
    parcel_address: str | None = None
    postal_code: str | None = None
    legal_dong_code: str | None = None
    road_name_code: str | None = None
    building_management_number: str | None = None
    building_name: str | None = None
    x: float | None = None
    y: float | None = None
    crs: str = "EPSG:4326"
    distance_m: float | None = None
    source: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", _freeze(self.raw))

    @property
    def formatted_address(self) -> str | None:
        return self.road_address or self.parcel_address


@dataclass(frozen=True, slots=True)
class NavigationBuildingRecord:
    """One building row from the Juso navigation database."""

    jurisdiction_emd_code: str
    sido_name: str
    sigungu_name: str
    eup_myeon_dong_name: str
    road_name_code: str
    road_name: str
    underground_yn: str
    building_main_no: str
    building_sub_no: str
    postal_code: str
    building_management_number: str
    sigungu_building_name: str
    building_use: str
    administrative_dong_code: str
    administrative_dong_name: str
    ground_floor_count: str
    underground_floor_count: str
    apartment_kind_code: str
    building_count: str
    detail_building_name: str
    building_name_history: str
    detail_building_name_history: str
    residential_yn: str
    building_center_x: str
    building_center_y: str
    entrance_x: str
    entrance_y: str
    sido_name_en: str
    sigungu_name_en: str
    eup_myeon_dong_name_en: str
    road_name_en: str
    eup_myeon_dong_type: str
    change_reason_code: str
    source_member: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", _freeze(self.raw))

    @property
    def legal_dong_code(self) -> str:
        return self.jurisdiction_emd_code

    @property
    def is_deleted(self) -> bool:
        return self.change_reason_code == "63"

    @property
    def building_number(self) -> str:
        main = _strip_number(self.building_main_no)
        sub = _strip_number(self.building_sub_no)
        return main if sub in {"", "0"} else f"{main}-{sub}"

    @property
    def building_name(self) -> str:
        return self.sigungu_building_name or self.detail_building_name

    @property
    def road_address(self) -> str:
        parts = [self.sido_name, self.sigungu_name]
        if self.eup_myeon_dong_type == "0":
            parts.append(self.eup_myeon_dong_name)
        parts.extend([self.road_name, self.building_number])
        address = " ".join(part for part in parts if part)
        if self.building_name:
            return f"{address} ({self.building_name})"
        return address

    def point_xy(self, *, prefer_entrance: bool = True) -> tuple[float, float] | None:
        entrance = _xy(self.entrance_x, self.entrance_y)
        center = _xy(self.building_center_x, self.building_center_y)
        if prefer_entrance:
            return entrance or center
        return center or entrance


class VWorldReverseGeocoder:
    """Async reverse-geocoding fallback through ``python-vworld-api``."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        api_key: str | None = None,
        domain: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        if client is not None:
            self.client = client
            return
        try:
            from vworld import AsyncVworldClient
        except ImportError as exc:
            raise KrAddrRequestError(
                "python-vworld-api is required for VWorld fallback reverse geocoding."
            ) from exc
        self.client = AsyncVworldClient(api_key=api_key, domain=domain, timeout=timeout)

    @classmethod
    def from_env(cls, **kwargs: Any) -> VWorldReverseGeocoder:
        try:
            from vworld import AsyncVworldClient
        except ImportError as exc:
            raise KrAddrRequestError(
                "python-vworld-api is required for VWorld fallback reverse geocoding."
            ) from exc
        return cls(client=AsyncVworldClient.from_env(**kwargs))

    @classmethod
    def from_env_file(cls, path: str | Path = ".env", **kwargs: Any) -> VWorldReverseGeocoder:
        try:
            from vworld import AsyncVworldClient
        except ImportError as exc:
            raise KrAddrRequestError(
                "python-vworld-api is required for VWorld fallback reverse geocoding."
            ) from exc
        return cls(client=AsyncVworldClient.from_env_file(path, **kwargs))

    async def aclose(self) -> None:
        aclose = getattr(self.client, "aclose", None)
        if aclose is not None:
            await aclose()

    async def __aenter__(self) -> VWorldReverseGeocoder:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def reverse_geocode(
        self,
        *,
        lon: float,
        lat: float,
        type: str = "both",
        zipcode: bool = True,
        simple: bool = False,
        crs: str = "EPSG:4326",
    ) -> tuple[ReverseGeocodeResult, ...]:
        payload = await self.client.reverse_geocode_latlon(
            lat,
            lon,
            type=type,
            zipcode=zipcode,
            simple=simple,
            crs=crs,
        )
        return tuple(
            _vworld_result(row, lon=lon, lat=lat, crs=crs) for row in _vworld_rows(payload)
        )

    async def reverse_road_address(
        self,
        *,
        lon: float,
        lat: float,
        zipcode: bool = True,
        simple: bool = False,
        crs: str = "EPSG:4326",
    ) -> ReverseGeocodeResult | None:
        results = await self.reverse_geocode(
            lon=lon,
            lat=lat,
            type="both",
            zipcode=zipcode,
            simple=simple,
            crs=crs,
        )
        for result in results:
            if result.road_address:
                return result
        return results[0] if results else None


class ReverseGeocoder:
    """Prefer the local SpatiaLite store and optionally fall back to VWorld."""

    def __init__(
        self,
        *,
        offline_store: OfflineReverseStore | None = None,
        vworld: VWorldReverseGeocoder | None = None,
        max_offline_distance_m: float | None = 50.0,
    ) -> None:
        self.offline_store = offline_store
        self.vworld = vworld
        self.max_offline_distance_m = max_offline_distance_m

    async def reverse_road_address(self, *, lon: float, lat: float) -> ReverseGeocodeResult | None:
        if self.offline_store is not None:
            result = self.offline_store.nearest_road_address(
                lon=lon,
                lat=lat,
                max_distance_m=self.max_offline_distance_m,
            )
            if result is not None:
                return result
        if self.vworld is not None:
            return await self.vworld.reverse_road_address(lon=lon, lat=lat)
        return None


def iter_navigation_building_records(
    path: str | Path | bytes,
    *,
    encoding: str | None = None,
) -> Iterator[NavigationBuildingRecord]:
    """Stream building records from a TXT, ZIP, or 7z navigation archive."""

    for member in _iter_navigation_building_text_members(path):
        for line in _iter_decoded_lines(member.content, encoding=encoding):
            if not line.strip():
                continue
            parts = _split_line(line)
            if _is_no_data_parts(parts) or len(parts) < len(NAVIGATION_BUILDING_COLUMNS):
                continue
            values = parts[: len(NAVIGATION_BUILDING_COLUMNS)]
            yield NavigationBuildingRecord(
                **dict(zip(NAVIGATION_BUILDING_COLUMNS, values, strict=True)),
                source_member=member.name,
                raw={"source_member": member.name},
            )


def load_navigation_building_records(
    path: str | Path | bytes,
    *,
    encoding: str | None = None,
) -> list[NavigationBuildingRecord]:
    return list(iter_navigation_building_records(path, encoding=encoding))


def _vworld_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    root = payload.get("response", payload)
    if not isinstance(root, Mapping):
        raise KrAddrParseError("VWorld response root must be an object")
    status = str(root.get("status") or "").upper()
    if status and status not in {"OK", "NORMAL"}:
        return []
    result = root.get("result")
    if result is None:
        return []
    if isinstance(result, list):
        return [row for row in result if isinstance(row, Mapping)]
    if isinstance(result, Mapping):
        items = result.get("items")
        if isinstance(items, list):
            return [row for row in items if isinstance(row, Mapping)]
        if isinstance(items, Mapping):
            return [items]
        return [result]
    raise KrAddrParseError("VWorld response.result must be an object or list")


def _vworld_result(
    row: Mapping[str, Any],
    *,
    lon: float,
    lat: float,
    crs: str,
) -> ReverseGeocodeResult:
    raw_address = row.get("address")
    address: Mapping[str, Any] = raw_address if isinstance(raw_address, Mapping) else {}
    address_type = (_text(row, "type") or _text(row, "category") or "").lower()
    text_value = _text(row, "text")
    road_address = _text(row, "roadAddr") or _text(address, "road")
    parcel_address = _text(row, "jibunAddr") or _text(address, "parcel")
    if address_type == "road" and road_address is None:
        road_address = text_value
    elif address_type == "parcel" and parcel_address is None:
        parcel_address = text_value
    elif road_address is None and parcel_address is None:
        road_address = text_value
    return ReverseGeocodeResult(
        address_type=address_type or ("road" if road_address else "parcel"),
        road_address=road_address,
        parcel_address=parcel_address,
        postal_code=_text(row, "zipcode") or _text(row, "zipNo") or _text(address, "zipcode"),
        x=lon,
        y=lat,
        crs=crs,
        source="vworld",
        raw=row,
    )


def _iter_navigation_building_text_members(path: str | Path | bytes) -> Iterator[Any]:
    if isinstance(path, bytes):
        yield from _iter_text_members(path)
        return
    archive_path = Path(path)
    if archive_path.suffix.lower() != ".7z":
        yield from _iter_text_members(_content_bytes(archive_path))
        return
    yield from _iter_navigation_building_7z_members(archive_path)


def _iter_navigation_building_7z_members(path: Path) -> Iterator[Any]:
    try:
        import py7zr
    except ImportError as exc:
        raise RuntimeError(
            "Reading Juso navigation .7z archives requires py7zr. "
            "Install python-kraddr-geo[spatialite]."
        ) from exc

    with py7zr.SevenZipFile(path) as archive:
        names = [
            name
            for name in archive.getnames()
            if Path(name).name.lower().startswith("match_build_") and name.lower().endswith(".txt")
        ]
    for name in names:
        with tempfile.TemporaryDirectory(prefix="kraddr-geo-7z-") as tmp:
            with py7zr.SevenZipFile(path) as archive:
                archive.extract(path=tmp, targets=[name])
            extracted = Path(tmp) / name
            yield type("_TextMember", (), {"name": name, "content": extracted.read_bytes()})()


def _xy(x: str, y: str) -> tuple[float, float] | None:
    x_value = _float_or_none(x)
    y_value = _float_or_none(y)
    if x_value is None or y_value is None:
        return None
    return (x_value, y_value)


def _float_or_none(value: str) -> float | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    try:
        return float(text_value)
    except ValueError:
        return None


def _strip_number(value: str) -> str:
    text_value = str(value or "").strip()
    return text_value.lstrip("0") or "0"


def _text(raw: Mapping[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _is_no_data_parts(parts: list[str]) -> bool:
    return len(parts) == 1 and parts[0].strip().lower().replace(" ", "") in {"nodata", "no_data"}
