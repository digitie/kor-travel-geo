"""Benchmark geocoding query latency on a full-load PostGIS database.

This script is an operational measurement tool, not a production API path.
It builds a deterministic smoke corpus from ``mv_geocode_target`` and related
tables, executes the same raw SQL statements used by repositories, and writes
JSON/Markdown artifacts under ``artifacts/perf/<run_id>/``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from sqlalchemy import TextClause, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from kraddr.geo.dto.region import EMPTY_REGION_PARAMS, RegionHint
from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.infra.geocode_repo import _FUZZY_ROADS, _LOOKUP_JIBUN, _LOOKUP_ROAD
from kraddr.geo.infra.reverse_repo import _NEAREST_SQL, _SPPN_AREAS_SQL
from kraddr.geo.infra.search_repo import _SEARCH_EXACT_SQL, _SEARCH_SQL, _normalize_search_query
from kraddr.geo.infra.zip_repo import _ZIP_BY_ADDRESS, _ZIP_BY_POINT
from kraddr.geo.settings import Settings, get_settings

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

BENCHMARK_SCHEMA_VERSION = 2

type QueryGroup = Literal[
    "Q1_ROAD_EXACT",
    "Q2_PARCEL_EXACT",
    "Q3_FUZZY_GEOCODE",
    "Q4_SEARCH",
    "Q5_REVERSE_NEAREST",
    "Q6_REVERSE_RADIUS",
    "Q7_ZIPCODE",
    "Q8_NO_RESULT",
    "Q11_SPPN",
]
type ParamValue = str | int | float | bool | None
type Params = dict[str, ParamValue]


@dataclass(frozen=True, slots=True)
class QuerySpec:
    name: str
    group: QueryGroup
    statement: TextClause
    setup_sql: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    group: QueryGroup
    sql_name: str
    params: Params
    label: str
    source: str
    expected_status: str = "OK"
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Measurement:
    case_id: str
    group: QueryGroup
    sql_name: str
    concurrency: int
    iteration: int
    warmup: bool
    ok: bool
    elapsed_ms: float
    row_count: int
    error: str | None = None
    checkout_ms: float | None = None
    execute_ms: float | None = None


@dataclass(frozen=True, slots=True)
class SummaryRow:
    group: QueryGroup
    sql_name: str
    concurrency: int
    samples: int
    errors: int
    p50_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    p95_checkout_ms: float | None
    p95_execute_ms: float | None
    p99_ms: float | None
    max_ms: float | None
    avg_rows: float | None


@dataclass(frozen=True, slots=True)
class EnvironmentSnapshot:
    run_id: str
    started_at: str
    git_commit: str | None
    git_branch: str | None
    python_version: str
    platform: str
    cpu_count: int | None
    cwd: str
    pg_pool_size: int
    pg_max_overflow: int
    database_version: str | None
    postgis_version: str | None
    pg_stat_statements: bool
    row_counts: dict[str, int | None]
    relation_sizes: dict[str, int | None]


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    schema_version: int
    run_id: str
    started_at: str
    finished_at: str
    cases: tuple[BenchmarkCase, ...]
    measurements: tuple[Measurement, ...]
    summaries: tuple[SummaryRow, ...]
    environment: EnvironmentSnapshot


QUERY_SPECS: dict[str, QuerySpec] = {
    "road_exact": QuerySpec("road_exact", "Q1_ROAD_EXACT", _LOOKUP_ROAD),
    "road_exact_sig": QuerySpec("road_exact_sig", "Q1_ROAD_EXACT", _LOOKUP_ROAD),
    "parcel_exact": QuerySpec("parcel_exact", "Q2_PARCEL_EXACT", _LOOKUP_JIBUN),
    "parcel_exact_bjd": QuerySpec("parcel_exact_bjd", "Q2_PARCEL_EXACT", _LOOKUP_JIBUN),
    "fuzzy_geocode": QuerySpec(
        "fuzzy_geocode",
        "Q3_FUZZY_GEOCODE",
        _FUZZY_ROADS,
        ("SET LOCAL pg_trgm.similarity_threshold = 0.42",),
    ),
    "fuzzy_geocode_wide": QuerySpec(
        "fuzzy_geocode_wide",
        "Q3_FUZZY_GEOCODE",
        _FUZZY_ROADS,
        ("SET LOCAL pg_trgm.similarity_threshold = 0.42",),
    ),
    "fuzzy_geocode_sig": QuerySpec(
        "fuzzy_geocode_sig",
        "Q3_FUZZY_GEOCODE",
        _FUZZY_ROADS,
        ("SET LOCAL pg_trgm.similarity_threshold = 0.42",),
    ),
    "search": QuerySpec(
        "search",
        "Q4_SEARCH",
        _SEARCH_SQL,
        ("SET LOCAL pg_trgm.similarity_threshold = 0.35",),
    ),
    "search_sig": QuerySpec(
        "search_sig",
        "Q4_SEARCH",
        _SEARCH_SQL,
        ("SET LOCAL pg_trgm.similarity_threshold = 0.35",),
    ),
    "search_fuzzy": QuerySpec(
        "search_fuzzy",
        "Q4_SEARCH",
        _SEARCH_SQL,
        ("SET LOCAL pg_trgm.similarity_threshold = 0.35",),
    ),
    "reverse_nearest": QuerySpec("reverse_nearest", "Q5_REVERSE_NEAREST", _NEAREST_SQL),
    "reverse_nearest_sig": QuerySpec("reverse_nearest_sig", "Q5_REVERSE_NEAREST", _NEAREST_SQL),
    "reverse_radius": QuerySpec("reverse_radius", "Q6_REVERSE_RADIUS", _NEAREST_SQL),
    "reverse_radius_sig": QuerySpec("reverse_radius_sig", "Q6_REVERSE_RADIUS", _NEAREST_SQL),
    "zipcode_address": QuerySpec("zipcode_address", "Q7_ZIPCODE", _ZIP_BY_ADDRESS),
    "zipcode_point": QuerySpec("zipcode_point", "Q7_ZIPCODE", _ZIP_BY_POINT),
    "no_result_road": QuerySpec("no_result_road", "Q8_NO_RESULT", _LOOKUP_ROAD),
    "no_result_reverse": QuerySpec("no_result_reverse", "Q8_NO_RESULT", _NEAREST_SQL),
    "sppn_reverse": QuerySpec("sppn_reverse", "Q11_SPPN", _SPPN_AREAS_SQL),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark geocoding/reverse/search SQL latency.",
    )
    parser.add_argument(
        "--pg-dsn",
        help="PostgreSQL DSN. Defaults to KRADDR_GEO_PG_DSN/settings.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact directory. Defaults to artifacts/perf/<run-id>.",
    )
    parser.add_argument("--run-id", help="Stable run id. Defaults to timestamp.")
    parser.add_argument(
        "--cases-per-group",
        type=int,
        default=5,
        help="Number of generated cases per query group.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Measured iterations per case and concurrency level.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Warm-up iterations excluded from summaries.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        action="append",
        default=None,
        help="Concurrency level. May be passed multiple times. Default: 1.",
    )
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        default=5_000,
        help="SET LOCAL statement_timeout for each measured query.",
    )
    parser.add_argument(
        "--pool-size",
        type=int,
        help="Override SQLAlchemy pool_size for this benchmark run.",
    )
    parser.add_argument(
        "--max-overflow",
        type=int,
        help="Override SQLAlchemy max_overflow for this benchmark run.",
    )
    parser.add_argument(
        "--explain-slowest-per-group",
        type=int,
        default=1,
        help="Number of slow non-error cases per group to EXPLAIN. Use 0 to disable.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Existing corpus JSON file. If omitted, corpus is generated from DB.",
    )
    parser.add_argument(
        "--reset-pg-stat-statements",
        action="store_true",
        help="Reset pg_stat_statements after corpus/environment capture and before measurements.",
    )
    parser.add_argument(
        "--pg-stat-limit",
        type=int,
        default=50,
        help="Maximum pg_stat_statements rows to store in before/after snapshots.",
    )
    return parser


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    if q < 0 or q > 100:
        msg = f"percentile must be between 0 and 100: {q}"
        raise ValueError(msg)
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (q / 100) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_measurements(measurements: Sequence[Measurement]) -> tuple[SummaryRow, ...]:
    grouped: dict[tuple[QueryGroup, str, int], list[Measurement]] = defaultdict(list)
    for item in measurements:
        if not item.warmup:
            grouped[(item.group, item.sql_name, item.concurrency)].append(item)

    summaries: list[SummaryRow] = []
    for (group, sql_name, concurrency), rows in sorted(grouped.items()):
        ok_rows = [row for row in rows if row.ok]
        elapsed = [row.elapsed_ms for row in ok_rows]
        checkout = [row.checkout_ms for row in ok_rows if row.checkout_ms is not None]
        execute = [row.execute_ms for row in ok_rows if row.execute_ms is not None]
        avg_rows = statistics.fmean(row.row_count for row in ok_rows) if ok_rows else None
        summaries.append(
            SummaryRow(
                group=group,
                sql_name=sql_name,
                concurrency=concurrency,
                samples=len(rows),
                errors=sum(1 for row in rows if not row.ok),
                p50_ms=_round_optional(percentile(elapsed, 50)),
                p90_ms=_round_optional(percentile(elapsed, 90)),
                p95_ms=_round_optional(percentile(elapsed, 95)),
                p95_checkout_ms=_round_optional(percentile(checkout, 95)),
                p95_execute_ms=_round_optional(percentile(execute, 95)),
                p99_ms=_round_optional(percentile(elapsed, 99)),
                max_ms=_round_optional(max(elapsed) if elapsed else None),
                avg_rows=_round_optional(avg_rows),
            )
        )
    return tuple(summaries)


async def build_corpus(engine: AsyncEngine, *, cases_per_group: int) -> tuple[BenchmarkCase, ...]:
    cases: list[BenchmarkCase] = []
    async with engine.connect() as conn:
        road_rows = await _sample_mv_rows(conn, cases_per_group)
        parcel_rows = await _sample_mv_rows(conn, cases_per_group, require_parcel=True)
        point_rows = await _sample_mv_rows(conn, cases_per_group, require_point=True)
        sppn_rows = await _sample_sppn_rows(conn, cases_per_group)

    for idx, row in enumerate(road_rows, start=1):
        params = _road_params(row)
        cases.append(
            BenchmarkCase(
                case_id=f"Q1-road-{idx:03d}",
                group="Q1_ROAD_EXACT",
                sql_name="road_exact",
                params=params,
                label=_row_label(row),
                source="mv_geocode_target",
            )
        )
        road_wide_params = dict(params)
        road_wide_params["si"] = None
        road_wide_params["sgg"] = None
        cases.append(
            BenchmarkCase(
                case_id=f"Q1-road-sig-{idx:03d}",
                group="Q1_ROAD_EXACT",
                sql_name="road_exact_sig",
                params=_with_region_params(road_wide_params, sig_cd=str(row["sig_cd"])),
                label=_row_label(row),
                source="mv_geocode_target",
                note="si/sgg removed and sig_cd filter applied",
            )
        )
        fuzzy_params = dict(params)
        fuzzy_params["road_nrm"] = _fuzzy_token(str(params["road_nrm"]))
        fuzzy_params["limit"] = 5
        cases.append(
            BenchmarkCase(
                case_id=f"Q3-fuzzy-{idx:03d}",
                group="Q3_FUZZY_GEOCODE",
                sql_name="fuzzy_geocode",
                params=fuzzy_params,
                label=_row_label(row),
                source="mv_geocode_target",
                note="road_nrm shortened to force trigram path",
            )
        )
        fuzzy_wide_params = dict(fuzzy_params)
        fuzzy_wide_params["si"] = None
        fuzzy_wide_params["sgg"] = None
        cases.append(
            BenchmarkCase(
                case_id=f"Q3-fuzzy-wide-{idx:03d}",
                group="Q3_FUZZY_GEOCODE",
                sql_name="fuzzy_geocode_wide",
                params=fuzzy_wide_params,
                label=_row_label(row),
                source="mv_geocode_target",
                note="si/sgg removed to measure wide trigram path",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q3-fuzzy-sig-{idx:03d}",
                group="Q3_FUZZY_GEOCODE",
                sql_name="fuzzy_geocode_sig",
                params=_with_region_params(fuzzy_wide_params, sig_cd=str(row["sig_cd"])),
                label=_row_label(row),
                source="mv_geocode_target",
                note="si/sgg removed and sig_cd filter applied",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q4-search-{idx:03d}",
                group="Q4_SEARCH",
                sql_name="search",
                params=_with_empty_region_params({"query": row["rn"], "limit": 10, "offset": 0}),
                label=str(row["rn"]),
                source="mv_geocode_target",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q4-search-sig-{idx:03d}",
                group="Q4_SEARCH",
                sql_name="search_sig",
                params=_with_region_params(
                    {"query": row["rn"], "limit": 10, "offset": 0},
                    sig_cd=str(row["sig_cd"]),
                ),
                label=str(row["rn"]),
                source="mv_geocode_target",
                note="sig_cd filter applied to search query",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q4-search-fuzzy-{idx:03d}",
                group="Q4_SEARCH",
                sql_name="search_fuzzy",
                params=_with_empty_region_params(
                    {
                        "query": f"{row['rn']}임의불일치",
                        "limit": 10,
                        "offset": 0,
                    }
                ),
                label=str(row["rn"]),
                source="synthetic",
                note="intentional no-exact-match search case for broad trigram fallback",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q7-zip-address-{idx:03d}",
                group="Q7_ZIPCODE",
                sql_name="zipcode_address",
                params={
                    "road_nrm": row["rn_nrm"],
                    "emd": row["li_nm"] or row["emd_nm"],
                    "mnnm": row["buld_mnnm"],
                },
                label=_row_label(row),
                source="mv_geocode_target",
            )
        )

    for idx, row in enumerate(parcel_rows, start=1):
        parcel_params = _parcel_params(row)
        cases.append(
            BenchmarkCase(
                case_id=f"Q2-parcel-{idx:03d}",
                group="Q2_PARCEL_EXACT",
                sql_name="parcel_exact",
                params=parcel_params,
                label=_row_label(row),
                source="mv_geocode_target",
            )
        )
        parcel_wide_params = dict(parcel_params)
        parcel_wide_params["si"] = None
        parcel_wide_params["sgg"] = None
        parcel_wide_params["emd"] = None
        cases.append(
            BenchmarkCase(
                case_id=f"Q2-parcel-bjd-{idx:03d}",
                group="Q2_PARCEL_EXACT",
                sql_name="parcel_exact_bjd",
                params=_with_region_params(parcel_wide_params, bjd_cd=str(row["bjd_cd"])),
                label=_row_label(row),
                source="mv_geocode_target",
                note="si/sgg/emd removed and bjd_cd filter applied",
            )
        )

    for idx, row in enumerate(point_rows, start=1):
        point_params: Params = {
            **EMPTY_REGION_PARAMS,
            "x": cast("float", row["lon"]),
            "y": cast("float", row["lat"]),
            "in_srid": 4326,
            "radius_m": 50,
            "limit": 5,
        }
        cases.append(
            BenchmarkCase(
                case_id=f"Q5-reverse-nearest-{idx:03d}",
                group="Q5_REVERSE_NEAREST",
                sql_name="reverse_nearest",
                params=point_params,
                label=_row_label(row),
                source="mv_geocode_target",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q5-reverse-nearest-sig-{idx:03d}",
                group="Q5_REVERSE_NEAREST",
                sql_name="reverse_nearest_sig",
                params=_with_region_params(point_params, sig_cd=str(row["sig_cd"])),
                label=_row_label(row),
                source="mv_geocode_target",
                note="sig_cd filter applied to nearest query",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q6-reverse-radius-{idx:03d}",
                group="Q6_REVERSE_RADIUS",
                sql_name="reverse_radius",
                params={**point_params, "radius_m": 200},
                label=_row_label(row),
                source="mv_geocode_target",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q6-reverse-radius-sig-{idx:03d}",
                group="Q6_REVERSE_RADIUS",
                sql_name="reverse_radius_sig",
                params=_with_region_params(
                    {**point_params, "radius_m": 200},
                    sig_cd=str(row["sig_cd"]),
                ),
                label=_row_label(row),
                source="mv_geocode_target",
                note="sig_cd filter applied to radius query",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q7-zip-point-{idx:03d}",
                group="Q7_ZIPCODE",
                sql_name="zipcode_point",
                params={
                    "x": cast("float", row["lon"]),
                    "y": cast("float", row["lat"]),
                },
                label=_row_label(row),
                source="mv_geocode_target",
            )
        )

    for idx in range(1, cases_per_group + 1):
        cases.append(
            BenchmarkCase(
                case_id=f"Q8-no-result-road-{idx:03d}",
                group="Q8_NO_RESULT",
                sql_name="no_result_road",
                params={
                    **EMPTY_REGION_PARAMS,
                    "si": "없는시",
                    "sgg": None,
                    "road_nrm": f"없는도로{idx}",
                    "mnnm": 999_999,
                    "slno": 0,
                    "buld_se_cd": None,
                },
                label=f"없는도로 {idx}",
                source="synthetic",
                expected_status="NOT_FOUND",
            )
        )
        cases.append(
            BenchmarkCase(
                case_id=f"Q8-no-result-reverse-{idx:03d}",
                group="Q8_NO_RESULT",
                sql_name="no_result_reverse",
                params={
                    **EMPTY_REGION_PARAMS,
                    "x": 0.0,
                    "y": 0.0,
                    "in_srid": 4326,
                    "radius_m": 200,
                    "limit": 5,
                },
                label="outside Korea",
                source="synthetic",
                expected_status="NOT_FOUND",
            )
        )

    for idx, row in enumerate(sppn_rows, start=1):
        cases.append(
            BenchmarkCase(
                case_id=f"Q11-sppn-reverse-{idx:03d}",
                group="Q11_SPPN",
                sql_name="sppn_reverse",
                params={
                    "x": cast("float", row["lon"]),
                    "y": cast("float", row["lat"]),
                    "in_srid": 4326,
                    "limit": 5,
                },
                label=str(row["makarea_nm"] or row["makarea_id"]),
                source="tl_sppn_makarea",
            )
        )

    return tuple(cases)


async def run_benchmark(
    engine: AsyncEngine,
    cases: Sequence[BenchmarkCase],
    *,
    run_id: str,
    settings: Settings,
    concurrency_levels: Sequence[int],
    iterations: int,
    warmup: int,
    statement_timeout_ms: int,
    started_at: str | None = None,
    environment: EnvironmentSnapshot | None = None,
) -> BenchmarkReport:
    started_at = started_at or datetime.now(UTC).isoformat()
    environment = environment or await collect_environment(
        engine,
        run_id=run_id,
        started_at=started_at,
        settings=settings,
    )
    measurements: list[Measurement] = []
    for concurrency in concurrency_levels:
        total_iterations = warmup + iterations
        for iteration in range(total_iterations):
            warmup_iteration = iteration < warmup
            results = await _run_iteration(
                engine,
                cases,
                concurrency=concurrency,
                iteration=iteration + 1,
                warmup=warmup_iteration,
                statement_timeout_ms=statement_timeout_ms,
            )
            measurements.extend(results)
    summaries = summarize_measurements(measurements)
    finished_at = datetime.now(UTC).isoformat()
    return BenchmarkReport(
        schema_version=BENCHMARK_SCHEMA_VERSION,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        cases=tuple(cases),
        measurements=tuple(measurements),
        summaries=summaries,
        environment=environment,
    )


async def collect_environment(
    engine: AsyncEngine,
    *,
    run_id: str,
    started_at: str,
    settings: Settings,
) -> EnvironmentSnapshot:
    async with engine.connect() as conn:
        database_version = await _optional_scalar_str(conn, "SELECT version()")
        postgis_version = await _optional_scalar_str(conn, "SELECT postgis_full_version()")
        row_counts = {
            "mv_geocode_target": await _optional_count(conn, "mv_geocode_target"),
            "mv_geocode_text_search": await _optional_count(conn, "mv_geocode_text_search"),
            "tl_sppn_makarea": await _optional_count(conn, "tl_sppn_makarea"),
            "postal_bulk_delivery": await _optional_count(conn, "postal_bulk_delivery"),
        }
        relation_sizes = {
            name: await _optional_relation_size(conn, name)
            for name in (
                "mv_geocode_target",
                "mv_geocode_text_search",
                "tl_sppn_makarea",
                "idx_mv_geocode_target_pk",
                "idx_mv_text_search_pk",
                "idx_mv_road",
                "idx_mv_jibun",
                "idx_mv_rn_trgm",
                "idx_mv_buld_nm_trgm",
                "idx_mv_rn_nrm_exact",
                "idx_mv_buld_nm_nrm_exact",
                "idx_mv_sigungu_buld_nm_nrm_exact",
                "idx_mv_text_search_sig_buld",
                "idx_mv_text_search_bjd_prefix_buld",
                "idx_mv_text_search_rn_trgm",
                "idx_mv_text_search_buld_nm_trgm",
                "idx_mv_text_search_sigungu_buld_nm_trgm",
                "idx_mv_geom5179",
            )
        }
        pg_stat_statements, _ = await _pg_stat_statements_status(conn)
    return EnvironmentSnapshot(
        run_id=run_id,
        started_at=started_at,
        git_commit=_git_output("rev-parse", "HEAD"),
        git_branch=_git_output("branch", "--show-current"),
        python_version=platform.python_version(),
        platform=platform.platform(),
        cpu_count=os.cpu_count(),
        cwd=str(Path.cwd()),
        pg_pool_size=settings.pg_pool_size,
        pg_max_overflow=settings.pg_max_overflow,
        database_version=database_version,
        postgis_version=postgis_version,
        pg_stat_statements=pg_stat_statements,
        row_counts=row_counts,
        relation_sizes=relation_sizes,
    )


async def explain_slowest_cases(
    engine: AsyncEngine,
    report: BenchmarkReport,
    *,
    output_dir: Path,
    per_group: int,
    statement_timeout_ms: int,
) -> None:
    if per_group <= 0:
        return
    plans_dir = output_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    cases_by_id = {case.case_id: case for case in report.cases}
    grouped: dict[QueryGroup, list[Measurement]] = defaultdict(list)
    for measurement in report.measurements:
        if measurement.ok and not measurement.warmup and measurement.concurrency == 1:
            grouped[measurement.group].append(measurement)
    async with engine.connect() as conn:
        for group, rows in grouped.items():
            slowest = sorted(rows, key=lambda row: row.elapsed_ms, reverse=True)[:per_group]
            for measurement in slowest:
                case = cases_by_id[measurement.case_id]
                plan = await _explain_case(conn, case, statement_timeout_ms=statement_timeout_ms)
                filename = f"{_safe_filename(group)}_{_safe_filename(case.case_id)}.json"
                plan_path = plans_dir / filename
                plan_path.write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )


def report_to_json(report: BenchmarkReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2)


def corpus_to_json(cases: Sequence[BenchmarkCase]) -> str:
    return json.dumps([asdict(case) for case in cases], ensure_ascii=False, indent=2)


def corpus_from_json(path: Path) -> tuple[BenchmarkCase, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        msg = f"corpus must be a JSON array: {path}"
        raise ValueError(msg)
    cases: list[BenchmarkCase] = []
    for item in raw:
        if not isinstance(item, dict):
            msg = f"corpus item must be an object: {item!r}"
            raise ValueError(msg)
        cases.append(
            BenchmarkCase(
                case_id=str(item["case_id"]),
                group=cast("QueryGroup", item["group"]),
                sql_name=str(item["sql_name"]),
                params=_with_empty_region_params(dict(item["params"])),
                label=str(item["label"]),
                source=str(item["source"]),
                expected_status=str(item.get("expected_status", "OK")),
                note=str(item["note"]) if item.get("note") is not None else None,
            )
        )
    return tuple(cases)


async def capture_pg_stat_statements(
    engine: AsyncEngine,
    *,
    limit: int,
    reset: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "captured_at": datetime.now(UTC).isoformat(),
        "available": False,
        "reset_requested": reset,
        "reset_error": None,
        "error": None,
        "rows": [],
    }
    async with engine.connect() as conn:
        available, status_error = await _pg_stat_statements_status(conn)
        payload["available"] = available
        if not available:
            payload["error"] = status_error
            return payload
        if reset:
            try:
                await conn.execute(text("SELECT x_extension.pg_stat_statements_reset()"))
                await conn.commit()
            except (DBAPIError, ProgrammingError) as exc:
                await conn.rollback()
                payload["reset_error"] = _redact_error(exc)
        try:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT queryid::text AS queryid,
       calls,
       total_exec_time,
       mean_exec_time,
       rows AS result_rows,
       shared_blks_hit,
       shared_blks_read,
       temp_blks_written,
       left(query, 4000) AS query
  FROM x_extension.pg_stat_statements
 WHERE dbid = (
       SELECT oid FROM pg_database WHERE datname = current_database()
 )
   AND query NOT ILIKE '%pg_stat_statements%'
 ORDER BY total_exec_time DESC
 LIMIT :limit
"""
                    ),
                    {"limit": limit},
                )
            ).mappings().all()
            payload["rows"] = [_plain_pg_stat_row(dict(row)) for row in rows]
        except (DBAPIError, ProgrammingError) as exc:
            payload["error"] = _redact_error(exc)
    return payload


def pg_stat_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "captured_at": datetime.now(UTC).isoformat(),
        "available": bool(before.get("available")) and bool(after.get("available")),
        "error": None,
        "rows": [],
    }
    if not payload["available"]:
        payload["error"] = before.get("error") or after.get("error") or "snapshot unavailable"
        return payload

    before_rows = {
        _pg_stat_row_key(row): row
        for row in cast("Sequence[Mapping[str, Any]]", before.get("rows", []))
    }
    delta_rows: list[dict[str, Any]] = []
    for row in cast("Sequence[Mapping[str, Any]]", after.get("rows", [])):
        key = _pg_stat_row_key(row)
        previous = before_rows.get(key, {})
        calls = int(row.get("calls", 0)) - int(previous.get("calls", 0))
        total_exec_time = float(row.get("total_exec_time_ms", 0.0)) - float(
            previous.get("total_exec_time_ms", 0.0)
        )
        result_rows = int(row.get("result_rows", 0)) - int(previous.get("result_rows", 0))
        if calls <= 0 and total_exec_time <= 0 and result_rows <= 0:
            continue
        delta_rows.append(
            {
                "queryid": row.get("queryid"),
                "delta_calls": calls,
                "delta_total_exec_time_ms": round(total_exec_time, 3),
                "delta_mean_exec_time_ms": round(total_exec_time / calls, 3)
                if calls > 0
                else None,
                "delta_result_rows": result_rows,
                "query": row.get("query"),
            }
        )
    payload["rows"] = sorted(
        delta_rows,
        key=lambda item: float(item["delta_total_exec_time_ms"]),
        reverse=True,
    )
    return payload


def write_summary_markdown(report: BenchmarkReport, output_path: Path) -> None:
    lines = [
        f"# T-047 query benchmark: {report.run_id}",
        "",
        "## 실행 환경",
        "",
        f"- 시작: `{report.started_at}`",
        f"- 종료: `{report.finished_at}`",
        f"- Git: `{report.environment.git_branch}` / `{report.environment.git_commit}`",
        f"- Python: `{report.environment.python_version}`",
        f"- Platform: `{report.environment.platform}`",
        f"- Pool: `size={report.environment.pg_pool_size}, "
        f"max_overflow={report.environment.pg_max_overflow}`",
        f"- `pg_stat_statements`: `{report.environment.pg_stat_statements}`",
        "",
        "### Row count",
        "",
        "| relation | rows |",
        "|----------|-----:|",
    ]
    for name, value in report.environment.row_counts.items():
        lines.append(f"| `{name}` | {value if value is not None else 'n/a'} |")
    lines.extend(
        [
            "",
            "## Latency summary",
            "",
            "| group | sql | conc | samples | errors | p50 ms | p90 ms | p95 ms | "
            "p95 checkout ms | p95 execute ms | p99 ms | max ms | avg rows |",
            "|-------|-----|-----:|--------:|-------:|-------:|-------:|-------:|"
            "----------------:|---------------:|-------:|-------:|---------:|",
        ]
    )
    for row in report.summaries:
        lines.append(
            "| "
            f"`{row.group}` | `{row.sql_name}` | {row.concurrency} | {row.samples} | "
            f"{row.errors} | {_md_num(row.p50_ms)} | {_md_num(row.p90_ms)} | "
            f"{_md_num(row.p95_ms)} | {_md_num(row.p95_checkout_ms)} | "
            f"{_md_num(row.p95_execute_ms)} | {_md_num(row.p99_ms)} | {_md_num(row.max_ms)} | "
            f"{_md_num(row.avg_rows)} |"
        )
    lines.extend(
        [
            "",
            "## Slowest measured samples",
            "",
            "| group | case | sql | conc | elapsed ms | rows |",
            "|-------|------|-----|-----:|-----------:|-----:|",
        ]
    )
    slow = sorted(
        (item for item in report.measurements if item.ok and not item.warmup),
        key=lambda item: item.elapsed_ms,
        reverse=True,
    )[:20]
    for item in slow:
        lines.append(
            f"| `{item.group}` | `{item.case_id}` | `{item.sql_name}` | {item.concurrency} | "
            f"{item.elapsed_ms:.2f} | {item.row_count} |"
        )
    errors = [item for item in report.measurements if not item.ok and not item.warmup]
    if errors:
        lines.extend(["", "## Errors", ""])
        for item in errors[:30]:
            lines.append(
                f"- `{item.group}` `{item.case_id}` `{item.sql_name}` "
                f"conc={item.concurrency}: {item.error}"
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _run_iteration(
    engine: AsyncEngine,
    cases: Sequence[BenchmarkCase],
    *,
    concurrency: int,
    iteration: int,
    warmup: bool,
    statement_timeout_ms: int,
) -> tuple[Measurement, ...]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(case: BenchmarkCase) -> Measurement:
        async with semaphore:
            return await _measure_case(
                engine,
                case,
                concurrency=concurrency,
                iteration=iteration,
                warmup=warmup,
                statement_timeout_ms=statement_timeout_ms,
            )

    return tuple(await asyncio.gather(*(one(case) for case in cases)))


async def _measure_case(
    engine: AsyncEngine,
    case: BenchmarkCase,
    *,
    concurrency: int,
    iteration: int,
    warmup: bool,
    statement_timeout_ms: int,
) -> Measurement:
    start = time.perf_counter()
    checkout_ms: float | None = None
    execute_ms: float | None = None
    execute_start: float | None = None
    try:
        checkout_start = time.perf_counter()
        async with engine.connect() as conn:
            checkout_ms = round((time.perf_counter() - checkout_start) * 1000, 3)
            execute_start = time.perf_counter()
            row_count = await _execute_case(conn, case, statement_timeout_ms=statement_timeout_ms)
            execute_ms = round((time.perf_counter() - execute_start) * 1000, 3)
        return Measurement(
            case_id=case.case_id,
            group=case.group,
            sql_name=case.sql_name,
            concurrency=concurrency,
            iteration=iteration,
            warmup=warmup,
            ok=True,
            elapsed_ms=round((time.perf_counter() - start) * 1000, 3),
            row_count=row_count,
            checkout_ms=checkout_ms,
            execute_ms=execute_ms,
        )
    except (DBAPIError, ProgrammingError, TimeoutError, ValueError) as exc:
        if execute_start is not None and execute_ms is None:
            execute_ms = round((time.perf_counter() - execute_start) * 1000, 3)
        return Measurement(
            case_id=case.case_id,
            group=case.group,
            sql_name=case.sql_name,
            concurrency=concurrency,
            iteration=iteration,
            warmup=warmup,
            ok=False,
            elapsed_ms=round((time.perf_counter() - start) * 1000, 3),
            row_count=0,
            error=_redact_error(exc),
            checkout_ms=checkout_ms,
            execute_ms=execute_ms,
        )


async def _execute_case(
    conn: AsyncConnection,
    case: BenchmarkCase,
    *,
    statement_timeout_ms: int,
) -> int:
    spec = _spec_for_case(case)
    async with conn.begin():
        await conn.execute(text(f"SET LOCAL statement_timeout = '{statement_timeout_ms}ms'"))
        for setup in spec.setup_sql:
            await conn.execute(text(setup))
        if _is_search_sql(case):
            return await _execute_search_case(conn, case)
        result = await conn.execute(spec.statement, case.params)
        return len(result.fetchall())


async def _explain_case(
    conn: AsyncConnection,
    case: BenchmarkCase,
    *,
    statement_timeout_ms: int,
) -> object:
    spec = _spec_for_case(case)
    async with conn.begin():
        await conn.execute(text(f"SET LOCAL statement_timeout = '{statement_timeout_ms}ms'"))
        for setup in spec.setup_sql:
            await conn.execute(text(setup))
        statement = spec.statement
        params = case.params
        if _is_search_sql(case) and await _search_exact_match_exists(conn, case):
            statement = _SEARCH_EXACT_SQL
            params = _search_exact_params(case.params)
        explain_sql = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON, SETTINGS) " + str(statement)
        result = await conn.execute(text(explain_sql), params)
        first = result.scalar_one()
    return first


async def _execute_search_case(conn: AsyncConnection, case: BenchmarkCase) -> int:
    exact_params = _search_exact_params(case.params)
    exact_rows = (await conn.execute(_SEARCH_EXACT_SQL, exact_params)).fetchall()
    exact_total = int(exact_rows[0]._mapping["total"]) if exact_rows else 0
    if exact_total > 0:
        return len(exact_rows)
    result = await conn.execute(_SEARCH_SQL, case.params)
    return len(result.fetchall())


async def _search_exact_match_exists(
    conn: AsyncConnection,
    case: BenchmarkCase,
) -> bool:
    exact_params = _search_exact_params(case.params)
    exact_rows = (await conn.execute(_SEARCH_EXACT_SQL, exact_params)).fetchall()
    exact_total = int(exact_rows[0]._mapping["total"]) if exact_rows else 0
    return exact_total > 0


def _search_exact_params(params: Params) -> Params:
    return {
        "query_nrm": _normalize_search_query(str(params["query"])),
        "limit": int(cast("int", params["limit"])),
        "offset": int(cast("int", params["offset"])),
        **_region_params_from_params(params),
    }


def _spec_for_case(case: BenchmarkCase) -> QuerySpec:
    try:
        return QUERY_SPECS[case.sql_name]
    except KeyError as exc:
        msg = f"unknown sql_name: {case.sql_name}"
        raise ValueError(msg) from exc


async def _sample_mv_rows(
    conn: AsyncConnection,
    limit: int,
    *,
    require_parcel: bool = False,
    require_point: bool = False,
) -> list[Mapping[str, Any]]:
    filters = [
        "rn_nrm IS NOT NULL",
        "rn IS NOT NULL",
        "buld_mnnm IS NOT NULL",
    ]
    if require_parcel:
        filters.extend(["mntn_yn IS NOT NULL", "lnbr_mnnm IS NOT NULL"])
    if require_point:
        filters.extend(["pt_4326 IS NOT NULL", "pt_5179 IS NOT NULL"])
    where = " AND ".join(filters)
    sql = f"""
SELECT bd_mgt_sn, left(bjd_cd, 5) AS sig_cd, bjd_cd, si_nm, sgg_nm, emd_nm, li_nm,
       rn, rn_nrm, buld_mnnm,
       buld_slno, buld_se_cd, mntn_yn, lnbr_mnnm, lnbr_slno, zip_no,
       ST_X(pt_4326) AS lon, ST_Y(pt_4326) AS lat
  FROM mv_geocode_target TABLESAMPLE SYSTEM (0.2) REPEATABLE (47)
 WHERE {where}
 LIMIT :limit
"""
    try:
        rows = (await conn.execute(text(sql), {"limit": limit})).mappings().all()
    except (DBAPIError, ProgrammingError):
        await conn.rollback()
        rows = []
    if len(rows) >= limit:
        return [dict(row) for row in rows]
    fallback = f"""
SELECT bd_mgt_sn, left(bjd_cd, 5) AS sig_cd, bjd_cd, si_nm, sgg_nm, emd_nm, li_nm,
       rn, rn_nrm, buld_mnnm,
       buld_slno, buld_se_cd, mntn_yn, lnbr_mnnm, lnbr_slno, zip_no,
       ST_X(pt_4326) AS lon, ST_Y(pt_4326) AS lat
  FROM mv_geocode_target
 WHERE {where}
 ORDER BY bd_mgt_sn
 LIMIT :limit
"""
    return [
        dict(row)
        for row in (await conn.execute(text(fallback), {"limit": limit})).mappings().all()
    ]


async def _sample_sppn_rows(
    conn: AsyncConnection,
    limit: int,
) -> list[Mapping[str, Any]]:
    sql = """
SELECT sig_cd, makarea_id, makarea_nm,
       ST_X(ST_Transform(ST_PointOnSurface(geom), 4326)) AS lon,
       ST_Y(ST_Transform(ST_PointOnSurface(geom), 4326)) AS lat
  FROM tl_sppn_makarea TABLESAMPLE SYSTEM (10) REPEATABLE (47)
 WHERE geom IS NOT NULL
 LIMIT :limit
"""
    try:
        rows = (await conn.execute(text(sql), {"limit": limit})).mappings().all()
        return [dict(row) for row in rows]
    except (DBAPIError, ProgrammingError):
        await conn.rollback()
        return []


def _road_params(row: Mapping[str, Any]) -> Params:
    return {
        **EMPTY_REGION_PARAMS,
        "si": row["si_nm"],
        "sgg": row["sgg_nm"],
        "road_nrm": row["rn_nrm"],
        "mnnm": row["buld_mnnm"],
        "slno": row["buld_slno"],
        "buld_se_cd": row["buld_se_cd"],
    }


def _parcel_params(row: Mapping[str, Any]) -> Params:
    return {
        **EMPTY_REGION_PARAMS,
        "si": row["si_nm"],
        "sgg": row["sgg_nm"],
        "emd": row["li_nm"] or row["emd_nm"],
        "mntn_yn": row["mntn_yn"],
        "mnnm": row["lnbr_mnnm"],
        "slno": row["lnbr_slno"],
    }


def _row_label(row: Mapping[str, Any]) -> str:
    return " ".join(
        str(part)
        for part in (
            row.get("si_nm"),
            row.get("sgg_nm"),
            row.get("rn"),
            row.get("buld_mnnm"),
        )
        if part not in (None, "")
    )


def _fuzzy_token(value: str) -> str:
    if len(value) <= 3:
        return value
    return value[:-1]


def _with_empty_region_params(params: Params) -> Params:
    return {**EMPTY_REGION_PARAMS, **params}


def _with_region_params(
    params: Params,
    *,
    sig_cd: str | None = None,
    bjd_cd: str | None = None,
) -> Params:
    hint = RegionHint(sig_cd=sig_cd, bjd_cd=bjd_cd)
    return {**params, **hint.sql_params()}


def _region_params_from_params(params: Params) -> Params:
    return {name: params.get(name) for name in EMPTY_REGION_PARAMS}


def _is_search_sql(case: BenchmarkCase) -> bool:
    return case.sql_name in {"search", "search_sig", "search_fuzzy"}


async def _optional_count(conn: AsyncConnection, relation: str) -> int | None:
    try:
        return int(await conn.scalar(text(f"SELECT count(*) FROM {relation}")) or 0)
    except (DBAPIError, ProgrammingError):
        return None


async def _optional_relation_size(conn: AsyncConnection, relation: str) -> int | None:
    try:
        value = await conn.scalar(
            text(
                """
SELECT CASE
         WHEN to_regclass(:relation) IS NULL THEN NULL
         ELSE pg_total_relation_size(to_regclass(:relation))
       END
"""
            ),
            {"relation": relation},
        )
        return int(value) if value is not None else None
    except (DBAPIError, ProgrammingError):
        return None


async def _optional_scalar_str(conn: AsyncConnection, sql: str) -> str | None:
    try:
        value = await conn.scalar(text(sql))
    except (DBAPIError, ProgrammingError):
        return None
    return str(value) if value is not None else None


async def _pg_stat_statements_status(conn: AsyncConnection) -> tuple[bool, str | None]:
    installed = bool(
        await conn.scalar(
            text(
                """
SELECT EXISTS (
    SELECT 1 FROM pg_extension WHERE extname='pg_stat_statements'
)
"""
            )
        )
    )
    if not installed:
        return False, "pg_stat_statements extension is not installed"
    try:
        await conn.execute(text("SELECT 1 FROM x_extension.pg_stat_statements LIMIT 1"))
    except (DBAPIError, ProgrammingError) as exc:
        await conn.rollback()
        return False, _redact_error(exc)
    return True, None


def _plain_pg_stat_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "queryid": str(row["queryid"]) if row.get("queryid") is not None else None,
        "calls": int(row.get("calls") or 0),
        "total_exec_time_ms": round(float(row.get("total_exec_time") or 0.0), 3),
        "mean_exec_time_ms": round(float(row.get("mean_exec_time") or 0.0), 3),
        "result_rows": int(row.get("result_rows") or 0),
        "shared_blks_hit": int(row.get("shared_blks_hit") or 0),
        "shared_blks_read": int(row.get("shared_blks_read") or 0),
        "temp_blks_written": int(row.get("temp_blks_written") or 0),
        "query": str(row.get("query") or ""),
    }


def _pg_stat_row_key(row: Mapping[str, Any]) -> str:
    queryid = row.get("queryid")
    if queryid not in (None, ""):
        return str(queryid)
    return str(row.get("query") or "")


def _round_optional(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _md_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def _redact_error(exc: BaseException) -> str:
    message = str(exc)
    return message.replace("addr:addr@", "***:***@")


def _git_output(*args: str) -> str | None:
    git_repo = _git_repo()
    command = _git_command(git_repo, *args)
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _git_command(git_repo: str | None, *args: str) -> tuple[str, ...]:
    if git_repo is None:
        return ("git", *args)
    if _is_windows_path(git_repo):
        return (_windows_git_executable(), "-C", git_repo, *args)
    return ("git", "-C", git_repo, *args)


def _git_repo() -> str | None:
    env_repo = os.environ.get("KRADDR_GEO_GIT_REPO")
    if env_repo:
        return _as_windows_path(env_repo)
    cwd = Path.cwd()
    if cwd.name.startswith("python-kraddr-geo-") and cwd.name.endswith("-test"):
        return f"F:/dev/{cwd.name.removesuffix('-test')}"
    if (Path("/mnt/f/dev/python-kraddr-geo-codex") / ".git").exists():
        return "F:/dev/python-kraddr-geo-codex"
    return None


def _as_windows_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("/mnt/") and len(normalized) > 6 and normalized[6] == "/":
        drive = normalized[5].upper()
        return f"{drive}:{normalized[6:]}"
    return normalized


def _is_windows_path(path: str) -> bool:
    return len(path) >= 3 and path[1:3] == ":/"


def _windows_git_executable() -> str:
    env_git = os.environ.get("KRADDR_GEO_GIT_EXE")
    if env_git:
        return env_git
    for candidate in (
        "/mnt/c/Program Files/Git/cmd/git.exe",
        "/mnt/c/Program Files/Git/bin/git.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return shutil.which("git.exe") or "git.exe"


def _run_id() -> str:
    return datetime.now(UTC).strftime("t047-%Y%m%d-%H%M%S")


def _settings_for_run(
    pg_dsn: str | None,
    *,
    pool_size: int | None,
    max_overflow: int | None,
) -> Settings:
    settings = get_settings()
    updates: dict[str, str | int] = {}
    if pg_dsn is not None:
        updates["pg_dsn"] = pg_dsn
    if pool_size is not None:
        updates["pg_pool_size"] = pool_size
    if max_overflow is not None:
        updates["pg_max_overflow"] = max_overflow
    return settings.model_copy(update=updates) if updates else settings


def _hash_cases(cases: Sequence[BenchmarkCase]) -> str:
    payload = corpus_to_json(cases).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def _amain(args: argparse.Namespace) -> None:
    run_id = args.run_id or _run_id()
    output_dir = args.output_dir or Path("artifacts") / "perf" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.pg_stat_limit < 1:
        msg = "--pg-stat-limit must be at least 1"
        raise ValueError(msg)
    settings = _settings_for_run(
        args.pg_dsn,
        pool_size=args.pool_size,
        max_overflow=args.max_overflow,
    )
    engine = make_async_engine(settings)
    try:
        if args.corpus:
            cases = corpus_from_json(args.corpus)
        else:
            cases = await build_corpus(engine, cases_per_group=args.cases_per_group)
        (output_dir / "corpus.json").write_text(corpus_to_json(cases), encoding="utf-8")
        (output_dir / "corpus-summary.json").write_text(
            json.dumps(
                {
                    "schema_version": BENCHMARK_SCHEMA_VERSION,
                    "case_count": len(cases),
                    "sha256": _hash_cases(cases),
                    "groups": _case_group_counts(cases),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        started_at = datetime.now(UTC).isoformat()
        environment = await collect_environment(
            engine,
            run_id=run_id,
            started_at=started_at,
            settings=settings,
        )
        pg_stat_before = await capture_pg_stat_statements(
            engine,
            limit=args.pg_stat_limit,
            reset=args.reset_pg_stat_statements,
        )
        (output_dir / "pg-stat-statements-before.json").write_text(
            json.dumps(pg_stat_before, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report = await run_benchmark(
            engine,
            cases,
            run_id=run_id,
            settings=settings,
            concurrency_levels=tuple(args.concurrency or [1]),
            iterations=args.iterations,
            warmup=args.warmup,
            statement_timeout_ms=args.statement_timeout_ms,
            started_at=started_at,
            environment=environment,
        )
        (output_dir / "benchmark.json").write_text(report_to_json(report), encoding="utf-8")
        (output_dir / "environment.json").write_text(
            json.dumps(asdict(report.environment), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pg_stat_after = await capture_pg_stat_statements(
            engine,
            limit=args.pg_stat_limit,
        )
        (output_dir / "pg-stat-statements-after.json").write_text(
            json.dumps(pg_stat_after, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "pg-stat-statements-delta.json").write_text(
            json.dumps(pg_stat_delta(pg_stat_before, pg_stat_after), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_summary_markdown(report, output_dir / "summary.md")
        await explain_slowest_cases(
            engine,
            report,
            output_dir=output_dir,
            per_group=args.explain_slowest_per_group,
            statement_timeout_ms=args.statement_timeout_ms,
        )
    finally:
        await engine.dispose()
    print(output_dir)


def _case_group_counts(cases: Iterable[BenchmarkCase]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for case in cases:
        counts[case.group] += 1
    return dict(sorted(counts.items()))


def main() -> None:
    asyncio.run(_amain(build_parser().parse_args()))


if __name__ == "__main__":
    main()
