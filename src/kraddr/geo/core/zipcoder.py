"""Zipcode lookup orchestration."""

from __future__ import annotations

from kraddr.geo.dto.zipcode import ZipcodeInput, ZipcodeResponse, ZipcodeResultItem

from .normalize import parse_address
from .protocols import ZipRepo
from .responses import service_meta


async def zipcode(repo: ZipRepo, inp: ZipcodeInput) -> ZipcodeResponse:
    if inp.address is not None:
        rows = await repo.lookup_zipcode_by_address(
            parse_address(inp.address),
            include_bulk=inp.include_bulk,
        )
    elif inp.point is not None:
        rows = await repo.lookup_zipcode_by_point(inp.point, include_bulk=inp.include_bulk)
    else:
        assert inp.bd_mgt_sn is not None
        rows = await repo.lookup_zipcode_by_bd_mgt_sn(inp.bd_mgt_sn, include_bulk=inp.include_bulk)
    items = tuple(
        ZipcodeResultItem(
            zip_no=row.zip_no,
            source=row.source,
            address=row.address,
            bd_mgt_sn=row.bd_mgt_sn,
            detail=row.detail,
        )
        for row in rows
    )
    return ZipcodeResponse(
        service=service_meta("zipcode"),
        status="OK" if items else "NOT_FOUND",
        input=inp,
        result=items,
    )
