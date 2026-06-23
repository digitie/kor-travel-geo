"""Geocode endpoint."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import ORJSONResponse
from pydantic import BeforeValidator

from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.api.vworld import (
    VWorldErrorEnvelope,
    VWorldGeocodeEnvelope,
    normalize_type_param,
    vworld_success_response,
)
from kortravelgeo.client import AsyncAddressClient

router = APIRouter(tags=["address"])


@router.get(
    "/address/geocode",
    response_model=VWorldGeocodeEnvelope,
    response_model_exclude_none=True,
    responses={400: {"model": VWorldErrorEnvelope, "description": "VWorld 호환 검증·도메인 오류"}},
)
async def geocode(
    address: str = Query(..., min_length=1, max_length=200),
    type: Annotated[Literal["road", "parcel"], BeforeValidator(normalize_type_param)] = "road",
    crs: str = "EPSG:4326",
    refine: bool = True,
    simple: bool = False,
    fallback: Literal["off", "local_only", "api"] = "local_only",
    sig_cd: str | None = Query(default=None, pattern=r"^(\d{2}|\d{5})$"),
    bjd_cd: str | None = Query(default=None, pattern=r"^(\d{8}|\d{10})$"),
    _api_key: None = Depends(require_public_api_key),
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
