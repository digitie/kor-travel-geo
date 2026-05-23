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
    client: AsyncAddressClient = Depends(get_client),
) -> ReverseResponse:
    return await client.reverse_geocode(
        x,
        y,
        crs=crs,
        type=type,
        zipcode=zipcode,
        radius_m=radius_m,
    )

