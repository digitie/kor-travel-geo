"""Raw SQL search repository."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.normalize import compact, normalize_spaces, parse_address
from kortravelgeo.core.protocols import SearchLookup
from kortravelgeo.dto.region import RegionHint, region_params
from kortravelgeo.exceptions import InvalidAddressError

from ._rows import map_region_search, map_search

_SEARCH_ROAD_ADDRESS_SQL = text(
    """
SELECT bd_mgt_sn, rncode_full, rn AS road_nm, buld_mnnm, buld_slno,
       buld_se_cd, buld_nm, bjd_cd, adm_cd, adm_kor_nm, mntn_yn,
       lnbr_mnnm, lnbr_slno, zip_no, si_nm, sgg_nm, emd_nm, li_nm,
       pnu, pt_source,
       CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_X(pt_4326) END AS lon,
       CASE WHEN pt_4326 IS NULL THEN NULL ELSE ST_Y(pt_4326) END AS lat,
       1.0::double precision AS score, count(*) OVER () AS total
  FROM mv_geocode_target
 WHERE rn_nrm = :road_nrm
   AND buld_mnnm = :mnnm
   AND buld_slno = :slno
   AND buld_se_cd = :buld_se_cd
   AND (CAST(:si AS text) IS NULL OR si_nm = CAST(:si AS text))
   AND (CAST(:sgg AS text) IS NULL OR sgg_nm = CAST(:sgg AS text))
   AND (CAST(:emd AS text) IS NULL OR emd_nm = CAST(:emd AS text))
   AND (CAST(:li AS text) IS NULL OR li_nm = CAST(:li AS text))
   AND (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
   AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
   AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
   AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
 ORDER BY bd_mgt_sn
 LIMIT :limit OFFSET :offset
"""
)

_SEARCH_EXACT_SQL = text(
    """
WITH exact_keys AS MATERIALIZED (
  SELECT bd_mgt_sn, 1.0::double precision AS score, 0 AS match_priority
    FROM mv_geocode_target
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
     AND rn_nrm = :query_nrm
  UNION ALL
  SELECT bd_mgt_sn, 1.0::double precision AS score, 1 AS match_priority
    FROM mv_geocode_target
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
     AND buld_nm_nrm IS NOT NULL
     AND buld_nm_nrm = :query_nrm
  UNION ALL
  SELECT bd_mgt_sn, 1.0::double precision AS score, 2 AS match_priority
    FROM mv_geocode_target
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%')
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR bjd_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR bjd_cd LIKE CAST(:bjd_cd_prefix AS text))
     AND sigungu_buld_nm_nrm IS NOT NULL
     AND sigungu_buld_nm_nrm = :query_nrm
),
deduped AS (
  SELECT DISTINCT ON (bd_mgt_sn) bd_mgt_sn, score, match_priority
    FROM exact_keys
   ORDER BY bd_mgt_sn, match_priority
),
matched AS (
  SELECT t.bd_mgt_sn, t.rncode_full, t.rn AS road_nm, t.buld_mnnm, t.buld_slno,
         t.buld_se_cd, t.buld_nm, t.bjd_cd, t.adm_cd, t.adm_kor_nm, t.mntn_yn,
         t.lnbr_mnnm, t.lnbr_slno, t.zip_no, t.si_nm, t.sgg_nm, t.emd_nm, t.li_nm,
         t.pnu, t.pt_source,
         CASE WHEN t.pt_4326 IS NULL THEN NULL ELSE ST_X(t.pt_4326) END AS lon,
         CASE WHEN t.pt_4326 IS NULL THEN NULL ELSE ST_Y(t.pt_4326) END AS lat,
         d.score,
         d.match_priority
    FROM deduped d
    JOIN mv_geocode_target t ON t.bd_mgt_sn = d.bd_mgt_sn
)
SELECT *, count(*) OVER () AS total
  FROM matched
 ORDER BY score DESC NULLS LAST, match_priority, bd_mgt_sn
 LIMIT :limit OFFSET :offset
"""
)

_SEARCH_SQL = text(
    """
WITH query_input AS (
  SELECT CAST(:query_nrm AS text) AS query_nrm
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

# 행정구역 이름 후보(T-311). geocode가 도로·지번을 못 찾으면 이 SQL로 떨어지므로(``client.py``
# ``_geocode_road_or_region_candidates``) 적재처럼 못 찾는 주소가 이어지는 호출자가 매번 탄다.
# 2026-11-10 odroid(CPU 포화)에서 이 SQL이 statement_timeout 5초를 넘겨 geocode가 504를 냈다 —
# 같은 주소는 다시 보내도 같은 504라 Map MOIS 적재 run이 끝났다. 결과는 그대로 두고 비용만 줄인다.
#
# - 대표점(ST_PointOnSurface + ST_Transform)은 페이지에 남은 행에만 계산한다(LIMIT 뒤 LATERAL).
# - 행정구역 전체 이름의 공백 제거(regexp_replace)는 행마다 한 번만 한다(``normalized``).
# - 길이 하한으로 regexp 전에 거른다. 네 점수 조건은 모두 ``query_nrm``이 공백 뺀 title의 부분
#   문자열(또는 그 LIKE 패턴)일 때만 참이고, 공백 제거는 길이를 줄이기만 하므로
#   ``char_length(title) >= (query_nrm 길이 - '%' 수 - '\' 수)``는 일치의 필요조건이다.
#   '%'는 빈 문자열과도, '\'는 escape로 다음 글자와 묶여 한 글자로 맞을 수 있어 둘 다 뺀다.
#   전체 주소 입력(``... 올림픽로 123``)은 어떤 행정구역 이름보다 길어 여기서 거의 다 빠진다.
_DISTRICT_SEARCH_SQL = text(
    """
WITH query_input AS MATERIALIZED (
  SELECT q.query_nrm,
         char_length(replace(replace(q.query_nrm, '%', ''), '\\', '')) AS min_title_len
    FROM (SELECT regexp_replace(:query, '\\s+', '', 'g') AS query_nrm) q
),
districts AS (
  SELECT 1 AS level,
         c.ctprvn_cd AS code,
         c.ctp_kor_nm AS title,
         c.ctp_kor_nm AS si_nm,
         NULL::text AS sgg_nm,
         NULL::text AS emd_nm,
         NULL::text AS li_nm,
         c.ctprvn_cd AS region_code
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
  SELECT 2 AS level,
         s.sig_cd AS code,
         concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm) AS title,
         c.ctp_kor_nm AS si_nm,
         s.sig_kor_nm AS sgg_nm,
         NULL::text AS emd_nm,
         NULL::text AS li_nm,
         s.sig_cd AS region_code
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
  SELECT 3 AS level,
         e.emd_cd AS code,
         concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm, e.emd_kor_nm) AS title,
         c.ctp_kor_nm AS si_nm,
         s.sig_kor_nm AS sgg_nm,
         e.emd_kor_nm AS emd_nm,
         NULL::text AS li_nm,
         e.emd_cd AS region_code
    FROM tl_scco_emd e
    LEFT JOIN tl_scco_sig s ON s.sig_cd = left(e.emd_cd, 5)
    LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(e.emd_cd, 2)
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR left(e.emd_cd, 5) = CAST(:sig_cd_filter AS text))
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR e.emd_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR e.emd_cd = left(CAST(:bjd_cd_filter AS text), 8))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR e.emd_cd LIKE CAST(:bjd_cd_prefix AS text))
  UNION ALL
  SELECT 4 AS level,
         l.li_cd AS code,
         concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm, e.emd_kor_nm, l.li_kor_nm) AS title,
         c.ctp_kor_nm AS si_nm,
         s.sig_kor_nm AS sgg_nm,
         e.emd_kor_nm AS emd_nm,
         l.li_kor_nm AS li_nm,
         l.li_cd AS region_code
    FROM tl_scco_li l
    LEFT JOIN tl_scco_emd e ON e.emd_cd = left(l.li_cd, 8)
    LEFT JOIN tl_scco_sig s ON s.sig_cd = left(l.li_cd, 5)
    LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(l.li_cd, 2)
   WHERE (CAST(:sig_cd_filter AS text) IS NULL OR left(l.li_cd, 5) = CAST(:sig_cd_filter AS text))
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR l.li_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (CAST(:bjd_cd_filter AS text) IS NULL OR l.li_cd = CAST(:bjd_cd_filter AS text))
     AND (CAST(:bjd_cd_prefix AS text) IS NULL OR l.li_cd LIKE CAST(:bjd_cd_prefix AS text))
),
normalized AS MATERIALIZED (
  SELECT d.*,
         regexp_replace(d.title, '\\s+', '', 'g') AS title_nrm
    FROM districts d
    CROSS JOIN query_input q
   WHERE char_length(d.title) >= q.min_title_len
),
ranked AS (
  SELECT n.*,
         CASE
           WHEN n.title_nrm = q.query_nrm THEN 1.0
           WHEN regexp_replace(
             coalesce(n.li_nm, n.emd_nm, n.sgg_nm, n.si_nm),
             '\\s+', '', 'g'
           ) = q.query_nrm THEN 0.98
           WHEN right(n.title_nrm, char_length(q.query_nrm)) = q.query_nrm THEN 0.95
           WHEN n.title_nrm LIKE '%' || q.query_nrm || '%' THEN 0.85
           ELSE 0.0
         END AS score
    FROM normalized n
    CROSS JOIN query_input q
),
page AS (
  SELECT r.*, count(*) OVER () AS total
    FROM ranked r
   WHERE r.score > 0
   ORDER BY r.score DESC, char_length(r.code), r.title
   LIMIT :limit OFFSET :offset
)
SELECT p.code, p.title, p.si_nm, p.sgg_nm, p.emd_nm, p.li_nm, p.region_code,
       pt.lon, pt.lat, p.score, p.total
  FROM page p
  LEFT JOIN LATERAL (
    SELECT CASE WHEN ST_IsEmpty(g.geom) THEN NULL
                ELSE ST_X(ST_Transform(ST_PointOnSurface(g.geom), 4326))
            END AS lon,
           CASE WHEN ST_IsEmpty(g.geom) THEN NULL
                ELSE ST_Y(ST_Transform(ST_PointOnSurface(g.geom), 4326))
            END AS lat
      FROM (
        SELECT c.geom FROM tl_scco_ctprvn c WHERE p.level = 1 AND c.ctprvn_cd = p.code
        UNION ALL
        SELECT s.geom FROM tl_scco_sig s WHERE p.level = 2 AND s.sig_cd = p.code
        UNION ALL
        SELECT e.geom FROM tl_scco_emd e WHERE p.level = 3 AND e.emd_cd = p.code
        UNION ALL
        SELECT l.geom FROM tl_scco_li l WHERE p.level = 4 AND l.li_cd = p.code
      ) g
     LIMIT 1
  ) pt ON true
 ORDER BY p.score DESC, char_length(p.code), p.title
"""
)


def _normalize_search_query(query: str) -> str:
    return compact(normalize_spaces(query)) or ""


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
        query_nrm = _normalize_search_query(query)
        params = {
            "query": query,
            "query_nrm": query_nrm,
            "limit": size,
            "offset": offset,
            **hint_params,
        }
        if search_type == "district":
            async with self.engine.begin() as conn:
                # 행정구역 표를 모두 훑어 추정 비용이 jit_above_cost를 살짝 넘지만, JIT 컴파일이
                # 실행보다 비싸다(운영 실측 warm 0.53초 중 0.29초, cold 2.7초). T-311.
                await conn.execute(text("SET LOCAL jit = off"))
                rows = (
                    await conn.execute(
                        _DISTRICT_SEARCH_SQL,
                        params,
                    )
                ).mappings().all()
            total = int(rows[0]["total"]) if rows else 0
            return ([map_region_search(dict(row)) for row in rows], total)
        exact_params = {
            "query_nrm": query_nrm,
            "limit": size,
            "offset": offset,
            **hint_params,
        }
        async with self.engine.begin() as conn:
            exact_rows = (
                await conn.execute(_SEARCH_EXACT_SQL, exact_params)
            ).mappings().all()
            exact_total = int(exact_rows[0]["total"]) if exact_rows else 0
            if exact_total > 0:
                return ([map_search(dict(row)) for row in exact_rows], exact_total)
        # 완성된 도로명 주소의 번호·지역은 일반 문자열 유사도로 대체하지 않는다.
        # 건물명·도로명 자동완성은 기존 정확/삼중자 검색을 그대로 사용한다.
        if search_type == "address":
            try:
                parts = parse_address(query)
            except InvalidAddressError:
                parts = None
            if parts is not None and parts.is_road and parts.mnnm is not None:
                address_params = {
                    **hint_params,
                    "road_nrm": parts.road_nrm,
                    "mnnm": parts.mnnm,
                    "slno": parts.slno,
                    "buld_se_cd": parts.buld_se_cd,
                    "si": parts.si,
                    "sgg": parts.sgg,
                    "emd": parts.emd,
                    "li": parts.li,
                    "limit": size,
                    "offset": offset,
                }
                async with self.engine.connect() as conn:
                    rows = (
                        await conn.execute(_SEARCH_ROAD_ADDRESS_SQL, address_params)
                    ).mappings().all()
                    total = int(rows[0]["total"]) if rows else 0
                    if not rows and offset > 0:
                        first = (
                            await conn.execute(
                                _SEARCH_ROAD_ADDRESS_SQL,
                                {**address_params, "limit": 1, "offset": 0},
                            )
                        ).mappings().first()
                        total = int(first["total"]) if first else 0
                return ([map_search(dict(row)) for row in rows], total)
        async with self.engine.begin() as conn:
            await conn.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.35"))
            rows = (await conn.execute(_SEARCH_SQL, params)).mappings().all()
        total = int(rows[0]["total"]) if rows else 0
        return ([map_search(dict(row)) for row in rows], total)
