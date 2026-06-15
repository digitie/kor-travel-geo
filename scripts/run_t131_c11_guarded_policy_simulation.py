"""Run T-131 guarded C11 candidate policy simulations."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

TASK_ID = "T-131"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("artifacts") / "t131-c11-guarded-policy-simulation"
FEATURE_TABLE = "_ktg_t131_c11_policy_features"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run T-131 C11 guarded policy simulation.")
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
        help="Directory for T-131 artifacts.",
    )
    parser.add_argument(
        "--sido",
        action="append",
        choices=t125.DEFAULT_SIDO_CODES,
        help="Sido code to load if T-125 candidate tables must be rebuilt.",
    )
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--reuse-candidate", action="store_true")
    parser.add_argument("--reuse-features", action="store_true")
    parser.add_argument("--keep-staging", action="store_true")
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
        "feature_table": FEATURE_TABLE,
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
            if not args.reuse_features:
                await rebuild_feature_table(conn, candidate_source_yyyymm=args.source_yyyymm)
            baseline = await t125.one_mapping(conn, baseline_sql())
            policies = await t125.list_mappings(conn, policy_summary_sql())

        artifacts = write_artifacts(
            output_dir,
            policies,
            source_yyyymm=args.source_yyyymm,
        )
        summary["baseline"] = baseline
        summary["policies"] = policies
        summary["artifacts"] = artifacts
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary["elapsed_seconds"] = round(time.monotonic() - run_started, 3)
        t125.write_json(output_dir / "summary.json", summary)
        print(json.dumps(policies, ensure_ascii=False, indent=2))
    finally:
        if not args.keep_staging:
            async with engine.begin() as conn:
                await t125.drop_work_tables(conn)
                await conn.execute(text(f"DROP TABLE IF EXISTS {FEATURE_TABLE}"))
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


async def rebuild_feature_table(conn: AsyncConnection, *, candidate_source_yyyymm: str) -> None:
    await conn.execute(text(f"DROP TABLE IF EXISTS {FEATURE_TABLE}"))
    await conn.execute(
        text(create_feature_table_sql()),
        {"candidate_source_yyyymm": candidate_source_yyyymm},
    )
    await conn.execute(
        text(f"CREATE UNIQUE INDEX {FEATURE_TABLE}_bd_idx ON {FEATURE_TABLE} (bd_mgt_sn)")
    )
    await conn.execute(text(f"ANALYZE {FEATURE_TABLE}"))


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


def feature_table_sql() -> str:
    return "\n".join(
        (
            f"DROP TABLE IF EXISTS {FEATURE_TABLE};",
            create_feature_table_sql().rstrip() + ";",
            f"CREATE UNIQUE INDEX {FEATURE_TABLE}_bd_idx ON {FEATURE_TABLE} (bd_mgt_sn);",
            f"ANALYZE {FEATURE_TABLE};",
        )
    )


def create_feature_table_sql() -> str:
    return f"""
    CREATE TABLE {FEATURE_TABLE} AS
    WITH serving_entrc AS MATERIALIZED (
      {serving_entrc_cte()}
    ),
    base AS MATERIALIZED (
        SELECT
            j.bd_mgt_sn,
            j.source_yyyymm AS text_source_yyyymm,
            CAST(:candidate_source_yyyymm AS text) AS candidate_source_yyyymm,
            mv.pt_source AS current_pt_source,
            mv.pt_5179 AS current_pt_5179,
            c.candidate_pt_5179,
            c.sig_cd AS candidate_sig_cd,
            c.rn_cd AS candidate_rn_cd,
            c.buld_se_cd,
            c.buld_mnnm,
            c.buld_slno,
            c.candidates_per_bd,
            j.rncode_full,
            j.bjd_cd,
            left(j.bjd_cd, 8) AS emd_cd,
            j.zip_no,
            e.geom AS baseline_pt_5179,
            e.bd_mgt_sn IS NOT NULL AS baseline_has_entrance
        FROM {t125.CANDIDATE_BEST_TABLE} AS c
        JOIN tl_juso_text AS j USING (bd_mgt_sn)
        JOIN mv_geocode_target AS mv USING (bd_mgt_sn)
        LEFT JOIN serving_entrc AS e USING (bd_mgt_sn)
        WHERE c.candidate_pt_5179 IS NOT NULL
    )
    SELECT
        b.bd_mgt_sn,
        b.text_source_yyyymm,
        b.candidate_source_yyyymm,
        b.current_pt_source,
        b.candidates_per_bd,
        b.baseline_has_entrance,
        ST_Distance(b.current_pt_5179, b.candidate_pt_5179) AS movement_m,
        candidate_building.dist_m AS candidate_c4_dist_m,
        baseline_building.dist_m AS baseline_c4_dist_m,
        (candidate_building.dist_m > 500) AS candidate_c4_over500,
        (baseline_building.dist_m > 500) AS baseline_c4_over500,
        COALESCE(candidate_zip.covered, false) AS candidate_c6_ok,
        COALESCE(baseline_zip.covered, true) AS baseline_c6_ok,
        COALESCE(candidate_emd.covered, false) AS candidate_c7_ok,
        COALESCE(baseline_emd.covered, true) AS baseline_c7_ok
    FROM base AS b
    LEFT JOIN LATERAL (
        SELECT ST_Distance(b.candidate_pt_5179, p.geom) AS dist_m
        FROM tl_spbd_buld_polygon AS p
        WHERE p.rncode_full = b.candidate_sig_cd || b.candidate_rn_cd
          AND p.buld_se_cd IS NOT DISTINCT FROM b.buld_se_cd
          AND p.buld_mnnm IS NOT DISTINCT FROM b.buld_mnnm
          AND p.buld_slno IS NOT DISTINCT FROM b.buld_slno
          AND p.geom IS NOT NULL
        ORDER BY b.candidate_pt_5179 <-> p.geom
        LIMIT 1
    ) AS candidate_building ON true
    LEFT JOIN LATERAL (
        SELECT ST_Distance(b.baseline_pt_5179, p.geom) AS dist_m
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
    ) AS baseline_building ON true
    LEFT JOIN LATERAL (
        SELECT bool_or(ST_Covers(z.geom, b.candidate_pt_5179)) AS covered
        FROM tl_kodis_bas AS z
        WHERE z.bas_id = b.zip_no
          AND z.geom IS NOT NULL
    ) AS candidate_zip ON true
    LEFT JOIN LATERAL (
        SELECT bool_or(ST_Covers(z.geom, b.baseline_pt_5179)) AS covered
        FROM tl_kodis_bas AS z
        WHERE b.baseline_pt_5179 IS NOT NULL
          AND z.bas_id = b.zip_no
          AND z.geom IS NOT NULL
    ) AS baseline_zip ON true
    LEFT JOIN LATERAL (
        SELECT bool_or(ST_Covers(e.geom, b.candidate_pt_5179)) AS covered
        FROM tl_scco_emd AS e
        WHERE e.emd_cd = b.emd_cd
          AND e.geom IS NOT NULL
    ) AS candidate_emd ON true
    LEFT JOIN LATERAL (
        SELECT bool_or(ST_Covers(e.geom, b.baseline_pt_5179)) AS covered
        FROM tl_scco_emd AS e
        WHERE b.baseline_pt_5179 IS NOT NULL
          AND e.emd_cd = b.emd_cd
          AND e.geom IS NOT NULL
    ) AS baseline_emd ON true;
    """


def baseline_sql() -> str:
    return f"""
    SELECT
        COUNT(*) AS candidate_rows,
        COUNT(*) FILTER (WHERE NOT baseline_has_entrance) AS baseline_c3_unresolved_in_candidates,
        COUNT(*) FILTER (WHERE baseline_c4_over500) AS baseline_c4_over500_in_candidates,
        COUNT(*) FILTER (WHERE NOT baseline_c6_ok) AS baseline_c6_error_in_candidates,
        COUNT(*) FILTER (WHERE NOT baseline_c7_ok) AS baseline_c7_error_in_candidates,
        COUNT(*) FILTER (WHERE text_source_yyyymm = candidate_source_yyyymm)
            AS same_text_month_candidate_rows
    FROM {FEATURE_TABLE}
    """


def policy_summary_sql() -> str:
    policies = {
        "blanket_c11": "true",
        "c4_50_c6_c7_ok": (
            "candidate_c4_dist_m <= 50 AND candidate_c6_ok AND candidate_c7_ok"
        ),
        "centroid_c4_50_c6_c7_ok": (
            "current_pt_source = 'centroid' AND candidate_c4_dist_m <= 50 "
            "AND candidate_c6_ok AND candidate_c7_ok"
        ),
        "centroid_c4_100_c6_c7_ok": (
            "current_pt_source = 'centroid' AND candidate_c4_dist_m <= 100 "
            "AND candidate_c6_ok AND candidate_c7_ok"
        ),
        "centroid_c4_50_c6_c7_single_candidate": (
            "current_pt_source = 'centroid' AND candidate_c4_dist_m <= 50 "
            "AND candidate_c6_ok AND candidate_c7_ok AND candidates_per_bd = 1"
        ),
        "centroid_c4_50_c6_c7_move_500": (
            "current_pt_source = 'centroid' AND candidate_c4_dist_m <= 50 "
            "AND candidate_c6_ok AND candidate_c7_ok AND movement_m <= 500"
        ),
        "same_text_month_only": "text_source_yyyymm = candidate_source_yyyymm",
    }
    selects = []
    for policy_name, predicate in policies.items():
        selects.append(policy_select(policy_name, predicate))
    return "\nUNION ALL\n".join(selects) + "\nORDER BY policy_name"


def policy_select(policy_name: str, predicate: str) -> str:
    return f"""
    SELECT
        '{policy_name}' AS policy_name,
        COUNT(*) FILTER (WHERE {predicate}) AS candidate_used_rows,
        COUNT(*) FILTER (WHERE {predicate} AND NOT baseline_has_entrance)
            AS fills_baseline_c3_unresolved,
        COUNT(*) FILTER (WHERE {predicate} AND baseline_c4_over500)
            AS replaces_baseline_c4_over500,
        COUNT(*) FILTER (WHERE {predicate} AND NOT baseline_c6_ok)
            AS replaces_baseline_c6_error,
        COUNT(*) FILTER (WHERE {predicate} AND NOT baseline_c7_ok)
            AS replaces_baseline_c7_error,
        COUNT(*) FILTER (WHERE {predicate} AND candidate_c4_over500)
            AS candidate_c4_over500,
        COUNT(*) FILTER (WHERE {predicate} AND NOT candidate_c6_ok)
            AS candidate_c6_error,
        COUNT(*) FILTER (WHERE {predicate} AND NOT candidate_c7_ok)
            AS candidate_c7_error,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY movement_m)
            FILTER (WHERE {predicate}) AS movement_p50_m,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY movement_m)
            FILTER (WHERE {predicate}) AS movement_p95_m,
        percentile_cont(0.99) WITHIN GROUP (ORDER BY movement_m)
            FILTER (WHERE {predicate}) AS movement_p99_m,
        MAX(movement_m) FILTER (WHERE {predicate}) AS movement_max_m,
        COUNT(*) FILTER (WHERE {predicate} AND movement_m > 100) AS movement_over_100m,
        COUNT(*) FILTER (WHERE {predicate} AND movement_m > 500) AS movement_over_500m
    FROM {FEATURE_TABLE}
    """


def write_artifacts(
    output_dir: Path,
    policies: Sequence[Mapping[str, Any]],
    *,
    source_yyyymm: str,
) -> dict[str, str]:
    csv_path = output_dir / "policy_summary.csv"
    if policies:
        with csv_path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(policies[0].keys()))
            writer.writeheader()
            writer.writerows(policies)
    else:
        csv_path.write_text("", encoding="utf-8")
    sql_path = output_dir / "reproduce_t131_policy_summary.sql"
    sql_path.write_text(
        feature_table_sql().replace(
            "CAST(:candidate_source_yyyymm AS text)",
            f"'{source_yyyymm}'::text",
        )
        + "\n\n"
        + policy_summary_sql()
        + ";\n",
        encoding="utf-8",
    )
    return {
        "policy_summary_csv": str(csv_path),
        "reproduction_sql": str(sql_path),
        "summary_json": str(output_dir / "summary.json"),
    }


if __name__ == "__main__":
    asyncio.run(main())
