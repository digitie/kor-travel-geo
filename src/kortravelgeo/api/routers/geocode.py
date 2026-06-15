"""Geocode endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import ORJSONResponse

from kortravelgeo.api.deps import get_client
from kortravelgeo.api.vworld import VWorldGeocodeEnvelope, vworld_success_response
from kortravelgeo.client import AsyncAddressClient

router = APIRouter(tags=["address"])


@router.get(
    "/address/geocode",
    response_model=VWorldGeocodeEnvelope,
    response_model_exclude_none=True,
)
async def geocode(
    address: str = Query(..., min_length=1, max_length=200),
    type: Literal["road", "parcel"] = "road",
    crs: str = "EPSG:4326",
    refine: bool = True,
    simple: bool = False,
    fallback: Literal["off", "local_only", "api"] = "local_only",
    sig_cd: str | None = Query(default=None, pattern=r"^(\d{2}|\d{5})$"),
    bjd_cd: str | None = Query(default=None, pattern=r"^(\d{8}|\d{10})$"),
    client: AsyncAddressClient = Depends(get_client),
) -> ORJSONResponse:
    response = await client._geocode_v1(
        address,
        type=type,
        crs=crs,
        refine=refine,
        simple=simple,
        fallback=fallback,
        sig_cd=sig_cd,
        bjd_cd=bjd_cd,
    )
    return vworld_success_response(response)
