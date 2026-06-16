"""PostGIS-backed coordinate projection helpers."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.dto.common import Point, normalize_crs

SRID_WGS84 = 4326
SRID_KOREA_2000 = 5179
ROUNDTRIP_MAX_ERROR_M = 0.001

_POINT_TO_5179_SQL = text(
    """
WITH target_pt AS (
  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179) AS geom
)
SELECT ST_X(geom) AS x5179,
       ST_Y(geom) AS y5179
  FROM target_pt
"""
)

_POINT_5179_TO_4326_SQL = text(
    """
WITH target_pt AS (
  SELECT ST_SetSRID(ST_MakePoint(:x, :y), 5179) AS geom
)
SELECT ST_X(ST_Transform(geom, 4326)) AS lon,
       ST_Y(ST_Transform(geom, 4326)) AS lat
  FROM target_pt
"""
)


def srid_from_crs(crs: str) -> int:
    """Return the EPSG SRID integer for a CRS string."""

    normalized = normalize_crs(crs)
    return int(normalized.split(":", 1)[1])


async def project_point_to_5179(
    engine: AsyncEngine,
    point: Point,
    *,
    crs: str,
) -> Point | None:
    """Project an input point from ``crs`` into EPSG:5179."""

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                _POINT_TO_5179_SQL,
                {"x": point.x, "y": point.y, "in_srid": srid_from_crs(crs)},
            )
        ).mappings().first()
    if row is None or row["x5179"] is None or row["y5179"] is None:
        return None
    return Point(x=float(row["x5179"]), y=float(row["y5179"]))


async def project_point_5179_to_4326(engine: AsyncEngine, point: Point) -> Point | None:
    """Project an EPSG:5179 point into EPSG:4326 `(lon, lat)` order."""

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                _POINT_5179_TO_4326_SQL,
                {"x": point.x, "y": point.y},
            )
        ).mappings().first()
    if row is None or row["lon"] is None or row["lat"] is None:
        return None
    return Point(x=float(row["lon"]), y=float(row["lat"]))
