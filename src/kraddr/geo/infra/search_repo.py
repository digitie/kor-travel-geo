"""Raw SQL search repository."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.protocols import SearchLookup
from kraddr.geo.dto.region import RegionHint, region_params

from ._rows import map_search

_SEARCH_EXACT_SQL = text(
    """
WITH matched AS (
  SELECT bd_mgt_sn, rncode_full, rn AS road_nm, buld_mnnm, buld_slno, buld_se_cd,
         buld_nm, bjd_cd, adm_cd, adm_kor_nm, mntn_yn, lnbr_mnnm, lnbr_slno, zip_no,
         si_nm, sgg_nm, emd_nm, li_nm, pnu, pt_source,
         CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_X(pt_4326) END AS lon,
         CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_Y(pt_4326) END AS lat,
         GREATEST(
           similarity(rn_nrm, :query_nrm),
           similarity(buld_nm_nrm, :query_nrm)
         ) AS score
    FROM mv_geocode_target
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
     AND (
       rn_nrm = :query_nrm
       OR (buld_nm_nrm = :query_nrm AND buld_nm_nrm IS NOT NULL)
     )
)
SELECT *, count(*) OVER () AS total
  FROM matched
 ORDER BY score DESC NULLS LAST, bd_mgt_sn
 LIMIT :limit OFFSET :offset
"""
)

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
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
     AND (
       rn_nrm ILIKE '%' || regexp_replace(:query, '\\s+', '', 'g') || '%'
       OR buld_nm_nrm ILIKE '%' || regexp_replace(:query, '\\s+', '', 'g') || '%'
       OR rn_nrm % regexp_replace(:query, '\\s+', '', 'g')
       OR buld_nm_nrm % regexp_replace(:query, '\\s+', '', 'g')
     )
)
SELECT *, count(*) OVER () AS total
  FROM scored
 ORDER BY score DESC NULLS LAST, bd_mgt_sn
 LIMIT :limit OFFSET :offset
"""
)


def _normalize_search_query(query: str) -> str:
    return "".join(query.split())


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
        region_hint: RegionHint | None = None,
    ) -> tuple[list[SearchLookup], int]:
        if search_type not in {"address", "road"}:
            return ([], 0)
        offset = (page - 1) * size
        hint_params = region_params(region_hint)
        params = {"query": query, "limit": size, "offset": offset, **hint_params}
        exact_params = {
            "query_nrm": _normalize_search_query(query),
            "limit": size,
            "offset": offset,
            **hint_params,
        }
        async with self.engine.begin() as conn:
            await conn.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.35"))
            exact_rows = (
                await conn.execute(
                    _SEARCH_EXACT_SQL,
                    exact_params,
                )
            ).mappings().all()
            exact_total = int(exact_rows[0]["total"]) if exact_rows else 0
            if exact_total > 0:
                rows = exact_rows
            else:
                rows = (
                    await conn.execute(
                        _SEARCH_SQL,
                        params,
                    )
                ).mappings().all()
        total = int(rows[0]["total"]) if rows else 0
        return ([map_search(dict(row)) for row in rows], total)
