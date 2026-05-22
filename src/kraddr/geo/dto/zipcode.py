"""Zipcode lookup request and response DTOs."""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import FrozenModel, Point, ServiceMeta, Status, ZipSource


class ZipcodeInput(FrozenModel):
    address: str | None = Field(default=None, min_length=1, max_length=200)
    point: Point | None = None
    bd_mgt_sn: str | None = Field(default=None, min_length=1, max_length=25)
    include_bulk: bool = True

    @model_validator(mode="after")
    def require_one_lookup_key(self) -> ZipcodeInput:
        values = [self.address, self.point, self.bd_mgt_sn]
        if sum(value is not None for value in values) != 1:
            msg = "exactly one of address, point, or bd_mgt_sn is required"
            raise ValueError(msg)
        return self


class ZipcodeResultItem(FrozenModel):
    zip_no: str
    source: ZipSource
    address: str | None = None
    bd_mgt_sn: str | None = None
    detail: str | None = None


class ZipcodeResponse(FrozenModel):
    service: ServiceMeta
    status: Status
    input: ZipcodeInput
    result: tuple[ZipcodeResultItem, ...] = ()
