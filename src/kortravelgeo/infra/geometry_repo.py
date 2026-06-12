"""Raw SQL geometry lookups for v2 debug overlays."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import TextClause

from kortravelgeo.core.protocols import GeometryLookup
from kortravelgeo.dto.common import Point
from kortravelgeo.dto.region import RegionHint, region_params
from kortravelgeo.dto.v2 import (
    BBoxV2,
    GeometryV2,
    RegionWithinRadiusItem,
    RegionWithinRadiusLevel,
    RegionWithinRadiusRelation,
    V2GeometryKind,
)

_BUILDING_DETAIL_RE = re.compile(r"^(?P<underground>지하\s*)?(?P<main>\d+)(?:-(?P<sub>\d+))?$")

_BUILDING_GEOMETRY_SQL = text(
    """
SELECT 'building'::text AS kind,
       p.bd_mgt_sn,
       p.rncode_full,
       p.bjd_cd,
       NULL::text AS title,
       NULL::text AS road_name,
       ST_AsGeoJSON(ST_Transform(p.geom, 4326), 6, 1)::jsonb AS geojson
  FROM tl_spbd_buld_polygon p
 WHERE (
       CAST(:bd_mgt_sn AS text) IS NOT NULL
       AND p.bd_mgt_sn = CAST(:bd_mgt_sn AS text)
   )
    OR (
       CAST(:rncode_full AS text) IS NOT NULL
       AND CAST(:bjd_cd AS text) IS NOT NULL
       AND CAST(:buld_mnnm AS integer) IS NOT NULL
       AND p.rncode_full = CAST(:rncode_full AS text)
       AND p.bjd_cd = CAST(:bjd_cd AS text)
       AND p.buld_mnnm = CAST(:buld_mnnm AS integer)
       AND p.buld_slno = CAST(:buld_slno AS integer)
       AND (CAST(:buld_se_cd AS text) IS NULL OR p.buld_se_cd = CAST(:buld_se_cd AS text))
   )
 ORDER BY CASE WHEN p.bd_mgt_sn = CAST(:bd_mgt_sn AS text) THEN 0 ELSE 1 END,
          p.bd_mgt_sn
 LIMIT 1
"""
)

_ROAD_GEOMETRY_SQL = text(
    """
WITH query_input AS (
  SELECT regexp_replace(:query, '\\s+', '', 'g') AS query_nrm
),
roads AS (
  SELECT m.sig_cd,
         m.rncode_full,
         m.rn AS road_name,
         concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm, m.rn) AS title,
         c.ctp_kor_nm AS sido,
         s.sig_kor_nm AS sigungu,
         ST_X(ST_Transform(ST_PointOnSurface(m.geom), 4326)) AS lon,
         ST_Y(ST_Transform(ST_PointOnSurface(m.geom), 4326)) AS lat,
         ST_AsGeoJSON(ST_Transform(m.geom, 4326), 6, 1)::jsonb AS geojson,
         q.query_nrm,
         regexp_replace(m.rn, '\\s+', '', 'g') AS rn_nrm,
         regexp_replace(concat_ws('', c.ctp_kor_nm, s.sig_kor_nm, m.rn), '\\s+', '', 'g')
           AS full_nrm,
         regexp_replace(concat_ws('', s.sig_kor_nm, m.rn), '\\s+', '', 'g') AS sigungu_nrm
    FROM tl_sprd_manage m
    CROSS JOIN query_input q
    LEFT JOIN tl_scco_sig s ON s.sig_cd = m.sig_cd
    LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(m.sig_cd, 2)
   WHERE m.geom IS NOT NULL
     AND NOT ST_IsEmpty(m.geom)
     AND (CAST(:sig_cd_filter AS text) IS NULL OR m.sig_cd = CAST(:sig_cd_filter AS text))
     AND (CAST(:sig_cd_prefix AS text) IS NULL OR m.sig_cd LIKE CAST(:sig_cd_prefix AS text))
     AND (
       CAST(:bjd_cd_filter AS text) IS NULL
       OR m.sig_cd = left(CAST(:bjd_cd_filter AS text), 5)
     )
     AND (
       CAST(:bjd_cd_prefix AS text) IS NULL
       OR m.sig_cd LIKE left(CAST(:bjd_cd_prefix AS text), 5) || '%'
     )
),
ranked AS (
  SELECT *,
         CASE
           WHEN rn_nrm = query_nrm THEN 1.0
           WHEN full_nrm = query_nrm OR sigungu_nrm = query_nrm THEN 0.98
           WHEN right(full_nrm, char_length(query_nrm)) = query_nrm THEN 0.95
           WHEN rn_nrm LIKE '%' || query_nrm || '%' THEN 0.86
           WHEN full_nrm LIKE '%' || query_nrm || '%' THEN 0.82
           ELSE 0.0
         END AS score
    FROM roads
)
SELECT *
  FROM ranked
 WHERE score > 0
 ORDER BY score DESC, char_length(title), title, rncode_full
 LIMIT :limit
"""
)

_REGION_CTPRVN_SQL = text(
    """
SELECT 'region'::text AS kind,
       c.ctprvn_cd AS sig_cd,
       NULL::text AS bjd_cd,
       c.ctp_kor_nm AS sido,
       NULL::text AS sigungu,
       NULL::text AS eup_myeon_dong,
       NULL::text AS li,
       c.ctp_kor_nm AS title,
       ST_AsGeoJSON(ST_Transform(c.geom, 4326), 6, 1)::jsonb AS geojson
  FROM tl_scco_ctprvn c
 WHERE c.ctprvn_cd = :code
 LIMIT 1
"""
)

_REGION_SIG_SQL = text(
    """
SELECT 'region'::text AS kind,
       s.sig_cd AS sig_cd,
       NULL::text AS bjd_cd,
       c.ctp_kor_nm AS sido,
       s.sig_kor_nm AS sigungu,
       NULL::text AS eup_myeon_dong,
       NULL::text AS li,
       concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm) AS title,
       ST_AsGeoJSON(ST_Transform(s.geom, 4326), 6, 1)::jsonb AS geojson
  FROM tl_scco_sig s
  LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(s.sig_cd, 2)
 WHERE s.sig_cd = :code
 LIMIT 1
"""
)

_REGION_EMD_SQL = text(
    """
SELECT 'region'::text AS kind,
       left(e.emd_cd, 5) AS sig_cd,
       e.emd_cd AS bjd_cd,
       c.ctp_kor_nm AS sido,
       s.sig_kor_nm AS sigungu,
       e.emd_kor_nm AS eup_myeon_dong,
       NULL::text AS li,
       concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm, e.emd_kor_nm) AS title,
       ST_AsGeoJSON(ST_Transform(e.geom, 4326), 6, 1)::jsonb AS geojson
  FROM tl_scco_emd e
  LEFT JOIN tl_scco_sig s ON s.sig_cd = left(e.emd_cd, 5)
  LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(e.emd_cd, 2)
 WHERE e.emd_cd = :code
 LIMIT 1
"""
)

_REGION_LI_SQL = text(
    """
SELECT 'region'::text AS kind,
       left(l.li_cd, 5) AS sig_cd,
       l.li_cd AS bjd_cd,
       c.ctp_kor_nm AS sido,
       s.sig_kor_nm AS sigungu,
       e.emd_kor_nm AS eup_myeon_dong,
       l.li_kor_nm AS li,
       concat_ws(' ', c.ctp_kor_nm, s.sig_kor_nm, e.emd_kor_nm, l.li_kor_nm) AS title,
       ST_AsGeoJSON(ST_Transform(l.geom, 4326), 6, 1)::jsonb AS geojson
  FROM tl_scco_li l
  LEFT JOIN tl_scco_emd e ON e.emd_cd = left(l.li_cd, 8)
  LEFT JOIN tl_scco_sig s ON s.sig_cd = left(l.li_cd, 5)
  LEFT JOIN tl_scco_ctprvn c ON c.ctprvn_cd = left(l.li_cd, 2)
 WHERE l.li_cd = :code
 LIMIT 1
"""
)

_REGIONS_WITHIN_RADIUS_SQL = text(
    """
WITH target AS (
  SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 5179) AS geom
),
contains AS (
  SELECT 'sido'::text AS level,
         c.ctprvn_cd AS code
    FROM tl_scco_ctprvn c
    CROSS JOIN target
   WHERE ST_Covers(c.geom, target.geom)
  UNION ALL
  SELECT 'sigungu'::text AS level,
         s.sig_cd AS code
    FROM tl_scco_sig s
    CROSS JOIN target
   WHERE ST_Covers(s.geom, target.geom)
  UNION ALL
  SELECT 'emd'::text AS level,
         e.emd_cd AS code
    FROM tl_scco_emd e
    CROSS JOIN target
   WHERE ST_Covers(e.geom, target.geom)
),
sido_candidates AS (
  SELECT 'sido'::text AS level,
         p.code,
         p.name,
         CASE WHEN bool_or(c.code IS NOT NULL) THEN 'contains' ELSE 'overlaps' END AS relation
    FROM region_radius_parts p
    CROSS JOIN target
    LEFT JOIN contains c ON c.level = p.level AND c.code = p.code
   WHERE p.level = 'sido'
     AND (
       CAST(:include_sido AS boolean)
       OR CAST(:include_sigungu AS boolean)
       OR CAST(:include_emd AS boolean)
     )
     AND ST_DWithin(p.geom, target.geom, :radius_m)
   GROUP BY p.code, p.name
),
sigungu_candidates AS (
  SELECT 'sigungu'::text AS level,
         p.code,
         p.name,
         CASE WHEN bool_or(c.code IS NOT NULL) THEN 'contains' ELSE 'overlaps' END AS relation
    FROM region_radius_parts p
    CROSS JOIN target
    JOIN sido_candidates sido ON sido.code = p.parent_sido_cd
    LEFT JOIN contains c ON c.level = p.level AND c.code = p.code
   WHERE p.level = 'sigungu'
     AND (CAST(:include_sigungu AS boolean) OR CAST(:include_emd AS boolean))
     AND ST_DWithin(p.geom, target.geom, :radius_m)
   GROUP BY p.code, p.name
),
emd_candidates AS (
  SELECT 'emd'::text AS level,
         p.code,
         p.name,
         CASE WHEN bool_or(c.code IS NOT NULL) THEN 'contains' ELSE 'overlaps' END AS relation
    FROM region_radius_parts p
    CROSS JOIN target
    JOIN sigungu_candidates sigungu ON sigungu.code = p.parent_sig_cd
    LEFT JOIN contains c ON c.level = p.level AND c.code = p.code
   WHERE p.level = 'emd'
     AND CAST(:include_emd AS boolean)
     AND ST_DWithin(p.geom, target.geom, :radius_m)
   GROUP BY p.code, p.name
),
selected AS (
  SELECT level, code, name, relation
    FROM sido_candidates
   WHERE CAST(:include_sido AS boolean)
  UNION ALL
  SELECT level, code, name, relation
    FROM sigungu_candidates
   WHERE CAST(:include_sigungu AS boolean)
  UNION ALL
  SELECT level, code, name, relation
    FROM emd_candidates
   WHERE CAST(:include_emd AS boolean)
)
SELECT level, code, name, relation
  FROM selected
 ORDER BY CASE level WHEN 'sido' THEN 0 WHEN 'sigungu' THEN 1 ELSE 2 END,
          CASE relation WHEN 'contains' THEN 0 ELSE 1 END,
          code
"""
)


class GeometryRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def building_geometry(
        self,
        *,
        bd_mgt_sn: str | None = None,
        rncode_full: str | None = None,
        bjd_cd: str | None = None,
        detail: str | None = None,
    ) -> GeometryLookup | None:
        parsed_detail = _parse_building_detail(detail)
        if bd_mgt_sn is None and (
            rncode_full is None or bjd_cd is None or parsed_detail is None
        ):
            return None
        params = {
            "bd_mgt_sn": bd_mgt_sn,
            "rncode_full": rncode_full,
            "bjd_cd": bjd_cd,
            "buld_mnnm": parsed_detail[0] if parsed_detail else None,
            "buld_slno": parsed_detail[1] if parsed_detail else 0,
            "buld_se_cd": parsed_detail[2] if parsed_detail else None,
        }
        async with self.engine.connect() as conn:
            row = (await conn.execute(_BUILDING_GEOMETRY_SQL, params)).mappings().first()
        return (
            _map_geometry_lookup(dict(row), source_table="tl_spbd_buld_polygon")
            if row
            else None
        )

    async def region_geometry(
        self,
        *,
        sig_cd: str | None = None,
        bjd_cd: str | None = None,
    ) -> GeometryLookup | None:
        query, code = _region_query(sig_cd=sig_cd, bjd_cd=bjd_cd)
        if query is None or code is None:
            return None
        async with self.engine.connect() as conn:
            row = (await conn.execute(query, {"code": code})).mappings().first()
        return (
            _map_geometry_lookup(dict(row), source_table=_region_source_table(code))
            if row
            else None
        )

    async def road_geometries(
        self,
        query: str,
        *,
        limit: int = 10,
        region_hint: RegionHint | None = None,
    ) -> list[GeometryLookup]:
        params = {
            "query": query,
            "limit": limit,
            **region_params(region_hint),
        }
        async with self.engine.connect() as conn:
            rows = (await conn.execute(_ROAD_GEOMETRY_SQL, params)).mappings().all()
        return [
            _map_geometry_lookup(dict(row), kind="road", source_table="tl_sprd_manage")
            for row in rows
        ]

    async def regions_within_radius(
        self,
        *,
        lon: float,
        lat: float,
        radius_km: float,
        levels: tuple[RegionWithinRadiusLevel, ...],
    ) -> dict[RegionWithinRadiusLevel, tuple[RegionWithinRadiusItem, ...]]:
        params = {
            "lon": lon,
            "lat": lat,
            "radius_m": radius_km * 1000.0,
            "include_sido": "sido" in levels,
            "include_sigungu": "sigungu" in levels,
            "include_emd": "emd" in levels,
        }
        async with self.engine.connect() as conn:
            rows = (await conn.execute(_REGIONS_WITHIN_RADIUS_SQL, params)).mappings().all()
        grouped: dict[RegionWithinRadiusLevel, list[RegionWithinRadiusItem]] = {
            level: [] for level in levels
        }
        for row in rows:
            level = cast("RegionWithinRadiusLevel", str(row["level"]))
            if level in grouped:
                grouped[level].append(_map_region_within_radius(dict(row)))
        result: dict[RegionWithinRadiusLevel, tuple[RegionWithinRadiusItem, ...]] = {
            level: tuple(items) for level, items in grouped.items()
        }
        return result


def _parse_building_detail(detail: str | None) -> tuple[int, int, str | None] | None:
    if detail is None:
        return None
    match = _BUILDING_DETAIL_RE.fullmatch(detail.strip())
    if not match:
        return None
    main = int(match.group("main"))
    sub = int(match.group("sub") or 0)
    buld_se_cd = "1" if match.group("underground") else None
    return (main, sub, buld_se_cd)


def _region_query(
    *,
    sig_cd: str | None,
    bjd_cd: str | None,
) -> tuple[TextClause | None, str | None]:
    if bjd_cd is not None:
        if len(bjd_cd) == 10 and not bjd_cd.endswith("00"):
            return (_REGION_LI_SQL, bjd_cd)
        return (_REGION_EMD_SQL, bjd_cd[:8])
    if sig_cd is None:
        return (None, None)
    if len(sig_cd) == 5:
        return (_REGION_SIG_SQL, sig_cd)
    return (_REGION_CTPRVN_SQL, sig_cd)


def _region_source_table(code: str) -> str:
    if len(code) == 2:
        return "tl_scco_ctprvn"
    if len(code) == 5:
        return "tl_scco_sig"
    if len(code) == 8:
        return "tl_scco_emd"
    return "tl_scco_li"


def _map_geometry_lookup(
    row: Mapping[str, Any],
    *,
    source_table: str,
    kind: V2GeometryKind | None = None,
) -> GeometryLookup:
    geojson = _geojson(row)
    geometry_kind = kind or cast("V2GeometryKind", str(row["kind"]))
    return GeometryLookup(
        kind=geometry_kind,
        geometry=GeometryV2(
            kind=geometry_kind,
            geojson=geojson,
            source_table=source_table,
        ),
        bbox=_bbox(geojson),
        point=_point(row),
        title=_as_str(row.get("title")),
        sig_cd=_as_str(row.get("sig_cd")),
        bjd_cd=_as_str(row.get("bjd_cd")),
        sido=_as_str(row.get("sido")),
        sigungu=_as_str(row.get("sigungu")),
        eup_myeon_dong=_as_str(row.get("eup_myeon_dong")),
        li=_as_str(row.get("li")),
        road_name=_as_str(row.get("road_name")),
        rncode_full=_as_str(row.get("rncode_full")),
        bd_mgt_sn=_as_str(row.get("bd_mgt_sn")),
        score=float(row["score"]) if row.get("score") is not None else None,
    )


def _map_region_within_radius(row: Mapping[str, Any]) -> RegionWithinRadiusItem:
    return RegionWithinRadiusItem(
        code=str(row["code"]),
        name=_as_str(row.get("name")),
        relation=cast("RegionWithinRadiusRelation", str(row["relation"])),
    )


def _geojson(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row["geojson"]
    if isinstance(raw, str):
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    if isinstance(raw, dict):
        return raw
    msg = "PostGIS GeoJSON result must be a JSON object"
    raise TypeError(msg)


def _bbox(geojson: Mapping[str, Any]) -> BBoxV2 | None:
    raw = geojson.get("bbox")
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    min_lon, min_lat, max_lon, max_lat = (
        float(raw[0]),
        float(raw[1]),
        float(raw[2]),
        float(raw[3]),
    )
    if min_lon >= max_lon or min_lat >= max_lat:
        return None
    return BBoxV2(min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat)


def _point(row: Mapping[str, Any]) -> Point | None:
    lon = row.get("lon")
    lat = row.get("lat")
    if lon is None or lat is None:
        return None
    return Point(x=float(lon), y=float(lat))


def _as_str(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)
