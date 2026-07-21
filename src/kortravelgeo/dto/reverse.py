"""Reverse geocode request and response DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_serializer, model_validator
from pydantic_core import PydanticCustomError

from .address import AddressStructure
from .common import (
    CRS,
    KOREA_LON_LAT_BOUNDS_MESSAGE,
    AddressType,
    FrozenModel,
    Point,
    ResultSource,
    ServiceMeta,
    Status,
    ZipSource,
    is_korea_lon_lat,
)
from .geocode import SppnMakareaContext

ReverseType = Literal["both", "road", "parcel"]
VWorldAddressType = Literal["ROAD", "PARCEL"]
VWorldReverseType = Literal["BOTH", "ROAD", "PARCEL"]


class ReverseInput(FrozenModel):
    point: Point
    crs: CRS = "EPSG:4326"
    type: ReverseType = "both"
    zipcode: bool = True
    radius_m: int = Field(default=200, ge=1, le=2_000)
    simple: bool = False

    @field_serializer("type", return_type=VWorldReverseType)
    def serialize_type(self, value: ReverseType) -> VWorldReverseType:
        if value == "both":
            return "BOTH"
        return "ROAD" if value == "road" else "PARCEL"

    @model_validator(mode="after")
    def validate_korea_lon_lat(self) -> ReverseInput:
        if not is_korea_lon_lat(self.point.x, self.point.y):
            raise PydanticCustomError(
                "kor_travel_geo.coordinate_bounds",
                KOREA_LON_LAT_BOUNDS_MESSAGE,
            )
        return self


class ReverseResultItem(FrozenModel):
    type: AddressType
    text: str
    structure: AddressStructure
    point: Point | None = None
    zipcode: str | None = None
    zip_source: ZipSource | None = None
    source: ResultSource = "local"
    distance_m: float | None = Field(default=None, ge=0.0)
    bd_mgt_sn: str | None = None
    rncode_full: str | None = None

    @field_serializer("type", return_type=VWorldAddressType)
    def serialize_type(self, value: AddressType) -> VWorldAddressType:
        return "ROAD" if value == "road" else "PARCEL"


class ReverseExtension(FrozenModel):
    national_point_number: str | None = None
    sppn_makarea: tuple[SppnMakareaContext, ...] = ()


class ReverseResponse(FrozenModel):
    service: ServiceMeta
    status: Status
    input: ReverseInput
    result: tuple[ReverseResultItem, ...] = ()
    x_extension: ReverseExtension | None = None
