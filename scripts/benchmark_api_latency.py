"""Benchmark REST API latency with a saved query-performance corpus."""

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
from typing import TYPE_CHECKING, Literal, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


API_BENCHMARK_SCHEMA_VERSION = 1

type ParamValue = str | int | float | bool | None
type Params = dict[str, ParamValue]


@dataclass(frozen=True, slots=True)
class CorpusCase:
    case_id: str
    group: str
    sql_name: str
    params: Params
    label: str
    source: str
    expected_status: str = "OK"
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ApiCase:
    case_id: str
    group: str
    sql_name: str
    method: Literal["GET"]
    path: str
    params: Params
    label: str
    source_case_id: str
    expected_status: str | None = "OK"


@dataclass(frozen=True, slots=True)
class ApiMeasurement:
    case_id: str
    group: str
    sql_name: str
    concurrency: int
    iteration: int
    warmup: bool
    ok: bool
    elapsed_ms: float
    http_status: int | None
    app_status: str | None
    response_bytes: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ApiSummaryRow:
    group: str
    sql_name: str
    concurrency: int
    samples: int
    errors: int
    p50_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    max_ms: float | None
    avg_response_bytes: float | None


@dataclass(frozen=True, slots=True)
class ApiEnvironment:
    run_id: str
    started_at: str
    git_commit: str | None
    git_branch: str | None
    python_version: str
    platform: str
    base_url: str
    corpus_path: str
    corpus_sha256: str
    case_count: int


@dataclass(frozen=True, slots=True)
class ApiBenchmarkReport:
    schema_version: int
    run_id: str
    started_at: str
    finished_at: str
    cases: tuple[ApiCase, ...]
    measurements: tuple[ApiMeasurement, ...]
    summaries: tuple[ApiSummaryRow, ...]
    environment: ApiEnvironment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark kraddr-geo REST API latency.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8888")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--run-id", help="Stable run id. Defaults to timestamp.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact directory. Defaults to artifacts/perf/<run-id>.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
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
        "--max-cases-per-sql",
        type=int,
        help="Limit converted cases per SQL/API group for a quick e2e sample.",
    )
    parser.add_argument("--timeout-s", type=float, default=10.0)
    return parser


def load_corpus(path: Path) -> tuple[CorpusCase, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        msg = f"corpus must be a JSON array: {path}"
        raise ValueError(msg)
    cases: list[CorpusCase] = []
    for item in raw:
        if not isinstance(item, dict):
            msg = f"corpus item must be an object: {item!r}"
            raise ValueError(msg)
        cases.append(
            CorpusCase(
                case_id=str(item["case_id"]),
                group=str(item["group"]),
                sql_name=str(item["sql_name"]),
                params=dict(cast("Mapping[str, ParamValue]", item["params"])),
                label=str(item["label"]),
                source=str(item["source"]),
                expected_status=str(item.get("expected_status", "OK")),
                note=str(item["note"]) if item.get("note") is not None else None,
            )
        )
    return tuple(cases)


def build_api_cases(
    corpus_cases: Sequence[CorpusCase],
    *,
    max_cases_per_sql: int | None = None,
) -> tuple[ApiCase, ...]:
    counters: dict[tuple[str, str], int] = defaultdict(int)
    api_cases: list[ApiCase] = []
    for case in corpus_cases:
        converted = _api_case_for_corpus(case)
        if converted is None:
            continue
        key = (converted.group, converted.sql_name)
        counters[key] += 1
        if max_cases_per_sql is not None and counters[key] > max_cases_per_sql:
            continue
        api_cases.append(converted)
    return tuple(api_cases)


def summarize(measurements: Sequence[ApiMeasurement]) -> tuple[ApiSummaryRow, ...]:
    grouped: dict[tuple[str, str, int], list[ApiMeasurement]] = defaultdict(list)
    for item in measurements:
        if not item.warmup:
            grouped[(item.group, item.sql_name, item.concurrency)].append(item)

    rows: list[ApiSummaryRow] = []
    for (group, sql_name, concurrency), items in sorted(grouped.items()):
        ok_items = [item for item in items if item.ok]
        elapsed = [item.elapsed_ms for item in ok_items]
        avg_response_bytes = (
            statistics.fmean(item.response_bytes for item in ok_items) if ok_items else None
        )
        rows.append(
            ApiSummaryRow(
                group=group,
                sql_name=sql_name,
                concurrency=concurrency,
                samples=len(items),
                errors=sum(1 for item in items if not item.ok),
                p50_ms=_round_optional(percentile(elapsed, 50)),
                p90_ms=_round_optional(percentile(elapsed, 90)),
                p95_ms=_round_optional(percentile(elapsed, 95)),
                p99_ms=_round_optional(percentile(elapsed, 99)),
                max_ms=_round_optional(max(elapsed) if elapsed else None),
                avg_response_bytes=_round_optional(avg_response_bytes),
            )
        )
    return tuple(rows)


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


async def run_benchmark(
    client: httpx.AsyncClient,
    cases: Sequence[ApiCase],
    *,
    run_id: str,
    environment: ApiEnvironment,
    concurrency_levels: Sequence[int],
    iterations: int,
    warmup: int,
) -> ApiBenchmarkReport:
    measurements: list[ApiMeasurement] = []
    for concurrency in concurrency_levels:
        for iteration in range(warmup + iterations):
            measurements.extend(
                await _run_iteration(
                    client,
                    cases,
                    concurrency=concurrency,
                    iteration=iteration + 1,
                    warmup=iteration < warmup,
                )
            )
    finished_at = datetime.now(UTC).isoformat()
    return ApiBenchmarkReport(
        schema_version=API_BENCHMARK_SCHEMA_VERSION,
        run_id=run_id,
        started_at=environment.started_at,
        finished_at=finished_at,
        cases=tuple(cases),
        measurements=tuple(measurements),
        summaries=summarize(measurements),
        environment=environment,
    )


def write_summary_markdown(report: ApiBenchmarkReport, output_path: Path) -> None:
    lines = [
        f"# T-047 REST API benchmark: {report.run_id}",
        "",
        "## 실행 환경",
        "",
        f"- 시작: `{report.started_at}`",
        f"- 종료: `{report.finished_at}`",
        f"- Git: `{report.environment.git_branch}` / `{report.environment.git_commit}`",
        f"- Python: `{report.environment.python_version}`",
        f"- Platform: `{report.environment.platform}`",
        f"- Base URL: `{report.environment.base_url}`",
        f"- Corpus: `{report.environment.corpus_path}`",
        f"- Corpus SHA-256: `{report.environment.corpus_sha256}`",
        f"- REST case count: `{report.environment.case_count}`",
        "",
        "## Latency summary",
        "",
        "| group | api | conc | samples | errors | p50 ms | p90 ms | p95 ms | "
        "p99 ms | max ms | avg bytes |",
        "|-------|-----|-----:|--------:|-------:|-------:|-------:|-------:|"
        "-------:|-------:|----------:|",
    ]
    for row in report.summaries:
        lines.append(
            "| "
            f"`{row.group}` | `{row.sql_name}` | {row.concurrency} | {row.samples} | "
            f"{row.errors} | {_md_num(row.p50_ms)} | {_md_num(row.p90_ms)} | "
            f"{_md_num(row.p95_ms)} | {_md_num(row.p99_ms)} | {_md_num(row.max_ms)} | "
            f"{_md_num(row.avg_response_bytes)} |"
        )

    slow = sorted(
        (item for item in report.measurements if item.ok and not item.warmup),
        key=lambda item: item.elapsed_ms,
        reverse=True,
    )[:20]
    lines.extend(
        [
            "",
            "## Slowest measured samples",
            "",
            "| group | case | api | conc | elapsed ms | http | status | bytes |",
            "|-------|------|-----|-----:|-----------:|-----:|--------|------:|",
        ]
    )
    for item in slow:
        lines.append(
            f"| `{item.group}` | `{item.case_id}` | `{item.sql_name}` | {item.concurrency} | "
            f"{item.elapsed_ms:.2f} | {item.http_status or 'n/a'} | "
            f"`{item.app_status or 'n/a'}` | {item.response_bytes} |"
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
    client: httpx.AsyncClient,
    cases: Sequence[ApiCase],
    *,
    concurrency: int,
    iteration: int,
    warmup: bool,
) -> tuple[ApiMeasurement, ...]:
    semaphore = asyncio.Semaphore(concurrency)

    async def one(case: ApiCase) -> ApiMeasurement:
        async with semaphore:
            return await _measure_case(
                client,
                case,
                concurrency=concurrency,
                iteration=iteration,
                warmup=warmup,
            )

    return tuple(await asyncio.gather(*(one(case) for case in cases)))


async def _measure_case(
    client: httpx.AsyncClient,
    case: ApiCase,
    *,
    concurrency: int,
    iteration: int,
    warmup: bool,
) -> ApiMeasurement:
    start = time.perf_counter()
    try:
        response = await client.request(case.method, case.path, params=case.params)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        app_status = _response_app_status(response)
        ok = 200 <= response.status_code < 300
        if case.expected_status is not None:
            ok = ok and app_status == case.expected_status
        return ApiMeasurement(
            case_id=case.case_id,
            group=case.group,
            sql_name=case.sql_name,
            concurrency=concurrency,
            iteration=iteration,
            warmup=warmup,
            ok=ok,
            elapsed_ms=elapsed_ms,
            http_status=response.status_code,
            app_status=app_status,
            response_bytes=len(response.content),
            error=None if ok else _status_error(case, response, app_status),
        )
    except (httpx.HTTPError, ValueError) as exc:
        return ApiMeasurement(
            case_id=case.case_id,
            group=case.group,
            sql_name=case.sql_name,
            concurrency=concurrency,
            iteration=iteration,
            warmup=warmup,
            ok=False,
            elapsed_ms=round((time.perf_counter() - start) * 1000, 3),
            http_status=None,
            app_status=None,
            response_bytes=0,
            error=str(exc),
        )


def _api_case_for_corpus(case: CorpusCase) -> ApiCase | None:
    params = case.params
    if case.sql_name in {"road_exact", "road_exact_sig"}:
        return _api_case(
            case,
            "geocode_road_hint" if case.sql_name == "road_exact_sig" else "geocode_road",
            "/v1/address/geocode",
            {
                "address": _road_address(params),
                "type": "road",
                "fallback": "local_only",
                **_api_region_hint_params(params),
            },
        )
    if case.sql_name in {"parcel_exact", "parcel_exact_bjd"}:
        return _api_case(
            case,
            "geocode_parcel_hint" if case.sql_name == "parcel_exact_bjd" else "geocode_parcel",
            "/v1/address/geocode",
            {
                "address": _parcel_address(params),
                "type": "parcel",
                "fallback": "local_only",
                **_api_region_hint_params(params),
            },
        )
    if case.sql_name in {"fuzzy_geocode", "fuzzy_geocode_wide", "fuzzy_geocode_sig"}:
        return _api_case(
            case,
            "geocode_fuzzy_hint" if case.sql_name == "fuzzy_geocode_sig" else "geocode_fuzzy",
            "/v1/address/geocode",
            {
                "address": _fuzzy_address(params),
                "type": "road",
                "fallback": "local_only",
                **_api_region_hint_params(params),
            },
            expected_status=None,
        )
    if case.sql_name in {"search", "search_sig", "search_fuzzy"}:
        api_sql_name = {
            "search": "search",
            "search_sig": "search_hint",
            "search_fuzzy": "search_fuzzy",
        }[case.sql_name]
        return _api_case(
            case,
            api_sql_name,
            "/v1/address/search",
            {
                "query": str(params["query"]),
                "type": "address",
                "page": 1,
                "size": int(cast("int", params["limit"])),
                **_api_region_hint_params(params),
            },
        )
    if case.sql_name == "no_result_reverse":
        return None
    if case.sql_name in {
        "reverse_nearest",
        "reverse_nearest_sig",
        "reverse_radius",
        "reverse_radius_sig",
        "sppn_reverse",
    }:
        return _api_case(
            case,
            f"reverse_{case.sql_name}",
            "/v1/address/reverse",
            {
                "x": cast("float", params["x"]),
                "y": cast("float", params["y"]),
                "crs": "EPSG:4326",
                "type": "both",
                "radius_m": int(cast("int", params.get("radius_m") or 200)),
                **_api_region_hint_params(params),
            },
            expected_status=case.expected_status,
        )
    if case.sql_name == "zipcode_address":
        return _api_case(
            case,
            "zipcode_address",
            "/v1/address/zipcode",
            {
                "address": _zipcode_address(params),
                "include_bulk": True,
            },
        )
    if case.sql_name == "zipcode_point":
        return _api_case(
            case,
            "zipcode_point",
            "/v1/address/zipcode",
            {
                "x": cast("float", params["x"]),
                "y": cast("float", params["y"]),
                "include_bulk": True,
            },
        )
    if case.sql_name == "no_result_road":
        return _api_case(
            case,
            "geocode_no_result_road",
            "/v1/address/geocode",
            {
                "address": f"없는도로 {int(cast('int', params['mnnm']))}",
                "type": "road",
                "fallback": "local_only",
            },
            expected_status="NOT_FOUND",
        )
    return None


def _api_case(
    case: CorpusCase,
    sql_name: str,
    path: str,
    params: Params,
    *,
    expected_status: str | None = "OK",
) -> ApiCase:
    return ApiCase(
        case_id=case.case_id,
        group=case.group,
        sql_name=sql_name,
        method="GET",
        path=path,
        params=params,
        label=case.label,
        source_case_id=case.case_id,
        expected_status=expected_status,
    )


def _road_address(params: Mapping[str, ParamValue]) -> str:
    parts = [
        str(params["si"]) if params.get("si") else None,
        str(params["sgg"]) if params.get("sgg") else None,
        "지하" if params.get("buld_se_cd") == "1" else None,
        str(params["road_nrm"]),
        _number(params["mnnm"], params.get("slno")),
    ]
    return _join(parts)


def _parcel_address(params: Mapping[str, ParamValue]) -> str:
    parts = [
        str(params["si"]) if params.get("si") else None,
        str(params["sgg"]) if params.get("sgg") else None,
        str(params["emd"]) if params.get("emd") else None,
        "산" if str(params.get("mntn_yn")) == "1" else None,
        _number(params["mnnm"], params.get("slno")),
    ]
    return _join(parts)


def _zipcode_address(params: Mapping[str, ParamValue]) -> str:
    parts = [
        str(params["emd"]) if params.get("emd") else None,
        str(params["road_nrm"]),
        _number(params["mnnm"], 0),
    ]
    return _join(parts)


def _fuzzy_address(params: Mapping[str, ParamValue]) -> str:
    road = str(params["road_nrm"])
    if road.endswith("대로"):
        mutated = f"{road[:-2]}로"
    elif road.endswith("로"):
        mutated = f"{road[:-1]}길"
    elif road.endswith("길"):
        mutated = f"{road[:-1]}로"
    else:
        mutated = f"{road}길"
    parts = [
        str(params["si"]) if params.get("si") else None,
        str(params["sgg"]) if params.get("sgg") else None,
        mutated,
        _number(params["mnnm"], params.get("slno")),
    ]
    return _join(parts)


def _api_region_hint_params(params: Mapping[str, ParamValue]) -> dict[str, str]:
    hints: dict[str, str] = {}
    sig_cd = params.get("sig_cd_filter") or params.get("sig_cd_prefix")
    if isinstance(sig_cd, str) and sig_cd:
        hints["sig_cd"] = sig_cd.rstrip("%")
    bjd_cd = params.get("bjd_cd_filter") or params.get("bjd_cd_prefix")
    if isinstance(bjd_cd, str) and bjd_cd:
        hints["bjd_cd"] = bjd_cd.rstrip("%")
    return hints


def _number(main: ParamValue, sub: ParamValue) -> str:
    main_value = int(cast("int", main))
    sub_value = int(cast("int", sub or 0))
    return str(main_value) if sub_value == 0 else f"{main_value}-{sub_value}"


def _join(parts: Sequence[str | None]) -> str:
    return " ".join(part for part in parts if part)


def _response_app_status(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("status"), str):
        return str(data["status"])
    if isinstance(data, dict) and isinstance(data.get("response"), dict):
        nested = data["response"]
        if isinstance(nested.get("status"), str):
            return str(nested["status"])
    return None


def _status_error(case: ApiCase, response: httpx.Response, app_status: str | None) -> str:
    expected = case.expected_status or "any"
    return f"http={response.status_code}, app_status={app_status}, expected={expected}"


def _round_optional(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _md_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    return datetime.now(UTC).strftime("t047-api-%Y%m%d-%H%M%S")


async def _amain(args: argparse.Namespace) -> None:
    if args.max_cases_per_sql is not None and args.max_cases_per_sql < 1:
        msg = "--max-cases-per-sql must be at least 1"
        raise ValueError(msg)
    run_id = args.run_id or _run_id()
    output_dir = args.output_dir or Path("artifacts") / "perf" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus_cases = load_corpus(args.corpus)
    api_cases = build_api_cases(corpus_cases, max_cases_per_sql=args.max_cases_per_sql)
    started_at = datetime.now(UTC).isoformat()
    environment = ApiEnvironment(
        run_id=run_id,
        started_at=started_at,
        git_commit=_git_output("rev-parse", "HEAD"),
        git_branch=_git_output("branch", "--show-current"),
        python_version=platform.python_version(),
        platform=platform.platform(),
        base_url=args.base_url.rstrip("/"),
        corpus_path=str(args.corpus),
        corpus_sha256=_hash_file(args.corpus),
        case_count=len(api_cases),
    )
    (output_dir / "api-cases.json").write_text(
        json.dumps([asdict(case) for case in api_cases], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    async with httpx.AsyncClient(
        base_url=environment.base_url,
        timeout=httpx.Timeout(args.timeout_s),
    ) as client:
        report = await run_benchmark(
            client,
            api_cases,
            run_id=run_id,
            environment=environment,
            concurrency_levels=tuple(args.concurrency or [1]),
            iterations=args.iterations,
            warmup=args.warmup,
        )
    (output_dir / "benchmark.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "environment.json").write_text(
        json.dumps(asdict(environment), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_summary_markdown(report, output_dir / "summary.md")
    print(output_dir)


def main() -> None:
    asyncio.run(_amain(build_parser().parse_args()))


if __name__ == "__main__":
    main()
