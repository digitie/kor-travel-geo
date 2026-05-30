"""V2 response conversion helpers built on the stable v1 core responses."""

from __future__ import annotations

from typing import Any

from kraddr.geo.dto.address import AddressStructure
from kraddr.geo.dto.common import AddressType, Point, ResultSource
from kraddr.geo.dto.geocode import GeocodeResponse
from kraddr.geo.dto.reverse import ReverseResponse, ReverseResultItem
from kraddr.geo.dto.search import SearchResponse, SearchResultItem
from kraddr.geo.dto.v2 import (
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
    return ReverseV2Response(
        status=response.status,
        input=inp,
        candidates=tuple(_candidate_from_reverse_item(inp, item) for item in response.result),
        region_hint_applied=inp.region_hint,
    )


def search_v2_from_v1(inp: SearchV2Input, response: SearchResponse) -> SearchV2Response:
    return SearchV2Response(
        status=response.status,
        input=inp,
        candidates=tuple(_candidate_from_search_item(item) for item in response.result),
        total=response.total,
        region_hint_applied=inp.region_hint,
    )


def geocode_v2_from_search(inp: GeocodeV2Input, response: SearchV2Response) -> GeocodeV2Response:
    return GeocodeV2Response(
        status=response.status,
        input=inp,
        candidates=response.candidates[: inp.limit],
        region_hint_applied=inp.region_hint,
    )


def geocode_v2_from_geometry_lookups(
    inp: GeocodeV2Input,
    rows: list[GeometryLookup],
) -> GeocodeV2Response:
    candidates = tuple(_candidate_from_geometry_lookup(inp, row) for row in rows[: inp.limit])
    return GeocodeV2Response(
        status="OK" if candidates else "NOT_FOUND",
        input=inp,
        candidates=candidates,
        region_hint_applied=inp.region_hint,
    )


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


def _candidate_from_reverse_item(inp: ReverseV2Input, item: ReverseResultItem) -> CandidateV2:
    return CandidateV2(
        confidence=_reverse_confidence(item.distance_m, inp.radius_m),
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
        confidence=item.score or 0.0,
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
    confidence = row.score if row.score is not None else 0.9
    match_kind: V2MatchKind = "region" if row.kind == "region" else "road"
    metadata = {
        "score": row.score,
        "geometry_kind": row.kind,
        "geometry_source_table": row.geometry.source_table,
        "rncode_full": row.rncode_full,
        "bd_mgt_sn": row.bd_mgt_sn,
    }
    return CandidateV2(
        confidence=max(0.0, min(1.0, confidence)),
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


def _reverse_confidence(distance_m: float | None, radius_m: int) -> float:
    if distance_m is None:
        return 1.0
    return max(0.0, min(1.0, 1.0 - (distance_m / radius_m)))


def _geocode_point_precision(response: GeocodeResponse) -> V2PointPrecision | None:
    if response.x_extension and response.x_extension.national_point_number:
        return "approximate"
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
        return "keyword"
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
    return source


def _as_str(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)
