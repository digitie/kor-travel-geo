"""T-122 phase-1 augmentation performance benchmark.

이 스크립트는 T-121 전국 실행 runner를 재사용해 C11~C17 보강 검증 harness의
wall-time, runner process RSS, 로컬 process I/O를 case별 artifact로 기록한다.
DB 서버 I/O와 PostgreSQL 내부 메모리는 측정 범위에 포함하지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kortravelgeo.infra.engine import make_async_engine  # noqa: E402
from kortravelgeo.loaders.augment_harness import SIDO_NAMES  # noqa: E402
from kortravelgeo.settings import get_settings  # noqa: E402
from scripts.run_phase1_augment_reports import (  # noqa: E402
    ALL_CASES,
    CaseId,
    SourceInput,
    build_source_plan,
    ensure_output_dir,
    run_phase1_case,
    write_report_json,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncEngine

BENCHMARK_SCHEMA_VERSION = 1
# Keep this order stable because benchmark JSON and Markdown emit deltas in this sequence.
PROC_IO_FIELDS = (
    "rchar",
    "wchar",
    "syscr",
    "syscw",
    "read_bytes",
    "write_bytes",
    "cancelled_write_bytes",
)
SAMPLER_STOP_TIMEOUT_S = 5.0
PhaseId = Literal["preparation", "C11", "C12", "C13", "C14", "C15", "C16", "C17"]


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    rss_bytes: int | None
    rss_hwm_bytes: int | None
    proc_io: Mapping[str, int | None]
    child_max_rss_bytes: int | None
    child_inblock: int | None
    child_oublock: int | None


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    started: ResourceSnapshot
    finished: ResourceSnapshot
    rss_peak_bytes: int | None
    proc_io_delta: Mapping[str, int | None]
    child_inblock_delta: int | None
    child_oublock_delta: int | None


@dataclass(frozen=True, slots=True)
class PreparationBenchmark:
    phase_id: Literal["preparation"]
    seconds: float
    resource: ResourceUsage
    sources_by_case: Mapping[str, tuple[SourceInput, ...]]


@dataclass(frozen=True, slots=True)
class CaseBenchmark:
    phase_id: CaseId
    task_id: str
    output_path: str
    seconds: float
    resource: ResourceUsage
    report_summary: Mapping[str, object]
    sources: tuple[SourceInput, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    schema_version: int
    run_id: str
    started_at: str
    finished_at: str
    total_seconds: float
    data_root: str
    output_dir: str
    git_commit: str | None
    git_branch: str | None
    sample_interval_s: float
    measurement_scope: str
    preparation: PreparationBenchmark
    cases: tuple[CaseBenchmark, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark C11-C17 phase-1 augmentation harness performance.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/juso"),
        help="도로명주소 실제 원천 root. 기본값은 data/juso.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact output directory. 기본값은 artifacts/perf/t122-phase1-<run-id>.",
    )
    parser.add_argument("--run-id", help="Stable run id. Defaults to timestamp.")
    parser.add_argument(
        "--case",
        action="append",
        choices=ALL_CASES,
        dest="cases",
        help="실행할 case. 여러 번 지정 가능하며 생략하면 C11~C17 전체를 실행한다.",
    )
    parser.add_argument(
        "--sido",
        action="append",
        help="C11~C13에서 실행할 시도명. 여러 번 지정 가능하며 생략하면 17개 시도 전체.",
    )
    parser.add_argument("--pg-dsn", help="PostgreSQL DSN. 생략하면 KTG_PG_DSN/.env를 사용한다.")
    parser.add_argument(
        "--pg-statement-timeout-ms",
        type=int,
        default=600_000,
        help="리포트 측정용 PostgreSQL statement_timeout. 기본값은 600000ms.",
    )
    parser.add_argument("--sample-limit", type=int, default=20, help="각 metric sample 개수.")
    parser.add_argument("--c12-tolerance-m", type=float, default=1.0)
    parser.add_argument("--c15-outlier-threshold-m", type=float, default=100.0)
    parser.add_argument("--c14-row-limit-per-layer", type=int)
    parser.add_argument("--c14-center-row-limit", type=int)
    parser.add_argument("--c15-row-limit", type=int)
    parser.add_argument("--c16-limit-per-member", type=int)
    parser.add_argument("--c17-limit-per-member", type=int)
    parser.add_argument(
        "--materialize-electronic-map",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="전자지도 시도별 ZIP materialization을 준비 단계에 포함한다.",
    )
    parser.add_argument(
        "--materialize-navi-7z",
        action="store_true",
        help="C17 입력이 .7z뿐이면 준비 단계에서 match_jibun_*.txt를 materialize한다.",
    )
    parser.add_argument(
        "--sample-interval-s",
        type=float,
        default=1.0,
        help="RSS peak sampling interval. 0이면 start/end만 기록한다.",
    )
    parser.add_argument(
        "--git-repo",
        type=Path,
        help="Git metadata를 기록할 repo path. WSL 미러에서는 F:/dev/... NTFS 경로 권장.",
    )
    parser.add_argument(
        "--allow-without-slow-real-data",
        action="store_true",
        help="KTG_SLOW_REAL_DATA=1 없이도 실행한다. 단위 smoke 외에는 사용하지 않는다.",
    )
    return parser


async def run_phase1_augment_benchmark(
    *,
    data_root: Path,
    output_dir: Path,
    cases: Sequence[CaseId] = ALL_CASES,
    sido_names: Sequence[str] | None = None,
    engine: AsyncEngine,
    sample_limit: int = 20,
    c12_tolerance_m: float = 1.0,
    c15_outlier_threshold_m: float = 100.0,
    c14_row_limit_per_layer: int | None = None,
    c14_center_row_limit: int | None = None,
    c15_row_limit: int | None = None,
    c16_limit_per_member: int | None = None,
    c17_limit_per_member: int | None = None,
    materialize_electronic_map: bool = True,
    materialize_navi_7z: bool = False,
    sample_interval_s: float = 1.0,
    git_repo: Path | None = None,
    run_id: str | None = None,
) -> BenchmarkSummary:
    started = datetime.now(UTC)
    started_clock = time.perf_counter()
    resolved_run_id = run_id or started.strftime("%Y%m%dT%H%M%SZ")
    ensure_output_dir(output_dir)
    selected_sidos = tuple(sido_names or SIDO_NAMES)

    print("[preparation] 벤치 시작", flush=True)
    prep_started = time.perf_counter()
    with ResourceSampler(sample_interval_s) as prep_sampler:
        source_plan = build_source_plan(
            data_root,
            output_dir=output_dir,
            sido_names=selected_sidos,
            materialize_electronic_map=materialize_electronic_map,
            materialize_navi_7z=materialize_navi_7z,
        )
    preparation = PreparationBenchmark(
        phase_id="preparation",
        seconds=round(time.perf_counter() - prep_started, 3),
        resource=prep_sampler.usage(),
        sources_by_case={case_id: source_plan.case_sources(case_id) for case_id in cases},
    )
    print("[preparation] 벤치 완료", flush=True)

    report_dir = output_dir / "reports"
    case_runs: list[CaseBenchmark] = []
    for case_id in cases:
        print(f"[{case_id}] 벤치 시작", flush=True)
        case_started = time.perf_counter()
        with ResourceSampler(sample_interval_s) as case_sampler:
            report = await run_phase1_case(
                case_id,
                engine=engine,
                source_plan=source_plan,
                sido_names=selected_sidos,
                sample_limit=sample_limit,
                c12_tolerance_m=c12_tolerance_m,
                c15_outlier_threshold_m=c15_outlier_threshold_m,
                c14_row_limit_per_layer=c14_row_limit_per_layer,
                c14_center_row_limit=c14_center_row_limit,
                c15_row_limit=c15_row_limit,
                c16_limit_per_member=c16_limit_per_member,
                c17_limit_per_member=c17_limit_per_member,
            )
        output_path = report_dir / f"{case_id.lower()}-{report.task_id.lower()}.json"
        write_report_json(report, output_path)
        case_run = CaseBenchmark(
            phase_id=case_id,
            task_id=report.task_id,
            output_path=str(output_path),
            seconds=round(time.perf_counter() - case_started, 3),
            resource=case_sampler.usage(),
            report_summary=report.summary(),
            sources=source_plan.case_sources(case_id),
        )
        case_runs.append(case_run)
        print(f"[{case_id}] 벤치 완료: {case_run.report_summary}", flush=True)

    finished = datetime.now(UTC)
    summary = BenchmarkSummary(
        schema_version=BENCHMARK_SCHEMA_VERSION,
        run_id=resolved_run_id,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        total_seconds=round(time.perf_counter() - started_clock, 3),
        data_root=str(data_root),
        output_dir=str(output_dir),
        git_commit=_git_value(git_repo, "rev-parse", "HEAD"),
        git_branch=_git_value(git_repo, "branch", "--show-current"),
        sample_interval_s=sample_interval_s,
        measurement_scope=(
            "runner process RSS and /proc/self/io; child process block I/O when "
            "resource.RUSAGE_CHILDREN is available; PostgreSQL server I/O excluded"
        ),
        preparation=preparation,
        cases=tuple(case_runs),
    )
    write_benchmark(summary, output_dir)
    return summary


class ResourceSampler:
    def __init__(self, interval_s: float = 1.0) -> None:
        if interval_s < 0:
            msg = "--sample-interval-s must be >= 0"
            raise ValueError(msg)
        self._interval_s = interval_s
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._peak_rss_bytes: int | None = None
        self._started: ResourceSnapshot | None = None
        self._finished: ResourceSnapshot | None = None

    def __enter__(self) -> ResourceSampler:
        self._started = read_resource_snapshot()
        self._observe(self._started)
        if self._interval_s > 0:
            self._thread = threading.Thread(
                target=self._sample_loop,
                name="ktg-t122-resource-sampler",
                daemon=True,
            )
            self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            # The sampler is daemon-backed, but give slow filesystems/runtimes room to stop cleanly.
            self._thread.join(timeout=max(SAMPLER_STOP_TIMEOUT_S, self._interval_s * 4))
        self._finished = read_resource_snapshot()
        self._observe(self._finished)

    def usage(self) -> ResourceUsage:
        if self._started is None or self._finished is None:
            msg = "ResourceSampler.usage() called before sampler finished"
            raise RuntimeError(msg)
        return ResourceUsage(
            started=self._started,
            finished=self._finished,
            rss_peak_bytes=self._peak_rss_bytes,
            proc_io_delta=diff_proc_io(self._started.proc_io, self._finished.proc_io),
            child_inblock_delta=optional_delta(
                self._started.child_inblock,
                self._finished.child_inblock,
            ),
            child_oublock_delta=optional_delta(
                self._started.child_oublock,
                self._finished.child_oublock,
            ),
        )

    def _sample_loop(self) -> None:
        while not self._stop.wait(self._interval_s):
            self._observe(read_resource_snapshot())

    def _observe(self, snapshot: ResourceSnapshot) -> None:
        if snapshot.rss_bytes is None:
            return
        with self._lock:
            if self._peak_rss_bytes is None or snapshot.rss_bytes > self._peak_rss_bytes:
                self._peak_rss_bytes = snapshot.rss_bytes


def read_resource_snapshot(proc_root: Path = Path("/proc/self")) -> ResourceSnapshot:
    rss_bytes: int | None = None
    rss_hwm_bytes: int | None = None
    status_path = proc_root / "status"
    if status_path.exists():
        rss_bytes, rss_hwm_bytes = parse_proc_status(status_path.read_text(encoding="utf-8"))

    proc_io: Mapping[str, int | None] = dict.fromkeys(PROC_IO_FIELDS)
    io_path = proc_root / "io"
    if io_path.exists():
        proc_io = parse_proc_io(io_path.read_text(encoding="utf-8"))

    child_max_rss_bytes, child_inblock, child_oublock = child_resource_snapshot()
    return ResourceSnapshot(
        rss_bytes=rss_bytes,
        rss_hwm_bytes=rss_hwm_bytes,
        proc_io=proc_io,
        child_max_rss_bytes=child_max_rss_bytes,
        child_inblock=child_inblock,
        child_oublock=child_oublock,
    )


def parse_proc_status(text: str) -> tuple[int | None, int | None]:
    rss_bytes: int | None = None
    rss_hwm_bytes: int | None = None
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key == "VmRSS":
            rss_bytes = parse_kb_value(value)
        elif key == "VmHWM":
            rss_hwm_bytes = parse_kb_value(value)
    return rss_bytes, rss_hwm_bytes


def parse_kb_value(value: str) -> int | None:
    parts = value.strip().split()
    if not parts:
        return None
    try:
        amount = int(parts[0])
    except ValueError:
        return None
    unit = parts[1] if len(parts) > 1 else "kB"
    if unit != "kB":
        return None
    return amount * 1024


def parse_proc_io(text: str) -> dict[str, int | None]:
    values: dict[str, int | None] = dict.fromkeys(PROC_IO_FIELDS)
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key not in values:
            continue
        try:
            values[key] = int(value.strip())
        except ValueError:
            values[key] = None
    return values


def child_resource_snapshot() -> tuple[int | None, int | None, int | None]:
    try:
        resource_module = importlib.import_module("resource")
    except ImportError:
        return None, None, None
    getrusage = getattr(resource_module, "getrusage", None)
    children = getattr(resource_module, "RUSAGE_CHILDREN", None)
    if getrusage is None or children is None:
        return None, None, None
    usage = getrusage(children)
    return (
        int(usage.ru_maxrss) * 1024,
        int(usage.ru_inblock),
        int(usage.ru_oublock),
    )


def optional_delta(start: int | None, finish: int | None) -> int | None:
    if start is None or finish is None:
        return None
    return finish - start


def diff_proc_io(
    started: Mapping[str, int | None],
    finished: Mapping[str, int | None],
) -> dict[str, int | None]:
    return {
        field: optional_delta(started.get(field), finished.get(field))
        for field in PROC_IO_FIELDS
    }


def write_benchmark(summary: BenchmarkSummary, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark.json").write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(benchmark_markdown(summary), encoding="utf-8")


def benchmark_markdown(summary: BenchmarkSummary) -> str:
    lines = [
        "# T-122 phase 1 보강 성능 벤치",
        "",
        f"- run_id: `{summary.run_id}`",
        f"- data_root: `{summary.data_root}`",
        f"- git_commit: `{summary.git_commit or 'unknown'}`",
        f"- total_seconds: `{summary.total_seconds}`",
        f"- measurement_scope: `{summary.measurement_scope}`",
        "",
    ]
    rows = [
        benchmark_row(
            phase="preparation",
            task="source-plan",
            used=None,
            failed=None,
            seconds=summary.preparation.seconds,
            resource=summary.preparation.resource,
            artifact=None,
        )
    ]
    for case in summary.cases:
        report_summary = case.report_summary
        rows.append(
            benchmark_row(
                phase=case.phase_id,
                task=case.task_id,
                used=as_int(report_summary.get("used")),
                failed=as_int(report_summary.get("failed")),
                seconds=case.seconds,
                resource=case.resource,
                artifact=case.output_path,
            )
        )
    lines.extend(
        markdown_table(
            headers=(
                "phase",
                "task",
                "used",
                "failed",
                "seconds",
                "peak RSS",
                "rchar",
                "read bytes",
                "wchar",
                "write bytes",
                "artifact",
            ),
            alignments=(
                "-------",
                "------",
                "-----:",
                "-------:",
                "--------:",
                "---------:",
                "------:",
                "-----------:",
                "------:",
                "------------:",
                "----------",
            ),
            rows=rows,
        )
    )
    lines.append("")
    return "\n".join(lines)


def benchmark_row(
    *,
    phase: str,
    task: str,
    used: int | None,
    failed: int | None,
    seconds: float,
    resource: ResourceUsage,
    artifact: str | None,
) -> tuple[str, ...]:
    io_delta = resource.proc_io_delta
    return (
        phase,
        task,
        md_count(used),
        md_count(failed),
        f"{seconds:.3f}",
        human_bytes(resource.rss_peak_bytes),
        human_bytes(io_delta.get("rchar")),
        human_bytes(io_delta.get("read_bytes")),
        human_bytes(io_delta.get("wchar")),
        human_bytes(io_delta.get("write_bytes")),
        "n/a" if artifact is None else f"`{artifact}`",
    )


def markdown_table(
    *,
    headers: Sequence[str],
    alignments: Sequence[str],
    rows: Iterable[Sequence[str]],
) -> list[str]:
    if len(headers) != len(alignments):
        msg = "markdown table headers and alignments must have the same length"
        raise ValueError(msg)
    lines = [markdown_row(headers), markdown_row(alignments, escape=False)]
    for row in rows:
        if len(row) != len(headers):
            msg = "markdown table row has unexpected column count"
            raise ValueError(msg)
        lines.append(markdown_row(row))
    return lines


def markdown_row(cells: Sequence[str], *, escape: bool = True) -> str:
    rendered = [cell.replace("|", r"\|") if escape else cell for cell in cells]
    return "| " + " | ".join(rendered) + " |"


def human_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    scaled = float(abs(value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if scaled < 1024 or unit == "TiB":
            if unit == "B":
                return f"{sign}{int(scaled)} {unit}"
            return f"{sign}{scaled:.1f} {unit}"
        scaled /= 1024
    return f"{sign}{scaled:.1f} TiB"


def md_count(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def as_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except ValueError:
        return None


def _git_value(git_repo: Path | None, *args: str) -> str | None:
    if git_repo is None:
        return None
    import subprocess

    for git_cmd in ("git.exe", "git"):
        proc = subprocess.run(
            [git_cmd, "-C", str(git_repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    return None


def _parse_cases(values: Iterable[str] | None) -> tuple[CaseId, ...]:
    if values is None:
        return ALL_CASES
    return cast("tuple[CaseId, ...]", tuple(values))


async def _main_async(args: argparse.Namespace) -> None:
    if os.environ.get("KTG_SLOW_REAL_DATA") != "1" and not args.allow_without_slow_real_data:
        msg = "T-122 benchmark requires KTG_SLOW_REAL_DATA=1"
        raise RuntimeError(msg)
    run_id = args.run_id or datetime.now(UTC).strftime("t122-phase1-%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or Path("artifacts") / "perf" / run_id
    settings = get_settings()
    settings_update: dict[str, object] = {
        "pg_statement_timeout_ms": args.pg_statement_timeout_ms,
    }
    if args.pg_dsn:
        settings_update["pg_dsn"] = args.pg_dsn
    settings = settings.model_copy(update=settings_update)
    engine = make_async_engine(settings)
    try:
        await run_phase1_augment_benchmark(
            data_root=args.data_root,
            output_dir=output_dir,
            cases=_parse_cases(args.cases),
            sido_names=tuple(args.sido) if args.sido else None,
            engine=engine,
            sample_limit=args.sample_limit,
            c12_tolerance_m=args.c12_tolerance_m,
            c15_outlier_threshold_m=args.c15_outlier_threshold_m,
            c14_row_limit_per_layer=args.c14_row_limit_per_layer,
            c14_center_row_limit=args.c14_center_row_limit,
            c15_row_limit=args.c15_row_limit,
            c16_limit_per_member=args.c16_limit_per_member,
            c17_limit_per_member=args.c17_limit_per_member,
            materialize_electronic_map=args.materialize_electronic_map,
            materialize_navi_7z=args.materialize_navi_7z,
            sample_interval_s=args.sample_interval_s,
            git_repo=args.git_repo,
            run_id=run_id,
        )
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_main_async(build_parser().parse_args()))


if __name__ == "__main__":
    main()
