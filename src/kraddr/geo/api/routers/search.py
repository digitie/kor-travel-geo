"""Search endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from kraddr.geo.api.deps import get_client
from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.dto.search import SearchResponse

router = APIRouter(tags=["search"])


@router.get("/address/search", response_model=SearchResponse, response_model_exclude_none=True)
async def search(
    query: str = Query(..., min_length=1, max_length=200),
    type: Literal["address", "place", "district", "road"] = "address",
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    client: AsyncAddressClient = Depends(get_client),
) -> SearchResponse:
    return await client.search(query, type=type, page=page, size=size)

