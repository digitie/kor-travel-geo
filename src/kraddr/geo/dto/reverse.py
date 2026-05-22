"""Reverse geocode request and response DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .address import AddressStructure
from .common import (
    CRS,
    AddressType,
    FrozenModel,
    Point,
    ResultSource,
    ServiceMeta,
    Status,
    ZipSource,
)

ReverseType = Literal["both", "road", "parcel"]


class ReverseInput(FrozenModel):
    point: Point
    crs: CRS = "EPSG:4326"
    type: ReverseType = "both"
    zipcode: bool = True
    radius_m: int = Field(default=200, ge=1, le=2_000)

    @model_validator(mode="after")
    def validate_korea_lon_lat(self) -> ReverseInput:
        if not (123 < self.point.x < 132 and 32 < self.point.y < 39):
            msg = "point must be within Korea lon/lat bounds: 123 < x < 132, 32 < y < 39"
            raise ValueError(msg)
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


class ReverseResponse(FrozenModel):
    service: ServiceMeta
    status: Status
    input: ReverseInput
    result: tuple[ReverseResultItem, ...] = ()
