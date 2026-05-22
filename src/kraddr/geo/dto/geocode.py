"""Geocode request and response DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .address import RefinedAddress
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

FallbackMode = Literal["off", "local_only", "api"]


class GeocodeInput(FrozenModel):
    address: str = Field(min_length=1, max_length=200)
    type: AddressType = "road"
    crs: CRS = "EPSG:4326"
    refine: bool = True
    simple: bool = False
    fallback: FallbackMode = "local_only"


class GeocodeResult(FrozenModel):
    crs: CRS = "EPSG:4326"
    point: Point


class GeocodeExtension(FrozenModel):
    source: ResultSource = "local"
    confidence: float = Field(ge=0.0, le=1.0)
    bd_mgt_sn: str | None = None
    rncode_full: str | None = None
    bjd_cd: str | None = None
    zip_no: str | None = None
    zip_source: ZipSource | None = None
    buld_nm: str | None = None


class GeocodeResponse(FrozenModel):
    service: ServiceMeta
    status: Status
    input: GeocodeInput
    refined: RefinedAddress | None = None
    result: GeocodeResult | None = None
    x_extension: GeocodeExtension | None = None
