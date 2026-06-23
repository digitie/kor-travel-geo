"""Pobox endpoint."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.pobox import PoboxResponse

router = APIRouter(tags=["pobox"])


@router.get("/address/pobox", response_model=PoboxResponse, response_model_exclude_none=True)
async def pobox(
    query: str | None = Query(default=None, min_length=1, max_length=200),
    si_nm: str | None = Query(default=None, min_length=1),
    sgg_nm: str | None = Query(default=None, min_length=1),
    kind: Literal["PO", "PG", "ALL"] = "ALL",
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    _api_key: None = Depends(require_public_api_key),
    client: AsyncAddressClient = Depends(get_client),
) -> PoboxResponse:
    return await client.pobox(
        query=query,
        si_nm=si_nm,
        sgg_nm=sgg_nm,
        kind=kind,
        page=page,
        size=size,
    )
