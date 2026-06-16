"""T-141 SQL/REST high-load benchmark matrix runner.

The older T-047/T-138 scripts measure one SQL or REST run at a time.  This
orchestrator builds deterministic workload mixes on top of their saved corpus and
executes a repeatable matrix: steady, burst, recovery, and soak profiles across
concurrency, pool, statement timeout, and optional REST server settings.
"""

from __future__ import annotations

# ruff: noqa: ASYNC240
import argparse
import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kortravelgeo.infra.engine import make_async_engine  # noqa: E402
from kortravelgeo.settings import Settings, get_settings  # noqa: E402
from scripts import benchmark_api_latency as restbench  # noqa: E402
from scripts import benchmark_query_performance as sqlbench  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

T141_SCHEMA_VERSION = 1
DEFAULT_CONCURRENCY = (1, 4, 16, 64, 128, 256)
QUICK_CONCURRENCY = (1, 4)
DEFAULT_WORKLOADS = (
    "actual_mix",
    "worst_case_mix",
    "adversarial_fuzzy",
    "reverse_polygon_heavy",
)

Target = Literal["sql", "rest"]
Phase = Literal["steady", "burst", "recovery", "soak"]


@dataclass(frozen=True, slots=True)
class AdminApiSpec:
    name: str
    path: str
    params: dict[str, str | int | float | bool | None]
    expected_status: str | None = None


@dataclass(frozen=True, slots=True)
class WorkloadSpec:
    name: str
    description: str
    sql_names: tuple[str, ...]
    weights: Mapping[str, int]
    admin_cases: tuple[AdminApiSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class MatrixPlanItem:
    profile_id: str
    target: Target
    workload: str
    phase: Phase
    concurrency: int
    iterations: int
    warmup: int
    duration_seconds: int
    statement_timeout_ms: int
    pool_size: int | None = None
    max_overflow: int | None = None
    rest_timeout_s: float = 15.0
    rest_max_cases_per_sql: int | None = None
    admission_limit: int | None = None
    cold_cache: bool = False


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    captured_at: str
    process_time_s: float
    rss_max_bytes: int | None
    proc_io: dict[str, int]


@dataclass(frozen=True, slots=True)
class MatrixRunResult:
    profile_id: str
    target: Target
    workload: str
    phase: Phase
    concurrency: int
    case_count: int
    cycles: int
    elapsed_seconds: float
    errors: int
    worst_p95_ms: float | None
    worst_p99_ms: float | None
    worst_max_ms: float | None
    p95_checkout_ms: float | None
    p95_execute_ms: float | None
    avg_response_bytes: float | None
    artifact_dir: str
    resource_before: ResourceSnapshot
    resource_after: ResourceSnapshot


@dataclass(frozen=True, slots=True)
class MatrixReport:
    schema_version: int
    run_id: str
    started_at: str
    finished_at: str
    git_commit: str | None
    git_branch: str | None
    python_version: str
    platform: str
    plan: tuple[MatrixPlanItem, ...]
    results: tuple[MatrixRunResult, ...]


WORKLOADS: dict[str, WorkloadSpec] = {
    "actual_mix": WorkloadSpec(
        name="actual_mix",
        description=(
            "Mixed read traffic: exact geocode, reverse, search, zipcode, no-result, "
            "and lightweight admin summary endpoints."
        ),
        sql_names=tuple(sqlbench.QUERY_SPECS.keys()),
        weights={
            "Q1_ROAD_EXACT": 6,
            "Q2_PARCEL_EXACT": 2,
            "Q3_FUZZY_GEOCODE": 1,
            "Q4_SEARCH": 2,
            "Q5_REVERSE_NEAREST": 3,
            "Q6_REVERSE_RADIUS": 1,
            "Q7_ZIPCODE": 1,
            "Q8_NO_RESULT": 1,
            "Q11_SPPN": 1,
        },
        admin_cases=(
            AdminApiSpec("admin_cache_metrics", "/v1/admin/cache/metrics", {}),
            AdminApiSpec("admin_tables", "/v1/admin/tables", {"limit": 50}),
        ),
    ),
    "worst_case_mix": WorkloadSpec(
        name="worst_case_mix",
        description="Known T-047/T-138 tail candidates: fuzzy/search/reverse-radius paths.",
        sql_names=(
            "fuzzy_geocode",
            "fuzzy_geocode_wide",
            "fuzzy_geocode_sig",
            "search",
            "search_sig",
            "search_fuzzy",
            "reverse_radius",
            "reverse_radius_sig",
            "zipcode_address",
        ),
        weights={"Q3_FUZZY_GEOCODE": 3, "Q4_SEARCH": 4, "Q6_REVERSE_RADIUS": 2, "Q7_ZIPCODE": 1},
        admin_cases=(AdminApiSpec("admin_tables", "/v1/admin/tables", {"limit": 100}),),
    ),
    "adversarial_fuzzy": WorkloadSpec(
        name="adversarial_fuzzy",
        description="Broad trigram and no-result fuzzy cases that stress p99 tail.",
        sql_names=(
            "fuzzy_geocode",
            "fuzzy_geocode_wide",
            "fuzzy_geocode_sig",
            "search_fuzzy",
            "no_result_road",
        ),
        weights={"Q3_FUZZY_GEOCODE": 4, "Q4_SEARCH": 5, "Q8_NO_RESULT": 1},
    ),
    "reverse_polygon_heavy": WorkloadSpec(
        name="reverse_polygon_heavy",
        description="Reverse, radius, zipcode-by-point, and SPPN reverse heavy workload.",
        sql_names=(
            "reverse_nearest",
            "reverse_nearest_sig",
            "reverse_radius",
            "reverse_radius_sig",
            "zipcode_point",
            "sppn_reverse",
        ),
        weights={
            "Q5_REVERSE_NEAREST": 3,
            "Q6_REVERSE_RADIUS": 4,
            "Q7_ZIPCODE": 1,
            "Q11_SPPN": 1,
        },
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or plan the T-141 high-load matrix.")
    parser.add_argument("--pg-dsn", help="PostgreSQL DSN for SQL profiles.")
    parser.add_argument("--base-url", help="REST API base URL for REST profiles.")
    parser.add_argument("--corpus", type=Path, help="Existing SQL benchmark corpus JSON.")
    parser.add_argument("--run-id", help="Stable run id. Defaults to timestamp.")
    parser.add_argument("--output-dir", type=Path, help="Artifact root.")
    parser.add_argument(
        "--mode",
        choices=("plan", "sql", "rest", "both"),
        default="plan",
        help="plan writes matrix-plan only; sql/rest/both execute matching profiles.",
    )
    parser.add_argument("--quick", action="store_true", help="Small c1/c4 matrix for PR checks.")
    parser.add_argument(
        "--workload",
        action="append",
        choices=tuple(WORKLOADS),
        help="Workload to include. May repeat. Default: all T-141 workloads.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        action="append",
        help="Override concurrency levels. May repeat.",
    )
    parser.add_argument("--cases-per-group", type=int, default=100)
    parser.add_argument("--max-cases-per-sql", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--statement-timeout-ms", type=int, default=5_000)
    parser.add_argument("--pool-size", type=int)
    parser.add_argument("--max-overflow", type=int)
    parser.add_argument("--rest-timeout-s", type=float, default=15.0)
    parser.add_argument(
        "--rest-max-cases-per-sql",
        type=int,
        help="Limit REST converted cases per API name. Defaults to --max-cases-per-sql.",
    )
    parser.add_argument(
        "--soak-seconds",
        type=int,
        default=0,
        help="Optional duration for soak profiles. Full runbook uses 1800-3600.",
    )
    parser.add_argument(
        "--include-soak",
        action="store_true",
        help="Include soak profiles. Omitted by default to keep accidental runs short.",
    )
    parser.add_argument(
        "--admission-limit",
        type=int,
        help="Record the API admission limit used by the server profile.",
    )
    parser.add_argument(
        "--server-profile",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help="REST server profile metadata, forwarded to REST artifacts.",
    )
    return parser


def build_plan(
    *,
    targets: Sequence[Target],
    workloads: Sequence[str] | None,
    concurrency_levels: Sequence[int],
    quick: bool,
    iterations: int,
    warmup: int,
    statement_timeout_ms: int,
    pool_size: int | None,
    max_overflow: int | None,
    rest_timeout_s: float,
    rest_max_cases_per_sql: int | None,
    admission_limit: int | None,
    include_soak: bool,
    soak_seconds: int,
) -> tuple[MatrixPlanItem, ...]:
    selected_workloads = tuple(workloads or DEFAULT_WORKLOADS)
    _validate_workloads(selected_workloads)
    levels = tuple(concurrency_levels)
    if not levels:
        msg = "at least one concurrency level is required"
        raise ValueError(msg)
    phases = _phases_for_levels(levels, quick=quick)
    items: list[MatrixPlanItem] = []
    for target in targets:
        for workload in selected_workloads:
            for phase, phase_levels in phases:
                if phase == "soak" and not include_soak:
                    continue
                for concurrency in phase_levels:
                    profile_id = f"{target}-{workload}-{phase}-c{concurrency}"
                    items.append(
                        MatrixPlanItem(
                            profile_id=profile_id,
                            target=target,
                            workload=workload,
                            phase=phase,
                            concurrency=concurrency,
                            iterations=1 if quick else iterations,
                            warmup=0 if quick else warmup,
                            duration_seconds=soak_seconds if phase == "soak" else 0,
                            statement_timeout_ms=statement_timeout_ms,
                            pool_size=pool_size,
                            max_overflow=max_overflow,
                            rest_timeout_s=rest_timeout_s,
                            rest_max_cases_per_sql=rest_max_cases_per_sql,
                            admission_limit=admission_limit,
                            cold_cache=phase == "steady" and concurrency == min(levels),
                        )
                    )
    return tuple(items)


def _phases_for_levels(
    levels: Sequence[int],
    *,
    quick: bool,
) -> tuple[tuple[Phase, tuple[int, ...]], ...]:
    if quick:
        return (("steady", tuple(levels)),)
    steady = tuple(level for level in levels if level <= 64)
    burst = tuple(level for level in levels if level > 64)
    recovery = (min((level for level in levels if level >= 16), default=max(levels)),)
    soak = (64,) if 64 in levels else (max(levels),)
    phases: list[tuple[Phase, tuple[int, ...]]] = []
    if steady:
        phases.append(("steady", steady))
    if burst:
        phases.append(("burst", burst))
    phases.append(("recovery", recovery))
    phases.append(("soak", soak))
    return tuple(phases)


def select_sql_cases(
    cases: Sequence[sqlbench.BenchmarkCase],
    workload_name: str,
    *,
    max_cases_per_sql: int | None,
) -> tuple[sqlbench.BenchmarkCase, ...]:
    workload = _workload(workload_name)
    by_sql: dict[str, list[sqlbench.BenchmarkCase]] = defaultdict(list)
    for case in cases:
        if case.sql_name in workload.sql_names:
            by_sql[case.sql_name].append(case)
    selected: list[sqlbench.BenchmarkCase] = []
    for sql_name in workload.sql_names:
        rows = by_sql.get(sql_name, [])
        if max_cases_per_sql is not None:
            rows = rows[:max_cases_per_sql]
        for row in rows:
            weight = max(1, int(workload.weights.get(row.group, 1)))
            for copy_index in range(weight):
                suffix = f"w{copy_index + 1:02d}"
                selected.append(
                    replace(
                        row,
                        case_id=f"{workload.name}-{suffix}-{row.case_id}",
                        note=_append_note(
                            row.note,
                            f"T-141 workload={workload.name} weight={weight}",
                        ),
                    )
                )
    if not selected:
        msg = f"workload {workload_name!r} selected no SQL cases"
        raise ValueError(msg)
    return tuple(selected)


def select_rest_cases(
    sql_cases: Sequence[sqlbench.BenchmarkCase],
    workload_name: str,
    *,
    max_cases_per_sql: int | None,
) -> tuple[restbench.ApiCase, ...]:
    workload = _workload(workload_name)
    corpus_cases = tuple(
        restbench.CorpusCase(
            case_id=case.case_id,
            group=case.group,
            sql_name=case.sql_name,
            params=case.params,
            label=case.label,
            source=case.source,
            expected_status=case.expected_status,
            note=case.note,
        )
        for case in sql_cases
    )
    api_cases = list(
        restbench.build_api_cases(corpus_cases, max_cases_per_sql=max_cases_per_sql)
    )
    for spec in workload.admin_cases:
        api_cases.append(
            restbench.ApiCase(
                case_id=f"{workload.name}-{spec.name}",
                group="ADMIN_SUMMARY",
                sql_name=spec.name,
                method="GET",
                path=spec.path,
                params=spec.params,
                label=spec.name,
                source_case_id="admin-summary",
                expected_status=spec.expected_status,
            )
        )
    if not api_cases:
        msg = f"workload {workload_name!r} selected no REST cases"
        raise ValueError(msg)
    return tuple(api_cases)


async def run_matrix(
    *,
    plan: Sequence[MatrixPlanItem],
    args: argparse.Namespace,
    output_dir: Path,
) -> tuple[MatrixRunResult, ...]:
    sql_items = tuple(item for item in plan if item.target == "sql")
    rest_items = tuple(item for item in plan if item.target == "rest")
    corpus: tuple[sqlbench.BenchmarkCase, ...] | None = None
    results: list[MatrixRunResult] = []
    settings: Settings | None = None
    engine = None
    if sql_items:
        settings = _settings_for_run(
            args.pg_dsn,
            pool_size=args.pool_size,
            max_overflow=args.max_overflow,
        )
        engine = make_async_engine(settings)
        try:
            corpus = await _load_or_build_corpus(engine, args.corpus, args.cases_per_group)
            for item in sql_items:
                results.append(
                    await _run_sql_item(
                        item,
                        corpus=corpus,
                        settings=settings,
                        engine=engine,
                        output_dir=output_dir / item.profile_id,
                        max_cases_per_sql=args.max_cases_per_sql,
                    )
                )
        finally:
            await engine.dispose()
    if rest_items:
        if not args.base_url:
            msg = "--base-url is required for REST matrix profiles"
            raise ValueError(msg)
        if corpus is None:
            if args.corpus is None:
                msg = "--corpus is required for REST-only matrix profiles"
                raise ValueError(msg)
            corpus = sqlbench.corpus_from_json(args.corpus)
        async with httpx.AsyncClient(
            base_url=str(args.base_url).rstrip("/"),
            timeout=httpx.Timeout(args.rest_timeout_s),
        ) as client:
            for item in rest_items:
                results.append(
                    await _run_rest_item(
                        item,
                        corpus=corpus,
                        client=client,
                        base_url=str(args.base_url).rstrip("/"),
                        server_profile=restbench.parse_server_profile(args.server_profile),
                        output_dir=output_dir / item.profile_id,
                        max_cases_per_sql=args.max_cases_per_sql,
                    )
                )
    return tuple(results)


async def _run_sql_item(
    item: MatrixPlanItem,
    *,
    corpus: Sequence[sqlbench.BenchmarkCase],
    settings: Settings,
    engine: Any,
    output_dir: Path,
    max_cases_per_sql: int | None,
) -> MatrixRunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = select_sql_cases(corpus, item.workload, max_cases_per_sql=max_cases_per_sql)
    (output_dir / "selected-corpus.json").write_text(
        sqlbench.corpus_to_json(cases),
        encoding="utf-8",
    )
    resource_before = capture_resource_snapshot()
    started_at = datetime.now(UTC).isoformat()
    environment = await sqlbench.collect_environment(
        engine,
        run_id=item.profile_id,
        started_at=started_at,
        settings=settings,
    )
    pg_before = await sqlbench.capture_pg_stat_statements(engine, limit=100, reset=False)
    (output_dir / "pg-stat-statements-before.json").write_text(
        json.dumps(pg_before, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    elapsed_start = time.perf_counter()
    cycles = 0
    measurements: list[sqlbench.Measurement] = []
    deadline = elapsed_start + item.duration_seconds if item.duration_seconds > 0 else None
    while True:
        cycles += 1
        report = await sqlbench.run_benchmark(
            engine,
            cases,
            run_id=f"{item.profile_id}-cycle{cycles}",
            settings=settings,
            concurrency_levels=(item.concurrency,),
            iterations=item.iterations,
            warmup=item.warmup,
            statement_timeout_ms=item.statement_timeout_ms,
            started_at=started_at,
            environment=environment,
        )
        measurements.extend(report.measurements)
        if deadline is None or time.perf_counter() >= deadline:
            break
    combined = sqlbench.BenchmarkReport(
        schema_version=sqlbench.BENCHMARK_SCHEMA_VERSION,
        run_id=item.profile_id,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        cases=tuple(cases),
        measurements=tuple(measurements),
        summaries=sqlbench.summarize_measurements(measurements),
        environment=environment,
    )
    (output_dir / "benchmark.json").write_text(sqlbench.report_to_json(combined), encoding="utf-8")
    (output_dir / "environment.json").write_text(
        json.dumps(asdict(environment), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pg_after = await sqlbench.capture_pg_stat_statements(engine, limit=100)
    (output_dir / "pg-stat-statements-after.json").write_text(
        json.dumps(pg_after, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "pg-stat-statements-delta.json").write_text(
        json.dumps(sqlbench.pg_stat_delta(pg_before, pg_after), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    sqlbench.write_summary_markdown(combined, output_dir / "summary.md")
    resource_after = capture_resource_snapshot()
    return _sql_result(
        item,
        report=combined,
        cycles=cycles,
        elapsed_seconds=time.perf_counter() - elapsed_start,
        artifact_dir=output_dir,
        resource_before=resource_before,
        resource_after=resource_after,
    )


async def _run_rest_item(
    item: MatrixPlanItem,
    *,
    corpus: Sequence[sqlbench.BenchmarkCase],
    client: httpx.AsyncClient,
    base_url: str,
    server_profile: Mapping[str, str],
    output_dir: Path,
    max_cases_per_sql: int | None,
) -> MatrixRunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    sql_cases = select_sql_cases(corpus, item.workload, max_cases_per_sql=max_cases_per_sql)
    rest_limit = (
        item.rest_max_cases_per_sql
        if item.rest_max_cases_per_sql is not None
        else max_cases_per_sql
    )
    cases = select_rest_cases(sql_cases, item.workload, max_cases_per_sql=rest_limit)
    (output_dir / "api-cases.json").write_text(
        json.dumps([asdict(case) for case in cases], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    resource_before = capture_resource_snapshot()
    started_at = datetime.now(UTC).isoformat()
    environment = restbench.ApiEnvironment(
        run_id=item.profile_id,
        started_at=started_at,
        git_commit=_git_output("rev-parse", "HEAD"),
        git_branch=_git_output("branch", "--show-current"),
        python_version=platform.python_version(),
        platform=platform.platform(),
        base_url=base_url,
        corpus_path="selected-from-t141-matrix",
        corpus_sha256=_hash_json([asdict(case) for case in sql_cases]),
        case_count=len(cases),
        server_profile={
            **dict(server_profile),
            "admission_limit": str(item.admission_limit)
            if item.admission_limit is not None
            else "unset",
        },
    )
    elapsed_start = time.perf_counter()
    cycles = 0
    measurements: list[restbench.ApiMeasurement] = []
    deadline = elapsed_start + item.duration_seconds if item.duration_seconds > 0 else None
    while True:
        cycles += 1
        report = await restbench.run_benchmark(
            client,
            cases,
            run_id=f"{item.profile_id}-cycle{cycles}",
            environment=environment,
            concurrency_levels=(item.concurrency,),
            iterations=item.iterations,
            warmup=item.warmup,
        )
        measurements.extend(report.measurements)
        if deadline is None or time.perf_counter() >= deadline:
            break
    combined = restbench.ApiBenchmarkReport(
        schema_version=restbench.API_BENCHMARK_SCHEMA_VERSION,
        run_id=item.profile_id,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        cases=tuple(cases),
        measurements=tuple(measurements),
        summaries=restbench.summarize(measurements),
        environment=environment,
    )
    (output_dir / "benchmark.json").write_text(
        json.dumps(asdict(combined), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "environment.json").write_text(
        json.dumps(asdict(environment), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    restbench.write_summary_markdown(combined, output_dir / "summary.md")
    resource_after = capture_resource_snapshot()
    return _rest_result(
        item,
        report=combined,
        cycles=cycles,
        elapsed_seconds=time.perf_counter() - elapsed_start,
        artifact_dir=output_dir,
        resource_before=resource_before,
        resource_after=resource_after,
    )


def _sql_result(
    item: MatrixPlanItem,
    *,
    report: sqlbench.BenchmarkReport,
    cycles: int,
    elapsed_seconds: float,
    artifact_dir: Path,
    resource_before: ResourceSnapshot,
    resource_after: ResourceSnapshot,
) -> MatrixRunResult:
    rows = tuple(report.summaries)
    return MatrixRunResult(
        profile_id=item.profile_id,
        target=item.target,
        workload=item.workload,
        phase=item.phase,
        concurrency=item.concurrency,
        case_count=len(report.cases),
        cycles=cycles,
        elapsed_seconds=round(elapsed_seconds, 3),
        errors=sum(row.errors for row in rows),
        worst_p95_ms=_max_optional(row.p95_ms for row in rows),
        worst_p99_ms=_max_optional(row.p99_ms for row in rows),
        worst_max_ms=_max_optional(row.max_ms for row in rows),
        p95_checkout_ms=_max_optional(row.p95_checkout_ms for row in rows),
        p95_execute_ms=_max_optional(row.p95_execute_ms for row in rows),
        avg_response_bytes=None,
        artifact_dir=str(artifact_dir),
        resource_before=resource_before,
        resource_after=resource_after,
    )


def _rest_result(
    item: MatrixPlanItem,
    *,
    report: restbench.ApiBenchmarkReport,
    cycles: int,
    elapsed_seconds: float,
    artifact_dir: Path,
    resource_before: ResourceSnapshot,
    resource_after: ResourceSnapshot,
) -> MatrixRunResult:
    rows = tuple(report.summaries)
    return MatrixRunResult(
        profile_id=item.profile_id,
        target=item.target,
        workload=item.workload,
        phase=item.phase,
        concurrency=item.concurrency,
        case_count=len(report.cases),
        cycles=cycles,
        elapsed_seconds=round(elapsed_seconds, 3),
        errors=sum(row.errors for row in rows),
        worst_p95_ms=_max_optional(row.p95_ms for row in rows),
        worst_p99_ms=_max_optional(row.p99_ms for row in rows),
        worst_max_ms=_max_optional(row.max_ms for row in rows),
        p95_checkout_ms=None,
        p95_execute_ms=None,
        avg_response_bytes=_max_optional(row.avg_response_bytes for row in rows),
        artifact_dir=str(artifact_dir),
        resource_before=resource_before,
        resource_after=resource_after,
    )


def write_plan(plan: Sequence[MatrixPlanItem], path: Path) -> None:
    path.write_text(
        json.dumps([asdict(item) for item in plan], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_summary_markdown(report: MatrixReport, output_path: Path) -> None:
    lines = [
        f"# T-141 load matrix: {report.run_id}",
        "",
        "## Plan",
        "",
        "| profile | target | workload | phase | c | iter | warmup | soak s | pool | timeout |",
        "|---------|--------|----------|-------|--:|-----:|-------:|-------:|------|--------:|",
    ]
    for item in report.plan:
        pool = (
            "default"
            if item.pool_size is None and item.max_overflow is None
            else f"{item.pool_size or 'default'}/{item.max_overflow or 'default'}"
        )
        lines.append(
            f"| `{item.profile_id}` | `{item.target}` | `{item.workload}` | `{item.phase}` | "
            f"{item.concurrency} | {item.iterations} | {item.warmup} | "
            f"{item.duration_seconds} | `{pool}` | {item.statement_timeout_ms} |"
        )
    lines.extend(["", "## Results", ""])
    if not report.results:
        lines.append("Plan-only run. No benchmark profiles were executed.")
    else:
        lines.extend(
            [
                "| profile | target | cases | cycles | errors | worst p95 | worst p99 | max | "
                "p95 checkout | p95 execute | elapsed s |",
                "|---------|--------|------:|-------:|-------:|----------:|----------:|----:|"
                "-------------:|------------:|----------:|",
            ]
        )
        for row in report.results:
            lines.append(
                f"| `{row.profile_id}` | `{row.target}` | {row.case_count} | {row.cycles} | "
                f"{row.errors} | {_md_num(row.worst_p95_ms)} | {_md_num(row.worst_p99_ms)} | "
                f"{_md_num(row.worst_max_ms)} | {_md_num(row.p95_checkout_ms)} | "
                f"{_md_num(row.p95_execute_ms)} | {row.elapsed_seconds:.3f} |"
            )
    lines.extend(
        [
            "",
            "## Workloads",
            "",
        ]
    )
    for workload in WORKLOADS.values():
        lines.append(f"- `{workload.name}`: {workload.description}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def capture_resource_snapshot() -> ResourceSnapshot:
    return ResourceSnapshot(
        captured_at=datetime.now(UTC).isoformat(),
        process_time_s=round(time.process_time(), 6),
        rss_max_bytes=_rss_max_bytes(),
        proc_io=_proc_io(),
    )


async def _load_or_build_corpus(
    engine: Any,
    corpus_path: Path | None,
    cases_per_group: int,
) -> tuple[sqlbench.BenchmarkCase, ...]:
    if corpus_path is not None:
        return sqlbench.corpus_from_json(corpus_path)
    return await sqlbench.build_corpus(engine, cases_per_group=cases_per_group)


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


def _targets_for_mode(mode: str) -> tuple[Target, ...]:
    if mode == "sql":
        return ("sql",)
    if mode == "rest":
        return ("rest",)
    if mode == "both":
        return ("sql", "rest")
    return ("sql", "rest")


def _workload(name: str) -> WorkloadSpec:
    try:
        return WORKLOADS[name]
    except KeyError as exc:
        msg = f"unknown workload: {name}"
        raise ValueError(msg) from exc


def _validate_workloads(names: Sequence[str]) -> None:
    for name in names:
        _workload(name)


def _append_note(note: str | None, extra: str) -> str:
    return extra if not note else f"{note}; {extra}"


def _max_optional(values: Iterable[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return round(max(present), 3) if present else None


def _md_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _rss_max_bytes() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if value <= 0:
        return None
    # Linux returns KiB, macOS returns bytes. This project runs perf checks in WSL/Linux.
    return value * 1024 if platform.system() != "Darwin" else value


def _proc_io() -> dict[str, int]:
    path = Path("/proc/self/io")
    if not path.exists():
        return {}
    result: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition(":")
        if sep:
            result[key] = _parse_int(value.strip())
    return result


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _hash_json(value: object) -> str:
    import hashlib

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_output(*args: str) -> str | None:
    git_repo = _git_repo()
    command = _git_command(git_repo, *args)
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
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
    env_repo = os.environ.get("KTG_GIT_REPO")
    if env_repo:
        return _as_windows_path(env_repo)
    cwd = Path.cwd()
    if cwd.name.startswith("kor-travel-geo-") and cwd.name.endswith("-test"):
        return f"F:/dev/{cwd.name.removesuffix('-test')}"
    if (Path("/mnt/f/dev/kor-travel-geo-codex") / ".git").exists():
        return "F:/dev/kor-travel-geo-codex"
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
    env_git = os.environ.get("KTG_GIT_EXE")
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
    return datetime.now(UTC).strftime("t141-load-matrix-%Y%m%d-%H%M%S")


async def _amain(args: argparse.Namespace) -> None:
    if args.max_cases_per_sql is not None and args.max_cases_per_sql < 1:
        msg = "--max-cases-per-sql must be at least 1"
        raise ValueError(msg)
    if args.rest_max_cases_per_sql is not None and args.rest_max_cases_per_sql < 1:
        msg = "--rest-max-cases-per-sql must be at least 1"
        raise ValueError(msg)
    levels = tuple(args.concurrency or (QUICK_CONCURRENCY if args.quick else DEFAULT_CONCURRENCY))
    targets = _targets_for_mode(args.mode)
    plan = build_plan(
        targets=targets,
        workloads=tuple(args.workload) if args.workload else None,
        concurrency_levels=levels,
        quick=args.quick,
        iterations=args.iterations,
        warmup=args.warmup,
        statement_timeout_ms=args.statement_timeout_ms,
        pool_size=args.pool_size,
        max_overflow=args.max_overflow,
        rest_timeout_s=args.rest_timeout_s,
        rest_max_cases_per_sql=args.rest_max_cases_per_sql,
        admission_limit=args.admission_limit,
        include_soak=args.include_soak,
        soak_seconds=args.soak_seconds,
    )
    run_id = args.run_id or _run_id()
    output_dir = args.output_dir or Path("artifacts") / "perf" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    write_plan(plan, output_dir / "matrix-plan.json")
    started_at = datetime.now(UTC).isoformat()
    results: tuple[MatrixRunResult, ...] = ()
    if args.mode != "plan":
        results = await run_matrix(plan=plan, args=args, output_dir=output_dir)
    report = MatrixReport(
        schema_version=T141_SCHEMA_VERSION,
        run_id=run_id,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        git_commit=_git_output("rev-parse", "HEAD"),
        git_branch=_git_output("branch", "--show-current"),
        python_version=platform.python_version(),
        platform=platform.platform(),
        plan=tuple(plan),
        results=results,
    )
    (output_dir / "matrix-report.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_summary_markdown(report, output_dir / "summary.md")
    print(output_dir)


def main() -> None:
    if sys.platform == "win32":
        asyncio.run(
            _amain(build_parser().parse_args()),
            loop_factory=asyncio.SelectorEventLoop,
        )
        return
    asyncio.run(_amain(build_parser().parse_args()))


if __name__ == "__main__":
    main()
