"""Raw SQL fragments for reverse geocoding repositories."""

from __future__ import annotations

from sqlalchemy import TextClause, text

NEAREST_ENTRANCE_SQL: TextClause = text(
    """
    WITH target_pt AS (
      SELECT ST_Transform(
        ST_SetSRID(ST_MakePoint(:lon, :lat), :in_srid),
        5179
      ) AS geom
    )
    SELECT
      t.bd_mgt_sn,
      t.rncode_full,
      t.bjd_cd,
      t.zip_no,
      t.road_nm,
      t.si_nm,
      t.sgg_nm,
      t.emd_nm,
      ST_Distance(t.ent_pt_5179, p.geom) AS dist_m,
      ST_X(t.ent_pt_4326) AS lon,
      ST_Y(t.ent_pt_4326) AS lat
    FROM mv_geocode_target AS t, target_pt AS p
    WHERE t.ent_pt_5179 IS NOT NULL
      AND ST_DWithin(t.ent_pt_5179, p.geom, :radius_m)
    ORDER BY t.ent_pt_5179 <-> p.geom
    LIMIT :limit
    """
)


KODIS_BAS_ZIP_AT_SQL: TextClause = text(
    """
    WITH target_pt AS (
      SELECT ST_Transform(
        ST_SetSRID(ST_MakePoint(:lon, :lat), :in_srid),
        5179
      ) AS geom
    )
    SELECT b.bas_id AS zip_no
    FROM tl_kodis_bas AS b, target_pt AS p
    WHERE ST_Contains(b.geom, p.geom)
    LIMIT 1
    """
)
