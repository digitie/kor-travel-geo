"""Text/SHP consistency report SQL builders."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.dto.admin import ConsistencyCase, ConsistencyReport
from kortravelgeo.infra.admin_repo import AdminRepository

ProgressReporter = Callable[[float, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CaseSpec:
    name: str
    threshold: str
    sql: str


CASE_SQL: dict[str, CaseSpec] = {
    "C1": CaseSpec(
        name="텍스트에만 존재하는 BD_MGT_SN",
        threshold="위반 1건 이상 WARN",
        sql="""
WITH total AS (
  SELECT count(*)::bigint AS total FROM tl_juso_text
),
violations AS (
  SELECT j.bd_mgt_sn, j.sig_cd, j.rn, j.buld_mnnm, j.buld_slno
    FROM tl_juso_text j
    LEFT JOIN tl_spbd_buld_polygon p
      ON p.rncode_full = j.rncode_full
     AND p.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
     AND p.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
     AND p.buld_slno IS NOT DISTINCT FROM j.buld_slno
     AND p.bjd_cd = j.bjd_cd
   WHERE p.bd_mgt_sn IS NULL
)
SELECT count(*)::bigint AS count,
       (SELECT total FROM total) AS total,
       '{}'::jsonb AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(s)) FROM (SELECT * FROM violations LIMIT 20) s),
         '[]'::jsonb
       ) AS sample
  FROM violations
""",
    ),
    "C2": CaseSpec(
        name="SHP polygon에만 존재하는 BD_MGT_SN",
        threshold="위반 1건 이상 ERROR",
        sql="""
WITH total AS (
  SELECT count(*)::bigint AS total FROM tl_spbd_buld_polygon
),
violations AS (
  SELECT p.bd_mgt_sn,
         p.rncode_full,
         p.bjd_cd,
         p.buld_mnnm,
         p.buld_slno,
         CASE
           WHEN p.rncode_full IS NULL
             OR p.bjd_cd IS NULL
             OR p.buld_mnnm IS NULL
             OR p.buld_slno IS NULL
           THEN 'missing_resolve_key'
           ELSE 'missing_text'
         END AS reason
    FROM tl_spbd_buld_polygon p
    LEFT JOIN tl_juso_text j
      ON j.rncode_full = p.rncode_full
     AND j.buld_se_cd IS NOT DISTINCT FROM p.buld_se_cd
     AND j.buld_mnnm IS NOT DISTINCT FROM p.buld_mnnm
     AND j.buld_slno IS NOT DISTINCT FROM p.buld_slno
     AND j.bjd_cd = p.bjd_cd
   WHERE j.bd_mgt_sn IS NULL
),
stats AS (
  SELECT count(*)::bigint AS count,
         count(*) FILTER (WHERE reason = 'missing_resolve_key')::bigint
           AS missing_resolve_key,
         count(*) FILTER (WHERE reason = 'missing_text')::bigint AS missing_text
    FROM violations
)
SELECT count,
       (SELECT total FROM total) AS total,
       jsonb_build_object(
         'missing_resolve_key', missing_resolve_key,
         'missing_text', missing_text,
         'error_count', count
       ) AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(s)) FROM (SELECT * FROM violations LIMIT 20) s),
         '[]'::jsonb
       ) AS sample
  FROM stats
""",
    ),
    "C3": CaseSpec(
        name="대표 출입구가 해소되지 않은 건물",
        threshold="5% 초과 WARN, 그 이하는 INFO",
        sql="""
WITH serving_entrc AS MATERIALIZED (
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn,
         ent_man_no,
         geom,
         source_kind
    FROM (
      SELECT bd_mgt_sn, ent_man_no, geom, 'locsum' AS source_kind,
             0 AS source_priority,
             CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END AS rep_priority
        FROM tl_locsum_entrc
       WHERE bd_mgt_sn IS NOT NULL
      UNION ALL
      SELECT bd_mgt_sn, ent_man_no, geom, 'roadaddr' AS source_kind,
             1 AS source_priority, 0 AS rep_priority
        FROM tl_roadaddr_entrc
       WHERE source_yyyymm IN (
         SELECT DISTINCT source_yyyymm
           FROM tl_juso_text
          WHERE source_yyyymm IS NOT NULL
       )
    ) e
   ORDER BY bd_mgt_sn, source_priority, rep_priority, ent_man_no NULLS LAST
),
total AS (
  SELECT count(*)::bigint AS total FROM tl_juso_text
),
violations AS (
  SELECT j.bd_mgt_sn, j.sig_cd, j.rn, j.buld_mnnm, j.buld_slno
    FROM tl_juso_text j
    LEFT JOIN serving_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
   WHERE e.bd_mgt_sn IS NULL
)
SELECT count(*)::bigint AS count,
       (SELECT total FROM total) AS total,
       '{}'::jsonb AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(s)) FROM (SELECT * FROM violations LIMIT 20) s),
         '[]'::jsonb
       ) AS sample
  FROM violations
""",
    ),
    "C4": CaseSpec(
        name="출입구 좌표와 건물 polygon 거리 이상치",
        threshold="50m 초과 WARN, 500m 초과 ERROR",
        sql="""
WITH serving_entrc AS MATERIALIZED (
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn,
         ent_man_no,
         geom,
         source_kind
    FROM (
      SELECT bd_mgt_sn, ent_man_no, geom, 'locsum' AS source_kind,
             0 AS source_priority,
             CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END AS rep_priority
        FROM tl_locsum_entrc
       WHERE bd_mgt_sn IS NOT NULL
      UNION ALL
      SELECT bd_mgt_sn, ent_man_no, geom, 'roadaddr' AS source_kind,
             1 AS source_priority, 0 AS rep_priority
        FROM tl_roadaddr_entrc
       WHERE source_yyyymm IN (
         SELECT DISTINCT source_yyyymm
           FROM tl_juso_text
          WHERE source_yyyymm IS NOT NULL
       )
    ) e
   ORDER BY bd_mgt_sn, source_priority, rep_priority, ent_man_no NULLS LAST
),
distances AS MATERIALIZED (
  SELECT j.bd_mgt_sn,
         e.ent_man_no,
         e.source_kind,
         nearest.dist_m
    FROM serving_entrc e
    JOIN tl_juso_text j ON j.bd_mgt_sn = e.bd_mgt_sn
    JOIN LATERAL (
      SELECT ST_Distance(e.geom, p.geom) AS dist_m
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
stats AS (
  SELECT count(*)::bigint AS total,
         count(*) FILTER (WHERE dist_m > 50)::bigint AS over_50m,
         count(*) FILTER (WHERE dist_m > 500)::bigint AS over_500m,
         percentile_cont(0.50) WITHIN GROUP (ORDER BY dist_m) AS p50_m,
         percentile_cont(0.95) WITHIN GROUP (ORDER BY dist_m) AS p95_m,
         percentile_cont(0.99) WITHIN GROUP (ORDER BY dist_m) AS p99_m
    FROM distances
),
violations AS (
  SELECT bd_mgt_sn, ent_man_no, source_kind, round(dist_m::numeric, 2)::float8 AS dist_m
    FROM distances
   WHERE dist_m > 50
   ORDER BY dist_m DESC
   LIMIT 20
)
SELECT over_50m AS count,
       total,
       jsonb_build_object(
         'p50_m', p50_m,
         'p95_m', p95_m,
         'p99_m', p99_m,
         'over_50m', over_50m,
         'over_500m', over_500m,
         'error_count', over_500m
       ) AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(v)) FROM violations v),
         '[]'::jsonb
       ) AS sample
  FROM stats
""",
    ),
    "C5": CaseSpec(
        name="내비 centroid와 건물 polygon centroid 거리 이상치",
        threshold="10m 초과 WARN",
        sql="""
WITH best_navi AS (
  SELECT DISTINCT ON (
         rncode_full, buld_se_cd, buld_mnnm, buld_slno, left(bjd_cd, 8)
         )
         rncode_full,
         buld_se_cd,
         buld_mnnm,
         buld_slno,
         left(bjd_cd, 8) AS bjd_emd_cd,
         centroid_5179
    FROM tl_navi_buld_centroid
   WHERE rncode_full IS NOT NULL
     AND bjd_cd IS NOT NULL
   ORDER BY rncode_full, buld_se_cd, buld_mnnm, buld_slno, left(bjd_cd, 8), bd_mgt_sn
),
distances AS (
  SELECT j.bd_mgt_sn,
         nearest.dist_m
    FROM tl_juso_text j
    JOIN best_navi n
      ON n.rncode_full = j.rncode_full
     AND n.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
     AND n.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
     AND n.buld_slno IS NOT DISTINCT FROM j.buld_slno
     AND n.bjd_emd_cd = left(j.bjd_cd, 8)
    JOIN LATERAL (
      SELECT ST_Distance(n.centroid_5179, ST_Centroid(p.geom)) AS dist_m
        FROM tl_spbd_buld_polygon p
       WHERE p.rncode_full = j.rncode_full
         AND p.buld_se_cd IS NOT DISTINCT FROM j.buld_se_cd
         AND p.buld_mnnm IS NOT DISTINCT FROM j.buld_mnnm
         AND p.buld_slno IS NOT DISTINCT FROM j.buld_slno
         AND p.bjd_cd = j.bjd_cd
       ORDER BY n.centroid_5179 <-> p.geom
       LIMIT 1
    ) nearest ON true
),
stats AS (
  SELECT count(*)::bigint AS total,
         count(*) FILTER (WHERE dist_m > 10)::bigint AS over_10m,
         percentile_cont(0.95) WITHIN GROUP (ORDER BY dist_m) AS p95_m,
         percentile_cont(0.99) WITHIN GROUP (ORDER BY dist_m) AS p99_m
    FROM distances
),
violations AS (
  SELECT bd_mgt_sn, round(dist_m::numeric, 2)::float8 AS dist_m
    FROM distances
   WHERE dist_m > 10
   ORDER BY dist_m DESC
   LIMIT 20
)
SELECT over_10m AS count,
       total,
       jsonb_build_object('p95_m', p95_m, 'p99_m', p99_m, 'over_10m', over_10m) AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(v)) FROM violations v),
         '[]'::jsonb
       ) AS sample
  FROM stats
""",
    ),
    "C6": CaseSpec(
        name="우편번호 텍스트와 기초구역 polygon 불일치",
        threshold="zip_no polygon 누락 WARN, 좌표 외부 ERROR",
        sql="""
WITH serving_entrc AS MATERIALIZED (
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn,
         ent_man_no,
         geom,
         source_kind
    FROM (
      SELECT bd_mgt_sn, ent_man_no, geom, 'locsum' AS source_kind,
             0 AS source_priority,
             CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END AS rep_priority
        FROM tl_locsum_entrc
       WHERE bd_mgt_sn IS NOT NULL
      UNION ALL
      SELECT bd_mgt_sn, ent_man_no, geom, 'roadaddr' AS source_kind,
             1 AS source_priority, 0 AS rep_priority
        FROM tl_roadaddr_entrc
       WHERE source_yyyymm IN (
         SELECT DISTINCT source_yyyymm
           FROM tl_juso_text
          WHERE source_yyyymm IS NOT NULL
       )
    ) e
   ORDER BY bd_mgt_sn, source_priority, rep_priority, ent_man_no NULLS LAST
),
base AS MATERIALIZED (
  SELECT j.bd_mgt_sn, j.zip_no, e.ent_man_no, e.source_kind, e.geom,
         k.bas_id, k.geom AS bas_geom
    FROM tl_juso_text j
    JOIN serving_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN tl_kodis_bas k ON k.bas_id = j.zip_no
   WHERE j.zip_no IS NOT NULL
),
violations AS MATERIALIZED (
  SELECT bd_mgt_sn,
         zip_no,
         ent_man_no,
         source_kind,
         CASE
           WHEN bas_id IS NULL THEN 'missing_zip_polygon'
           WHEN NOT ST_Covers(bas_geom, geom) THEN 'outside_zip_polygon'
           ELSE 'ok'
         END AS reason
    FROM base
   WHERE bas_id IS NULL OR NOT ST_Covers(bas_geom, geom)
),
stats AS (
  SELECT (SELECT count(*)::bigint FROM base) AS total,
         count(*)::bigint AS count,
         count(*) FILTER (WHERE reason = 'missing_zip_polygon')::bigint AS missing_polygon,
         count(*) FILTER (WHERE reason = 'outside_zip_polygon')::bigint AS outside_polygon
    FROM violations
)
SELECT count,
       total,
       jsonb_build_object(
         'missing_polygon', missing_polygon,
         'outside_polygon', outside_polygon,
         'error_count', outside_polygon
       ) AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(v)) FROM (SELECT * FROM violations LIMIT 20) v),
         '[]'::jsonb
       ) AS sample
  FROM stats
""",
    ),
    "C7": CaseSpec(
        name="행정구역 polygon과 출입구 좌표 불일치",
        threshold="polygon 누락 WARN, 좌표 외부 ERROR",
        sql="""
WITH serving_entrc AS MATERIALIZED (
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn,
         ent_man_no,
         geom,
         source_kind
    FROM (
      SELECT bd_mgt_sn, ent_man_no, geom, 'locsum' AS source_kind,
             0 AS source_priority,
             CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END AS rep_priority
        FROM tl_locsum_entrc
       WHERE bd_mgt_sn IS NOT NULL
      UNION ALL
      SELECT bd_mgt_sn, ent_man_no, geom, 'roadaddr' AS source_kind,
             1 AS source_priority, 0 AS rep_priority
        FROM tl_roadaddr_entrc
       WHERE source_yyyymm IN (
         SELECT DISTINCT source_yyyymm
           FROM tl_juso_text
          WHERE source_yyyymm IS NOT NULL
       )
    ) e
   ORDER BY bd_mgt_sn, source_priority, rep_priority, ent_man_no NULLS LAST
),
base AS MATERIALIZED (
  SELECT j.bd_mgt_sn, left(j.bjd_cd, 8) AS emd_cd, e.ent_man_no, e.source_kind,
         e.geom, p.geom AS emd_geom
    FROM tl_juso_text j
    JOIN serving_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN tl_scco_emd p ON p.emd_cd = left(j.bjd_cd, 8)
),
violations AS MATERIALIZED (
  SELECT bd_mgt_sn,
         emd_cd,
         ent_man_no,
         source_kind,
         CASE
           WHEN emd_geom IS NULL THEN 'missing_emd_polygon'
           WHEN NOT ST_Covers(emd_geom, geom) THEN 'outside_emd_polygon'
           ELSE 'ok'
         END AS reason
    FROM base
   WHERE emd_geom IS NULL OR NOT ST_Covers(emd_geom, geom)
),
stats AS (
  SELECT (SELECT count(*)::bigint FROM base) AS total,
         count(*)::bigint AS count,
         count(*) FILTER (WHERE reason = 'missing_emd_polygon')::bigint AS missing_polygon,
         count(*) FILTER (WHERE reason = 'outside_emd_polygon')::bigint AS outside_polygon
    FROM violations
)
SELECT count,
       total,
       jsonb_build_object(
         'missing_polygon', missing_polygon,
         'outside_polygon', outside_polygon,
         'error_count', outside_polygon
       ) AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(v)) FROM (SELECT * FROM violations LIMIT 20) v),
         '[]'::jsonb
       ) AS sample
  FROM stats
""",
    ),
    "C8": CaseSpec(
        name="도로명 폴리라인과 출입구 좌표 인접성 불일치",
        threshold="같은 도로명 100m 밖 WARN",
        sql="""
WITH serving_entrc AS MATERIALIZED (
  SELECT DISTINCT ON (bd_mgt_sn)
         bd_mgt_sn,
         ent_man_no,
         geom,
         source_kind
    FROM (
      SELECT bd_mgt_sn, ent_man_no, geom, 'locsum' AS source_kind,
             0 AS source_priority,
             CASE WHEN ent_se_cd = '0' THEN 0 ELSE 1 END AS rep_priority
        FROM tl_locsum_entrc
       WHERE bd_mgt_sn IS NOT NULL
      UNION ALL
      SELECT bd_mgt_sn, ent_man_no, geom, 'roadaddr' AS source_kind,
             1 AS source_priority, 0 AS rep_priority
        FROM tl_roadaddr_entrc
       WHERE source_yyyymm IN (
         SELECT DISTINCT source_yyyymm
           FROM tl_juso_text
          WHERE source_yyyymm IS NOT NULL
       )
    ) e
   ORDER BY bd_mgt_sn, source_priority, rep_priority, ent_man_no NULLS LAST
),
base AS (
  SELECT j.bd_mgt_sn, j.rncode_full, e.ent_man_no, e.source_kind, e.geom
    FROM tl_juso_text j
    JOIN serving_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
),
violations AS (
  SELECT b.bd_mgt_sn, b.rncode_full, b.ent_man_no, b.source_kind
    FROM base b
   WHERE NOT EXISTS (
       SELECT 1
           FROM tl_sprd_manage m
          WHERE m.rncode_full = b.rncode_full
            AND m.geom IS NOT NULL
            AND ST_DWithin(b.geom, m.geom, 100)
       )
)
SELECT count(*)::bigint AS count,
       (SELECT count(*)::bigint FROM base) AS total,
       '{}'::jsonb AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(v)) FROM (SELECT * FROM violations LIMIT 20) v),
         '[]'::jsonb
       ) AS sample
  FROM violations
""",
    ),
    "C9": CaseSpec(
        name="PNU 형식 오류",
        threshold="위반 1건 이상 ERROR",
        sql="""
WITH total AS (
  SELECT count(*)::bigint AS total FROM tl_juso_text WHERE pnu IS NOT NULL
),
violations AS (
  SELECT bd_mgt_sn, pnu, bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno
    FROM tl_juso_text
   WHERE pnu IS NOT NULL
     AND (char_length(pnu) <> 19 OR substring(pnu from 11 for 1) NOT IN ('1','2'))
)
SELECT count(*)::bigint AS count,
       (SELECT total FROM total) AS total,
       '{}'::jsonb AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(v)) FROM (SELECT * FROM violations LIMIT 20) v),
         '[]'::jsonb
       ) AS sample
  FROM violations
""",
    ),
    "C10": CaseSpec(
        name="텍스트/SHP 적재 기준월 불일치",
        threshold="기준월 2종 이상 WARN",
        sql="""
WITH row_sources AS (
  SELECT 'tl_juso_text' AS table_name, source_yyyymm, count(*)::bigint AS row_count
    FROM tl_juso_text
   WHERE source_yyyymm IS NOT NULL
   GROUP BY source_yyyymm
  UNION ALL
  SELECT 'tl_locsum_entrc' AS table_name, source_yyyymm, count(*)::bigint AS row_count
    FROM tl_locsum_entrc
   WHERE source_yyyymm IS NOT NULL
   GROUP BY source_yyyymm
  UNION ALL
  SELECT 'tl_roadaddr_entrc' AS table_name, source_yyyymm, count(*)::bigint AS row_count
    FROM tl_roadaddr_entrc
   WHERE source_yyyymm IS NOT NULL
   GROUP BY source_yyyymm
  UNION ALL
  SELECT 'tl_navi_buld_centroid' AS table_name, source_yyyymm, count(*)::bigint AS row_count
    FROM tl_navi_buld_centroid
   WHERE source_yyyymm IS NOT NULL
   GROUP BY source_yyyymm
  UNION ALL
  SELECT 'tl_navi_entrc' AS table_name, source_yyyymm, count(*)::bigint AS row_count
    FROM tl_navi_entrc
   WHERE source_yyyymm IS NOT NULL
   GROUP BY source_yyyymm
  UNION ALL
  SELECT 'tl_spbd_buld_polygon' AS table_name, source_yyyymm, count(*)::bigint AS row_count
    FROM tl_spbd_buld_polygon
   WHERE source_yyyymm IS NOT NULL
   GROUP BY source_yyyymm
  UNION ALL
  SELECT 'tl_sppn_makarea' AS table_name, source_yyyymm, count(*)::bigint AS row_count
    FROM tl_sppn_makarea
   WHERE source_yyyymm IS NOT NULL
   GROUP BY source_yyyymm
),
manifest_sources AS (
  SELECT table_name, source_yyyymm, row_count::bigint
    FROM load_manifest
   WHERE table_name IN (
         'tl_juso_text',
         'tl_locsum_entrc',
         'tl_roadaddr_entrc',
         'tl_navi_buld_centroid',
         'tl_navi_entrc',
         'tl_spbd_buld_polygon',
         'tl_sppn_makarea'
       )
     AND source_yyyymm IS NOT NULL
),
sources AS (
  SELECT table_name, source_yyyymm, row_count, 'rows' AS evidence
    FROM row_sources
  UNION ALL
  SELECT table_name, source_yyyymm, row_count, 'manifest' AS evidence
    FROM manifest_sources m
   WHERE NOT EXISTS (
     SELECT 1
       FROM row_sources r
      WHERE r.table_name = m.table_name
   )
),
stats AS (
  SELECT count(*)::bigint AS total,
         count(DISTINCT source_yyyymm)::bigint AS distinct_months
    FROM sources
)
SELECT CASE WHEN distinct_months > 1 THEN total ELSE 0 END AS count,
       total,
       jsonb_build_object('distinct_months', distinct_months) AS metric,
       COALESCE(
         (SELECT jsonb_agg(to_jsonb(s)) FROM sources s),
         '[]'::jsonb
       ) AS sample
  FROM stats
""",
    ),
}

DEFAULT_CASES = tuple(CASE_SQL.keys())


async def run_case(engine: AsyncEngine, code: str) -> ConsistencyCase:
    spec = CASE_SQL[code]
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL statement_timeout = 0"))
        row = (await conn.execute(text(spec.sql))).mappings().one()
    count = int(row["count"] or 0)
    total = int(row["total"] or 0)
    ratio = (count / total) if total else 0.0
    metric = _metric(row.get("metric"))
    sample = _sample(row.get("sample"))
    return ConsistencyCase(
        code=code,
        name=spec.name,
        severity=_severity(code, count=count, ratio=ratio, metric=metric),
        count=count,
        ratio=ratio,
        threshold=spec.threshold,
        metric=metric,
        sample=sample,
    )


async def run_all_cases(
    engine: AsyncEngine,
    *,
    scope: str = "full",
    cases: tuple[str, ...] = DEFAULT_CASES,
    generated_by: Literal["cli", "api", "cron"] = "api",
    source_set: dict[str, Any] | None = None,
    on_progress: ProgressReporter | None = None,
) -> ConsistencyReport:
    started_at = datetime.now(UTC)
    case_results: list[ConsistencyCase] = []
    for index, code in enumerate(cases, start=1):
        result = await run_case(engine, code)
        case_results.append(result)
        if on_progress is not None:
            await on_progress(index / len(cases), code)
    severity_max = _max_severity(tuple(case_results))
    report = ConsistencyReport(
        report_id=f"consistency_{uuid4().hex}",
        scope=scope,
        severity_max=severity_max,
        source_set=source_set or {},
        started_at=started_at,
        finished_at=datetime.now(UTC),
        cases=tuple(case_results),
        generated_by=generated_by,
    )
    await AdminRepository(engine).insert_consistency_report(report)
    return report


def _severity(
    code: str,
    *,
    count: int,
    ratio: float,
    metric: dict[str, float] | None,
) -> Literal["OK", "INFO", "WARN", "ERROR"]:
    if count == 0:
        return "OK"
    metric = metric or {}
    if code in {"C2", "C9"}:
        return "ERROR"
    if code in {"C4", "C6", "C7"} and metric.get("error_count", 0.0) > 0:
        return "ERROR"
    if code == "C4" and metric.get("over_500m", 0.0) > 0:
        return "ERROR"
    if code == "C3":
        return "WARN" if ratio > 0.05 else "INFO"
    return "WARN"


def _metric(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    metric = {str(key): float(value) for key, value in raw.items() if value is not None}
    return metric or None


def _sample(raw: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(dict(item) for item in raw if isinstance(item, dict))


def _max_severity(cases: tuple[ConsistencyCase, ...]) -> Literal["OK", "INFO", "WARN", "ERROR"]:
    order = {"OK": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
    reverse = {value: key for key, value in order.items()}
    return reverse[max(order[case.severity] for case in cases)]  # type: ignore[return-value]
