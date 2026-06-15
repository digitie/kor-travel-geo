"""Run T-132 repeatable validation for guarded C11 candidate policies."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
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
from scripts import run_t131_c11_guarded_policy_simulation as t131  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncConnection

type CurrentPointSource = Literal["centroid", "any"]

TASK_ID = "T-132"
SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("artifacts") / "t132-c11-guarded-policy-validation"
DEFAULT_SAMPLE_LIMIT = 200
DEFAULT_SAMPLE_MOVEMENT_MIN_M = 100.0
DEFAULT_BUILDING_DISTANCE_MAX_M = 50.0
DEFAULT_MOVEMENT_MAX_M = 500.0
COORD_SOURCE_DETAIL = "c11_bundle_guarded"

SUMMARY_KEYS: tuple[str, ...] = (
    "task",
    "schema_version",
    "started_at",
    "finished_at",
    "elapsed_seconds",
    "source_yyyymm",
    "data_root",
    "sido_codes",
    "feature_table",
    "policy",
    "database",
    "baseline",
    "policy_result",
    "gate_result",
    "artifacts",
    "cleanup",
)


@dataclass(frozen=True)
class GuardedPolicyConfig:
    policy_name: str
    current_pt_source: CurrentPointSource = "centroid"
    building_distance_max_m: float = DEFAULT_BUILDING_DISTANCE_MAX_M
    movement_max_m: float | None = DEFAULT_MOVEMENT_MAX_M
    require_c6_c7_ok: bool = True
    require_single_candidate: bool = False
    require_same_source_month: bool = False
    coord_source_detail: str = COORD_SOURCE_DETAIL

    def summary(self) -> dict[str, Any]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run T-132 repeatable C11 guarded policy validation.",
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
        help="Directory for T-132 JSON/CSV/GeoJSON artifacts.",
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
    parser.add_argument(
        "--current-pt-source",
        choices=("centroid", "any"),
        default="centroid",
        help="Existing serving point source allowed for C11 replacement.",
    )
    parser.add_argument(
        "--building-distance-max-m",
        type=float,
        default=DEFAULT_BUILDING_DISTANCE_MAX_M,
        help="Maximum C4 candidate building distance in meters.",
    )
    parser.add_argument(
        "--movement-max-m",
        type=float,
        default=DEFAULT_MOVEMENT_MAX_M,
        help="Maximum current-to-candidate movement in meters.",
    )
    parser.add_argument(
        "--no-movement-limit",
        action="store_true",
        help="Do not apply movement_m upper bound.",
    )
    parser.add_argument(
        "--allow-c6-c7-errors",
        action="store_true",
        help="Do not require candidate C6/C7 polygon containment.",
    )
    parser.add_argument(
        "--require-single-candidate",
        action="store_true",
        help="Require exactly one C11 candidate per bd_mgt_sn.",
    )
    parser.add_argument(
        "--require-same-source-month",
        action="store_true",
        help="Require candidate source month to match text source month.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=DEFAULT_SAMPLE_LIMIT,
        help="Maximum policy sample rows to export.",
    )
    parser.add_argument(
        "--sample-movement-min-m",
        type=float,
        default=DEFAULT_SAMPLE_MOVEMENT_MIN_M,
        help="Minimum movement distance for exported policy samples.",
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

    policy = build_policy_config(args)
    validate_positive_int("sample_limit", args.sample_limit)
    validate_non_negative_number("sample_movement_min_m", args.sample_movement_min_m)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    run_started = time.monotonic()
    sido_codes: Sequence[str] = tuple(args.sido or t125.DEFAULT_SIDO_CODES)

    engine = make_async_engine(settings)
    cleanup: dict[str, Any] = {"status": "not_started"}
    summary = build_summary_payload(
        started_at=started_at,
        source_yyyymm=args.source_yyyymm,
        data_root=args.data_root,
        sido_codes=sido_codes,
        policy=policy,
    )
    try:
        async with engine.begin() as conn:
            await t125.set_no_statement_timeout(conn)
            summary["database"] = await t125.collect_database_identity(conn)

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
                await require_table(conn, t131.FEATURE_TABLE)
            else:
                await t131.rebuild_feature_table(
                    conn,
                    candidate_source_yyyymm=args.source_yyyymm,
                )
            baseline = await t125.one_mapping(conn, t131.baseline_sql())
            policy_result = await t125.one_mapping(conn, policy_result_sql(policy))
            samples = await collect_policy_samples(
                conn,
                policy,
                sample_limit=args.sample_limit,
                sample_movement_min_m=args.sample_movement_min_m,
            )

        artifacts = write_artifacts(
            output_dir,
            samples,
            policy=policy,
            source_yyyymm=args.source_yyyymm,
            sample_limit=args.sample_limit,
            sample_movement_min_m=args.sample_movement_min_m,
        )
        summary["baseline"] = baseline
        summary["policy_result"] = policy_result
        summary["gate_result"] = evaluate_policy_result(policy_result)
        summary["artifacts"] = artifacts
        print(json.dumps(summary["gate_result"], ensure_ascii=False, indent=2))
    finally:
        if args.keep_staging:
            cleanup = {
                "status": "skipped_keep_staging",
                "checked_relations": cleanup_relation_names(),
                "remaining_relations": "not_checked",
                "passed": None,
            }
        else:
            async with engine.begin() as conn:
                await cleanup_work_tables(conn)
                cleanup = await verify_cleanup(conn)
        await engine.dispose()
        summary["cleanup"] = cleanup
        summary["finished_at"] = datetime.now(UTC).isoformat()
        summary["elapsed_seconds"] = round(time.monotonic() - run_started, 3)
        t125.write_json(output_dir / "summary.json", summary)


def build_policy_config(args: argparse.Namespace) -> GuardedPolicyConfig:
    validate_non_negative_number("building_distance_max_m", args.building_distance_max_m)
    movement_max_m: float | None
    if args.no_movement_limit:
        movement_max_m = None
    else:
        validate_non_negative_number("movement_max_m", args.movement_max_m)
        movement_max_m = float(args.movement_max_m)
    config = GuardedPolicyConfig(
        policy_name=policy_name(
            current_pt_source=args.current_pt_source,
            building_distance_max_m=float(args.building_distance_max_m),
            movement_max_m=movement_max_m,
            require_c6_c7_ok=not bool(args.allow_c6_c7_errors),
            require_single_candidate=bool(args.require_single_candidate),
            require_same_source_month=bool(args.require_same_source_month),
        ),
        current_pt_source=args.current_pt_source,
        building_distance_max_m=float(args.building_distance_max_m),
        movement_max_m=movement_max_m,
        require_c6_c7_ok=not bool(args.allow_c6_c7_errors),
        require_single_candidate=bool(args.require_single_candidate),
        require_same_source_month=bool(args.require_same_source_month),
    )
    return config


def policy_name(
    *,
    current_pt_source: CurrentPointSource,
    building_distance_max_m: float,
    movement_max_m: float | None,
    require_c6_c7_ok: bool,
    require_single_candidate: bool,
    require_same_source_month: bool,
) -> str:
    parts = [current_pt_source, f"c4_{number_token(building_distance_max_m)}"]
    if require_c6_c7_ok:
        parts.append("c6_c7")
    else:
        parts.append("allow_c6_c7")
    if movement_max_m is None:
        parts.append("move_any")
    else:
        parts.append(f"move_{number_token(movement_max_m)}")
    if require_single_candidate:
        parts.append("single")
    if require_same_source_month:
        parts.append("same_month")
    return "guarded_" + "_".join(parts)


def policy_predicate(config: GuardedPolicyConfig) -> str:
    clauses = [f"candidate_c4_dist_m <= {sql_number(config.building_distance_max_m)}"]
    if config.current_pt_source != "any":
        clauses.append(f"current_pt_source = '{config.current_pt_source}'")
    if config.require_c6_c7_ok:
        clauses.append("candidate_c6_ok AND candidate_c7_ok")
    if config.movement_max_m is not None:
        clauses.append(f"movement_m <= {sql_number(config.movement_max_m)}")
    if config.require_single_candidate:
        clauses.append("candidates_per_bd = 1")
    if config.require_same_source_month:
        clauses.append("text_source_yyyymm = candidate_source_yyyymm")
    return " AND ".join(clauses)


def policy_result_sql(config: GuardedPolicyConfig) -> str:
    return t131.policy_select(config.policy_name, policy_predicate(config))


async def collect_policy_samples(
    conn: AsyncConnection,
    config: GuardedPolicyConfig,
    *,
    sample_limit: int,
    sample_movement_min_m: float,
) -> list[dict[str, Any]]:
    return await t125.list_mappings(
        conn,
        policy_sample_sql(config),
        {
            "sample_limit": sample_limit,
            "sample_movement_min_m": sample_movement_min_m,
        },
    )


def policy_sample_sql(config: GuardedPolicyConfig) -> str:
    return f"""
    SELECT
        f.bd_mgt_sn,
        concat_ws(
            ' ',
            mv.si_nm,
            mv.sgg_nm,
            mv.emd_nm,
            mv.rn,
            CASE
              WHEN mv.buld_mnnm IS NULL THEN NULL
              WHEN COALESCE(mv.buld_slno, 0) > 0
                THEN mv.buld_mnnm::text || '-' || mv.buld_slno::text
              ELSE mv.buld_mnnm::text
            END
        ) AS road_addr,
        '{config.policy_name}' AS policy_name,
        '{config.coord_source_detail}' AS coord_source_detail,
        f.text_source_yyyymm,
        f.candidate_source_yyyymm,
        f.current_pt_source,
        f.candidates_per_bd,
        f.baseline_has_entrance,
        f.movement_m,
        f.candidate_c4_dist_m,
        f.baseline_c4_dist_m,
        f.candidate_c6_ok,
        f.baseline_c6_ok,
        f.candidate_c7_ok,
        f.baseline_c7_ok,
        ST_X(ST_Transform(mv.pt_5179, 4326)) AS current_lon,
        ST_Y(ST_Transform(mv.pt_5179, 4326)) AS current_lat,
        ST_X(ST_Transform(c.candidate_pt_5179, 4326)) AS candidate_lon,
        ST_Y(ST_Transform(c.candidate_pt_5179, 4326)) AS candidate_lat
    FROM {t131.FEATURE_TABLE} AS f
    JOIN mv_geocode_target AS mv USING (bd_mgt_sn)
    JOIN {t125.CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)
    WHERE {policy_predicate(config)}
      AND f.movement_m >= :sample_movement_min_m
    ORDER BY f.movement_m DESC, f.bd_mgt_sn
    LIMIT :sample_limit
    """


def write_artifacts(
    output_dir: Path,
    samples: Sequence[Mapping[str, Any]],
    *,
    policy: GuardedPolicyConfig,
    source_yyyymm: str,
    sample_limit: int,
    sample_movement_min_m: float,
) -> dict[str, str]:
    sample_csv = output_dir / "guarded_policy_samples.csv"
    sample_geojson = output_dir / "guarded_policy_samples.geojson"
    reproduction_sql_path = output_dir / "reproduce_t132_guarded_policy.sql"
    t125.write_csv(sample_csv, samples)
    t125.write_geojson(sample_geojson, samples)
    reproduction_sql_path.write_text(
        reproduction_sql(
            policy,
            source_yyyymm=source_yyyymm,
            sample_limit=sample_limit,
            sample_movement_min_m=sample_movement_min_m,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "policy_samples_csv": str(sample_csv),
        "policy_samples_geojson": str(sample_geojson),
        "reproduction_sql": str(reproduction_sql_path),
        "summary_json": str(output_dir / "summary.json"),
    }


def reproduction_sql(
    policy: GuardedPolicyConfig,
    *,
    source_yyyymm: str,
    sample_limit: int,
    sample_movement_min_m: float,
) -> str:
    source_literal = source_yyyymm.replace("'", "''")
    feature_sql = t131.feature_table_sql().replace(
        "CAST(:candidate_source_yyyymm AS text)",
        f"'{source_literal}'::text",
    )
    sample_sql = policy_sample_sql(policy)
    sample_sql = sample_sql.replace(":sample_limit", str(sample_limit))
    sample_sql = sample_sql.replace(
        ":sample_movement_min_m",
        sql_number(sample_movement_min_m),
    )
    return f"""-- T-132 guarded C11 policy validation reproduction SQL
-- 전제: {t125.CANDIDATE_BEST_TABLE}가 존재해야 한다.

{feature_sql}

-- Policy result
{policy_result_sql(policy)};

-- Exported policy samples
{sample_sql};
"""


def evaluate_policy_result(policy_result: Mapping[str, Any]) -> dict[str, Any]:
    hard_blocks: list[str] = []
    warnings: list[str] = []
    if int(policy_result.get("candidate_used_rows") or 0) <= 0:
        hard_blocks.append("policy selected no candidate rows")
    if int(policy_result.get("candidate_c4_over500") or 0) > 0:
        hard_blocks.append("policy still has C4 over500 rows")
    if int(policy_result.get("candidate_c6_error") or 0) > 0:
        hard_blocks.append("policy still has C6 error rows")
    if int(policy_result.get("candidate_c7_error") or 0) > 0:
        hard_blocks.append("policy still has C7 error rows")
    if int(policy_result.get("movement_over_500m") or 0) > 0:
        hard_blocks.append("policy still has movement over 500m")
    if int(policy_result.get("movement_over_100m") or 0) > 0:
        warnings.append("policy still has movement over 100m")
    return {
        "status": "repeatable_candidate" if not hard_blocks else "blocked",
        "serving_promotion_allowed": False,
        "hard_blocks": hard_blocks,
        "warnings": warnings,
    }


async def require_table(conn: AsyncConnection, table_name: str) -> None:
    exists = await conn.scalar(text("SELECT to_regclass(:table_name)"), {"table_name": table_name})
    if exists is None:
        raise RuntimeError(f"{table_name} does not exist; rerun without --reuse-features")


async def cleanup_work_tables(conn: AsyncConnection) -> None:
    await t125.drop_work_tables(conn)
    await conn.execute(text(f"DROP TABLE IF EXISTS {t131.FEATURE_TABLE}"))


async def verify_cleanup(conn: AsyncConnection) -> dict[str, Any]:
    remaining: list[str] = []
    for relation_name in cleanup_relation_names():
        exists = await conn.scalar(
            text("SELECT to_regclass(:relation_name)"),
            {"relation_name": relation_name},
        )
        if exists is not None:
            remaining.append(relation_name)
    return {
        "status": "checked",
        "checked_relations": cleanup_relation_names(),
        "remaining_relations": remaining,
        "passed": not remaining,
    }


def cleanup_relation_names() -> list[str]:
    return [
        t125.ADDRESS_TABLE,
        t125.ENTRANCE_TABLE,
        t125.CANDIDATE_RAW_TABLE,
        t125.CANDIDATE_BEST_TABLE,
        t131.FEATURE_TABLE,
    ]


def build_summary_payload(
    *,
    started_at: datetime,
    source_yyyymm: str,
    data_root: Path,
    sido_codes: Sequence[str],
    policy: GuardedPolicyConfig,
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
        "feature_table": t131.FEATURE_TABLE,
        "policy": policy.summary(),
        "database": None,
        "baseline": None,
        "policy_result": None,
        "gate_result": None,
        "artifacts": None,
        "cleanup": None,
    }


def validate_positive_int(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def validate_non_negative_number(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def sql_number(value: float) -> str:
    validate_non_negative_number("sql_number", value)
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def number_token(value: float) -> str:
    return sql_number(value).replace(".", "p")


if __name__ == "__main__":
    asyncio.run(main())
