"""Run T-130 C11 C4/C6/C7 regression root-cause analysis."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kortravelgeo.infra.engine import make_async_engine  # noqa: E402
from kortravelgeo.settings import get_settings  # noqa: E402
from scripts import run_t125_c11_serving_preflight as t125  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

RegressionKind = Literal[
    "candidate_regression",
    "candidate_improves_baseline",
    "shared_error",
    "baseline_only_error",
    "manual_review",
]

TASK_ID = "T-130"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("artifacts") / "t130-c11-regression-root-cause"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run T-130 C11 C4/C6/C7 regression root-cause analysis.",
    )
    parser.add_argument("--pg-dsn", help="PostgreSQL DSN. Defaults to KTG_PG_DSN/settings.")
    parser.add_argument(
        "--pg-database",
        help="Override only the database name from the configured PostgreSQL DSN.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=t125._default_data_root(),
        help="Juso data root that contains unused/도로명주소 건물 도형.",
    )
    parser.add_argument(
        "--source-yyyymm",
        default=t125.DEFAULT_SOURCE_YYYYMM,
        help="Roadaddr building shape bundle yyyymm used by T-125.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for T-130 JSON/CSV/GeoJSON artifacts.",
    )
    parser.add_argument(
        "--sido",
        action="append",
        choices=t125.DEFAULT_SIDO_CODES,
        help="Sido code to load if T-125 candidate tables must be rebuilt.",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Reuse existing T-125 address/entrance staging tables.",
    )
    parser.add_argument(
        "--reuse-candidate",
        action="store_true",
        help="Reuse existing T-125 candidate table without rebuilding it.",
    )
    parser.add_argument(
        "--keep-staging",
        action="store_true",
        help="Keep _ktg_t125_* tables after analysis.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    if args.pg_dsn:
        settings = settings.model_copy(update={"pg_dsn": args.pg_dsn})
    if args.pg_database:
        url = make_url(settings.pg_dsn).set(database=args.pg_database)
        settings = settings.model_copy(update={"pg_dsn": url.render_as_string(hide_password=False)})

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    run_started = time.monotonic()
    sido_codes: Sequence[str] = tuple(args.sido or t125.DEFAULT_SIDO_CODES)

    engine = make_async_engine(settings)
    summary: dict[str, Any] = {
        "task": TASK_ID,
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at.isoformat(),
        "source_yyyymm": args.source_yyyymm,
        "data_root": str(args.data_root),
        "sido_codes": list(sido_codes),
    }
    try:
        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            summary["database"] = await t125.collect_database_identity(conn)

        await ensure_candidate_tables(
            engine,
            data_root=args.data_root,
            source_yyyymm=args.source_yyyymm,
            sido_codes=sido_codes,
            skip_load=bool(args.skip_load),
            reuse_candidate=bool(args.reuse_candidate),
        )

        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            c4_rows = tag_rows("C4", await t125.list_mappings(conn, c4_sql()))
            c6_rows = tag_rows("C6", await t125.list_mappings(conn, c6_sql()))
            c7_rows = tag_rows("C7", await t125.list_mappings(conn, c7_sql()))

        artifacts = write_artifacts(output_dir, c4_rows, c6_rows, c7_rows)
        summary.update(build_summary(c4_rows, c6_rows, c7_rows, artifacts))
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary["elapsed_seconds"] = round(time.monotonic() - run_started, 3)
        t125.write_json(output_dir / "summary.json", summary)
        print(json.dumps(summary["case_summaries"], ensure_ascii=False, indent=2))
    finally:
        if not args.keep_staging:
            async with engine.begin() as conn:
                await t125.drop_work_tables(conn)
        await engine.dispose()


async def ensure_candidate_tables(
    engine: AsyncEngine,
    *,
    data_root: Path,
    source_yyyymm: str,
    sido_codes: Sequence[str],
    skip_load: bool,
    reuse_candidate: bool,
) -> None:
    if reuse_candidate:
        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            exists = await conn.scalar(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": t125.CANDIDATE_BEST_TABLE},
            )
            if exists is None:
                raise RuntimeError(
                    f"{t125.CANDIDATE_BEST_TABLE} does not exist; rerun without "
                    "--reuse-candidate"
                )
        return

    if not skip_load:
        await t125.load_staging(engine, data_root, source_yyyymm, sido_codes)
    else:
        await t125.create_t125_staging_indexes(engine)

    async with engine.begin() as conn:
        await t125.set_no_statement_timeout(conn)
        await t125.rebuild_candidate_tables(conn)


def serving_entrc_cte() -> str:
    return """
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
    """


def base_select_cte() -> str:
    return f"""
    SELECT
        j.bd_mgt_sn,
        concat_ws(
            ' ',
            j.ctp_kor_nm,
            j.sig_kor_nm,
            j.emd_kor_nm,
            j.rn,
            CASE
              WHEN j.buld_mnnm IS NULL THEN NULL
              WHEN COALESCE(j.buld_slno, 0) > 0
                THEN j.buld_mnnm::text || '-' || j.buld_slno::text
              ELSE j.buld_mnnm::text
            END
        ) AS road_addr,
        left(j.bjd_cd, 2) AS sido_cd,
        left(j.bjd_cd, 8) AS emd_cd,
        j.bjd_cd,
        j.rncode_full,
        j.buld_se_cd,
        j.buld_mnnm,
        j.buld_slno,
        j.zip_no,
        j.source_yyyymm AS text_source_yyyymm,
        c.sig_cd AS candidate_sig_cd,
        c.ent_man_no AS candidate_ent_man_no,
        c.entrc_se AS candidate_entrc_se,
        c.candidates_per_bd,
        c.rn_cd AS candidate_rn_cd,
        c.candidate_pt_5179,
        e.ent_man_no AS baseline_ent_man_no,
        e.source_kind AS baseline_source_kind,
        e.geom AS baseline_pt_5179,
        ST_X(ST_Transform(c.candidate_pt_5179, 4326)) AS candidate_lon,
        ST_Y(ST_Transform(c.candidate_pt_5179, 4326)) AS candidate_lat,
        CASE WHEN e.geom IS NULL THEN NULL ELSE ST_X(ST_Transform(e.geom, 4326)) END
            AS baseline_lon,
        CASE WHEN e.geom IS NULL THEN NULL ELSE ST_Y(ST_Transform(e.geom, 4326)) END
            AS baseline_lat
    FROM {t125.CANDIDATE_BEST_TABLE} AS c
    JOIN tl_juso_text AS j USING (bd_mgt_sn)
    LEFT JOIN serving_entrc AS e USING (bd_mgt_sn)
    WHERE c.candidate_pt_5179 IS NOT NULL
    """


def c4_sql() -> str:
    return f"""
    WITH serving_entrc AS MATERIALIZED (
      {serving_entrc_cte()}
    ),
    base AS MATERIALIZED (
      {base_select_cte()}
    ),
    distances AS MATERIALIZED (
        SELECT
            b.*,
            candidate_nearest.polygon_count AS candidate_polygon_count,
            candidate_nearest.dist_m AS candidate_dist_m,
            candidate_nearest.polygon_bd_mgt_sn AS candidate_polygon_bd_mgt_sn,
            candidate_nearest.polygon_bjd_cd AS candidate_polygon_bjd_cd,
            baseline_nearest.dist_m AS baseline_dist_m,
            baseline_nearest.polygon_bd_mgt_sn AS baseline_polygon_bd_mgt_sn,
            baseline_nearest.polygon_bjd_cd AS baseline_polygon_bjd_cd
        FROM base AS b
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) OVER () AS polygon_count,
                p.bd_mgt_sn AS polygon_bd_mgt_sn,
                p.bjd_cd AS polygon_bjd_cd,
                ST_Distance(b.candidate_pt_5179, p.geom) AS dist_m
            FROM tl_spbd_buld_polygon AS p
            WHERE p.rncode_full = b.candidate_sig_cd || b.candidate_rn_cd
              AND p.buld_se_cd IS NOT DISTINCT FROM b.buld_se_cd
              AND p.buld_mnnm IS NOT DISTINCT FROM b.buld_mnnm
              AND p.buld_slno IS NOT DISTINCT FROM b.buld_slno
              AND p.geom IS NOT NULL
            ORDER BY b.candidate_pt_5179 <-> p.geom
            LIMIT 1
        ) AS candidate_nearest ON true
        LEFT JOIN LATERAL (
            SELECT
                p.bd_mgt_sn AS polygon_bd_mgt_sn,
                p.bjd_cd AS polygon_bjd_cd,
                ST_Distance(b.baseline_pt_5179, p.geom) AS dist_m
            FROM tl_spbd_buld_polygon AS p
            WHERE b.baseline_pt_5179 IS NOT NULL
              AND p.rncode_full = b.rncode_full
              AND p.buld_se_cd IS NOT DISTINCT FROM b.buld_se_cd
              AND p.buld_mnnm IS NOT DISTINCT FROM b.buld_mnnm
              AND p.buld_slno IS NOT DISTINCT FROM b.buld_slno
              AND p.bjd_cd = b.bjd_cd
              AND p.geom IS NOT NULL
            ORDER BY b.baseline_pt_5179 <-> p.geom
            LIMIT 1
        ) AS baseline_nearest ON true
    )
    SELECT *
    FROM distances
    WHERE candidate_dist_m > 500
       OR baseline_dist_m > 500
    ORDER BY GREATEST(
        COALESCE(candidate_dist_m, 0),
        COALESCE(baseline_dist_m, 0)
    ) DESC, bd_mgt_sn
    """


def c6_sql() -> str:
    return polygon_coverage_sql(
        case_code="C6",
        polygon_table="tl_kodis_bas",
        polygon_key="bas_id",
        target_key_expr="b.zip_no",
        missing_reason="missing_zip_polygon",
        outside_reason="outside_zip_polygon",
    )


def c7_sql() -> str:
    return polygon_coverage_sql(
        case_code="C7",
        polygon_table="tl_scco_emd",
        polygon_key="emd_cd",
        target_key_expr="b.emd_cd",
        missing_reason="missing_emd_polygon",
        outside_reason="outside_emd_polygon",
    )


def polygon_coverage_sql(
    *,
    case_code: str,
    polygon_table: str,
    polygon_key: str,
    target_key_expr: str,
    missing_reason: str,
    outside_reason: str,
) -> str:
    return f"""
    WITH serving_entrc AS MATERIALIZED (
      {serving_entrc_cte()}
    ),
    base AS MATERIALIZED (
      {base_select_cte()}
    ),
    coverage AS MATERIALIZED (
        SELECT
            b.*,
            '{case_code}'::text AS case_code,
            p.{polygon_key} AS polygon_key,
            CASE
              WHEN p.{polygon_key} IS NULL THEN '{missing_reason}'
              WHEN NOT ST_Covers(p.geom, b.candidate_pt_5179) THEN '{outside_reason}'
              ELSE 'ok'
            END AS candidate_reason,
            CASE
              WHEN b.baseline_pt_5179 IS NULL THEN 'no_baseline_entrance'
              WHEN p.{polygon_key} IS NULL THEN '{missing_reason}'
              WHEN NOT ST_Covers(p.geom, b.baseline_pt_5179) THEN '{outside_reason}'
              ELSE 'ok'
            END AS baseline_reason
        FROM base AS b
        LEFT JOIN {polygon_table} AS p
          ON p.{polygon_key} = {target_key_expr}
         AND p.geom IS NOT NULL
    )
    SELECT *
    FROM coverage
    WHERE candidate_reason <> 'ok'
       OR baseline_reason IN ('{missing_reason}', '{outside_reason}')
    ORDER BY
      CASE WHEN candidate_reason <> 'ok' THEN 0 ELSE 1 END,
      bd_mgt_sn
    """


def tag_rows(case_code: str, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [tag_row(case_code, row) for row in rows]


def tag_row(case_code: str, row: Mapping[str, Any]) -> dict[str, Any]:
    tagged = dict(row)
    if case_code == "C4":
        regression_kind, root_cause = classify_c4(row)
    else:
        regression_kind, root_cause = classify_polygon_case(row)
    tagged["case_code"] = case_code
    tagged["regression_kind"] = regression_kind
    tagged["root_cause_tag"] = root_cause
    return tagged


def classify_c4(row: Mapping[str, Any]) -> tuple[RegressionKind, str]:
    candidate_dist = _float(row.get("candidate_dist_m"))
    baseline_dist = _float_or_none(row.get("baseline_dist_m"))
    candidate_over = candidate_dist > 500
    baseline_over = baseline_dist is not None and baseline_dist > 500
    if candidate_over and not baseline_over:
        if int(row.get("candidates_per_bd") or 0) > 1:
            return "candidate_regression", "multiple_candidates_candidate_far_from_building"
        if str(row.get("candidate_polygon_bjd_cd") or "") != str(row.get("bjd_cd") or ""):
            return "candidate_regression", "nearest_polygon_bjd_differs"
        return "candidate_regression", "candidate_far_from_building"
    if candidate_over and baseline_over:
        return "shared_error", "both_points_far_from_building"
    if baseline_over and not candidate_over:
        return "candidate_improves_baseline", "candidate_closer_than_baseline"
    return "manual_review", "distance_threshold_context"


def classify_polygon_case(row: Mapping[str, Any]) -> tuple[RegressionKind, str]:
    candidate_reason = str(row.get("candidate_reason") or "ok")
    baseline_reason = str(row.get("baseline_reason") or "ok")
    candidate_error = candidate_reason != "ok"
    baseline_error = baseline_reason not in {"ok", "no_baseline_entrance"}
    if candidate_error and not baseline_error:
        if baseline_reason == "no_baseline_entrance":
            return "candidate_regression", "candidate_error_without_baseline_entrance"
        return "candidate_regression", f"candidate_{candidate_reason}_baseline_ok"
    if candidate_error and baseline_error:
        if candidate_reason == baseline_reason:
            return "shared_error", f"shared_{candidate_reason}"
        return "shared_error", "candidate_and_baseline_different_polygon_errors"
    if baseline_error and not candidate_error:
        return "candidate_improves_baseline", f"baseline_{baseline_reason}_candidate_ok"
    return "manual_review", "coverage_threshold_context"


def build_summary(
    c4_rows: Sequence[Mapping[str, Any]],
    c6_rows: Sequence[Mapping[str, Any]],
    c7_rows: Sequence[Mapping[str, Any]],
    artifacts: Mapping[str, str],
) -> dict[str, Any]:
    case_rows = {"C4": c4_rows, "C6": c6_rows, "C7": c7_rows}
    case_summaries = {
        case_code: summarize_case(rows) for case_code, rows in case_rows.items()
    }
    return {
        "case_summaries": case_summaries,
        "artifacts": dict(artifacts),
    }


def summarize_case(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    regression_counts = Counter(str(row.get("regression_kind")) for row in rows)
    root_cause_counts = Counter(str(row.get("root_cause_tag")) for row in rows)
    if rows and "candidate_reason" in rows[0]:
        candidate_error_count = sum(1 for row in rows if row.get("candidate_reason") != "ok")
        baseline_error_count = sum(
            1
            for row in rows
            if row.get("baseline_reason") not in {"ok", "no_baseline_entrance"}
        )
    else:
        candidate_error_count = sum(
            1 for row in rows if _float(row.get("candidate_dist_m")) > 500
        )
        baseline_error_count = sum(
            1
            for row in rows
            if (_float_or_none(row.get("baseline_dist_m")) or 0.0) > 500
        )
    return {
        "row_count": len(rows),
        "candidate_error_count": candidate_error_count,
        "baseline_error_count": baseline_error_count,
        "regression_kind_counts": dict(sorted(regression_counts.items())),
        "root_cause_counts": dict(sorted(root_cause_counts.items())),
        "samples": [sample_row(row) for row in rows[:10]],
    }


def sample_row(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "bd_mgt_sn",
        "road_addr",
        "regression_kind",
        "root_cause_tag",
        "candidate_reason",
        "baseline_reason",
        "candidate_dist_m",
        "baseline_dist_m",
        "candidate_lon",
        "candidate_lat",
        "baseline_lon",
        "baseline_lat",
    )
    return {key: row.get(key) for key in keys if key in row}


def write_artifacts(
    output_dir: Path,
    c4_rows: Sequence[Mapping[str, Any]],
    c6_rows: Sequence[Mapping[str, Any]],
    c7_rows: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for case_code, rows in (("c4", c4_rows), ("c6", c6_rows), ("c7", c7_rows)):
        csv_path = output_dir / f"{case_code}_regression_rows.csv"
        geojson_path = output_dir / f"{case_code}_regression_rows.geojson"
        t125.write_csv(csv_path, rows)
        t125.write_geojson(geojson_path, rows)
        artifacts[f"{case_code}_csv"] = str(csv_path)
        artifacts[f"{case_code}_geojson"] = str(geojson_path)
    sql_path = output_dir / "reproduce_t130_regression_samples.sql"
    sql_path.write_text(reproduction_sql() + "\n", encoding="utf-8")
    artifacts["reproduction_sql"] = str(sql_path)
    artifacts["summary_json"] = str(output_dir / "summary.json")
    return artifacts


def reproduction_sql() -> str:
    return f"""-- T-130 C11 C4/C6/C7 회귀 샘플 재현 SQL
-- 전제: {t125.CANDIDATE_BEST_TABLE}가 존재해야 한다.

-- C4 후보 500m 초과 또는 baseline 500m 초과
{c4_sql()};

-- C6 후보/baseline 우편번호 polygon 오류
{c6_sql()};

-- C7 후보/baseline 행정구역 polygon 오류
{c7_sql()};
"""


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


if __name__ == "__main__":
    asyncio.run(main())
