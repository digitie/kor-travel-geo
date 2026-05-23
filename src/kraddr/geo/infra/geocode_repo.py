"""Raw SQL geocode repository."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.normalize import AddrParts
from kraddr.geo.core.protocols import AddressLookup

from ._rows import map_address

_BASE_SELECT = """
SELECT bd_mgt_sn, rncode_full, rn AS road_nm, buld_mnnm, buld_slno, buld_se_cd,
       buld_nm, bjd_cd, adm_cd, adm_kor_nm, mntn_yn, lnbr_mnnm, lnbr_slno, zip_no,
       si_nm, sgg_nm, emd_nm, li_nm, pnu, pt_source,
       CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_X(pt_4326) END AS lon,
       CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_Y(pt_4326) END AS lat
  FROM mv_geocode_target
"""

_LOOKUP_ROAD = text(
    _BASE_SELECT
    + """
 WHERE (:si IS NULL OR si_nm = :si)
   AND (:sgg IS NULL OR sgg_nm = :sgg)
   AND rn_nrm = :road_nrm
   AND buld_mnnm = :mnnm
   AND buld_slno = :slno
   AND (:buld_se_cd IS NULL OR buld_se_cd = :buld_se_cd)
 ORDER BY CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END, bd_mgt_sn
 LIMIT 1
"""
)

_LOOKUP_JIBUN = text(
    _BASE_SELECT
    + """
 WHERE (:si IS NULL OR si_nm = :si)
   AND (:sgg IS NULL OR sgg_nm = :sgg)
   AND (:emd IS NULL OR emd_nm = :emd OR li_nm = :emd)
   AND mntn_yn = :mntn_yn
   AND lnbr_mnnm = :mnnm
   AND lnbr_slno = :slno
 ORDER BY CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END, bd_mgt_sn
 LIMIT 1
"""
)

_FUZZY_ROADS = text(
    _BASE_SELECT
    + """
       , similarity(rn_nrm, :road_nrm) AS confidence
 WHERE (:si IS NULL OR si_nm = :si)
   AND (:sgg IS NULL OR sgg_nm = :sgg)
   AND rn_nrm % :road_nrm
   AND buld_mnnm = :mnnm
 ORDER BY similarity(rn_nrm, :road_nrm) DESC,
          CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END,
          bd_mgt_sn
 LIMIT :limit
"""
)


class GeocodeRepository:
    """Geocode lookups against ``mv_geocode_target``."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def lookup_by_road(self, parts: AddrParts) -> AddressLookup | None:
        if parts.road_nrm is None or parts.mnnm is None:
            return None
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    _LOOKUP_ROAD,
                    {
                        "si": parts.si,
                        "sgg": parts.sgg,
                        "road_nrm": parts.road_nrm,
                        "mnnm": parts.mnnm,
                        "slno": parts.slno,
                        "buld_se_cd": parts.buld_se_cd,
                    },
                )
            ).mappings().first()
        return map_address(dict(row), address_type="road") if row else None

    async def lookup_by_jibun(self, parts: AddrParts) -> AddressLookup | None:
        if parts.mnnm is None:
            return None
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    _LOOKUP_JIBUN,
                    {
                        "si": parts.si,
                        "sgg": parts.sgg,
                        "emd": parts.li or parts.emd,
                        "mntn_yn": parts.mntn_yn,
                        "mnnm": parts.mnnm,
                        "slno": parts.slno,
                    },
                )
            ).mappings().first()
        return map_address(dict(row), address_type="parcel") if row else None

    async def fuzzy_roads(self, parts: AddrParts, *, limit: int = 5) -> list[AddressLookup]:
        if parts.road_nrm is None or parts.mnnm is None:
            return []
        async with self.engine.begin() as conn:
            await conn.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.42"))
            rows = (
                await conn.execute(
                    _FUZZY_ROADS,
                    {
                        "si": parts.si,
                        "sgg": parts.sgg,
                        "road_nrm": parts.road_nrm,
                        "mnnm": parts.mnnm,
                        "limit": limit,
                    },
                )
            ).mappings().all()
        return [map_address(dict(row), address_type="road") for row in rows]
