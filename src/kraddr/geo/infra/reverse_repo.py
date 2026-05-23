"""Raw SQL reverse geocode repository."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.protocols import ReverseLookup
from kraddr.geo.dto.common import Point

from ._rows import map_reverse

_NEAREST_SQL = text(
    """
WITH target_pt AS (
  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179) AS geom
)
SELECT t.bd_mgt_sn, t.rncode_full, t.rn AS road_nm, t.buld_mnnm, t.buld_slno,
       t.buld_se_cd, t.buld_nm, t.bjd_cd, t.adm_cd, t.adm_kor_nm, t.mntn_yn,
       t.lnbr_mnnm, t.lnbr_slno, t.zip_no, t.si_nm, t.sgg_nm, t.emd_nm, t.li_nm,
       t.pnu, t.pt_source,
       ST_X(t.pt_4326) AS lon, ST_Y(t.pt_4326) AS lat,
       ST_Distance(t.pt_5179, p.geom) AS distance_m
  FROM mv_geocode_target t, target_pt p
 WHERE t.pt_5179 IS NOT NULL
   AND ST_DWithin(t.pt_5179, p.geom, :radius_m)
 ORDER BY t.pt_5179 <-> p.geom
 LIMIT :limit
"""
)


class ReverseRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def nearest(
        self,
        point: Point,
        *,
        crs: str,
        address_type: Literal["both", "road", "parcel"],
        radius_m: int,
        limit: int = 5,
    ) -> list[ReverseLookup]:
        in_srid = int(crs.split(":", 1)[1])
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    _NEAREST_SQL,
                    {
                        "x": point.x,
                        "y": point.y,
                        "in_srid": in_srid,
                        "radius_m": radius_m,
                        "limit": limit,
                    },
                )
            ).mappings().all()
        if address_type == "both":
            both: list[ReverseLookup] = []
            for row in rows:
                raw = dict(row)
                both.append(map_reverse(raw, address_type="road"))
                both.append(map_reverse(raw, address_type="parcel"))
            return both
        if address_type == "parcel":
            return [map_reverse(dict(row), address_type="parcel") for row in rows]
        return [map_reverse(dict(row), address_type="road") for row in rows]
