"""Text/SHP consistency report SQL builders."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.dto.admin import ConsistencyCase, ConsistencyReport

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
    LEFT JOIN tl_spbd_buld_polygon p ON p.bd_mgt_sn = j.bd_mgt_sn
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
  SELECT p.bd_mgt_sn, p.source_file, p.source_yyyymm
    FROM tl_spbd_buld_polygon p
    LEFT JOIN tl_juso_text j ON j.bd_mgt_sn = p.bd_mgt_sn
   WHERE j.bd_mgt_sn IS NULL
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
    "C3": CaseSpec(
        name="대표 출입구가 해소되지 않은 건물",
        threshold="5% 초과 WARN, 그 이하는 INFO",
        sql="""
WITH total AS (
  SELECT count(*)::bigint AS total FROM tl_juso_text
),
violations AS (
  SELECT j.bd_mgt_sn, j.sig_cd, j.rn, j.buld_mnnm, j.buld_slno
    FROM tl_juso_text j
    LEFT JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
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
WITH distances AS (
  SELECT e.bd_mgt_sn,
         e.ent_man_no,
         ST_Distance(e.geom, p.geom) AS dist_m
    FROM tl_locsum_entrc e
    JOIN tl_spbd_buld_polygon p ON p.bd_mgt_sn = e.bd_mgt_sn
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
  SELECT bd_mgt_sn, ent_man_no, round(dist_m::numeric, 2)::float8 AS dist_m
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
         'over_500m', over_500m
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
WITH distances AS (
  SELECT n.bd_mgt_sn,
         ST_Distance(n.centroid_5179, ST_Centroid(p.geom)) AS dist_m
    FROM tl_navi_buld_centroid n
    JOIN tl_spbd_buld_polygon p ON p.bd_mgt_sn = n.bd_mgt_sn
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
WITH base AS (
  SELECT j.bd_mgt_sn, j.zip_no, e.ent_man_no, e.geom, k.bas_id, k.geom AS bas_geom
    FROM tl_juso_text j
    JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN tl_kodis_bas k ON k.bas_id = j.zip_no
   WHERE j.zip_no IS NOT NULL
),
violations AS (
  SELECT bd_mgt_sn,
         zip_no,
         ent_man_no,
         CASE
           WHEN bas_id IS NULL THEN 'missing_zip_polygon'
           WHEN NOT ST_Contains(bas_geom, geom) THEN 'outside_zip_polygon'
           ELSE 'ok'
         END AS reason
    FROM base
   WHERE bas_id IS NULL OR NOT ST_Contains(bas_geom, geom)
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
WITH base AS (
  SELECT j.bd_mgt_sn, left(j.bjd_cd, 8) AS emd_cd, e.ent_man_no, e.geom, p.geom AS emd_geom
    FROM tl_juso_text j
    JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
    LEFT JOIN tl_scco_emd p ON p.emd_cd = left(j.bjd_cd, 8)
),
violations AS (
  SELECT bd_mgt_sn,
         emd_cd,
         ent_man_no,
         CASE
           WHEN emd_geom IS NULL THEN 'missing_emd_polygon'
           WHEN NOT ST_Contains(emd_geom, geom) THEN 'outside_emd_polygon'
           ELSE 'ok'
         END AS reason
    FROM base
   WHERE emd_geom IS NULL OR NOT ST_Contains(emd_geom, geom)
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
WITH base AS (
  SELECT j.bd_mgt_sn, j.rncode_full, e.ent_man_no, e.geom
    FROM tl_juso_text j
    JOIN tl_locsum_entrc e ON e.bd_mgt_sn = j.bd_mgt_sn
),
violations AS (
  SELECT b.bd_mgt_sn, b.rncode_full, b.ent_man_no
    FROM base b
   WHERE NOT EXISTS (
         SELECT 1
           FROM tl_sprd_manage m
           JOIN tl_sprd_rw rw
             ON rw.sig_cd = m.sig_cd
            AND rw.rds_man_no = m.rds_man_no
          WHERE m.rncode_full = b.rncode_full
            AND ST_DWithin(b.geom, rw.geom, 100)
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
WITH sources AS (
  SELECT table_name, source_yyyymm
    FROM load_manifest
   WHERE table_name IN (
         'tl_juso_text',
         'tl_locsum_entrc',
         'tl_navi_buld_centroid',
         'tl_navi_entrc',
         'tl_spbd_buld_polygon'
       )
     AND source_yyyymm IS NOT NULL
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
    async with engine.connect() as conn:
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
    source_set: dict[str, str] | None = None,
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
    async with engine.begin() as conn:
        await conn.execute(
            _json_text(
                """
INSERT INTO load_consistency_reports
  (report_id, scope, started_at, finished_at, source_set, cases, severity_max, generated_by)
VALUES
  (:report_id, :scope, :started_at, :finished_at, :source_set, :cases, :severity_max, :generated_by)
""",
                "source_set",
                "cases",
            ),
            report.model_dump(mode="json"),
        )
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


def _json_text(sql: str, *json_params: str) -> Any:
    return text(sql).bindparams(*(bindparam(name, type_=JSONB) for name in json_params))
