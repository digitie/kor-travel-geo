"""Run T-133 C11 shadow serving performance and rollback rehearsal."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kortravelgeo.infra.engine import make_async_engine  # noqa: E402
from kortravelgeo.settings import Settings, get_settings  # noqa: E402
from scripts import benchmark_query_performance as sqlbench  # noqa: E402
from scripts import run_t125_c11_serving_preflight as t125  # noqa: E402
from scripts import run_t131_c11_guarded_policy_simulation as t131  # noqa: E402
from scripts import run_t132_c11_guarded_policy_validation as t132  # noqa: E402

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

TASK_ID = "T-133"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("artifacts") / "t133-c11-shadow-serving-rehearsal"
DEFAULT_SHADOW_SCHEMA = "_ktg_t133_shadow"
DEFAULT_SQL_REGRESSION_BUDGET_PCT = 5.0
DEFAULT_REST_REGRESSION_BUDGET_PCT = 5.0
DEFAULT_SAMPLE_HASH_LIMIT = 1_000
DEFAULT_SAMPLE_LIMIT = 50
DEFAULT_CASES_PER_GROUP = 5
DEFAULT_CONCURRENCY_LEVELS = (1, 4, 16, 64)
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
SHADOW_SCHEMA_PATTERN = re.compile(r"_ktg_t133_[A-Za-z0-9_]*\Z")

SUMMARY_KEYS: tuple[str, ...] = (
    "task",
    "schema_version",
    "started_at",
    "finished_at",
    "elapsed_seconds",
    "source_yyyymm",
    "data_root",
    "sido_codes",
    "shadow_schema",
    "shadow_search_path",
    "policy",
    "database",
    "policy_result",
    "flag_off_before",
    "shadow_build",
    "flag_on",
    "sql_benchmark",
    "rest_benchmark",
    "rollback",
    "flag_off_after",
    "gate_result",
    "cleanup",
    "artifacts",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run T-133 C11 shadow serving performance and rollback rehearsal.",
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
        help="Directory for T-133 artifacts.",
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
    parser.add_argument(
        "--reuse-shadow",
        action="store_true",
        help="Reuse existing shadow schema/table instead of rebuilding it.",
    )
    parser.add_argument("--keep-staging", action="store_true")
    parser.add_argument("--keep-shadow", action="store_true")
    parser.add_argument(
        "--shadow-schema",
        default=DEFAULT_SHADOW_SCHEMA,
        help="Temporary schema for shadow serving objects. Must start with _ktg_t133_.",
    )
    parser.add_argument(
        "--current-pt-source",
        choices=("centroid", "any"),
        default="centroid",
        help="Existing serving point source allowed for C11 replacement.",
    )
    parser.add_argument(
        "--building-distance-max-m",
        type=float,
        default=t132.DEFAULT_BUILDING_DISTANCE_MAX_M,
        help="Maximum C4 candidate building distance in meters.",
    )
    parser.add_argument(
        "--movement-max-m",
        type=float,
        default=t132.DEFAULT_MOVEMENT_MAX_M,
        help="Maximum current-to-candidate movement in meters.",
    )
    parser.add_argument("--no-movement-limit", action="store_true")
    parser.add_argument("--allow-c6-c7-errors", action="store_true")
    parser.add_argument("--require-single-candidate", action="store_true")
    parser.add_argument("--require-same-source-month", action="store_true")
    parser.add_argument(
        "--sample-hash-limit",
        type=int,
        default=DEFAULT_SAMPLE_HASH_LIMIT,
        help="Number of deterministic public rows used for flag-off hash checks.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=DEFAULT_SAMPLE_LIMIT,
        help="Maximum shadow movement samples to export.",
    )
    parser.add_argument(
        "--skip-sql-benchmark",
        action="store_true",
        help="Build/probe shadow objects but skip SQL p95 comparison.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Existing SQL benchmark corpus JSON. Defaults to a new deterministic corpus.",
    )
    parser.add_argument(
        "--cases-per-group",
        type=int,
        default=DEFAULT_CASES_PER_GROUP,
        help="Cases per query group when generating a SQL corpus.",
    )
    parser.add_argument(
        "--concurrency",
        action="append",
        type=int,
        help="Benchmark concurrency level. Repeat to test several levels.",
    )
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--statement-timeout-ms", type=int, default=5_000)
    parser.add_argument(
        "--sql-regression-budget-pct",
        type=float,
        default=DEFAULT_SQL_REGRESSION_BUDGET_PCT,
    )
    parser.add_argument(
        "--public-rest-report",
        type=Path,
        help="benchmark_api_latency.py JSON for the public/flag-off API path.",
    )
    parser.add_argument(
        "--shadow-rest-report",
        type=Path,
        help="benchmark_api_latency.py JSON for the shadow/flag-on API path.",
    )
    parser.add_argument(
        "--rest-regression-budget-pct",
        type=float,
        default=DEFAULT_REST_REGRESSION_BUDGET_PCT,
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    await run(args)


async def run(args: argparse.Namespace) -> None:
    validate_positive_int("sample_hash_limit", args.sample_hash_limit)
    validate_positive_int("sample_limit", args.sample_limit)
    validate_positive_int("cases_per_group", args.cases_per_group)
    validate_positive_int("iterations", args.iterations)
    validate_non_negative_int("warmup", args.warmup)
    validate_positive_int("statement_timeout_ms", args.statement_timeout_ms)
    validate_non_negative_number("sql_regression_budget_pct", args.sql_regression_budget_pct)
    validate_non_negative_number("rest_regression_budget_pct", args.rest_regression_budget_pct)
    shadow_schema = validate_shadow_schema(args.shadow_schema)

    settings = settings_from_args(args)
    shadow_search_path = f"{shadow_schema},public,x_extension"
    shadow_settings = settings.model_copy(update={"pg_search_path": shadow_search_path})
    policy = t132.build_policy_config(args)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    run_started = time.monotonic()
    sido_codes: Sequence[str] = tuple(args.sido or t125.DEFAULT_SIDO_CODES)
    artifacts: dict[str, str] = {"summary_json": str(output_dir / "summary.json")}

    engine = make_async_engine(settings)
    shadow_engine = make_async_engine(shadow_settings)
    shadow_dropped = False
    summary = build_summary_payload(
        started_at=started_at,
        source_yyyymm=args.source_yyyymm,
        data_root=args.data_root,
        sido_codes=sido_codes,
        shadow_schema=shadow_schema,
        shadow_search_path=shadow_search_path,
        policy=policy,
    )
    try:
        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            summary["database"] = await t125.collect_database_identity(conn)
            summary["flag_off_before"] = await collect_serving_identity(
                conn,
                "public",
                sample_hash_limit=args.sample_hash_limit,
            )

        await t131.ensure_candidate_tables(
            engine,
            data_root=args.data_root,
            source_yyyymm=args.source_yyyymm,
            sido_codes=sido_codes,
            skip_load=bool(args.skip_load),
            reuse_candidate=bool(args.reuse_candidate),
        )

        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            if args.reuse_features:
                await t132.require_table(conn, t131.FEATURE_TABLE)
            else:
                await t131.rebuild_feature_table(
                    conn,
                    candidate_source_yyyymm=args.source_yyyymm,
                )
            policy_result = await t125.one_mapping(conn, t132.policy_result_sql(policy))
            summary["policy_result"] = policy_result
            if args.reuse_shadow:
                await require_shadow_relations(conn, shadow_schema)
                shadow_build: dict[str, Any] = {
                    "status": "reused",
                    "schema": shadow_schema,
                    "target_relation": qualified_identifier(shadow_schema, "mv_geocode_target"),
                    "text_search_relation": qualified_identifier(
                        shadow_schema,
                        "mv_geocode_text_search",
                    ),
                }
            else:
                columns = await public_target_columns(conn)
                await rebuild_shadow_serving(conn, shadow_schema, policy, columns)
                shadow_build = {
                    "status": "rebuilt",
                    "schema": shadow_schema,
                    "target_relation": qualified_identifier(shadow_schema, "mv_geocode_target"),
                    "text_search_relation": qualified_identifier(
                        shadow_schema,
                        "mv_geocode_text_search",
                    ),
                    "columns": list(columns),
                    "index_count": len(shadow_index_sql(shadow_schema)),
                }
            summary["shadow_build"] = shadow_build
            shadow_identity = await collect_serving_identity(
                conn,
                shadow_schema,
                sample_hash_limit=args.sample_hash_limit,
            )
            movement_samples = await collect_shadow_movement_samples(
                conn,
                shadow_schema,
                policy,
                sample_limit=args.sample_limit,
            )
            sample_path = output_dir / "shadow_movement_samples.csv"
            t125.write_csv(sample_path, movement_samples)
            artifacts["shadow_movement_samples_csv"] = str(sample_path)
            summary["flag_on"] = {
                "shadow_identity": shadow_identity,
                "applied_rows": int(policy_result.get("candidate_used_rows") or 0),
                "coord_source_detail": policy.coord_source_detail,
                "movement_samples": movement_samples,
            }

        if args.skip_sql_benchmark:
            summary["sql_benchmark"] = {
                "status": "not_run",
                "reason": "--skip-sql-benchmark was set",
                "required": True,
            }
        else:
            sql_benchmark = await run_sql_benchmark_pair(
                engine,
                shadow_engine,
                settings=settings,
                shadow_settings=shadow_settings,
                output_dir=output_dir,
                corpus_path=args.corpus,
                cases_per_group=args.cases_per_group,
                concurrency_levels=tuple(args.concurrency or DEFAULT_CONCURRENCY_LEVELS),
                iterations=args.iterations,
                warmup=args.warmup,
                statement_timeout_ms=args.statement_timeout_ms,
                regression_budget_pct=args.sql_regression_budget_pct,
            )
            summary["sql_benchmark"] = sql_benchmark
            artifacts.update(sql_benchmark.get("artifacts", {}))

        summary["rest_benchmark"] = rest_benchmark_summary(
            args.public_rest_report,
            args.shadow_rest_report,
            regression_budget_pct=args.rest_regression_budget_pct,
        )

        if args.keep_shadow:
            rollback = {
                "status": "skipped_keep_shadow",
                "shadow_schema": shadow_schema,
                "dropped": False,
            }
        else:
            async with engine.begin() as conn:
                rollback = await drop_shadow_schema(conn, shadow_schema)
                shadow_dropped = True
        summary["rollback"] = rollback

        async with engine.begin() as conn:
            summary["flag_off_after"] = await collect_serving_identity(
                conn,
                "public",
                sample_hash_limit=args.sample_hash_limit,
            )
        summary["gate_result"] = evaluate_gate(summary)
        print(json.dumps(summary["gate_result"], ensure_ascii=False, indent=2))
    finally:
        cleanup: dict[str, Any]
        if not args.keep_shadow and not shadow_dropped:
            async with engine.begin() as conn:
                await drop_shadow_schema(conn, shadow_schema)
        if args.keep_staging:
            cleanup = {
                "status": "skipped_keep_staging",
                "checked_relations": t132.cleanup_relation_names(),
                "remaining_relations": "not_checked",
                "passed": None,
            }
        else:
            async with engine.begin() as conn:
                await t132.cleanup_work_tables(conn)
                cleanup = await t132.verify_cleanup(conn)
        await shadow_engine.dispose()
        await engine.dispose()
        summary["cleanup"] = cleanup
        summary["artifacts"] = artifacts
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary["elapsed_seconds"] = round(time.monotonic() - run_started, 3)
        t125.write_json(output_dir / "summary.json", summary)


def settings_from_args(args: argparse.Namespace) -> Settings:
    settings = get_settings()
    if args.pg_dsn:
        settings = settings.model_copy(update={"pg_dsn": args.pg_dsn})
    if args.pg_database:
        url = make_url(settings.pg_dsn).set(database=args.pg_database)
        settings = settings.model_copy(update={"pg_dsn": url.render_as_string(hide_password=False)})
    return settings


async def rebuild_shadow_serving(
    conn: AsyncConnection,
    shadow_schema: str,
    policy: t132.GuardedPolicyConfig,
    columns: Sequence[str],
) -> None:
    await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(shadow_schema)}"))
    await conn.execute(
        text(
            f"""
            DROP TABLE IF EXISTS {qualified_identifier(shadow_schema, "mv_geocode_text_search")};
            DROP TABLE IF EXISTS {qualified_identifier(shadow_schema, "mv_geocode_target")};
            """
        )
    )
    await conn.execute(text(create_shadow_target_sql(shadow_schema, policy, columns)))
    await conn.execute(text(create_shadow_text_search_sql(shadow_schema)))
    for statement in shadow_index_sql(shadow_schema):
        await conn.execute(text(statement))
    await conn.execute(text(f"ANALYZE {qualified_identifier(shadow_schema, 'mv_geocode_target')}"))
    await conn.execute(
        text(f"ANALYZE {qualified_identifier(shadow_schema, 'mv_geocode_text_search')}")
    )


def create_shadow_target_sql(
    shadow_schema: str,
    policy: t132.GuardedPolicyConfig,
    columns: Sequence[str],
) -> str:
    validate_shadow_schema(shadow_schema)
    select_list = ",\n  ".join(shadow_target_select_expressions(columns))
    feature_table = quote_identifier(t131.FEATURE_TABLE)
    candidate_table = quote_identifier(t125.CANDIDATE_BEST_TABLE)
    return f"""
CREATE UNLOGGED TABLE {qualified_identifier(shadow_schema, "mv_geocode_target")} AS
WITH policy AS MATERIALIZED (
  SELECT f.bd_mgt_sn
    FROM {feature_table} AS f
   WHERE {t132.policy_predicate(policy)}
)
SELECT
  {select_list}
FROM public.mv_geocode_target AS mv
LEFT JOIN policy AS p
  ON p.bd_mgt_sn = mv.bd_mgt_sn
LEFT JOIN {candidate_table} AS c
  ON c.bd_mgt_sn = p.bd_mgt_sn
"""


def shadow_target_select_expressions(columns: Sequence[str]) -> tuple[str, ...]:
    if "bd_mgt_sn" not in columns:
        msg = "mv_geocode_target must contain bd_mgt_sn"
        raise ValueError(msg)
    if "pt_5179" not in columns or "pt_4326" not in columns:
        msg = "mv_geocode_target must contain pt_5179 and pt_4326"
        raise ValueError(msg)
    expressions: list[str] = []
    for column in columns:
        quoted = quote_identifier(column)
        if column == "pt_5179":
            expressions.append(
                "CASE WHEN p.bd_mgt_sn IS NOT NULL "
                f"THEN c.candidate_pt_5179 ELSE mv.{quoted} END AS {quoted}"
            )
        elif column == "pt_4326":
            expressions.append(
                "CASE WHEN p.bd_mgt_sn IS NOT NULL "
                f"THEN ST_Transform(c.candidate_pt_5179, 4326) ELSE mv.{quoted} END AS {quoted}"
            )
        else:
            expressions.append(f"mv.{quoted} AS {quoted}")
    return tuple(expressions)


def create_shadow_text_search_sql(shadow_schema: str) -> str:
    target = qualified_identifier(shadow_schema, "mv_geocode_target")
    text_search = qualified_identifier(shadow_schema, "mv_geocode_text_search")
    return f"""
CREATE UNLOGGED TABLE {text_search} AS
SELECT
  bd_mgt_sn,
  left(bjd_cd, 2) AS sido_cd,
  left(bjd_cd, 5) AS sig_cd,
  bjd_cd,
  si_nm,
  sgg_nm,
  rn_nrm,
  buld_nm_nrm,
  sigungu_buld_nm_nrm,
  buld_mnnm,
  pt_source
FROM {target}
WHERE rn_nrm IS NOT NULL
  AND rn_nrm <> ''
"""


def shadow_index_sql(shadow_schema: str) -> tuple[str, ...]:
    target = qualified_identifier(shadow_schema, "mv_geocode_target")
    text_search = qualified_identifier(shadow_schema, "mv_geocode_text_search")

    def idx(name: str) -> str:
        return quote_identifier(name)

    return (
        f"CREATE UNIQUE INDEX {idx('idx_mv_geocode_target_pk')} ON {target} (bd_mgt_sn)",
        (
            f"CREATE INDEX {idx('idx_mv_road')} ON {target} "
            "(rncode_full, buld_mnnm, buld_slno, buld_se_cd)"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_jibun')} ON {target} "
            "(bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno)"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_jibun_name_exact')} ON {target} "
            "(si_nm, sgg_nm, mntn_yn, lnbr_mnnm, lnbr_slno, "
            "emd_nm, li_nm, pt_source, bd_mgt_sn)"
        ),
        f"CREATE INDEX {idx('idx_mv_rn_nrm_exact')} ON {target} (rn_nrm, bd_mgt_sn)",
        (
            f"CREATE INDEX {idx('idx_mv_buld_nm_nrm_exact')} ON {target} "
            "(buld_nm_nrm, bd_mgt_sn) WHERE buld_nm_nrm IS NOT NULL"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_sigungu_buld_nm_nrm_exact')} ON {target} "
            "(sigungu_buld_nm_nrm, bd_mgt_sn) WHERE sigungu_buld_nm_nrm IS NOT NULL"
        ),
        f"CREATE INDEX {idx('idx_mv_rn_trgm')} ON {target} USING GIN (rn_nrm gin_trgm_ops)",
        (
            f"CREATE INDEX {idx('idx_mv_buld_nm_trgm')} ON {target} "
            "USING GIN (buld_nm_nrm gin_trgm_ops)"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_geom5179')} ON {target} "
            "USING GIST (pt_5179) WHERE pt_5179 IS NOT NULL"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_geom4326')} ON {target} "
            "USING GIST (pt_4326) WHERE pt_4326 IS NOT NULL"
        ),
        f"CREATE INDEX {idx('idx_mv_pt_source')} ON {target} (pt_source)",
        f"CREATE UNIQUE INDEX {idx('idx_mv_text_search_pk')} ON {text_search} (bd_mgt_sn)",
        (
            f"CREATE INDEX {idx('idx_mv_text_search_sig_buld')} ON {text_search} "
            "(sig_cd, buld_mnnm, bd_mgt_sn)"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_text_search_sido_buld')} ON {text_search} "
            "(sido_cd, buld_mnnm, bd_mgt_sn)"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_text_search_bjd_prefix_buld')} ON {text_search} "
            "(bjd_cd text_pattern_ops, buld_mnnm, bd_mgt_sn)"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_text_search_rn_trgm')} ON {text_search} "
            "USING GIN (rn_nrm gin_trgm_ops)"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_text_search_buld_nm_trgm')} ON {text_search} "
            "USING GIN (buld_nm_nrm gin_trgm_ops) WHERE buld_nm_nrm IS NOT NULL"
        ),
        (
            f"CREATE INDEX {idx('idx_mv_text_search_sigungu_buld_nm_trgm')} ON {text_search} "
            "USING GIN (sigungu_buld_nm_nrm gin_trgm_ops) "
            "WHERE sigungu_buld_nm_nrm IS NOT NULL"
        ),
    )


async def public_target_columns(conn: AsyncConnection) -> tuple[str, ...]:
    rows = (
        await conn.execute(
            text(
                """
                SELECT a.attname
                  FROM pg_attribute AS a
                  JOIN pg_class AS c ON c.oid = a.attrelid
                  JOIN pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public'
                   AND c.relname = 'mv_geocode_target'
                   AND a.attnum > 0
                   AND NOT a.attisdropped
                 ORDER BY a.attnum
                """
            )
        )
    ).scalars().all()
    columns = tuple(str(row) for row in rows)
    if not columns:
        msg = "public.mv_geocode_target has no columns or does not exist"
        raise RuntimeError(msg)
    shadow_target_select_expressions(columns)
    return columns


async def collect_serving_identity(
    conn: AsyncConnection,
    schema: str,
    *,
    sample_hash_limit: int,
) -> dict[str, Any]:
    validate_schema_identifier(schema)
    target = qualified_identifier(schema, "mv_geocode_target")
    text_search = qualified_identifier(schema, "mv_geocode_text_search")
    row = await t125.one_mapping(
        conn,
        f"""
        WITH sample AS (
            SELECT bd_mgt_sn, pt_source, pt_5179, pt_4326
              FROM {target}
             ORDER BY bd_mgt_sn
             LIMIT :sample_hash_limit
        )
        SELECT
            (SELECT COUNT(*) FROM {target})::bigint AS target_rows,
            (SELECT COUNT(*) FROM {target} WHERE pt_5179 IS NOT NULL)::bigint AS target_point_rows,
            (SELECT COUNT(*) FROM {text_search})::bigint AS text_search_rows,
            (
              SELECT md5(COALESCE(string_agg(
                bd_mgt_sn || ':' ||
                COALESCE(pt_source, '') || ':' ||
                COALESCE(encode(ST_AsEWKB(pt_5179), 'hex'), '') || ':' ||
                COALESCE(encode(ST_AsEWKB(pt_4326), 'hex'), ''),
                '|' ORDER BY bd_mgt_sn
              ), ''))
              FROM sample
            ) AS sample_hash
        """,
        {"sample_hash_limit": sample_hash_limit},
    )
    if schema == "public":
        row["active_release"] = await collect_active_release(conn)
    return row


async def collect_active_release(conn: AsyncConnection) -> dict[str, Any]:
    exists = await conn.scalar(text("SELECT to_regclass('ops.serving_releases')"))
    if exists is None:
        return {}
    result = await conn.execute(
        text(
            """
            SELECT
                serving_release_id::text AS serving_release_id,
                dataset_snapshot_id::text AS dataset_snapshot_id,
                release_kind,
                mv_name,
                mv_hash,
                consistency_gate,
                state
            FROM ops.serving_releases
            WHERE state = 'active'
            ORDER BY activated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
            """
        )
    )
    return dict(result.mappings().first() or {})


async def collect_shadow_movement_samples(
    conn: AsyncConnection,
    shadow_schema: str,
    policy: t132.GuardedPolicyConfig,
    *,
    sample_limit: int,
) -> list[dict[str, Any]]:
    shadow_target = qualified_identifier(shadow_schema, "mv_geocode_target")
    return await t125.list_mappings(
        conn,
        f"""
        SELECT
            f.bd_mgt_sn,
            '{policy.policy_name}' AS policy_name,
            '{policy.coord_source_detail}' AS coord_source_detail,
            public_mv.pt_source AS public_pt_source,
            shadow_mv.pt_source AS shadow_pt_source,
            f.movement_m,
            f.candidate_c4_dist_m,
            f.candidate_c6_ok,
            f.candidate_c7_ok,
            ST_X(ST_Transform(public_mv.pt_5179, 4326)) AS public_lon,
            ST_Y(ST_Transform(public_mv.pt_5179, 4326)) AS public_lat,
            ST_X(ST_Transform(shadow_mv.pt_5179, 4326)) AS shadow_lon,
            ST_Y(ST_Transform(shadow_mv.pt_5179, 4326)) AS shadow_lat
        FROM {quote_identifier(t131.FEATURE_TABLE)} AS f
        JOIN public.mv_geocode_target AS public_mv USING (bd_mgt_sn)
        JOIN {shadow_target} AS shadow_mv USING (bd_mgt_sn)
        WHERE {t132.policy_predicate(policy)}
        ORDER BY f.movement_m DESC, f.bd_mgt_sn
        LIMIT :sample_limit
        """,
        {"sample_limit": sample_limit},
    )


async def run_sql_benchmark_pair(
    public_engine: AsyncEngine,
    shadow_engine: AsyncEngine,
    *,
    settings: Settings,
    shadow_settings: Settings,
    output_dir: Path,
    corpus_path: Path | None,
    cases_per_group: int,
    concurrency_levels: Sequence[int],
    iterations: int,
    warmup: int,
    statement_timeout_ms: int,
    regression_budget_pct: float,
) -> dict[str, Any]:
    validate_concurrency_levels(concurrency_levels)
    if corpus_path is None:
        cases = await sqlbench.build_corpus(public_engine, cases_per_group=cases_per_group)
    else:
        cases = sqlbench.corpus_from_json(corpus_path)
    corpus_output = output_dir / "sql_corpus.json"
    corpus_output.write_text(sqlbench.corpus_to_json(cases), encoding="utf-8")
    started_at = datetime.now(UTC).isoformat()
    public_report = await sqlbench.run_benchmark(
        public_engine,
        cases,
        run_id="t133-public-sql",
        settings=settings,
        concurrency_levels=concurrency_levels,
        iterations=iterations,
        warmup=warmup,
        statement_timeout_ms=statement_timeout_ms,
        started_at=started_at,
    )
    shadow_report = await sqlbench.run_benchmark(
        shadow_engine,
        cases,
        run_id="t133-shadow-sql",
        settings=shadow_settings,
        concurrency_levels=concurrency_levels,
        iterations=iterations,
        warmup=warmup,
        statement_timeout_ms=statement_timeout_ms,
        started_at=started_at,
    )
    public_path = output_dir / "sql_public_benchmark.json"
    shadow_path = output_dir / "sql_shadow_benchmark.json"
    public_path.write_text(sqlbench.report_to_json(public_report), encoding="utf-8")
    shadow_path.write_text(sqlbench.report_to_json(shadow_report), encoding="utf-8")
    comparison = compare_summary_rows(
        public_report.summaries,
        shadow_report.summaries,
        regression_budget_pct=regression_budget_pct,
    )
    return {
        **comparison,
        "run": {
            "cases": len(cases),
            "concurrency_levels": list(concurrency_levels),
            "iterations": iterations,
            "warmup": warmup,
            "statement_timeout_ms": statement_timeout_ms,
        },
        "artifacts": {
            "sql_corpus_json": str(corpus_output),
            "sql_public_benchmark_json": str(public_path),
            "sql_shadow_benchmark_json": str(shadow_path),
        },
    }


def rest_benchmark_summary(
    public_report_path: Path | None,
    shadow_report_path: Path | None,
    *,
    regression_budget_pct: float,
) -> dict[str, Any]:
    if public_report_path is None or shadow_report_path is None:
        return {
            "status": "not_run",
            "required": True,
            "reason": "public/shadow REST benchmark reports were not both provided",
            "public_report": str(public_report_path) if public_report_path else None,
            "shadow_report": str(shadow_report_path) if shadow_report_path else None,
        }
    public_payload = json.loads(public_report_path.read_text(encoding="utf-8"))
    shadow_payload = json.loads(shadow_report_path.read_text(encoding="utf-8"))
    comparison = compare_summary_rows(
        public_payload.get("summaries", ()),
        shadow_payload.get("summaries", ()),
        regression_budget_pct=regression_budget_pct,
    )
    return {
        **comparison,
        "public_report": str(public_report_path),
        "shadow_report": str(shadow_report_path),
        "public_case_count": len(public_payload.get("cases", ())),
        "shadow_case_count": len(shadow_payload.get("cases", ())),
    }


def compare_summary_rows(
    public_rows: Sequence[Any],
    shadow_rows: Sequence[Any],
    *,
    regression_budget_pct: float,
) -> dict[str, Any]:
    public_by_key = {summary_key(row): row for row in public_rows}
    shadow_by_key = {summary_key(row): row for row in shadow_rows}
    keys = sorted(set(public_by_key) | set(shadow_by_key))
    rows: list[dict[str, Any]] = []
    hard_blocks: list[str] = []
    max_regression: float | None = None
    for key in keys:
        public = public_by_key.get(key)
        shadow = shadow_by_key.get(key)
        group, sql_name, concurrency = key
        if public is None or shadow is None:
            hard_blocks.append(f"missing benchmark row for {group}/{sql_name}/c{concurrency}")
            rows.append(
                {
                    "group": group,
                    "sql_name": sql_name,
                    "concurrency": concurrency,
                    "status": "missing",
                }
            )
            continue
        public_errors = int(summary_value(public, "errors") or 0)
        shadow_errors = int(summary_value(shadow, "errors") or 0)
        public_p95 = optional_float(summary_value(public, "p95_ms"))
        shadow_p95 = optional_float(summary_value(shadow, "p95_ms"))
        regression = p95_regression_pct(public_p95, shadow_p95)
        row_status = "passed"
        if public_errors or shadow_errors:
            row_status = "failed"
            hard_blocks.append(f"errors in {group}/{sql_name}/c{concurrency}")
        if regression is None:
            row_status = "failed"
            hard_blocks.append(f"invalid p95 comparison for {group}/{sql_name}/c{concurrency}")
        elif regression > regression_budget_pct:
            row_status = "failed"
            hard_blocks.append(
                f"p95 regression {regression:.3f}% exceeds budget for "
                f"{group}/{sql_name}/c{concurrency}"
            )
        if regression is not None:
            max_regression = (
                regression if max_regression is None else max(max_regression, regression)
            )
        rows.append(
            {
                "group": group,
                "sql_name": sql_name,
                "concurrency": concurrency,
                "public_samples": int(summary_value(public, "samples") or 0),
                "shadow_samples": int(summary_value(shadow, "samples") or 0),
                "public_errors": public_errors,
                "shadow_errors": shadow_errors,
                "public_p95_ms": round(public_p95, 3) if public_p95 is not None else None,
                "shadow_p95_ms": round(shadow_p95, 3) if shadow_p95 is not None else None,
                "p95_regression_pct": round(regression, 3) if regression is not None else None,
                "status": row_status,
            }
        )
    return {
        "status": "passed" if not hard_blocks else "failed",
        "required": True,
        "regression_budget_pct": regression_budget_pct,
        "max_p95_regression_pct": (
            round(max_regression, 3) if max_regression is not None else None
        ),
        "hard_blocks": hard_blocks,
        "rows": rows,
    }


def evaluate_gate(summary: Mapping[str, Any]) -> dict[str, Any]:
    hard_blocks: list[str] = []
    warnings: list[str] = []
    policy_gate = t132.evaluate_policy_result(summary.get("policy_result") or {})
    hard_blocks.extend(f"policy: {item}" for item in policy_gate["hard_blocks"])
    warnings.extend(f"policy: {item}" for item in policy_gate["warnings"])

    flag_off_before = summary.get("flag_off_before") or {}
    flag_off_after = summary.get("flag_off_after") or {}
    flag_on = summary.get("flag_on") or {}
    shadow_identity = flag_on.get("shadow_identity") or {}
    identity_blocks = flag_off_identity_blocks(flag_off_before, flag_off_after)
    hard_blocks.extend(identity_blocks)
    if flag_off_before.get("target_rows") != shadow_identity.get("target_rows"):
        hard_blocks.append("shadow target row count differs from public")
    if flag_off_before.get("text_search_rows") != shadow_identity.get("text_search_rows"):
        hard_blocks.append("shadow text-search row count differs from public")
    if int(flag_on.get("applied_rows") or 0) <= 0:
        hard_blocks.append("shadow policy applied no rows")

    for section_name in ("sql_benchmark", "rest_benchmark"):
        section = summary.get(section_name) or {}
        if section.get("status") != "passed":
            hard_blocks.append(f"{section_name} status is {section.get('status') or 'missing'}")
        hard_blocks.extend(
            f"{section_name}: {item}" for item in section.get("hard_blocks", ())
        )

    rollback = summary.get("rollback") or {}
    if rollback.get("status") != "dropped":
        hard_blocks.append(f"rollback status is {rollback.get('status') or 'missing'}")
    return {
        "status": "passed" if not hard_blocks else "blocked",
        "active_serving_promotion_allowed": False,
        "hard_blocks": hard_blocks,
        "warnings": warnings,
    }


def flag_off_identity_blocks(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> list[str]:
    blocks: list[str] = []
    for key in ("target_rows", "target_point_rows", "text_search_rows", "sample_hash"):
        if before.get(key) != after.get(key):
            blocks.append(f"flag-off public identity changed: {key}")
    before_release = before.get("active_release") or {}
    after_release = after.get("active_release") or {}
    for key in ("serving_release_id", "dataset_snapshot_id", "mv_hash", "state"):
        if before_release.get(key) != after_release.get(key):
            blocks.append(f"flag-off active release changed: {key}")
    return blocks


async def require_shadow_relations(conn: AsyncConnection, shadow_schema: str) -> None:
    for relation in ("mv_geocode_target", "mv_geocode_text_search"):
        regclass = f"{shadow_schema}.{relation}"
        exists = await conn.scalar(text("SELECT to_regclass(:regclass)"), {"regclass": regclass})
        if exists is None:
            msg = f"{regclass} does not exist; rerun without --reuse-shadow"
            raise RuntimeError(msg)


async def drop_shadow_schema(conn: AsyncConnection, shadow_schema: str) -> dict[str, Any]:
    validate_shadow_schema(shadow_schema)
    await conn.execute(text(f"DROP SCHEMA IF EXISTS {quote_identifier(shadow_schema)} CASCADE"))
    exists = await conn.scalar(
        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
        {"schema": shadow_schema},
    )
    return {
        "status": "dropped",
        "shadow_schema": shadow_schema,
        "dropped": exists is None,
    }


def summary_key(row: Any) -> tuple[str, str, int]:
    return (
        str(summary_value(row, "group")),
        str(summary_value(row, "sql_name")),
        int(summary_value(row, "concurrency") or 0),
    )


def summary_value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key)


def p95_regression_pct(public_p95_ms: float | None, shadow_p95_ms: float | None) -> float | None:
    if public_p95_ms is None or shadow_p95_ms is None:
        return None
    if public_p95_ms <= 0:
        return 0.0 if shadow_p95_ms <= public_p95_ms else None
    return ((shadow_p95_ms - public_p95_ms) / public_p95_ms) * 100.0


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def validate_shadow_schema(schema: str) -> str:
    normalized = schema.strip()
    if not SHADOW_SCHEMA_PATTERN.fullmatch(normalized):
        msg = "shadow schema must be a simple identifier starting with _ktg_t133_"
        raise ValueError(msg)
    return normalized


def validate_schema_identifier(schema: str) -> None:
    if not IDENTIFIER_PATTERN.fullmatch(schema):
        msg = f"invalid schema identifier: {schema!r}"
        raise ValueError(msg)


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        msg = f"invalid SQL identifier: {identifier!r}"
        raise ValueError(msg)
    return f'"{identifier}"'


def qualified_identifier(schema: str, relation: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(relation)}"


def validate_concurrency_levels(levels: Sequence[int]) -> None:
    if not levels:
        msg = "at least one concurrency level is required"
        raise ValueError(msg)
    for level in levels:
        validate_positive_int("concurrency", int(level))


def validate_positive_int(name: str, value: int) -> None:
    if value <= 0:
        msg = f"{name} must be positive"
        raise ValueError(msg)


def validate_non_negative_int(name: str, value: int) -> None:
    if value < 0:
        msg = f"{name} must be non-negative"
        raise ValueError(msg)


def validate_non_negative_number(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        msg = f"{name} must be a finite non-negative number"
        raise ValueError(msg)


def build_summary_payload(
    *,
    started_at: datetime,
    source_yyyymm: str,
    data_root: Path,
    sido_codes: Sequence[str],
    shadow_schema: str,
    shadow_search_path: str,
    policy: t132.GuardedPolicyConfig,
) -> dict[str, Any]:
    return {
        "task": TASK_ID,
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "elapsed_seconds": None,
        "source_yyyymm": source_yyyymm,
        "data_root": str(data_root),
        "sido_codes": list(sido_codes),
        "shadow_schema": shadow_schema,
        "shadow_search_path": shadow_search_path,
        "policy": asdict(policy),
        "database": None,
        "policy_result": None,
        "flag_off_before": None,
        "shadow_build": None,
        "flag_on": None,
        "sql_benchmark": None,
        "rest_benchmark": None,
        "rollback": None,
        "flag_off_after": None,
        "gate_result": None,
        "cleanup": None,
        "artifacts": None,
    }


if __name__ == "__main__":
    asyncio.run(main())
