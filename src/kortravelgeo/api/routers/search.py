"""Search endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.search import SearchResponse

router = APIRouter(tags=["search"])


@router.get("/address/search", response_model=SearchResponse, response_model_exclude_none=True)
async def search(
    query: str = Query(..., min_length=1, max_length=200),
    type: Literal["address", "place", "district", "road"] = "address",
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    sig_cd: str | None = Query(default=None, pattern=r"^(\d{2}|\d{5})$"),
    bjd_cd: str | None = Query(default=None, pattern=r"^(\d{8}|\d{10})$"),
    _api_key: None = Depends(require_public_api_key),
    client: AsyncAddressClient = Depends(get_client),
) -> SearchResponse:
    return await client._search_v1(
        query,
        type=type,
        page=page,
        size=size,
        sig_cd=sig_cd,
        bjd_cd=bjd_cd,
    )
