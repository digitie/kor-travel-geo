"""Raw SQL zipcode repository."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.normalize import AddrParts
from kraddr.geo.core.protocols import ZipLookup
from kraddr.geo.dto.common import Point

from ._rows import map_zip

_ZIP_BY_BD = text(
    """
SELECT zip_no, 'building_bsi_zon_no' AS source,
       si_nm || ' ' || sgg_nm || ' ' || rn || ' ' || buld_mnnm::text AS address,
       bd_mgt_sn, buld_nm AS detail
  FROM mv_geocode_target
 WHERE bd_mgt_sn = :bd_mgt_sn AND zip_no IS NOT NULL
UNION ALL
SELECT zip_no, 'bulk_delivery' AS source, NULL AS address, bd_mgt_sn, detail
  FROM postal_bulk_delivery
 WHERE :include_bulk AND bd_mgt_sn = :bd_mgt_sn
"""
)

_ZIP_BY_POINT = text(
    """
WITH target_pt AS (
  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 4326), 5179) AS geom
)
SELECT bas_id AS zip_no, 'kodis_bas_within' AS source, NULL AS address,
       NULL AS bd_mgt_sn, NULL AS detail
  FROM tl_kodis_bas k, target_pt p
 WHERE ST_Contains(k.geom, p.geom)
 LIMIT 1
"""
)

_ZIP_BY_ADDRESS = text(
    """
SELECT zip_no, 'building_bsi_zon_no' AS source,
       si_nm || ' ' || sgg_nm || ' ' || rn || ' ' || buld_mnnm::text AS address,
       bd_mgt_sn, buld_nm AS detail
  FROM mv_geocode_target
 WHERE (:road_nrm IS NULL OR rn_nrm = :road_nrm)
   AND (:emd IS NULL OR emd_nm = :emd OR li_nm = :emd)
   AND (:mnnm IS NULL OR buld_mnnm = :mnnm OR lnbr_mnnm = :mnnm)
   AND zip_no IS NOT NULL
 ORDER BY CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END, bd_mgt_sn
 LIMIT 10
"""
)


class ZipRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def lookup_zipcode_by_address(
        self,
        parts: AddrParts,
        *,
        include_bulk: bool,
    ) -> list[ZipLookup]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    _ZIP_BY_ADDRESS,
                    {"road_nrm": parts.road_nrm, "emd": parts.li or parts.emd, "mnnm": parts.mnnm},
                )
            ).mappings().all()
        return [map_zip(dict(row)) for row in rows]

    async def lookup_zipcode_by_point(
        self,
        point: Point,
        *,
        include_bulk: bool,
    ) -> list[ZipLookup]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(_ZIP_BY_POINT, {"x": point.x, "y": point.y})
            ).mappings().all()
        return [map_zip(dict(row)) for row in rows]

    async def lookup_zipcode_by_bd_mgt_sn(
        self,
        bd_mgt_sn: str,
        *,
        include_bulk: bool,
    ) -> list[ZipLookup]:
        async with self.engine.connect() as conn:
            rows = (
                await conn.execute(
                    _ZIP_BY_BD,
                    {"bd_mgt_sn": bd_mgt_sn, "include_bulk": include_bulk},
                )
            ).mappings().all()
        return [map_zip(dict(row)) for row in rows]
