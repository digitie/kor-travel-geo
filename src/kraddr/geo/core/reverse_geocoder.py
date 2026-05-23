"""Reverse-geocoding orchestration."""

from __future__ import annotations

from kraddr.geo.dto.reverse import ReverseInput, ReverseResponse, ReverseResultItem

from .protocols import ReverseRepo
from .responses import service_meta, structure_from_lookup


async def reverse_geocode(repo: ReverseRepo, inp: ReverseInput) -> ReverseResponse:
    rows = await repo.nearest(
        inp.point,
        crs=inp.crs,
        address_type=inp.type,
        radius_m=inp.radius_m,
        limit=5,
    )
    items = tuple(
        ReverseResultItem(
            type=row.address_type,
            text=row.text,
            structure=structure_from_lookup(row),
            point=row.point,
            zipcode=row.zip_no if inp.zipcode else None,
            zip_source="building_bsi_zon_no" if inp.zipcode and row.zip_no else None,
            source="local",
            distance_m=row.distance_m,
        )
        for row in rows
    )
    return ReverseResponse(
        service=service_meta("reverse_geocode"),
        status="OK" if items else "NOT_FOUND",
        input=inp,
        result=items,
    )

