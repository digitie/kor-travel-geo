"""Version 2 API DTOs with provider-neutral candidate responses."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, FiniteFloat, field_validator, model_validator
from pydantic_core import PydanticCustomError

from kortravelgeo.dto.common import (
    CRS,
    KOREA_LON_LAT_BOUNDS_MESSAGE,
    AddressType,
    FrozenModel,
    Page,
    Point,
    Status,
    is_korea_lon_lat,
    reject_control_characters,
)
from kortravelgeo.dto.region import RegionHint

V2Source = Literal["local", "vworld", "juso"]
V2MatchKind = Literal["road", "parcel", "keyword", "region", "sppn", "detail", "poi"]
V2FallbackMode = Literal["none", "api"]
V2PointPrecision = Literal["exact", "interpolated", "centroid", "approximate", "grid_cell"]
V2GeometryKind = Literal["building", "region", "road"]
RegionWithinRadiusLevel = Literal["sido", "sigungu", "emd"]
RegionWithinRadiusRelation = Literal["contains", "overlaps"]


class BBoxV2(FrozenModel):
    """EPSG:4326 bounding box in external `(lon, lat)` order."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @model_validator(mode="after")
    def validate_order(self) -> BBoxV2:
        if self.min_lon >= self.max_lon or self.min_lat >= self.max_lat:
            msg = "bbox minimum coordinates must be less than maximum coordinates"
            raise ValueError(msg)
        return self


class AddressV2(FrozenModel):
    """Provider-neutral address projection."""

    type: AddressType | None = None
    full: str
    road_address: str | None = None
    parcel_address: str | None = None
    postal_code: str | None = None
    legal_dong_code: str | None = None
    admin_dong_code: str | None = None
    road_name: str | None = None
    road_name_code: str | None = None
    building_management_number: str | None = None


class RegionV2(FrozenModel):
    sig_cd: str | None = None
    bjd_cd: str | None = None
    sido: str | None = None
    sigungu: str | None = None
    eup_myeon_dong: str | None = None
    legal_dong: str | None = None
    admin_dong: str | None = None


class PlaceV2(FrozenModel):
    name: str
    category_code: str | None = None
    category_name: str | None = None
    phone: str | None = None
    url: str | None = None


class GeometryV2(FrozenModel):
    kind: V2GeometryKind
    crs: CRS = "EPSG:4326"
    geojson: dict[str, Any]
    source_table: str | None = None


class CandidateV2(FrozenModel):
    confidence: float = Field(ge=0.0, le=1.0)
    match_kind: V2MatchKind
    address: AddressV2 | None = None
    point: Point | None = None
    point_precision: V2PointPrecision | None = None
    distance_m: float | None = Field(default=None, ge=0.0)
    bbox: BBoxV2 | None = None
    geometry: GeometryV2 | None = None
    region: RegionV2 | None = None
    place: PlaceV2 | None = None
    source: V2Source = "local"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeocodeV2Input(FrozenModel):
    query: str | None = Field(default=None, min_length=1, max_length=200)
    road_address: str | None = Field(default=None, min_length=1, max_length=200)
    jibun_address: str | None = Field(default=None, min_length=1, max_length=200)
    keyword: str | None = Field(default=None, min_length=1, max_length=200)
    sig_cd: str | None = Field(default=None, pattern=r"^(\d{2}|\d{5})$")
    bjd_cd: str | None = Field(default=None, pattern=r"^(\d{8}|\d{10})$")
    bbox: BBoxV2 | None = None
    limit: int = Field(default=10, ge=1, le=100)
    fallback: V2FallbackMode = "none"
    include_geometry: bool = False

    @field_validator("query", "road_address", "jibun_address", "keyword")
    @classmethod
    def reject_text_control_characters(cls, value: str | None) -> str | None:
        return reject_control_characters(value)

    @model_validator(mode="after")
    def require_query_surface(self) -> GeocodeV2Input:
        if not any((self.query, self.road_address, self.jibun_address, self.keyword)):
            msg = "one of query, road_address, jibun_address, or keyword is required"
            raise ValueError(msg)
        return self

    @property
    def region_hint(self) -> RegionHint | None:
        if self.sig_cd is None and self.bjd_cd is None:
            return None
        return RegionHint(sig_cd=self.sig_cd, bjd_cd=self.bjd_cd)


class GeocodeV2Response(FrozenModel):
    status: Status
    query_id: str = Field(default_factory=lambda: uuid4().hex)
    input: GeocodeV2Input
    candidates: tuple[CandidateV2, ...] = ()
    region_hint_applied: RegionHint | None = None


class ReverseV2Input(FrozenModel):
    lon: FiniteFloat
    lat: FiniteFloat
    crs: CRS = "EPSG:4326"
    include_region: bool = True
    include_zipcode: bool = True
    radius_m: int = Field(default=200, ge=1, le=2_000)
    sig_cd: str | None = Field(default=None, pattern=r"^(\d{2}|\d{5})$")
    bjd_cd: str | None = Field(default=None, pattern=r"^(\d{8}|\d{10})$")

    @model_validator(mode="after")
    def validate_korea_lon_lat(self) -> ReverseV2Input:
        if not is_korea_lon_lat(self.lon, self.lat):
            raise PydanticCustomError(
                "kor_travel_geo.coordinate_bounds",
                KOREA_LON_LAT_BOUNDS_MESSAGE,
            )
        return self

    @property
    def region_hint(self) -> RegionHint | None:
        if self.sig_cd is None and self.bjd_cd is None:
            return None
        return RegionHint(sig_cd=self.sig_cd, bjd_cd=self.bjd_cd)


class ReverseV2Response(FrozenModel):
    status: Status
    query_id: str = Field(default_factory=lambda: uuid4().hex)
    input: ReverseV2Input
    candidates: tuple[CandidateV2, ...] = ()
    region_hint_applied: RegionHint | None = None


class SearchV2Input(Page):
    query: str = Field(min_length=1, max_length=200)
    type: Literal["address", "place", "district", "road", "category"] = "address"
    category_group_code: str | None = Field(default=None, min_length=1, max_length=20)
    sig_cd: str | None = Field(default=None, pattern=r"^(\d{2}|\d{5})$")
    bjd_cd: str | None = Field(default=None, pattern=r"^(\d{8}|\d{10})$")
    bbox: BBoxV2 | None = None

    @property
    def region_hint(self) -> RegionHint | None:
        if self.sig_cd is None and self.bjd_cd is None:
            return None
        return RegionHint(sig_cd=self.sig_cd, bjd_cd=self.bjd_cd)


class SearchV2Response(FrozenModel):
    status: Status
    query_id: str = Field(default_factory=lambda: uuid4().hex)
    input: SearchV2Input
    candidates: tuple[CandidateV2, ...] = ()
    total: int = Field(default=0, ge=0)
    region_hint_applied: RegionHint | None = None


class RegionWithinRadiusCenter(FrozenModel):
    """Query center in external `(lon, lat)` order."""

    lon: float = Field(ge=-180.0, le=180.0)
    lat: float = Field(ge=-90.0, le=90.0)


class RegionWithinRadiusItem(FrozenModel):
    """Administrative region intersecting a POI radius."""

    code: str = Field(min_length=2, max_length=8)
    name: str | None = None
    relation: RegionWithinRadiusRelation


class RegionsWithinRadiusInput(FrozenModel):
    lon: float = Field(ge=-180.0, le=180.0)
    lat: float = Field(ge=-90.0, le=90.0)
    radius_km: float = Field(default=3.0, gt=0.0, le=500.0)
    levels: tuple[RegionWithinRadiusLevel, ...] = ("sigungu", "emd")

    @field_validator("levels", mode="before")
    @classmethod
    def dedupe_levels(cls, value: object) -> object:
        if value is None:
            return ("sigungu", "emd")
        if isinstance(value, str):
            values: Sequence[object] = (value,)
        elif isinstance(value, Sequence):
            values = value
        else:
            return value
        return tuple(dict.fromkeys(values))

    @model_validator(mode="after")
    def require_levels(self) -> RegionsWithinRadiusInput:
        if not self.levels:
            msg = "levels must include at least one of sido, sigungu, or emd"
            raise ValueError(msg)
        return self

    @property
    def center(self) -> RegionWithinRadiusCenter:
        return RegionWithinRadiusCenter(lon=self.lon, lat=self.lat)


class RegionsWithinRadiusResponse(FrozenModel):
    center: RegionWithinRadiusCenter
    radius_km: float = Field(gt=0.0, le=500.0)
    sido: tuple[RegionWithinRadiusItem, ...] = ()
    sigungu: tuple[RegionWithinRadiusItem, ...] = ()
    emd: tuple[RegionWithinRadiusItem, ...] = ()
