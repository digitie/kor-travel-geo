"""Search request and response DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .address import AddressStructure
from .common import CRS, FrozenModel, Page, Point, ResultSource, ServiceMeta, Status

SearchType = Literal["address", "place", "district", "road"]


class BBox(FrozenModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @model_validator(mode="after")
    def validate_order(self) -> BBox:
        if self.min_x >= self.max_x or self.min_y >= self.max_y:
            msg = "bbox minimum coordinates must be less than maximum coordinates"
            raise ValueError(msg)
        return self


class SearchInput(Page):
    query: str = Field(min_length=1, max_length=200)
    type: SearchType = "address"
    category: str | None = None
    crs: CRS = "EPSG:4326"
    bbox: BBox | None = None


class SearchResultItem(FrozenModel):
    type: SearchType
    title: str
    address: str | None = None
    structure: AddressStructure | None = None
    point: Point | None = None
    source: ResultSource = "local"
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class SearchResponse(FrozenModel):
    service: ServiceMeta
    status: Status
    input: SearchInput
    result: tuple[SearchResultItem, ...] = ()
    total: int = Field(default=0, ge=0)
