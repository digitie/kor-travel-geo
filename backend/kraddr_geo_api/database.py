"""SQLite/SpatiaLite-backed address and geocoding queries."""

from __future__ import annotations

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
    where_sql, params = _where_clause(query=query, scope=scope)
    params.update({"limit": normalized_page_size, "offset": offset})
    items_sql = sa.text(
        f"""
        select *
        from juso_address_points
        where {where_sql}
        order by source_priority, road_name_code, building_main_no, building_sub_no, point_id
        limit :limit offset :offset
        """
    )
    count_sql = sa.text(f"select count(*) from juso_address_points where {where_sql}")
    current = store()
    with current.engine.connect() as connection:
        rows = connection.execute(items_sql, params).mappings().all()
        total = int(connection.scalar(count_sql, params) or 0)
    return {
        "items": [_row_to_address(row) for row in rows],
        "page": normalized_page,
        "page_size": normalized_page_size,
        "total": total,
        "has_next": offset + normalized_page_size < total,
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


def _where_clause(*, query: str, scope: str) -> tuple[str, dict[str, Any]]:
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    value = query.strip()
    if not value:
        return " and ".join(conditions), params
    like = f"%{_escape_like(value.lower())}%"
    prefix = f"{_escape_like(value)}%"
    params.update({"like": like, "prefix": prefix})
    if scope == "road":
        conditions.append(
            """
            (
                lower(coalesce(road_address, '')) like :like escape '\\'
                or lower(coalesce(road_name, '')) like :like escape '\\'
            )
            """
        )
    elif scope == "jibun":
        conditions.append(
            """
            (
                lower(coalesce(parcel_address, '')) like :like escape '\\'
                or coalesce(legal_dong_code, '') like :prefix escape '\\'
            )
            """
        )
    elif scope == "code":
        conditions.append(
            """
            (
                coalesce(legal_dong_code, '') like :prefix escape '\\'
                or coalesce(road_name_code, '') like :prefix escape '\\'
                or coalesce(building_management_number, '') like :prefix escape '\\'
                or coalesce(postal_code, '') like :prefix escape '\\'
            )
            """
        )
    else:
        conditions.append(
            """
            (
                lower(coalesce(road_address, '')) like :like escape '\\'
                or lower(coalesce(parcel_address, '')) like :like escape '\\'
                or lower(coalesce(building_name, '')) like :like escape '\\'
                or coalesce(legal_dong_code, '') like :prefix escape '\\'
                or coalesce(road_name_code, '') like :prefix escape '\\'
                or coalesce(building_management_number, '') like :prefix escape '\\'
                or coalesce(postal_code, '') like :prefix escape '\\'
            )
            """
        )
    return " and ".join(conditions), params


def _row_to_address(row: sa.RowMapping) -> dict[str, Any]:
    lon, lat = _to_wgs84(row["x"], row["y"])
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
        "boundary": [],
        "radiusMeters": 40 if row["source_dataset"] == "location_summary" else 80,
        "updatedAt": "",
        "tags": [
            tag
            for tag in [row["sido_name"], row["sigungu_name"], row["source_dataset"]]
            if tag
        ],
        "boundaryName": "",
        "boundaryLevel": "",
        "coordinateSource": row["source_dataset"] or row["source"] or "sqlite_spatialite",
    }


def _to_wgs84(x: Any, y: Any) -> tuple[float, float]:
    try:
        from pyproj import Transformer
    except ImportError:
        return float(x), float(y)
    transformer = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(float(x), float(y))
    return float(lon), float(lat)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
