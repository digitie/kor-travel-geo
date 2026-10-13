"""Provider-neutral v2 address endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from kortravelgeo.api.dataset_ref import get_dataset_ref
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.v2 import (
    DatasetRef,
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

def _stamp[
    R: (GeocodeV2Response, ReverseV2Response, SearchV2Response, RegionsWithinRadiusResponse)
](response: R, dataset: DatasetRef | None) -> R:
    """Attach the active release's dataset stamp (ADR-069 D7) to a frozen v2 response."""
    if dataset is None:
        return response
    return response.model_copy(update={"dataset": dataset})


# v2 endpoints return the v2 error envelope on validation/domain failure (ADR-060 §4); the
# structured 4xx is intended input-safety (T-173). Declaring it makes the published contract
# match the wire and lets the OpenAPI customization drop the misleading auto-422.
_V2_VALIDATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": V2ErrorEnvelope, "description": "v2 error envelope (ADR-060 §4)"},
    401: {"model": V2ErrorEnvelope, "description": "공개 API key 인증 실패"},
}


@router.post(
    "/geocode",
    response_model=GeocodeV2Response,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def geocode_v2(
    req: GeocodeV2Input,
    _api_key: None = Depends(require_public_api_key),
    client: AsyncAddressClient = Depends(get_client),
    dataset: DatasetRef | None = Depends(get_dataset_ref),
) -> GeocodeV2Response:
    response = await client.geocode(
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
    return _stamp(response, dataset)


@router.post(
    "/reverse",
    response_model=ReverseV2Response,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def reverse_v2(
    req: ReverseV2Input,
    _api_key: None = Depends(require_public_api_key),
    client: AsyncAddressClient = Depends(get_client),
    dataset: DatasetRef | None = Depends(get_dataset_ref),
) -> ReverseV2Response:
    response = await client.reverse(
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
    return _stamp(response, dataset)


@router.post(
    "/search",
    response_model=SearchV2Response,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def search_v2(
    req: SearchV2Input,
    _api_key: None = Depends(require_public_api_key),
    client: AsyncAddressClient = Depends(get_client),
    dataset: DatasetRef | None = Depends(get_dataset_ref),
) -> SearchV2Response:
    response = await client.search(
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
    return _stamp(response, dataset)


@router.post(
    "/regions/within-radius",
    response_model=RegionsWithinRadiusResponse,
    response_model_exclude_none=True,
    responses=_V2_VALIDATION_RESPONSES,
)
async def regions_within_radius_v2(
    req: RegionsWithinRadiusInput,
    _api_key: None = Depends(require_public_api_key),
    client: AsyncAddressClient = Depends(get_client),
    dataset: DatasetRef | None = Depends(get_dataset_ref),
) -> RegionsWithinRadiusResponse:
    response = await client.regions_within_radius(
        lon=req.lon,
        lat=req.lat,
        radius_km=req.radius_km,
        levels=req.levels,
    )
    return _stamp(response, dataset)
