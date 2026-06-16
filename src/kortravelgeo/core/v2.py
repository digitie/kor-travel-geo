"""V2 response conversion helpers built on the stable v1 core responses."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from kortravelgeo.dto.address import AddressStructure
from kortravelgeo.dto.common import AddressType, Point, ResultSource, Status
from kortravelgeo.dto.geocode import GeocodeResponse, SppnMakareaContext
from kortravelgeo.dto.reverse import ReverseResponse, ReverseResultItem
from kortravelgeo.dto.search import SearchResponse, SearchResultItem
from kortravelgeo.dto.v2 import (
    AddressV2,
    CandidateV2,
    GeocodeV2Input,
    GeocodeV2Response,
    PlaceV2,
    RegionV2,
    ReverseV2Input,
    ReverseV2Response,
    SearchV2Input,
    SearchV2Response,
    V2MatchKind,
    V2PointPrecision,
    V2Source,
)

from .confidence import (
    geometry_confidence,
    reverse_distance_confidence,
    search_confidence,
    sppn_reverse_confidence,
)
from .protocols import GeometryLookup


def geocode_v2_from_v1(inp: GeocodeV2Input, response: GeocodeResponse) -> GeocodeV2Response:
    candidate: CandidateV2 | None = None
    if response.refined is not None:
        source = response.x_extension.source if response.x_extension else "local"
        candidate = CandidateV2(
            confidence=response.x_extension.confidence if response.x_extension else 0.0,
            match_kind=_geocode_match_kind(inp, response),
            address=_address_from_v1(
                full=response.refined.text,
                address_type=response.input.type,
                structure=response.refined.structure,
                point=response.result.point if response.result else None,
                metadata=_geocode_metadata(response),
            ),
            point=response.result.point if response.result else None,
            point_precision=_geocode_point_precision(response),
            region=_region_from_structure(response.refined.structure),
            source=_source_from_v1(source),
            metadata=_geocode_metadata(response),
        )
    return GeocodeV2Response(
        status=response.status,
        input=inp,
        candidates=(candidate,) if candidate is not None else (),
        region_hint_applied=inp.region_hint,
    )


def reverse_v2_from_v1(inp: ReverseV2Input, response: ReverseResponse) -> ReverseV2Response:
    candidates = [*(_candidate_from_reverse_item(inp, item) for item in response.result)]
    if response.x_extension is not None:
        national_point_number = response.x_extension.national_point_number
        candidates.extend(
            _candidate_from_sppn_area(inp, area, national_point_number=national_point_number)
            for area in response.x_extension.sppn_makarea
        )
        if national_point_number and not response.x_extension.sppn_makarea:
            candidates.append(_candidate_from_sppn_number(inp, national_point_number))
    return ReverseV2Response(
        status=response.status,
        input=inp,
        candidates=dedupe_candidates(candidates),
        region_hint_applied=inp.region_hint,
    )


def search_v2_from_v1(inp: SearchV2Input, response: SearchResponse) -> SearchV2Response:
    return SearchV2Response(
        status=response.status,
        input=inp,
        candidates=dedupe_candidates(_candidate_from_search_item(item) for item in response.result),
        total=response.total,
        region_hint_applied=inp.region_hint,
    )


def geocode_v2_from_search(inp: GeocodeV2Input, response: SearchV2Response) -> GeocodeV2Response:
    candidates = dedupe_candidates(response.candidates, limit=inp.limit)
    return GeocodeV2Response(
        status="OK" if candidates else response.status,
        input=inp,
        candidates=candidates,
        region_hint_applied=inp.region_hint,
    )


def geocode_v2_from_geometry_lookups(
    inp: GeocodeV2Input,
    rows: list[GeometryLookup],
) -> GeocodeV2Response:
    candidates = dedupe_candidates(
        (_candidate_from_geometry_lookup(inp, row) for row in rows),
        limit=inp.limit,
    )
    return GeocodeV2Response(
        status="OK" if candidates else "NOT_FOUND",
        input=inp,
        candidates=candidates,
        region_hint_applied=inp.region_hint,
    )


def merge_geocode_v2_responses(
    inp: GeocodeV2Input,
    *responses: GeocodeV2Response,
) -> GeocodeV2Response:
    """Merge producer paths while preserving first-candidate priority."""
    candidates = dedupe_candidates(
        (candidate for response in responses for candidate in response.candidates),
        limit=inp.limit,
    )
    status: Status = "OK" if candidates else _merged_geocode_status(responses)
    return GeocodeV2Response(
        status=status,
        input=inp,
        candidates=candidates,
        region_hint_applied=inp.region_hint,
    )


def dedupe_candidates(
    candidates: Iterable[CandidateV2],
    *,
    limit: int | None = None,
) -> tuple[CandidateV2, ...]:
    seen: set[tuple[object, ...]] = set()
    deduped: list[CandidateV2] = []
    for candidate in candidates:
        key = _candidate_dedupe_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
        if limit is not None and len(deduped) >= limit:
            break
    return tuple(deduped)


def with_candidate_geometry(
    candidate: CandidateV2,
    geometry: GeometryLookup | None,
    *,
    include_geometry: bool,
) -> CandidateV2:
    if geometry is None:
        return candidate
    point_precision = candidate.point_precision
    if point_precision is None and geometry.kind == "region":
        point_precision = "centroid"
    return candidate.model_copy(
        update={
            "bbox": geometry.bbox if include_geometry else candidate.bbox,
            "geometry": geometry.geometry if include_geometry else None,
            "point_precision": point_precision,
        }
    )


def _geocode_match_kind(inp: GeocodeV2Input, response: GeocodeResponse) -> V2MatchKind:
    if response.x_extension and response.x_extension.national_point_number:
        return "sppn"
    if inp.keyword:
        return "keyword"
    return response.input.type


def _merged_geocode_status(responses: tuple[GeocodeV2Response, ...]) -> Status:
    for response in responses:
        if response.status == "ERROR":
            return "ERROR"
    return "NOT_FOUND"


def _candidate_dedupe_key(candidate: CandidateV2) -> tuple[object, ...]:
    national_point_number = _as_str(candidate.metadata.get("national_point_number"))
    if national_point_number:
        return ("sppn", national_point_number)

    bd_mgt_sn = _as_str(candidate.metadata.get("bd_mgt_sn"))
    if bd_mgt_sn:
        return ("building", bd_mgt_sn)

    rncode_full = _as_str(
        candidate.metadata.get("rncode_full")
        or (candidate.address.road_name_code if candidate.address else None)
    )
    if rncode_full and candidate.match_kind == "road":
        return ("road", rncode_full, _address_full(candidate), _point_key(candidate.point))

    region_code = (
        candidate.region.bjd_cd or candidate.region.sig_cd if candidate.region is not None else None
    )
    if region_code and candidate.match_kind == "region":
        return ("region", region_code)

    if candidate.place is not None:
        return (
            "place",
            candidate.place.name,
            candidate.place.category_code,
            _point_key(candidate.point),
        )

    if candidate.address is not None:
        return (
            "address",
            candidate.match_kind,
            candidate.address.full,
            _point_key(candidate.point),
        )

    return (
        "candidate",
        candidate.match_kind,
        candidate.source,
        _point_key(candidate.point),
        tuple(sorted((key, repr(value)) for key, value in candidate.metadata.items())),
    )


def _candidate_from_reverse_item(inp: ReverseV2Input, item: ReverseResultItem) -> CandidateV2:
    return CandidateV2(
        confidence=reverse_distance_confidence(item.distance_m, inp.radius_m),
        match_kind=item.type,
        address=_address_from_v1(
            full=item.text,
            address_type=item.type,
            structure=item.structure,
            point=item.point,
            metadata={"distance_m": item.distance_m, "zip_source": item.zip_source},
            postal_code=item.zipcode,
        ),
        point=item.point,
        distance_m=item.distance_m,
        region=_region_from_structure(item.structure),
        source=_source_from_v1(item.source),
        metadata={"distance_m": item.distance_m, "zip_source": item.zip_source},
    )


def _candidate_from_sppn_area(
    inp: ReverseV2Input,
    area: SppnMakareaContext,
    *,
    national_point_number: str | None = None,
) -> CandidateV2:
    metadata = {
        "national_point_number": national_point_number,
        "sig_cd": area.sig_cd,
        "makarea_id": area.makarea_id,
        "makarea_nm": area.makarea_nm,
        "ntfc_yn": area.ntfc_yn,
        "ntfc_de": area.ntfc_de,
        "mvm_res_cd": area.mvm_res_cd,
        "source_file": area.source_file,
        "source_yyyymm": area.source_yyyymm,
        "area_m2": area.area_m2,
    }
    return CandidateV2(
        confidence=sppn_reverse_confidence(),
        match_kind="sppn",
        point=Point(x=inp.lon, y=inp.lat),
        point_precision="grid_cell",
        region=RegionV2(sig_cd=area.sig_cd),
        source="local",
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _candidate_from_sppn_number(inp: ReverseV2Input, national_point_number: str) -> CandidateV2:
    return CandidateV2(
        confidence=sppn_reverse_confidence(),
        match_kind="sppn",
        point=Point(x=inp.lon, y=inp.lat),
        point_precision="grid_cell",
        source="local",
        metadata={"national_point_number": national_point_number},
    )


def _candidate_from_search_item(item: SearchResultItem) -> CandidateV2:
    match_kind = _search_match_kind(item)
    address = (
        _address_from_v1(
            full=item.address or item.title,
            address_type="road" if item.type == "road" else None,
            structure=item.structure,
            point=item.point,
            metadata={},
        )
        if item.address or item.structure
        else None
    )
    place = PlaceV2(name=item.title) if item.type == "place" else None
    return CandidateV2(
        confidence=search_confidence(item.score),
        match_kind=match_kind,
        address=address,
        point=item.point,
        point_precision="centroid" if match_kind == "region" and item.point else None,
        region=_region_from_structure(item.structure),
        place=place,
        source=_source_from_v1(item.source),
        metadata={"score": item.score},
    )


def _candidate_from_geometry_lookup(inp: GeocodeV2Input, row: GeometryLookup) -> CandidateV2:
    match_kind: V2MatchKind = "region" if row.kind == "region" else "road"
    metadata = {
        "score": row.score,
        "geometry_kind": row.kind,
        "geometry_source_table": row.geometry.source_table,
        "rncode_full": row.rncode_full,
        "bd_mgt_sn": row.bd_mgt_sn,
    }
    return CandidateV2(
        confidence=geometry_confidence(row.score),
        match_kind=match_kind,
        address=_address_from_geometry_lookup(row),
        point=row.point,
        point_precision="centroid" if row.point else None,
        bbox=row.bbox if inp.include_geometry else None,
        geometry=row.geometry if inp.include_geometry else None,
        region=_region_from_geometry_lookup(row),
        source="local",
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _address_from_geometry_lookup(row: GeometryLookup) -> AddressV2 | None:
    if row.title is None:
        return None
    return AddressV2(
        type="road" if row.kind in {"building", "road"} else None,
        full=row.title,
        road_address=row.title if row.kind in {"building", "road"} else None,
        road_name=row.road_name,
        road_name_code=row.rncode_full,
        building_management_number=row.bd_mgt_sn,
    )


def _region_from_geometry_lookup(row: GeometryLookup) -> RegionV2 | None:
    if not any((row.sig_cd, row.bjd_cd, row.sido, row.sigungu, row.eup_myeon_dong, row.li)):
        return None
    return RegionV2(
        sig_cd=row.sig_cd,
        bjd_cd=row.bjd_cd,
        sido=row.sido,
        sigungu=row.sigungu,
        legal_dong=row.eup_myeon_dong,
    )


def _geocode_point_precision(response: GeocodeResponse) -> V2PointPrecision | None:
    if response.x_extension and response.x_extension.national_point_number:
        return "grid_cell"
    return None


def _address_from_v1(
    *,
    full: str,
    address_type: AddressType | None,
    structure: AddressStructure | None,
    point: Point | None,
    metadata: dict[str, Any],
    postal_code: str | None = None,
) -> AddressV2:
    return AddressV2(
        type=address_type,
        full=full,
        road_address=full if address_type == "road" else None,
        parcel_address=full if address_type == "parcel" else None,
        postal_code=postal_code or _as_str(metadata.get("zip_no")),
        legal_dong_code=(
            structure.level4LC if structure and len(structure.level4LC or "") >= 8 else None
        ),
        admin_dong_code=structure.level4AC if structure else None,
        road_name=structure.level5 if structure else None,
        road_name_code=_as_str(metadata.get("rncode_full")),
        building_management_number=_as_str(metadata.get("bd_mgt_sn")),
    )


def _region_from_structure(structure: AddressStructure | None) -> RegionV2 | None:
    if structure is None:
        return None
    if not any(
        (
            structure.level1,
            structure.level2,
            structure.level4L,
            structure.level4LC,
            structure.level4A,
            structure.level4AC,
        )
    ):
        return None
    code = structure.level4LC
    sig_cd = code[:5] if code and len(code) >= 5 else None
    bjd_cd = code if code and len(code) >= 8 else None
    return RegionV2(
        sig_cd=sig_cd,
        bjd_cd=bjd_cd,
        sido=structure.level1,
        sigungu=structure.level2,
        legal_dong=structure.level4L,
        admin_dong=structure.level4A,
    )


def _search_match_kind(item: SearchResultItem) -> V2MatchKind:
    if item.type == "place":
        return "poi"
    if item.type == "district":
        return "region"
    return "road"


def _geocode_metadata(response: GeocodeResponse) -> dict[str, Any]:
    if response.x_extension is None:
        return {}
    return {
        "bd_mgt_sn": response.x_extension.bd_mgt_sn,
        "rncode_full": response.x_extension.rncode_full,
        "bjd_cd": response.x_extension.bjd_cd,
        "zip_no": response.x_extension.zip_no,
        "zip_source": response.x_extension.zip_source,
        "buld_nm": response.x_extension.buld_nm,
        "detail": response.refined.structure.detail if response.refined else None,
        "national_point_number": response.x_extension.national_point_number,
    }


def _source_from_v1(source: ResultSource) -> V2Source:
    if source == "api_vworld":
        return "vworld"
    if source == "api_juso":
        return "juso"
    return "local"


def _as_str(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _address_full(candidate: CandidateV2) -> str | None:
    return candidate.address.full if candidate.address is not None else None


def _point_key(point: Point | None) -> tuple[float, float] | None:
    if point is None:
        return None
    return (round(point.x, 7), round(point.y, 7))
