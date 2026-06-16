"""Geocoding orchestration independent from SQLAlchemy/FastAPI."""

from __future__ import annotations

from kortravelgeo.dto.address import AddressStructure, RefinedAddress
from kortravelgeo.dto.common import Point
from kortravelgeo.dto.geocode import (
    GeocodeExtension,
    GeocodeInput,
    GeocodeResponse,
    GeocodeResult,
    SppnMakareaContext,
)
from kortravelgeo.dto.region import RegionHint

from .normalize import parse_address
from .protocols import AddressLookup, GeocodeRepo, SppnAreaLookup
from .responses import refined_from_lookup, service_meta
from .sppn import NationalPointNumber, parse_national_point_number


def _confidence(row: AddressLookup) -> float:
    value = row.confidence
    if row.pt_source == "centroid":
        value = min(value, 0.82)
    return max(0.0, min(value, 1.0))


def _response_from_row(inp: GeocodeInput, row: AddressLookup) -> GeocodeResponse:
    return GeocodeResponse(
        service=service_meta("geocode"),
        status="OK",
        input=inp,
        refined=refined_from_lookup(row),
        result=GeocodeResult(crs=inp.crs, point=row.point) if row.point else None,
        x_extension=GeocodeExtension(
            source="local",
            confidence=_confidence(row),
            bd_mgt_sn=row.bd_mgt_sn,
            rncode_full=row.rncode_full,
            bjd_cd=row.bjd_cd,
            zip_no=row.zip_no,
            zip_source="building_bsi_zon_no" if row.zip_no else None,
            buld_nm=row.buld_nm,
        ),
    )


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


def _response_from_sppn(
    inp: GeocodeInput,
    sppn: NationalPointNumber,
    point_4326: Point,
    area: SppnAreaLookup | None,
) -> GeocodeResponse:
    return GeocodeResponse(
        service=service_meta("geocode"),
        status="OK",
        input=inp,
        refined=RefinedAddress(
            text=f"국가지점번호 {sppn.text}",
            structure=AddressStructure(),
        ),
        result=GeocodeResult(crs="EPSG:4326", point=point_4326),
        x_extension=GeocodeExtension(
            source="local",
            confidence=0.72,
            national_point_number=sppn.text,
            sppn_makarea=_sppn_context(area) if area is not None else None,
        ),
    )


async def geocode(
    repo: GeocodeRepo,
    inp: GeocodeInput,
    *,
    region_hint: RegionHint | None = None,
) -> GeocodeResponse:
    sppn = parse_national_point_number(inp.address)
    if sppn is not None:
        area = await repo.lookup_sppn_area(sppn.point_5179)
        point_4326 = area.point if area is not None and area.point else None
        if point_4326 is None:
            point_4326 = await repo.project_sppn_point_4326(sppn.point_5179)
        if point_4326 is None:
            return GeocodeResponse(service=service_meta("geocode"), status="NOT_FOUND", input=inp)
        return _response_from_sppn(inp, sppn, point_4326, area)

    parts = parse_address(inp.address)
    row: AddressLookup | None
    if inp.type == "road":
        row = await repo.lookup_by_road(parts, region_hint=region_hint)
        if row is None and inp.fallback != "off":
            fuzzy = await repo.fuzzy_roads(parts, limit=5, region_hint=region_hint)
            row = fuzzy[0] if fuzzy else None
    else:
        row = await repo.lookup_by_jibun(parts, region_hint=region_hint)

    if row is None:
        return GeocodeResponse(service=service_meta("geocode"), status="NOT_FOUND", input=inp)
    return _response_from_row(inp, row)
