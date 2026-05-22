"""Postal box lookup DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import FrozenModel, Page, ServiceMeta, Status

PoboxKind = Literal["PO", "PG", "ALL"]


class PoboxInput(Page):
    query: str | None = Field(default=None, min_length=1, max_length=200)
    si_nm: str | None = Field(default=None, min_length=1)
    sgg_nm: str | None = Field(default=None, min_length=1)
    kind: PoboxKind = "ALL"


class PoboxResultItem(FrozenModel):
    zip_no: str
    pobox_kind: Literal["PO", "PG"]
    pobox_name: str | None = None
    pobox_no_mn: int | None = Field(default=None, ge=0)
    pobox_no_sl: int | None = Field(default=None, ge=0)
    si_nm: str | None = None
    sgg_nm: str | None = None
    emd_nm: str | None = None
    bjd_cd: str | None = None


class PoboxResponse(FrozenModel):
    service: ServiceMeta
    status: Status
    input: PoboxInput
    result: tuple[PoboxResultItem, ...] = ()
    total: int = Field(default=0, ge=0)
