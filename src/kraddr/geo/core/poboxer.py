"""Postal box lookup orchestration."""

from __future__ import annotations

from kraddr.geo.dto.pobox import PoboxInput, PoboxResponse, PoboxResultItem

from .protocols import PoboxRepo
from .responses import service_meta


async def pobox(repo: PoboxRepo, inp: PoboxInput) -> PoboxResponse:
    rows, total = await repo.lookup_poboxes(
        query=inp.query,
        si_nm=inp.si_nm,
        sgg_nm=inp.sgg_nm,
        kind=inp.kind,
        page=inp.page,
        size=inp.size,
    )
    items = tuple(
        PoboxResultItem(
            zip_no=row.zip_no,
            pobox_kind=row.pobox_kind,
            pobox_name=row.pobox_name,
            pobox_no_mn=row.pobox_no_mn,
            pobox_no_sl=row.pobox_no_sl,
            si_nm=row.si_nm,
            sgg_nm=row.sgg_nm,
            emd_nm=row.emd_nm,
            bjd_cd=row.bjd_cd,
        )
        for row in rows
    )
    return PoboxResponse(
        service=service_meta("pobox"),
        status="OK" if items else "NOT_FOUND",
        input=inp,
        result=items,
        total=total,
    )

