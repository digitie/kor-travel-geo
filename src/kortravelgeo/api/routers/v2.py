"""Provider-neutral v2 address endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from kortravelgeo.api.deps import get_client
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.v2 import (
    GeocodeV2Input,
    GeocodeV2Response,
    RegionsWithinRadiusInput,
    RegionsWithinRadiusResponse,
    ReverseV2Input,
    ReverseV2Response,
    SearchV2Input,
    SearchV2Response,
    V2ErrorEnvelope,
)

router = APIRouter(tags=["v2"])

# v2 endpoints return the v2 error envelope on validation/domain failure (ADR-060 §4); the
# structured 4xx is intended input-safety (T-173). Declaring it makes the published contract
# match the wire and lets the OpenAPI customization drop the misleading auto-422.
_V2_VALIDATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": V2ErrorEnvelope, "description": "v2 error envelope (ADR-060 §4)"}
}


@router.post(
    "/geocode",
    response_model=GeocodeV2Response,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def geocode_v2(
    req: GeocodeV2Input,
    client: AsyncAddressClient = Depends(get_client),
) -> GeocodeV2Response:
    return await client.geocode(
        query=req.query,
        road_address=req.road_address,
        jibun_address=req.jibun_address,
        keyword=req.keyword,
        sig_cd=req.sig_cd,
        bjd_cd=req.bjd_cd,
        bbox=req.bbox,
        limit=req.limit,
        fallback=req.fallback,
        include_geometry=req.include_geometry,
    )


@router.post(
    "/reverse",
    response_model=ReverseV2Response,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def reverse_v2(
    req: ReverseV2Input,
    client: AsyncAddressClient = Depends(get_client),
) -> ReverseV2Response:
    return await client.reverse(
        req.lon,
        req.lat,
        crs=req.crs,
        include_region=req.include_region,
        include_zipcode=req.include_zipcode,
        radius_m=req.radius_m,
        sig_cd=req.sig_cd,
        bjd_cd=req.bjd_cd,
        include_geometry=req.include_geometry,
    )


@router.post(
    "/search",
    response_model=SearchV2Response,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def search_v2(
    req: SearchV2Input,
    client: AsyncAddressClient = Depends(get_client),
) -> SearchV2Response:
    return await client.search(
        query=req.query,
        type=req.type,
        category_group_code=req.category_group_code,
        page=req.page,
        size=req.size,
        sig_cd=req.sig_cd,
        bjd_cd=req.bjd_cd,
        bbox=req.bbox,
        include_geometry=req.include_geometry,
    )


@router.post(
    "/regions/within-radius",
    response_model=RegionsWithinRadiusResponse,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def regions_within_radius_v2(
    req: RegionsWithinRadiusInput,
    client: AsyncAddressClient = Depends(get_client),
) -> RegionsWithinRadiusResponse:
    return await client.regions_within_radius(
        lon=req.lon,
        lat=req.lat,
        radius_km=req.radius_km,
        levels=req.levels,
    )
