"""Zipcode endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from kortravelgeo.api.deps import get_client
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.zipcode import ZipcodeResponse

router = APIRouter(tags=["zipcode"])


@router.get("/address/zipcode", response_model=ZipcodeResponse, response_model_exclude_none=True)
async def zipcode(
    address: str | None = Query(default=None, min_length=1, max_length=200),
    x: float | None = None,
    y: float | None = None,
    bd_mgt_sn: str | None = Query(default=None, min_length=1, max_length=25),
    include_bulk: bool = True,
    client: AsyncAddressClient = Depends(get_client),
) -> ZipcodeResponse:
    point = (x, y) if x is not None and y is not None else None
    return await client.zipcode(
        address=address,
        point=point,
        bd_mgt_sn=bd_mgt_sn,
        include_bulk=include_bulk,
    )

