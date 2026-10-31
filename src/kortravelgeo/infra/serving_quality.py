"""원천을 보존하는 서빙 좌표 격리와 검증된 NAVI 대체 좌표 스냅샷."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

POLICY_VERSION = "verified-coordinate-v1"

QUALITY_DDL = (
    """
CREATE TABLE IF NOT EXISTS serving_quality_runs (
  run_id UUID PRIMARY KEY,
  policy_version TEXT NOT NULL,
  source_stamp TEXT NOT NULL,
  source_manifest JSONB NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
)
""",
    """
CREATE TABLE IF NOT EXISTS serving_coordinate_quarantine (
  run_id UUID NOT NULL REFERENCES serving_quality_runs(run_id),
  entity_kind TEXT NOT NULL CHECK (entity_kind IN ('point', 'building_polygon')),
  entity_id TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_key TEXT NOT NULL,
  source_file TEXT,
  source_yyyymm TEXT,
  original_geom geometry(Point, 5179),
  reasons TEXT[] NOT NULL CHECK (cardinality(reasons) > 0),
  source_attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
  replacement_source_kind TEXT,
  replacement_source_key TEXT,
  replacement_source_file TEXT,
  replacement_source_yyyymm TEXT,
  replacement_geom geometry(Point, 5179),
  PRIMARY KEY (run_id, entity_kind, entity_id),
  CHECK ((replacement_geom IS NULL) = (replacement_source_kind IS NULL)),
  CHECK (replacement_source_kind IS NULL OR replacement_source_kind = 'navi')
)
""",
    """
CREATE INDEX IF NOT EXISTS idx_serving_quality_stamp
  ON serving_quality_runs (source_stamp, policy_version, finished_at DESC)
  WHERE finished_at IS NOT NULL
""",
)

# 적재/일일 갱신은 같은 트랜잭션의 manifest 갱신으로 이전 판정을 무효화한다.
SOURCE_MANIFEST_SQL = """
SELECT COALESCE(jsonb_agg(to_jsonb(m) || jsonb_build_object(
  'updated_at', extract(epoch FROM updated_at),
  'last_full_load_at', extract(epoch FROM last_full_load_at),
  'last_delta_at', extract(epoch FROM last_delta_at)
) ORDER BY table_name), '[]'::jsonb)
  FROM load_manifest m
"""
SOURCE_STAMP_SQL = f"SELECT md5(({SOURCE_MANIFEST_SQL})::text)"
ACTIVE_RUN_SQL = f"""
SELECT run_id FROM serving_quality_runs
 WHERE source_stamp = ({SOURCE_STAMP_SQL})
   AND policy_version = '{POLICY_VERSION}' AND finished_at IS NOT NULL
 ORDER BY finished_at DESC, run_id DESC LIMIT 1
"""

# MV와 검사에서 같은 원천 우선순위와 주소키를 사용한다.
RAW_POINT_CTES = """
raw_best_entrance AS (
  SELECT DISTINCT ON (bd_mgt_sn) * FROM (
    SELECT bd_mgt_sn, ent_man_no, geom, 'locsum'::text AS source_kind,
           sig_cd || ':' || ent_man_no::text AS source_key,
           source_file, source_yyyymm, 0 AS source_priority,
           CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END AS rep_priority
      FROM tl_locsum_entrc WHERE bd_mgt_sn IS NOT NULL
    UNION ALL
    SELECT bd_mgt_sn, ent_man_no, geom, 'roadaddr'::text, bd_mgt_sn,
           source_file, source_yyyymm, 1, 0
      FROM tl_roadaddr_entrc
     WHERE source_yyyymm IN (
       SELECT DISTINCT source_yyyymm FROM tl_juso_text WHERE source_yyyymm IS NOT NULL
     )
  ) e ORDER BY bd_mgt_sn, source_priority, rep_priority, ent_man_no NULLS LAST
),
raw_best_navi AS (
  SELECT DISTINCT ON (rncode_full, buld_se_cd, buld_mnnm, buld_slno, left(bjd_cd, 8))
         * FROM tl_navi_buld_centroid
   WHERE rncode_full IS NOT NULL AND bjd_cd IS NOT NULL
   ORDER BY rncode_full, buld_se_cd, buld_mnnm, buld_slno, left(bjd_cd, 8), bd_mgt_sn
),
raw_serving_points AS (
  SELECT j.bd_mgt_sn, COALESCE(e.geom, n.centroid_5179) AS geom,
         e.ent_man_no,
         CASE WHEN e.geom IS NOT NULL THEN e.source_kind ELSE 'navi' END AS source_kind,
         CASE WHEN e.geom IS NOT NULL THEN e.source_key ELSE n.bd_mgt_sn END AS source_key,
         CASE WHEN e.geom IS NOT NULL THEN e.source_file ELSE n.source_file END AS source_file,
         CASE WHEN e.geom IS NOT NULL THEN e.source_yyyymm ELSE n.source_yyyymm END
           AS source_yyyymm
    FROM tl_juso_text j
    LEFT JOIN raw_best_entrance e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN raw_best_navi n ON n.rncode_full = j.rncode_full
     AND n.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
     AND n.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
     AND n.buld_slno IS NOT DISTINCT FROM j.buld_slno
     AND left(n.bjd_cd, 8) = left(j.bjd_cd, 8)
)
"""

SERVING_POINT_CTES = f"""
{RAW_POINT_CTES},
serving_entrc AS MATERIALIZED (
  SELECT r.bd_mgt_sn,
         CASE WHEN q.entity_id IS NOT NULL THEN q.replacement_geom ELSE r.geom END AS geom,
         CASE WHEN q.entity_id IS NOT NULL THEN NULL ELSE r.ent_man_no END AS ent_man_no,
         CASE WHEN q.entity_id IS NOT NULL THEN q.replacement_source_kind
              ELSE r.source_kind END AS source_kind
    FROM raw_serving_points r
    LEFT JOIN serving_coordinate_quarantine q
      ON q.run_id = ({ACTIVE_RUN_SQL}) AND q.entity_kind = 'point'
     AND q.entity_id = r.bd_mgt_sn
   WHERE CASE WHEN q.entity_id IS NOT NULL THEN q.replacement_geom ELSE r.geom END IS NOT NULL
)
"""

_POLYGON_ADDRESS_JOIN = """
(p.rncode_full = j.rncode_full OR (p.sig_cd || p.rn_cd) = j.rncode_full)
 AND p.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
 AND p.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
 AND p.buld_slno IS NOT DISTINCT FROM j.buld_slno AND p.bjd_cd = j.bjd_cd
"""

CHECK_POINTS_SQL = f"""
CREATE TEMP TABLE _ktg_bad_serving_points ON COMMIT DROP AS
WITH {RAW_POINT_CTES},
checked AS (
  SELECT r.*, ST_Distance(p.geom, r.geom) AS building_distance_m,
         ST_Distance(k.geom, r.geom) AS zip_distance_m,
         ST_Distance(a.geom, r.geom) AS emd_distance_m,
         array_remove(ARRAY[
    CASE WHEN ST_IsEmpty(r.geom) THEN 'empty_coordinate' END,
    CASE WHEN r.source_yyyymm IS NULL OR j.source_yyyymm IS NULL
              OR r.source_yyyymm IS DISTINCT FROM j.source_yyyymm
         THEN 'source_month_mismatch' END,
    CASE WHEN p.geom IS NULL THEN 'missing_building_polygon' END,
    CASE WHEN r.source_kind <> 'navi' AND NOT ST_DWithin(p.geom, r.geom, 500)
         THEN 'building_distance_over_500m' END,
    CASE WHEN r.source_kind = 'navi' AND NOT ST_Covers(p.geom, r.geom)
         THEN 'outside_building_polygon' END,
    CASE WHEN k.geom IS NULL THEN 'missing_zip_polygon'
         WHEN NOT ST_Covers(k.geom, r.geom) THEN 'outside_zip_polygon' END,
    CASE WHEN a.geom IS NULL THEN 'missing_emd_polygon'
         WHEN NOT ST_Covers(a.geom, r.geom) THEN 'outside_emd_polygon' END
  ], NULL) AS reasons
    FROM raw_serving_points r
    JOIN tl_juso_text j ON j.bd_mgt_sn = r.bd_mgt_sn
    LEFT JOIN LATERAL (
      SELECT k.geom FROM tl_kodis_bas k WHERE k.bas_id = j.zip_no
       ORDER BY r.geom <-> k.geom LIMIT 1
    ) k ON true
    LEFT JOIN tl_scco_emd a ON a.emd_cd = left(j.bjd_cd, 8)
    LEFT JOIN LATERAL (
      SELECT p.geom FROM tl_spbd_buld_polygon p WHERE {_POLYGON_ADDRESS_JOIN}
       ORDER BY r.geom <-> p.geom LIMIT 1
    ) p ON true
   WHERE r.geom IS NOT NULL
)
SELECT * FROM checked WHERE cardinality(reasons) > 0
"""

QUARANTINE_POINTS_SQL = f"""
INSERT INTO serving_coordinate_quarantine (
  run_id, entity_kind, entity_id, source_kind, source_key, source_file, source_yyyymm,
  original_geom, reasons, source_attributes, replacement_source_kind,
  replacement_source_key, replacement_source_file, replacement_source_yyyymm, replacement_geom
)
SELECT CAST(:run_id AS uuid), 'point', b.bd_mgt_sn, b.source_kind, b.source_key,
       b.source_file, b.source_yyyymm, b.geom, b.reasons,
       jsonb_build_object('rncode_full', j.rncode_full, 'bjd_cd', j.bjd_cd,
         'buld_se_cd', j.buld_se_cd, 'buld_mnnm', j.buld_mnnm,
         'buld_slno', j.buld_slno, 'zip_no', j.zip_no,
         'building_distance_m', b.building_distance_m,
         'zip_distance_m', b.zip_distance_m, 'emd_distance_m', b.emd_distance_m),
       CASE WHEN n.centroid_5179 IS NOT NULL THEN 'navi' END,
       n.bd_mgt_sn, n.source_file, n.source_yyyymm, n.centroid_5179
  FROM _ktg_bad_serving_points b JOIN tl_juso_text j ON j.bd_mgt_sn = b.bd_mgt_sn
  LEFT JOIN tl_scco_emd a ON a.emd_cd = left(j.bjd_cd, 8)
  LEFT JOIN LATERAL (
    SELECT n.bd_mgt_sn, n.source_file, n.source_yyyymm, n.centroid_5179
      FROM tl_navi_buld_centroid n
      JOIN tl_spbd_buld_polygon p ON p.bd_mgt_sn = n.bd_mgt_sn
     WHERE n.rncode_full = j.rncode_full
       AND n.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
       AND n.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
       AND n.buld_slno IS NOT DISTINCT FROM j.buld_slno
       AND left(n.bjd_cd, 8) = left(j.bjd_cd, 8)
       AND n.source_yyyymm = j.source_yyyymm
       AND {_POLYGON_ADDRESS_JOIN}
       AND NOT ST_IsEmpty(n.centroid_5179)
       AND ST_Covers(p.geom, n.centroid_5179)
       AND EXISTS (SELECT 1 FROM tl_kodis_bas k
                    WHERE k.bas_id = j.zip_no AND ST_Covers(k.geom, n.centroid_5179))
       AND ST_Covers(a.geom, n.centroid_5179)
     ORDER BY n.bd_mgt_sn LIMIT 1
  ) n ON true
"""

QUARANTINE_POLYGONS_SQL = f"""
INSERT INTO serving_coordinate_quarantine (
  run_id, entity_kind, entity_id, source_kind, source_key, source_file, source_yyyymm,
  reasons, source_attributes
)
SELECT CAST(:run_id AS uuid), 'building_polygon', p.bd_mgt_sn, 'shp', p.bd_mgt_sn,
       p.source_file, p.source_yyyymm, ARRAY[
         CASE WHEN (p.rncode_full IS NULL AND (NULLIF(p.sig_cd, '') IS NULL
                    OR NULLIF(p.rn_cd, '') IS NULL)) OR p.bjd_cd IS NULL
                    OR p.buld_mnnm IS NULL OR p.buld_slno IS NULL
              THEN 'missing_resolve_key' ELSE 'missing_text' END
       ], jsonb_build_object('rncode_full', p.rncode_full, 'bjd_cd', p.bjd_cd,
         'buld_se_cd', p.buld_se_cd, 'buld_mnnm', p.buld_mnnm, 'buld_slno', p.buld_slno)
  FROM tl_spbd_buld_polygon p
 WHERE NOT EXISTS (SELECT 1 FROM tl_juso_text j WHERE {_POLYGON_ADDRESS_JOIN})
"""


async def prepare_serving_quality(engine: AsyncEngine) -> str:
    """적재 manifest에 대응하는 판정을 원자적으로 게시한다. 원천은 변경하지 않는다."""
    async with engine.begin() as conn:
        await conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        return await _prepare_serving_quality(conn)


async def _prepare_serving_quality(conn: AsyncConnection) -> str:
    """호출자가 소유한 트랜잭션 안에서 판정과 이력을 함께 저장한다."""
    await conn.execute(text("SET LOCAL statement_timeout = 0"))
    await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ktg.serving_quality'))"))
    run_id = str(uuid4())
    await conn.execute(
        text(
            "INSERT INTO serving_quality_runs (run_id,policy_version,source_stamp,source_manifest) "
            f"VALUES (CAST(:run_id AS uuid),:policy,({SOURCE_STAMP_SQL}),({SOURCE_MANIFEST_SQL}))"
        ),
        {"run_id": run_id, "policy": POLICY_VERSION},
    )
    await conn.execute(text("DROP TABLE IF EXISTS pg_temp._ktg_bad_serving_points"))
    await conn.execute(text(CHECK_POINTS_SQL))
    await conn.execute(text(QUARANTINE_POINTS_SQL), {"run_id": run_id})
    await conn.execute(text(QUARANTINE_POLYGONS_SQL), {"run_id": run_id})
    await conn.execute(
        text(
            "UPDATE serving_quality_runs SET finished_at=clock_timestamp() "
            "WHERE run_id=CAST(:run_id AS uuid)"
        ),
        {"run_id": run_id},
    )
    return run_id


async def require_serving_quality(conn: AsyncConnection, *, run_id: str | None = None) -> None:
    """현재 입력에 대응하는 완료 판정이 없으면 게시·검사 완료를 차단한다."""
    active = await conn.scalar(text(ACTIVE_RUN_SQL))
    if active is None or (run_id is not None and str(active) != run_id):
        raise RuntimeError("서빙 좌표 품질 판정 뒤 원천이 변경됐습니다. 다시 검증해야 합니다.")
