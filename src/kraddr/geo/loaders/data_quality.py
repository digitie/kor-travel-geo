"""Follow-up SQL exports for T-027 consistency data-quality analysis."""

from __future__ import annotations

import asyncio
import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

DATA_QUALITY_CASES = ("C2", "C4", "C6", "C7")


@dataclass(frozen=True, slots=True)
class ExportSpec:
    case_code: str
    name: str
    filename: str
    columns: tuple[str, ...]
    sql: str


EXPORT_SPECS: tuple[ExportSpec, ...] = (
    ExportSpec(
        case_code="C2",
        name="SHP polygon only samples",
        filename="c2_samples.csv",
        columns=(
            "reason",
            "bd_mgt_sn",
            "rncode_full",
            "bjd_cd",
            "buld_se_cd",
            "buld_mnnm",
            "buld_slno",
            "rds_sig_cd",
            "rn_cd",
            "sig_cd",
            "emd_cd",
            "li_cd",
            "missing_rncode_full",
            "missing_bjd_cd",
            "missing_buld_mnnm",
            "missing_buld_slno",
            "source_file",
            "source_yyyymm",
            "lon",
            "lat",
        ),
        sql="""
WITH missing_resolve_key AS (
  SELECT 'missing_resolve_key' AS reason,
         p.bd_mgt_sn,
         p.rncode_full,
         p.bjd_cd,
         p.buld_se_cd,
         p.buld_mnnm,
         p.buld_slno,
         p.rds_sig_cd,
         p.rn_cd,
         p.sig_cd,
         p.emd_cd,
         p.li_cd,
         (p.rncode_full IS NULL) AS missing_rncode_full,
         (p.bjd_cd IS NULL) AS missing_bjd_cd,
         (p.buld_mnnm IS NULL) AS missing_buld_mnnm,
         (p.buld_slno IS NULL) AS missing_buld_slno,
         p.source_file,
         p.source_yyyymm,
         round(ST_X(ST_Transform(ST_PointOnSurface(p.geom), 4326))::numeric, 8)::float8
           AS lon,
         round(ST_Y(ST_Transform(ST_PointOnSurface(p.geom), 4326))::numeric, 8)::float8
           AS lat
    FROM tl_spbd_buld_polygon p
   WHERE p.rncode_full IS NULL
      OR p.bjd_cd IS NULL
      OR p.buld_mnnm IS NULL
      OR p.buld_slno IS NULL
   ORDER BY p.bd_mgt_sn
   LIMIT :limit
),
missing_text AS (
  SELECT 'missing_text' AS reason,
         p.bd_mgt_sn,
         p.rncode_full,
         p.bjd_cd,
         p.buld_se_cd,
         p.buld_mnnm,
         p.buld_slno,
         p.rds_sig_cd,
         p.rn_cd,
         p.sig_cd,
         p.emd_cd,
         p.li_cd,
         false AS missing_rncode_full,
         false AS missing_bjd_cd,
         false AS missing_buld_mnnm,
         false AS missing_buld_slno,
         p.source_file,
         p.source_yyyymm,
         round(ST_X(ST_Transform(ST_PointOnSurface(p.geom), 4326))::numeric, 8)::float8
           AS lon,
         round(ST_Y(ST_Transform(ST_PointOnSurface(p.geom), 4326))::numeric, 8)::float8
           AS lat
    FROM tl_spbd_buld_polygon p
   WHERE p.rncode_full IS NOT NULL
     AND p.bjd_cd IS NOT NULL
     AND p.buld_mnnm IS NOT NULL
     AND p.buld_slno IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
         FROM tl_juso_text j
        WHERE j.rncode_full = p.rncode_full
          AND j.buld_se_cd IS NOT DISTINCT FROM p.buld_se_cd
          AND j.buld_mnnm IS NOT DISTINCT FROM p.buld_mnnm
          AND j.buld_slno IS NOT DISTINCT FROM p.buld_slno
          AND j.bjd_cd = p.bjd_cd
     )
   ORDER BY p.bd_mgt_sn
   LIMIT :limit
)
SELECT * FROM missing_resolve_key
UNION ALL
SELECT * FROM missing_text
ORDER BY reason, bd_mgt_sn
""",
    ),
    ExportSpec(
        case_code="C2",
        name="SHP missing resolve key summary",
        filename="c2_missing_key_summary.csv",
        columns=(
            "rows",
            "missing_rds_sig_cd",
            "missing_rn_cd",
            "missing_sig_cd",
            "missing_emd_cd",
            "missing_buld_mnnm",
            "missing_buld_slno",
            "null_source_file",
        ),
        sql="""
SELECT count(*)::bigint AS rows,
       count(*) FILTER (WHERE NULLIF(rds_sig_cd, '') IS NULL)::bigint
         AS missing_rds_sig_cd,
       count(*) FILTER (WHERE NULLIF(rn_cd, '') IS NULL)::bigint AS missing_rn_cd,
       count(*) FILTER (WHERE NULLIF(sig_cd, '') IS NULL)::bigint AS missing_sig_cd,
       count(*) FILTER (WHERE NULLIF(emd_cd, '') IS NULL)::bigint AS missing_emd_cd,
       count(*) FILTER (WHERE buld_mnnm IS NULL)::bigint AS missing_buld_mnnm,
       count(*) FILTER (WHERE buld_slno IS NULL)::bigint AS missing_buld_slno,
       count(*) FILTER (WHERE source_file IS NULL)::bigint AS null_source_file
  FROM tl_spbd_buld_polygon
 WHERE rncode_full IS NULL
    OR bjd_cd IS NULL
    OR buld_mnnm IS NULL
    OR buld_slno IS NULL
""",
    ),
    ExportSpec(
        case_code="C4",
        name="entrance to polygon distance samples",
        filename="c4_distance_samples.csv",
        columns=(
            "bucket",
            "dist_m",
            "bd_mgt_sn",
            "ent_man_no",
            "rncode_full",
            "bjd_cd",
            "entrance_source_file",
            "polygon_bd_mgt_sn",
            "polygon_source_file",
            "entrance_lon",
            "entrance_lat",
            "polygon_lon",
            "polygon_lat",
            "delta_lon",
            "delta_lat",
        ),
        sql="""
WITH distances AS (
  SELECT j.bd_mgt_sn,
         e.ent_man_no,
         j.rncode_full,
         j.bjd_cd,
         e.source_file AS entrance_source_file,
         nearest.polygon_bd_mgt_sn,
         nearest.polygon_source_file,
         ST_Distance(e.geom, nearest.geom) AS dist_m,
         round(ST_X(ST_Transform(e.geom, 4326))::numeric, 8)::float8 AS entrance_lon,
         round(ST_Y(ST_Transform(e.geom, 4326))::numeric, 8)::float8 AS entrance_lat,
         round(ST_X(ST_Transform(ST_PointOnSurface(nearest.geom), 4326))::numeric, 8)::float8
           AS polygon_lon,
         round(ST_Y(ST_Transform(ST_PointOnSurface(nearest.geom), 4326))::numeric, 8)::float8
           AS polygon_lat
    FROM tl_locsum_entrc e
    JOIN tl_juso_text j ON j.bd_mgt_sn = e.bd_mgt_sn
    JOIN LATERAL (
      SELECT p.bd_mgt_sn AS polygon_bd_mgt_sn,
             p.source_file AS polygon_source_file,
             p.geom
        FROM tl_spbd_buld_polygon p
       WHERE p.rncode_full = j.rncode_full
         AND p.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
         AND p.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
         AND p.buld_slno IS NOT DISTINCT FROM j.buld_slno
         AND p.bjd_cd = j.bjd_cd
       ORDER BY e.geom <-> p.geom
       LIMIT 1
    ) nearest ON true
)
SELECT CASE
         WHEN dist_m > 500 THEN '500+'
         WHEN dist_m > 100 THEN '100-500'
         ELSE '50-100'
       END AS bucket,
       round(dist_m::numeric, 2)::float8 AS dist_m,
       bd_mgt_sn,
       ent_man_no,
       rncode_full,
       bjd_cd,
       entrance_source_file,
       polygon_bd_mgt_sn,
       polygon_source_file,
       entrance_lon,
       entrance_lat,
       polygon_lon,
       polygon_lat,
       round((entrance_lon - polygon_lon)::numeric, 8)::float8 AS delta_lon,
       round((entrance_lat - polygon_lat)::numeric, 8)::float8 AS delta_lat
  FROM distances
 WHERE dist_m > 50
 ORDER BY dist_m DESC, bd_mgt_sn
 LIMIT :limit
""",
    ),
    ExportSpec(
        case_code="C4",
        name="entrance distance bucket summary",
        filename="c4_distance_buckets.csv",
        columns=("bucket", "rows", "min_m", "avg_m", "max_m"),
        sql="""
WITH distances AS (
  SELECT ST_Distance(e.geom, nearest.geom) AS dist_m
    FROM tl_locsum_entrc e
    JOIN tl_juso_text j ON j.bd_mgt_sn = e.bd_mgt_sn
    JOIN LATERAL (
      SELECT p.geom
        FROM tl_spbd_buld_polygon p
       WHERE p.rncode_full = j.rncode_full
         AND p.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
         AND p.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
         AND p.buld_slno IS NOT DISTINCT FROM j.buld_slno
         AND p.bjd_cd = j.bjd_cd
       ORDER BY e.geom <-> p.geom
       LIMIT 1
    ) nearest ON true
),
buckets AS (
  SELECT CASE
           WHEN dist_m > 500 THEN '500+'
           WHEN dist_m > 100 THEN '100-500'
           WHEN dist_m > 50 THEN '50-100'
           ELSE '0-50'
         END AS bucket,
         CASE
           WHEN dist_m > 500 THEN 3
           WHEN dist_m > 100 THEN 2
           WHEN dist_m > 50 THEN 1
           ELSE 0
         END AS bucket_order,
         dist_m
    FROM distances
)
SELECT bucket,
       count(*)::bigint AS rows,
       round(min(dist_m)::numeric, 2)::float8 AS min_m,
       round(avg(dist_m)::numeric, 2)::float8 AS avg_m,
       round(max(dist_m)::numeric, 2)::float8 AS max_m
  FROM buckets
 GROUP BY bucket, bucket_order
 ORDER BY bucket_order
""",
    ),
    ExportSpec(
        case_code="C6",
        name="zip polygon mismatch samples",
        filename="c6_samples.csv",
        columns=(
            "case_code",
            "reason",
            "bd_mgt_sn",
            "region_key",
            "ent_man_no",
            "source_file",
            "source_yyyymm",
            "lon",
            "lat",
        ),
        sql="""
WITH base AS (
  SELECT j.bd_mgt_sn,
         j.zip_no,
         e.ent_man_no,
         e.geom,
         e.source_file,
         e.source_yyyymm,
         k.bas_id,
         k.geom AS bas_geom
    FROM tl_juso_text j
    JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN tl_kodis_bas k ON k.bas_id = j.zip_no
   WHERE j.zip_no IS NOT NULL
),
violations AS (
  SELECT 'C6' AS case_code,
         CASE
           WHEN bas_id IS NULL THEN 'missing_zip_polygon'
           WHEN NOT ST_Covers(bas_geom, geom) THEN 'outside_zip_polygon'
           ELSE 'ok'
         END AS reason,
         bd_mgt_sn,
         zip_no AS region_key,
         ent_man_no,
         source_file,
         source_yyyymm,
         round(ST_X(ST_Transform(geom, 4326))::numeric, 8)::float8 AS lon,
         round(ST_Y(ST_Transform(geom, 4326))::numeric, 8)::float8 AS lat
    FROM base
   WHERE bas_id IS NULL OR NOT ST_Covers(bas_geom, geom)
)
SELECT *
  FROM violations
 ORDER BY reason, region_key, bd_mgt_sn
 LIMIT :limit
""",
    ),
    ExportSpec(
        case_code="C6",
        name="zip polygon mismatch region summary",
        filename="c6_region_summary.csv",
        columns=("case_code", "region_key", "rows", "missing_polygon", "outside_polygon"),
        sql="""
WITH base AS (
  SELECT j.bd_mgt_sn, j.zip_no, e.geom, k.bas_id, k.geom AS bas_geom
    FROM tl_juso_text j
    JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN tl_kodis_bas k ON k.bas_id = j.zip_no
   WHERE j.zip_no IS NOT NULL
),
violations AS (
  SELECT zip_no AS region_key,
         CASE
           WHEN bas_id IS NULL THEN 'missing_zip_polygon'
           WHEN NOT ST_Covers(bas_geom, geom) THEN 'outside_zip_polygon'
           ELSE 'ok'
         END AS reason
    FROM base
   WHERE bas_id IS NULL OR NOT ST_Covers(bas_geom, geom)
)
SELECT 'C6' AS case_code,
       region_key,
       count(*)::bigint AS rows,
       count(*) FILTER (WHERE reason = 'missing_zip_polygon')::bigint AS missing_polygon,
       count(*) FILTER (WHERE reason = 'outside_zip_polygon')::bigint AS outside_polygon
  FROM violations
 GROUP BY region_key
 ORDER BY rows DESC, region_key
 LIMIT :limit
""",
    ),
    ExportSpec(
        case_code="C7",
        name="admin polygon mismatch samples",
        filename="c7_samples.csv",
        columns=(
            "case_code",
            "reason",
            "bd_mgt_sn",
            "region_key",
            "ent_man_no",
            "source_file",
            "source_yyyymm",
            "lon",
            "lat",
        ),
        sql="""
WITH base AS (
  SELECT j.bd_mgt_sn,
         left(j.bjd_cd, 8) AS emd_cd,
         e.ent_man_no,
         e.geom,
         e.source_file,
         e.source_yyyymm,
         p.geom AS emd_geom
    FROM tl_juso_text j
    JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN tl_scco_emd p ON p.emd_cd = left(j.bjd_cd, 8)
),
violations AS (
  SELECT 'C7' AS case_code,
         CASE
           WHEN emd_geom IS NULL THEN 'missing_emd_polygon'
           WHEN NOT ST_Covers(emd_geom, geom) THEN 'outside_emd_polygon'
           ELSE 'ok'
         END AS reason,
         bd_mgt_sn,
         emd_cd AS region_key,
         ent_man_no,
         source_file,
         source_yyyymm,
         round(ST_X(ST_Transform(geom, 4326))::numeric, 8)::float8 AS lon,
         round(ST_Y(ST_Transform(geom, 4326))::numeric, 8)::float8 AS lat
    FROM base
   WHERE emd_geom IS NULL OR NOT ST_Covers(emd_geom, geom)
)
SELECT *
  FROM violations
 ORDER BY reason, region_key, bd_mgt_sn
 LIMIT :limit
""",
    ),
    ExportSpec(
        case_code="C7",
        name="admin polygon mismatch region summary",
        filename="c7_region_summary.csv",
        columns=("case_code", "region_key", "rows", "missing_polygon", "outside_polygon"),
        sql="""
WITH base AS (
  SELECT j.bd_mgt_sn, left(j.bjd_cd, 8) AS emd_cd, e.geom, p.geom AS emd_geom
    FROM tl_juso_text j
    JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN tl_scco_emd p ON p.emd_cd = left(j.bjd_cd, 8)
),
violations AS (
  SELECT emd_cd AS region_key,
         CASE
           WHEN emd_geom IS NULL THEN 'missing_emd_polygon'
           WHEN NOT ST_Covers(emd_geom, geom) THEN 'outside_emd_polygon'
           ELSE 'ok'
         END AS reason
    FROM base
   WHERE emd_geom IS NULL OR NOT ST_Covers(emd_geom, geom)
)
SELECT 'C7' AS case_code,
       region_key,
       count(*)::bigint AS rows,
       count(*) FILTER (WHERE reason = 'missing_emd_polygon')::bigint AS missing_polygon,
       count(*) FILTER (WHERE reason = 'outside_emd_polygon')::bigint AS outside_polygon
  FROM violations
 GROUP BY region_key
 ORDER BY rows DESC, region_key
 LIMIT :limit
""",
    ),
)


async def export_data_quality_samples(
    engine: AsyncEngine,
    output_dir: Path | str,
    *,
    cases: tuple[str, ...] = DATA_QUALITY_CASES,
    limit: int = 200,
) -> tuple[Path, ...]:
    """Export reproducible CSV samples for the T-027 C2/C4/C6/C7 follow-up."""
    selected = set(cases)
    unknown = selected.difference(DATA_QUALITY_CASES)
    if unknown:
        joined = ", ".join(sorted(unknown))
        msg = f"unsupported data quality case(s): {joined}"
        raise ValueError(msg)

    directory = Path(output_dir)
    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
    paths: list[Path] = []
    async with engine.connect() as conn:
        for spec in EXPORT_SPECS:
            if spec.case_code not in selected:
                continue
            result = await conn.execute(text(spec.sql), {"limit": limit})
            rows = tuple(dict(row) for row in result.mappings())
            path = directory / spec.filename
            _write_csv(path, spec.columns, rows)
            paths.append(path)
    return tuple(paths)


def _write_csv(
    path: Path,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=tuple(columns),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column)) for column in columns})


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
