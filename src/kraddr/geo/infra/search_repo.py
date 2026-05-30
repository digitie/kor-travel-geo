"""Raw SQL search repository."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.core.protocols import SearchLookup
from kraddr.geo.dto.region import RegionHint, region_params

from ._rows import map_region_search, map_search

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
           similarity(buld_nm_nrm, :query_nrm),
           similarity(sigungu_buld_nm_nrm, :query_nrm)
         ) AS score
    FROM mv_geocode_target
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
     AND (
       rn_nrm = :query_nrm
       OR (buld_nm_nrm = :query_nrm AND buld_nm_nrm IS NOT NULL)
       OR (sigungu_buld_nm_nrm = :query_nrm AND sigungu_buld_nm_nrm IS NOT NULL)
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
           similarity(ts.buld_nm_nrm, q.query_nrm),
           similarity(ts.sigungu_buld_nm_nrm, q.query_nrm)
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
       OR ts.sigungu_buld_nm_nrm ILIKE '%' || q.query_nrm || '%'
       OR ts.rn_nrm % q.query_nrm
       OR ts.buld_nm_nrm % q.query_nrm
       OR ts.sigungu_buld_nm_nrm % q.query_nrm
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

_DISTRICT_SEARCH_SQL = text(
    """
WITH query_input AS (
  SELECT regexp_replace(:query, '\\s+', '', 'g') AS query_nrm
),
districts AS (
  SELECT c.ctprvn_cd AS code,
         c.ctp_kor_nm AS title,
         c.ctp_kor_nm AS si_nm,
         NULL::text AS sgg_nm,
         NULL::text AS emd_nm,
         NULL::text AS li_nm,
         c.ctprvn_cd AS region_code,
         CASE WHEN ST_IsEmpty(c.geom) THEN NULL
              ELSE ST_X(ST_Transform(ST_PointOnSurface(c.geom), 4326))
          END AS lon,
         CASE WHEN ST_IsEmpty(c.geom) THEN NULL
              ELSE ST_Y(ST_Transform(ST_PointOnSurface(c.geom), 4326))
          END AS lat
    FROM tl_scco_ctprvn c
   WHERE (
       CAST(:sig_cd_filter AS text) IS NULL
       OR c.ctprvn_cd = left(CAST(:sig_cd_filter AS text), 2)
     )
     AND (
       CAST(:sig_cd_prefix AS text) IS NULL
       OR c.ctprvn_cd = left(CAST(:sig_cd_prefix AS text), 2)
     )
     AND (
       CAST(:bjd_cd_filter AS text) IS NULL
       OR c.ctprvn_cd = left(CAST(:bjd_cd_filter AS text), 2)
     )
     AND (
       CAST(:bjd_cd_prefix AS text) IS NULL
       OR c.ctprvn_cd = left(CAST(:bjd_cd_prefix AS text), 2)
     )
  UNION ALL
  SELECT s.sig_cd AS code,
         concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm) AS title,
         c.ctp_kor_nm AS si_nm,
         s.sig_kor_nm AS sgg_nm,
         NULL::text AS emd_nm,
         NULL::text AS li_nm,
         s.sig_cd AS region_code,
         CASE WHEN ST_IsEmpty(s.geom) THEN NULL
              ELSE ST_X(ST_Transform(ST_PointOnSurface(s.geom), 4326))
          END AS lon,
         CASE WHEN ST_IsEmpty(s.geom) THEN NULL
              ELSE ST_Y(ST_Transform(ST_PointOnSurface(s.geom), 4326))
          END AS lat
    FROM tl_scco_sig s
    LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(s.sig_cd, 2)
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR s.sig_cd = CAST(:sig_cd_filter AS text))
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR s.sig_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR s.sig_cd = left(CAST(:bjd_cd_filter AS text), 5))
     AND (
       CAST(:bjd_cd_prefix AS text) IS NULL
       OR s.sig_cd LIKE left(CAST(:bjd_cd_prefix AS text), 5) || '%'
     )
  UNION ALL
  SELECT e.emd_cd AS code,
         concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm, e.emd_kor_nm) AS title,
         c.ctp_kor_nm AS si_nm,
         s.sig_kor_nm AS sgg_nm,
         e.emd_kor_nm AS emd_nm,
         NULL::text AS li_nm,
         e.emd_cd AS region_code,
         CASE WHEN ST_IsEmpty(e.geom) THEN NULL
              ELSE ST_X(ST_Transform(ST_PointOnSurface(e.geom), 4326))
          END AS lon,
         CASE WHEN ST_IsEmpty(e.geom) THEN NULL
              ELSE ST_Y(ST_Transform(ST_PointOnSurface(e.geom), 4326))
          END AS lat
    FROM tl_scco_emd e
    LEFT JOIN tl_scco_sig s ON s.sig_cd = left(e.emd_cd, 5)
    LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(e.emd_cd, 2)
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR left(e.emd_cd, 5) = CAST(:sig_cd_filter AS text))
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR e.emd_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR e.emd_cd = left(CAST(:bjd_cd_filter AS text), 8))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR e.emd_cd LIKE CAST(:bjd_cd_prefix AS text))
  UNION ALL
  SELECT l.li_cd AS code,
         concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm, e.emd_kor_nm, l.li_kor_nm) AS title,
         c.ctp_kor_nm AS si_nm,
         s.sig_kor_nm AS sgg_nm,
         e.emd_kor_nm AS emd_nm,
         l.li_kor_nm AS li_nm,
         l.li_cd AS region_code,
         CASE WHEN ST_IsEmpty(l.geom) THEN NULL
              ELSE ST_X(ST_Transform(ST_PointOnSurface(l.geom), 4326))
          END AS lon,
         CASE WHEN ST_IsEmpty(l.geom) THEN NULL
              ELSE ST_Y(ST_Transform(ST_PointOnSurface(l.geom), 4326))
          END AS lat
    FROM tl_scco_li l
    LEFT JOIN tl_scco_emd e ON e.emd_cd = left(l.li_cd, 8)
    LEFT JOIN tl_scco_sig s ON s.sig_cd = left(l.li_cd, 5)
    LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(l.li_cd, 2)
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR left(l.li_cd, 5) = CAST(:sig_cd_filter AS text))
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR l.li_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR l.li_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR l.li_cd LIKE CAST(:bjd_cd_prefix AS text))
),
ranked AS (
  SELECT d.*,
         CASE
           WHEN regexp_replace(d.title, '\\s+', '', 'g') = q.query_nrm THEN 1.0
           WHEN regexp_replace(
             coalesce(d.li_nm, d.emd_nm, d.sgg_nm, d.si_nm),
             '\\s+', '', 'g'
           ) = q.query_nrm THEN 0.98
           WHEN right(
             regexp_replace(d.title, '\\s+', '', 'g'),
             char_length(q.query_nrm)
           ) = q.query_nrm THEN 0.95
           WHEN regexp_replace(d.title, '\\s+', '', 'g') LIKE '%' || q.query_nrm || '%' THEN 0.85
           ELSE 0.0
         END AS score
    FROM districts d
    CROSS JOIN query_input q
)
SELECT *, count(*) OVER () AS total
  FROM ranked
 WHERE score > 0
 ORDER BY score DESC, char_length(code), title
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
        if search_type not in {"address", "road", "district"}:
            return ([], 0)
        offset = (page - 1) * size
        hint_params = region_params(region_hint)
        params = {"query": query, "limit": size, "offset": offset, **hint_params}
        if search_type == "district":
            async with self.engine.begin() as conn:
                rows = (
                    await conn.execute(
                        _DISTRICT_SEARCH_SQL,
                        params,
                    )
                ).mappings().all()
            total = int(rows[0]["total"]) if rows else 0
            return ([map_region_search(dict(row)) for row in rows], total)
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
