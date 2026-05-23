"""Geocoding orchestration independent from SQLAlchemy/FastAPI."""

from __future__ import annotations

from kraddr.geo.dto.geocode import GeocodeExtension, GeocodeInput, GeocodeResponse, GeocodeResult

from .normalize import parse_address
from .protocols import AddressLookup, GeocodeRepo
from .responses import refined_from_lookup, service_meta


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


async def geocode(repo: GeocodeRepo, inp: GeocodeInput) -> GeocodeResponse:
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
