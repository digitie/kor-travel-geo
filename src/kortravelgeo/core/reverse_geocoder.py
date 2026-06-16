"""Reverse-geocoding orchestration."""

from __future__ import annotations

from kortravelgeo.dto.geocode import SppnMakareaContext
from kortravelgeo.dto.region import RegionHint
from kortravelgeo.dto.reverse import (
    ReverseExtension,
    ReverseInput,
    ReverseResponse,
    ReverseResultItem,
)

from .protocols import ReverseRepo, SppnAreaLookup
from .responses import service_meta, structure_from_lookup
from .sppn import format_national_point_number_from_5179


def _sppn_context(area: SppnAreaLookup) -> SppnMakareaContext:
    return SppnMakareaContext(
        sig_cd=area.sig_cd,
        makarea_id=area.makarea_id,
        makarea_nm=area.makarea_nm,
        ntfc_yn=area.ntfc_yn,
        ntfc_de=area.ntfc_de,
        mvm_res_cd=area.mvm_res_cd,
        source_file=area.source_file,
        source_yyyymm=area.source_yyyymm,
        area_m2=area.area_m2,
    )


async def reverse_geocode(
    repo: ReverseRepo,
    inp: ReverseInput,
    *,
    region_hint: RegionHint | None = None,
) -> ReverseResponse:
    rows = await repo.nearest(
        inp.point,
        crs=inp.crs,
        address_type=inp.type,
        radius_m=inp.radius_m,
        limit=5,
        region_hint=region_hint,
    )
    sppn_areas = await repo.sppn_areas(inp.point, crs=inp.crs, limit=5)
    point_5179 = await repo.project_reverse_point_5179(inp.point, crs=inp.crs)
    sppn = format_national_point_number_from_5179(point_5179) if point_5179 else None
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
    extension = None
    if sppn is not None or sppn_areas:
        extension = ReverseExtension(
            national_point_number=sppn.text if sppn is not None else None,
            sppn_makarea=tuple(_sppn_context(area) for area in sppn_areas),
        )
    return ReverseResponse(
        service=service_meta("reverse_geocode"),
        status="OK" if items or extension else "NOT_FOUND",
        input=inp,
        result=items,
        x_extension=extension,
    )
