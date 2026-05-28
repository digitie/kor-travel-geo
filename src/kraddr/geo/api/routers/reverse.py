"""Reverse-geocode endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from kraddr.geo.api.deps import get_client
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.dto.reverse import ReverseResponse

router = APIRouter(tags=["address"])


@router.get("/address/reverse", response_model=ReverseResponse, response_model_exclude_none=True)
async def reverse_geocode(
    x: float = Query(...),
    y: float = Query(...),
    crs: str = "EPSG:4326",
    type: Literal["both", "road", "parcel"] = "both",
    zipcode: bool = True,
    radius_m: int | None = Query(default=None, ge=1, le=2000),
    sig_cd: str | None = Query(default=None, pattern=r"^(\d{2}|\d{5})$"),
    bjd_cd: str | None = Query(default=None, pattern=r"^(\d{8}|\d{10})$"),
    client: AsyncAddressClient = Depends(get_client),
) -> ReverseResponse:
    return await client.reverse_geocode(
        x,
        y,
        crs=crs,
        type=type,
        zipcode=zipcode,
        radius_m=radius_m,
        sig_cd=sig_cd,
        bjd_cd=bjd_cd,
    )
