"""Geocode endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from kraddr.geo.api.deps import get_client
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.dto.geocode import GeocodeResponse

router = APIRouter(tags=["address"])


@router.get("/address/geocode", response_model=GeocodeResponse, response_model_exclude_none=True)
async def geocode(
    address: str = Query(..., min_length=1, max_length=200),
    type: Literal["road", "parcel"] = "road",
    crs: str = "EPSG:4326",
    refine: bool = True,
    simple: bool = False,
    fallback: Literal["off", "local_only", "api"] = "local_only",
    client: AsyncAddressClient = Depends(get_client),
) -> GeocodeResponse:
    return await client.geocode(
        address,
        type=type,
        crs=crs,
        refine=refine,
        simple=simple,
        fallback=fallback,
    )

