"""SQLite/SpatiaLite-backed address and geocoding queries."""

from __future__ import annotations

import math
from collections import OrderedDict
from functools import lru_cache
from typing import Any

import sqlalchemy as sa

from kraddr.geo import SpatialiteAddressStore

from .config import load_settings


@lru_cache(maxsize=1)
def store() -> SpatialiteAddressStore:
    settings = load_settings()
    return SpatialiteAddressStore(
        settings.spatialite_path,
        load_spatialite=True,
        vworld_api_key=settings.vworld_api_key,
        vworld_domain=settings.vworld_domain,
    )


def health() -> dict[str, Any]:
    """Return the backend and geocoding database status."""

    current = store()
    with current.engine.connect() as connection:
        boundary_count = int(
            connection.scalar(sa.text("select count(*) from juso_boundary_polygons")) or 0
        )
        sources = connection.execute(
            sa.text(
                """
                select source_dataset, count(*) as row_count
                from juso_address_points
                group by source_dataset
                order by source_dataset
                """
            )
        ).mappings().all()
    return {
        "ok": True,
        "mode": "sqlite_spatialite",
        "spatialite_path": str(load_settings().spatialite_path),
        "address_point_count": current.count_points(),
        "boundary_count": boundary_count,
        "sources": [dict(row) for row in sources],
        "spatialite_enabled": current.spatialite_enabled,
        "sqlalchemy": sa.__version__,
    }


def list_addresses(
    *,
    query: str = "",
    scope: str = "all",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Return address point candidates in the same shape used by the web UI."""

    normalized_page = max(page, 1)
    normalized_page_size = max(1, min(page_size, 100))
    offset = (normalized_page - 1) * normalized_page_size
    current = store()
    with current.engine.connect() as connection:
        if query.strip():
            rows, total, has_next = _search_address_rows(
                connection,
                query=query,
                scope=scope,
                page_size=normalized_page_size,
                offset=offset,
            )
        else:
            params = {"limit": normalized_page_size + 1, "offset": offset}
            rows = connection.execute(
                sa.text(
                    """
                    select *
                    from juso_address_points
                    order by
                        source_priority,
                        road_name_code,
                        building_main_no,
                        building_sub_no,
                        point_id
                    limit :limit offset :offset
                    """
                ),
                params,
            ).mappings().all()
            has_next = len(rows) > normalized_page_size
            rows = rows[:normalized_page_size]
            total = int(
                connection.scalar(sa.text("select count(*) from juso_address_points")) or 0
            )
        boundary_cache: dict[str, dict[str, Any]] = {}
        items = [
            _row_to_address(row, connection=connection, boundary_cache=boundary_cache)
            for row in rows
        ]
    return {
        "items": items,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "has_next": has_next,
    }


def geocode(
    *,
    query: str = "",
    road_name_code: str | None = None,
    legal_dong_code: str | None = None,
    underground_yn: str | None = None,
    building_main_no: str | int | None = None,
    building_sub_no: str | int | None = None,
    crs: str = "EPSG:4326",
    limit: int = 10,
) -> dict[str, Any]:
    candidates = store().get_coord(
        {
            "query": query or None,
            "rnMgtSn": road_name_code,
            "admCd": legal_dong_code,
            "udrtYn": underground_yn,
            "buldMnnm": building_main_no,
            "buldSlno": building_sub_no,
            "crs": crs,
            "limit": limit,
        }
    )
    return {
        "items": [item.model_dump(mode="json") for item in candidates],
        "total": len(candidates),
    }


def reverse_geocode(
    *,
    x: float,
    y: float,
    crs: str = "EPSG:4326",
    max_distance_m: float = 50.0,
) -> dict[str, Any]:
    candidate = store().get_address(
        {
            "x": x,
            "y": y,
            "crs": crs,
            "max_distance_m": max_distance_m,
        }
    )
    return {"item": candidate.model_dump(mode="json") if candidate else None}


def lookup_postal_code(zipcode: str, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    candidates = store().lookup_postal_code({"zipNo": zipcode, "limit": limit, "offset": offset})
    return {
        "items": [item.model_dump(mode="json") for item in candidates],
        "total": len(candidates),
    }


_SEARCH_INDEXES = {
    "road_name": "ix_juso_points_road_name",
    "road_address": "ix_juso_points_road_address",
    "parcel_address": "ix_juso_points_parcel_address",
    "building_name": "ix_juso_points_building_name",
    "legal_dong_code": "ix_juso_points_legal_dong",
    "sido_name": "ix_juso_points_sido_name",
    "sigungu_name": "ix_juso_points_sigungu_name",
    "eup_myeon_dong_name": "ix_juso_points_eup_myeon_dong_name",
    "road_name_code": "ix_juso_points_road_lookup",
    "building_management_number": "ix_juso_points_building_mgmt",
    "postal_code": "ix_juso_points_postal_lookup",
}

_SEARCH_COLUMNS_BY_SCOPE = {
    "road": ("road_name", "road_address", "sido_name", "sigungu_name", "eup_myeon_dong_name"),
    "jibun": (
        "parcel_address",
        "legal_dong_code",
        "sido_name",
        "sigungu_name",
        "eup_myeon_dong_name",
    ),
    "code": (
        "legal_dong_code",
        "road_name_code",
        "building_management_number",
        "postal_code",
    ),
    "all": (
        "road_name",
        "road_address",
        "parcel_address",
        "building_name",
        "legal_dong_code",
        "sido_name",
        "sigungu_name",
        "eup_myeon_dong_name",
        "road_name_code",
        "building_management_number",
        "postal_code",
    ),
}
_FTS_COLUMNS_BY_SCOPE = {
    "road": ("road_name", "road_address"),
    "jibun": ("parcel_address", "road_address"),
    "all": ("road_name", "road_address", "parcel_address", "building_name"),
}
_FTS_MIN_QUERY_LENGTH = 3
_BOUNDARY_RESPONSE_CACHE_MAX_SIZE = 2048
_BOUNDARY_RESPONSE_CACHE: OrderedDict[
    int, tuple[tuple[str, str, str, int], dict[str, Any]]
] = OrderedDict()


def _search_address_rows(
    connection: sa.Connection,
    *,
    query: str,
    scope: str,
    page_size: int,
    offset: int,
) -> tuple[list[sa.RowMapping], int, bool]:
    value = query.strip()
    if (
        scope in _FTS_COLUMNS_BY_SCOPE
        and len(value) >= _FTS_MIN_QUERY_LENGTH
        and _has_ready_fts_index(connection)
    ):
        fts_rows, fts_total, fts_has_next = _search_address_rows_fts(
            connection,
            query=value,
            scope=scope,
            page_size=page_size,
            offset=offset,
        )
        if fts_rows:
            return fts_rows, fts_total, fts_has_next

    prefix_end = _prefix_end(value)
    columns = _SEARCH_COLUMNS_BY_SCOPE.get(scope, _SEARCH_COLUMNS_BY_SCOPE["all"])
    rowid_queries = [
        f"""
        select rowid
        from juso_address_points indexed by {_SEARCH_INDEXES[column]}
        where {column} >= :prefix_start and {column} < :prefix_end
        """
        for column in columns
    ]
    rows = connection.execute(
        sa.text(
            f"""
            with candidate_rowids(rowid) as (
                {" union ".join(rowid_queries)}
            )
            select p.*
            from juso_address_points as p
            join candidate_rowids as c on p.rowid = c.rowid
            order by
                p.source_priority,
                p.road_name_code,
                p.building_main_no,
                p.building_sub_no,
                p.point_id
            limit :limit offset :offset
            """
        ),
        {
            "prefix_start": value,
            "prefix_end": prefix_end,
            "limit": page_size + 1,
            "offset": offset,
        },
    ).mappings().all()
    has_next = len(rows) > page_size
    rows = rows[:page_size]
    total = offset + len(rows) + (1 if has_next else 0)
    return list(rows), total, has_next


def _search_address_rows_fts(
    connection: sa.Connection,
    *,
    query: str,
    scope: str,
    page_size: int,
    offset: int,
) -> tuple[list[sa.RowMapping], int, bool]:
    match_query = _fts_match_query(query, scope=scope)
    rows = connection.execute(
        sa.text(
            """
            with candidate_rowids(rowid) as (
                select rowid
                from juso_address_fts
                where juso_address_fts match :match_query
            )
            select p.*
            from juso_address_points as p
            join candidate_rowids as c on p.rowid = c.rowid
            order by
                p.source_priority,
                p.road_name_code,
                p.building_main_no,
                p.building_sub_no,
                p.point_id
            limit :limit offset :offset
            """
        ),
        {"match_query": match_query, "limit": page_size + 1, "offset": offset},
    ).mappings().all()
    total = int(
        connection.scalar(
            sa.text(
                """
                select count(*)
                from juso_address_fts
                where juso_address_fts match :match_query
                """
            ),
            {"match_query": match_query},
        )
        or 0
    )
    has_next = offset + page_size < total
    rows = rows[:page_size]
    return list(rows), total, has_next


def _has_ready_fts_index(connection: sa.Connection) -> bool:
    exists = connection.scalar(
        sa.text("select 1 from sqlite_master where type = 'table' and name = 'juso_address_fts'")
    )
    if not exists:
        return False
    ready = connection.scalar(
        sa.text(
            """
            select 1
            from juso_spatial_metadata
            where key = 'address_search_index_ready'
            limit 1
            """
        )
    )
    return bool(ready)


def _fts_match_query(query: str, *, scope: str) -> str:
    escaped = query.replace('"', '""')
    phrase = f'"{escaped}"'
    columns = _FTS_COLUMNS_BY_SCOPE.get(scope)
    if not columns:
        return phrase
    return f"{{{' '.join(columns)}}} : {phrase}"


def _prefix_end(value: str) -> str:
    return f"{value[:-1]}{chr(ord(value[-1]) + 1)}"


def _row_to_address(
    row: sa.RowMapping,
    *,
    connection: sa.Connection | None = None,
    boundary_cache: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    lon, lat = _to_wgs84(row["x"], row["y"])
    boundary = (
        _boundary_for_address_row(connection, row, boundary_cache=boundary_cache)
        if connection is not None
        else _empty_boundary()
    )
    return {
        "id": row["point_id"],
        "title": row["road_address"] or row["parcel_address"] or row["point_id"],
        "category": "road",
        "roadAddress": row["road_address"] or "",
        "jibunAddress": row["parcel_address"] or "",
        "postalCode": row["postal_code"] or "",
        "legalDongCode": row["legal_dong_code"] or "",
        "roadNameCode": row["road_name_code"] or "",
        "pnu": "",
        "coordinate": {"lat": lat, "lng": lon},
        "boundary": boundary["boundary"],
        "radiusMeters": 40 if row["source_dataset"] == "location_summary" else 80,
        "updatedAt": "",
        "tags": [
            tag
            for tag in [row["sido_name"], row["sigungu_name"], row["source_dataset"]]
            if tag
        ],
        "boundaryName": boundary["boundaryName"],
        "boundaryLevel": boundary["boundaryLevel"],
        "coordinateSource": row["source_dataset"] or row["source"] or "sqlite_spatialite",
    }


def _boundary_for_address_row(
    connection: sa.Connection,
    row: sa.RowMapping,
    *,
    boundary_cache: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    legal_dong_code = str(row["legal_dong_code"] or "")
    if not legal_dong_code:
        return _empty_boundary()

    if boundary_cache is not None and legal_dong_code in boundary_cache:
        return boundary_cache[legal_dong_code]

    boundary_row = _find_boundary_row(connection, legal_dong_code)
    if boundary_row is None:
        result = _empty_boundary()
    else:
        boundary_id_key = f"boundary:{boundary_row['id']}"
        if boundary_cache is not None and boundary_id_key in boundary_cache:
            result = boundary_cache[boundary_id_key]
        else:
            result = _boundary_result(boundary_row)
            if boundary_cache is not None:
                boundary_cache[boundary_id_key] = result

    if boundary_cache is not None:
        boundary_cache[legal_dong_code] = result
    return result


def _find_boundary_row(connection: sa.Connection, legal_dong_code: str) -> sa.RowMapping | None:
    sigungu_code = legal_dong_code[:5] if len(legal_dong_code) >= 5 else ""
    sido_code = legal_dong_code[:2] if len(legal_dong_code) >= 2 else ""
    legal_token = f"%{legal_dong_code}%"
    emd_token = f"%{legal_dong_code[:8]}%" if len(legal_dong_code) >= 8 else legal_token
    sigungu_token = f"%{sigungu_code}%" if sigungu_code else legal_token
    sido_token = f"%{sido_code}%" if sido_code else legal_token
    row = connection.execute(
        sa.text(
            """
            select id, source_name, boundary_level, srid, geom_wkt
            from juso_boundary_polygons
            where legal_dong_code = :legal_dong_code
               or source_code like :legal_token
               or source_code like :emd_token
               or (boundary_level = 'sigungu' and source_code like :sigungu_token)
               or (boundary_level = 'sido' and source_code like :sido_token)
            order by
                case
                    when legal_dong_code = :legal_dong_code then 0
                    when boundary_level in ('legal_dong', 'eup_myeon_dong')
                         and source_code like :emd_token then 1
                    when boundary_level = 'sigungu'
                         and source_code like :sigungu_token then 2
                    when boundary_level = 'sido'
                         and source_code like :sido_token then 3
                    else 9
                end,
                id
            limit 1
            """
        ),
        {
            "legal_dong_code": legal_dong_code,
            "legal_token": legal_token,
            "emd_token": emd_token,
            "sigungu_token": sigungu_token,
            "sido_token": sido_token,
        },
    ).mappings().first()
    return row


def _boundary_result(row: sa.RowMapping) -> dict[str, Any]:
    geom_wkt = row["geom_wkt"] or ""
    boundary_id = int(row["id"])
    signature = (
        str(row["source_name"] or ""),
        str(row["boundary_level"] or ""),
        str(row["srid"] or ""),
        hash(geom_wkt),
    )
    cached = _BOUNDARY_RESPONSE_CACHE.get(boundary_id)
    if cached is not None and cached[0] == signature:
        _BOUNDARY_RESPONSE_CACHE.move_to_end(boundary_id)
        return cached[1]

    result = {
        "boundary": _boundary_points(row),
        "boundaryName": row["source_name"] or "",
        "boundaryLevel": row["boundary_level"] or "",
    }
    if not result["boundary"]:
        result = _empty_boundary()

    _BOUNDARY_RESPONSE_CACHE[boundary_id] = (signature, result)
    _BOUNDARY_RESPONSE_CACHE.move_to_end(boundary_id)
    while len(_BOUNDARY_RESPONSE_CACHE) > _BOUNDARY_RESPONSE_CACHE_MAX_SIZE:
        _BOUNDARY_RESPONSE_CACHE.popitem(last=False)
    return result


def _boundary_points(row: sa.RowMapping) -> list[dict[str, float]]:
    try:
        from shapely import wkt
    except ImportError:
        return []

    try:
        geometry = wkt.loads(row["geom_wkt"])
    except Exception:
        return []
    if geometry.is_empty:
        return []

    if geometry.geom_type == "MultiPolygon":
        geometry = max(geometry.geoms, key=lambda item: item.area)
    if geometry.geom_type != "Polygon":
        return []

    srid = str(row["srid"] or "5179")
    tolerance = 0.00025 if srid == "4326" else 25.0
    geometry = geometry.simplify(tolerance, preserve_topology=True)
    if geometry.geom_type == "MultiPolygon":
        geometry = max(geometry.geoms, key=lambda item: item.area)
    if geometry.geom_type != "Polygon":
        return []

    coordinates = list(geometry.exterior.coords)
    if not coordinates:
        return []
    max_points = 800
    if len(coordinates) > max_points:
        step = math.ceil(len(coordinates) / max_points)
        coordinates = coordinates[::step]
        if coordinates[0] != coordinates[-1]:
            coordinates.append(coordinates[0])

    points = []
    for x, y, *_ in coordinates:
        lon, lat = _transform_to_wgs84(x, y, source_crs=f"EPSG:{srid}")
        if math.isfinite(lat) and math.isfinite(lon):
            points.append({"lat": lat, "lng": lon})
    return points


def _empty_boundary() -> dict[str, Any]:
    return {"boundary": [], "boundaryName": "", "boundaryLevel": ""}


def _to_wgs84(x: Any, y: Any) -> tuple[float, float]:
    return _transform_to_wgs84(x, y, source_crs="EPSG:5179")


def _transform_to_wgs84(x: Any, y: Any, *, source_crs: str) -> tuple[float, float]:
    try:
        transformer = _wgs84_transformer(source_crs)
    except ImportError:
        return float(x), float(y)
    lon, lat = transformer.transform(float(x), float(y))
    return float(lon), float(lat)


@lru_cache(maxsize=8)
def _wgs84_transformer(source_crs: str) -> Any:
    from pyproj import Transformer

    return Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
