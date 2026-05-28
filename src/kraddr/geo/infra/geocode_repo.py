"""Raw SQL geocode repository."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.normalize import AddrParts
from kraddr.geo.core.protocols import AddressLookup, SppnAreaLookup
from kraddr.geo.dto.common import Point
from kraddr.geo.dto.region import RegionHint, region_params

from ._rows import map_address, map_sppn_area

_BASE_SELECT = """
SELECT bd_mgt_sn, rncode_full, rn AS road_nm, buld_mnnm, buld_slno, buld_se_cd,
       buld_nm, bjd_cd, adm_cd, adm_kor_nm, mntn_yn, lnbr_mnnm, lnbr_slno, zip_no,
       si_nm, sgg_nm, emd_nm, li_nm, pnu, pt_source,
       CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_X(pt_4326) END AS lon,
       CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_Y(pt_4326) END AS lat
  FROM mv_geocode_target
"""

_REGION_FILTER = """
   AND (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
   AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
   AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
   AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
"""

_TEXT_SEARCH_REGION_FILTER = """
   AND (CAST(:sig_cd_filter AS text) IS NULL OR ts.sig_cd = CAST(:sig_cd_filter AS text))
   AND (
     CAST(:sig_cd_prefix AS text) IS NULL
     OR ts.sido_cd = left(CAST(:sig_cd_prefix AS text), 2)
   )
   AND (CAST(:bjd_cd_filter AS text) IS NULL OR ts.bjd_cd = CAST(:bjd_cd_filter AS text))
   AND (CAST(:bjd_cd_prefix AS text) IS NULL OR ts.bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
"""

_LOOKUP_ROAD = text(
    _BASE_SELECT
    + """
 WHERE (CAST(:si AS text) IS NULL OR si_nm = CAST(:si AS text))
   AND (CAST(:sgg AS text) IS NULL OR sgg_nm = CAST(:sgg AS text))
"""
    + _REGION_FILTER
    + """
   AND rn_nrm = :road_nrm
   AND buld_mnnm = :mnnm
   AND buld_slno = :slno
   AND (CAST(:buld_se_cd AS text) IS NULL OR buld_se_cd = CAST(:buld_se_cd AS text))
 ORDER BY CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END, bd_mgt_sn
 LIMIT 1
"""
)

_LOOKUP_JIBUN = text(
    _BASE_SELECT
    + """
 WHERE (CAST(:si AS text) IS NULL OR si_nm = CAST(:si AS text))
   AND (CAST(:sgg AS text) IS NULL OR sgg_nm = CAST(:sgg AS text))
   AND (CAST(:emd AS text) IS NULL OR emd_nm = CAST(:emd AS text) OR li_nm = CAST(:emd AS text))
"""
    + _REGION_FILTER
    + """
   AND mntn_yn = :mntn_yn
   AND lnbr_mnnm = :mnnm
   AND lnbr_slno = :slno
 ORDER BY CASE WHEN pt_source = 'entrance' THEN 0 ELSE 1 END, bd_mgt_sn
 LIMIT 1
"""
)

_FUZZY_ROADS = text(
    """
WITH candidates AS MATERIALIZED (
  SELECT ts.bd_mgt_sn,
         similarity(ts.rn_nrm, :road_nrm) AS confidence
    FROM mv_geocode_text_search ts
   WHERE (CAST(:si AS text) IS NULL OR ts.si_nm = CAST(:si AS text))
     AND (CAST(:sgg AS text) IS NULL OR ts.sgg_nm = CAST(:sgg AS text))
"""
    + _TEXT_SEARCH_REGION_FILTER
    + """
     AND ts.rn_nrm % :road_nrm
     AND ts.buld_mnnm = :mnnm
   ORDER BY confidence DESC,
            CASE WHEN ts.pt_source = 'entrance' THEN 0 ELSE 1 END,
            ts.bd_mgt_sn
   LIMIT :limit
)
SELECT t.bd_mgt_sn, t.rncode_full, t.rn AS road_nm, t.buld_mnnm, t.buld_slno, t.buld_se_cd,
       t.buld_nm, t.bjd_cd, t.adm_cd, t.adm_kor_nm, t.mntn_yn, t.lnbr_mnnm, t.lnbr_slno,
       t.zip_no, t.si_nm, t.sgg_nm, t.emd_nm, t.li_nm, t.pnu, t.pt_source,
       CASE WHEN t.pt_4326 IS NULL THEN NULL ELSE ST_X(t.pt_4326) END AS lon,
       CASE WHEN t.pt_4326 IS NULL THEN NULL ELSE ST_Y(t.pt_4326) END AS lat,
       c.confidence
  FROM candidates c
  JOIN mv_geocode_target t ON t.bd_mgt_sn = c.bd_mgt_sn
 ORDER BY c.confidence DESC,
          CASE WHEN t.pt_source = 'entrance' THEN 0 ELSE 1 END,
          t.bd_mgt_sn
 LIMIT :limit
"""
)

_SPPN_AREA_BY_POINT = text(
    """
WITH target_pt AS (
  SELECT ST_SetSRID(ST_MakePoint(:x, :y), 5179) AS geom
)
SELECT m.sig_cd,
       m.makarea_id,
       m.makarea_nm,
       m.ntfc_yn,
       m.ntfc_de,
       m.mvm_res_cd,
       m.source_file,
       m.source_yyyymm,
       ST_Area(m.geom) AS area_m2,
       ST_X(ST_Transform(p.geom, 4326)) AS lon,
       ST_Y(ST_Transform(p.geom, 4326)) AS lat
  FROM tl_sppn_makarea m, target_pt p
 WHERE ST_Covers(m.geom, p.geom)
 ORDER BY ST_Area(m.geom) ASC, m.sig_cd, m.makarea_id
 LIMIT 1
"""
)


class GeocodeRepository:
    """Geocode lookups against ``mv_geocode_target``."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def lookup_by_road(
        self,
        parts: AddrParts,
        *,
        region_hint: RegionHint | None = None,
    ) -> AddressLookup | None:
        if parts.road_nrm is None or parts.mnnm is None:
            return None
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    _LOOKUP_ROAD,
                    {
                        **region_params(region_hint),
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

    async def lookup_by_jibun(
        self,
        parts: AddrParts,
        *,
        region_hint: RegionHint | None = None,
    ) -> AddressLookup | None:
        if parts.mnnm is None:
            return None
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    _LOOKUP_JIBUN,
                    {
                        **region_params(region_hint),
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

    async def fuzzy_roads(
        self,
        parts: AddrParts,
        *,
        limit: int = 5,
        region_hint: RegionHint | None = None,
    ) -> list[AddressLookup]:
        if parts.road_nrm is None or parts.mnnm is None:
            return []
        async with self.engine.begin() as conn:
            await conn.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.42"))
            rows = (
                await conn.execute(
                    _FUZZY_ROADS,
                    {
                        **region_params(region_hint),
                        "si": parts.si,
                        "sgg": parts.sgg,
                        "road_nrm": parts.road_nrm,
                        "mnnm": parts.mnnm,
                        "limit": limit,
                    },
                )
            ).mappings().all()
        return [map_address(dict(row), address_type="road") for row in rows]

    async def lookup_sppn_area(self, point_5179: Point) -> SppnAreaLookup | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    _SPPN_AREA_BY_POINT,
                    {"x": point_5179.x, "y": point_5179.y},
                )
            ).mappings().first()
        return map_sppn_area(dict(row)) if row else None
