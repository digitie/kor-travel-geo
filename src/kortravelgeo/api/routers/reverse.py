"""Reverse-geocode endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import ORJSONResponse

from kortravelgeo.api.deps import get_client
from kortravelgeo.api.vworld import VWorldReverseEnvelope, vworld_success_response
from kortravelgeo.client import AsyncAddressClient

router = APIRouter(tags=["address"])


@router.get(
    "/address/reverse",
    response_model=VWorldReverseEnvelope,
    response_model_exclude_none=True,
)
async def reverse_geocode(
    x: float = Query(...),
    y: float = Query(...),
    crs: str = "EPSG:4326",
    type: Literal["both", "road", "parcel"] = "both",
    zipcode: bool = True,
    simple: bool = False,
    radius_m: int | None = Query(default=None, ge=1, le=2000),
    sig_cd: str | None = Query(default=None, pattern=r"^(\d{2}|\d{5})$"),
    bjd_cd: str | None = Query(default=None, pattern=r"^(\d{8}|\d{10})$"),
    client: AsyncAddressClient = Depends(get_client),
) -> ORJSONResponse:
    response = await client._reverse_geocode_v1(
        x,
        y,
        crs=crs,
        type=type,
        zipcode=zipcode,
        simple=simple,
        radius_m=radius_m,
        sig_cd=sig_cd,
        bjd_cd=bjd_cd,
    )
    return vworld_success_response(response)
