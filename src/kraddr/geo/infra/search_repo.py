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
WITH query_input AS (
  SELECT regexp_replace(:query, '\\s+', '', 'g') AS query_nrm
),
scored AS MATERIALIZED (
  SELECT ts.bd_mgt_sn,
         GREATEST(
           similarity(ts.rn_nrm, q.query_nrm),
           similarity(ts.buld_nm_nrm, q.query_nrm)
         ) AS score
    FROM mv_geocode_text_search ts
    CROSS JOIN query_input q
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR ts.sig_cd = CAST(:sig_cd_filter AS text))
     AND (
       CAST(:sig_cd_prefix AS text) IS NULL
       OR ts.sido_cd = left(CAST(:sig_cd_prefix AS text), 2)
     )
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR ts.bjd_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR ts.bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
     AND (
       ts.rn_nrm ILIKE '%' || q.query_nrm || '%'
       OR ts.buld_nm_nrm ILIKE '%' || q.query_nrm || '%'
       OR ts.rn_nrm % q.query_nrm
       OR ts.buld_nm_nrm % q.query_nrm
     )
),
ranked AS (
  SELECT t.bd_mgt_sn, t.rncode_full, t.rn AS road_nm, t.buld_mnnm, t.buld_slno,
         t.buld_se_cd, t.buld_nm, t.bjd_cd, t.adm_cd, t.adm_kor_nm, t.mntn_yn,
         t.lnbr_mnnm, t.lnbr_slno, t.zip_no, t.si_nm, t.sgg_nm, t.emd_nm, t.li_nm,
         t.pnu, t.pt_source,
         CASE WHEN t.pt_4326 IS NULL THEN NULL ELSE ST_X(t.pt_4326) END AS lon,
         CASE WHEN t.pt_4326 IS NULL THEN NULL ELSE ST_Y(t.pt_4326) END AS lat,
         s.score
    FROM scored s
    JOIN mv_geocode_target t ON t.bd_mgt_sn = s.bd_mgt_sn
)
SELECT *, count(*) OVER () AS total
  FROM ranked
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
