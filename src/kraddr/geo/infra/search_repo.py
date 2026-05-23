"""Raw SQL search repository."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.protocols import SearchLookup

from ._rows import map_search

_SEARCH_SQL = text(
    """
WITH scored AS (
  SELECT bd_mgt_sn, rncode_full, rn AS road_nm, buld_mnnm, buld_slno, buld_se_cd,
         buld_nm, bjd_cd, adm_cd, adm_kor_nm, mntn_yn, lnbr_mnnm, lnbr_slno, zip_no,
         si_nm, sgg_nm, emd_nm, li_nm, pnu, pt_source,
         CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_X(pt_4326) END AS lon,
         CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_Y(pt_4326) END AS lat,
         GREATEST(
           similarity(rn_nrm, regexp_replace(:query, '\\s+', '', 'g')),
           similarity(buld_nm_nrm, regexp_replace(:query, '\\s+', '', 'g'))
         ) AS score
    FROM mv_geocode_target
   WHERE rn_nrm ILIKE '%' || regexp_replace(:query, '\\s+', '', 'g') || '%'
      OR buld_nm_nrm ILIKE '%' || regexp_replace(:query, '\\s+', '', 'g') || '%'
      OR rn_nrm % regexp_replace(:query, '\\s+', '', 'g')
      OR buld_nm_nrm % regexp_replace(:query, '\\s+', '', 'g')
)
SELECT *, count(*) OVER () AS total
  FROM scored
 ORDER BY score DESC NULLS LAST, bd_mgt_sn
 LIMIT :limit OFFSET :offset
"""
)


class SearchRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def search(
        self,
        query: str,
        *,
        search_type: Literal["address", "place", "district", "road"],
        page: int,
        size: int,
    ) -> tuple[list[SearchLookup], int]:
        if search_type not in {"address", "road"}:
            return ([], 0)
        async with self.engine.begin() as conn:
            await conn.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.35"))
            rows = (
                await conn.execute(
                    _SEARCH_SQL,
                    {"query": query, "limit": size, "offset": (page - 1) * size},
                )
            ).mappings().all()
        total = int(rows[0]["total"]) if rows else 0
        return ([map_search(dict(row)) for row in rows], total)
