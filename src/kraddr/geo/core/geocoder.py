"""Geocoding orchestration independent from SQLAlchemy/FastAPI."""

from __future__ import annotations

from kraddr.geo.dto.address import AddressStructure, RefinedAddress
from kraddr.geo.dto.geocode import (
    GeocodeExtension,
    GeocodeInput,
    GeocodeResponse,
    GeocodeResult,
    SppnMakareaContext,
)

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
    area: SppnAreaLookup,
) -> GeocodeResponse:
    return GeocodeResponse(
        service=service_meta("geocode"),
        status="OK",
        input=inp,
        refined=RefinedAddress(
            text=f"국가지점번호 {sppn.text}",
            structure=AddressStructure(),
        ),
        result=GeocodeResult(crs="EPSG:4326", point=area.point) if area.point else None,
        x_extension=GeocodeExtension(
            source="local",
            confidence=0.72,
            national_point_number=sppn.text,
            sppn_makarea=_sppn_context(area),
        ),
    )


async def geocode(repo: GeocodeRepo, inp: GeocodeInput) -> GeocodeResponse:
    sppn = parse_national_point_number(inp.address)
    if sppn is not None:
        area = await repo.lookup_sppn_area(sppn.point_5179)
        if area is None:
            return GeocodeResponse(service=service_meta("geocode"), status="NOT_FOUND", input=inp)
        return _response_from_sppn(inp, sppn, area)

    parts = parse_address(inp.address)
    row: AddressLookup | None
    if inp.type == "road":
        row = await repo.lookup_by_road(parts)
        if row is None and inp.fallback != "off":
            fuzzy = await repo.fuzzy_roads(parts, limit=5)
            row = fuzzy[0] if fuzzy else None
    else:
        row = await repo.lookup_by_jibun(parts)

    if row is None:
        return GeocodeResponse(service=service_meta("geocode"), status="NOT_FOUND", input=inp)
    return _response_from_row(inp, row)
