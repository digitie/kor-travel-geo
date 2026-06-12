"""Common pydantic DTO primitives."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, FiniteFloat

type Status = Literal["OK", "NOT_FOUND", "ERROR"]
type ResultSource = Literal["local", "api_juso", "api_vworld", "cache"]
type AddressType = Literal["road", "parcel"]

_CRS_RE = re.compile(r"^EPSG:\d{4,6}$")


class FrozenModel(BaseModel):
    """Base class for immutable API DTOs."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


def normalize_crs(value: object) -> str:
    """Normalize CRS strings such as ``epsg-4326`` to ``EPSG:4326``."""

    if not isinstance(value, str):
        msg = "CRS must be a string"
        raise TypeError(msg)

    text = value.strip().upper().replace("-", ":")
    if text.isdigit():
        text = f"EPSG:{text}"
    elif text.startswith("EPSG") and not text.startswith("EPSG:"):
        suffix = text.removeprefix("EPSG")
        if suffix.isdigit():
            text = f"EPSG:{suffix}"

    if not _CRS_RE.match(text):
        msg = "CRS must look like EPSG:4326"
        raise ValueError(msg)
    return text


type CRS = Annotated[
    str,
    BeforeValidator(normalize_crs),
    Field(description="Coordinate reference system normalized as EPSG:XXXX"),
]


class Point(FrozenModel):
    """Coordinate point. External interfaces use ``x=lon`` and ``y=lat``."""

    x: FiniteFloat
    y: FiniteFloat


class ServiceMeta(FrozenModel):
    name: str
    operation: str
    version: str = "2.0"
    time: str | None = None


class Page(FrozenModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)


class ZipSource(StrEnum):
    BUILDING_BSI_ZON_NO = "building_bsi_zon_no"
    BULK_DELIVERY = "bulk_delivery"
    KODIS_BAS_WITHIN = "kodis_bas_within"
    KODIS_BAS_CENTROID = "kodis_bas_centroid"
    POBOX = "pobox"
