"""Run or plan the T-146 post-load read-optimized maintenance pipeline."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import selectors
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kortravelgeo.client import AsyncAddressClient  # noqa: E402
from kortravelgeo.dto.admin import BenchmarkArtifactRegisterRequest, BenchmarkMetrics  # noqa: E402
from kortravelgeo.infra.engine import make_async_engine  # noqa: E402
from kortravelgeo.loaders.postload_maintenance import (  # noqa: E402
    DEFAULT_DEAD_TUPLE_RATIO_WARN,
    DEFAULT_INDEX_BUDGET_BYTES,
    maintenance_report_metrics,
    maintenance_report_to_dict,
    run_postload_maintenance,
)
from kortravelgeo.settings import get_settings  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="T-146 post-load read-optimized maintenance plan/report.",
    )
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    parser.add_argument(
        "--mode",
        choices=("plan", "execute-safe"),
        default="plan",
        help="plan is read-only; execute-safe runs selected automated maintenance.",
    )
    parser.add_argument(
        "--strategy",
        choices=("concurrent", "swap"),
        default="swap",
        help="MV refresh strategy recorded or executed.",
    )
    parser.add_argument(
        "--vacuum-analyze",
        action="store_true",
        help="In execute-safe mode, run VACUUM (ANALYZE) on source relations.",
    )
    parser.add_argument(
        "--no-table-stats-capture",
        action="store_true",
        help="Skip ops.table_stats_snapshots insert in execute-safe mode.",
    )
    parser.add_argument(
        "--index-budget-gib",
        type=float,
        default=DEFAULT_INDEX_BUDGET_BYTES / (1024**3),
        help="Advisory total index footprint budget for warnings.",
    )
    parser.add_argument(
        "--dead-tuple-ratio-warn",
        type=float,
        default=DEFAULT_DEAD_TUPLE_RATIO_WARN,
        help="Dead tuple ratio warning threshold.",
    )
    parser.add_argument(
        "--dead-tuple-count-warn",
        type=int,
        default=100_000,
        help="Minimum dead tuple count before ratio warning is emitted.",
    )
    parser.add_argument(
        "--connect-timeout-s",
        type=int,
        default=10,
        help="PostgreSQL connection timeout for plan/report runs.",
    )
    parser.add_argument(
        "--register-artifact",
        action="store_true",
        help="Register the report as an ops benchmark artifact. Requires --output.",
    )
    parser.add_argument("--display-name", default="T-146 post-load maintenance report")
    parser.add_argument("--run-id", help="Artifact run id. Default uses UTC timestamp.")
    parser.add_argument("--notes", help="Optional artifact notes.")
    return parser


async def _async_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.register_artifact and args.output is None:
        raise SystemExit("--register-artifact requires --output")
    settings = get_settings()
    engine = make_async_engine(settings, connect_args={"connect_timeout": args.connect_timeout_s})
    try:
        report = await run_postload_maintenance(
            engine,
            mode="execute_safe" if args.mode == "execute-safe" else "plan",
            strategy=args.strategy,
            vacuum_analyze=args.vacuum_analyze,
            capture_stats=not args.no_table_stats_capture,
            index_budget_bytes=int(args.index_budget_gib * 1024 * 1024 * 1024),
            dead_tuple_ratio_warn=args.dead_tuple_ratio_warn,
            dead_tuple_count_warn=args.dead_tuple_count_warn,
        )
    finally:
        await engine.dispose()
    payload = json.dumps(maintenance_report_to_dict(report), ensure_ascii=False, indent=2)
    output_path: Path | None = args.output
    if output_path is not None:
        await asyncio.to_thread(output_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(output_path.write_text, payload + "\n", encoding="utf-8")
    print(payload)
    if args.register_artifact:
        assert output_path is not None
        await _register_artifact(args, output_path, report)
    return 0


async def _register_artifact(args: argparse.Namespace, output_path: Path, report: Any) -> None:
    content = await asyncio.to_thread(output_path.read_bytes)
    digest = hashlib.sha256(content).hexdigest()
    stat = await asyncio.to_thread(output_path.stat)
    metrics = maintenance_report_metrics(report)
    run_id = args.run_id or datetime.now(UTC).strftime("t146-%Y%m%dT%H%M%SZ")
    async with AsyncAddressClient() as client:
        await client.register_benchmark_artifact(
            BenchmarkArtifactRegisterRequest(
                run_id=run_id,
                kind="other",
                display_name=args.display_name,
                profile=f"postload-maintenance/{report.strategy}",
                workload="postload_maintenance",
                phase=report.mode,
                metrics=BenchmarkMetrics(
                    samples=int(metrics["samples"]),
                    error_count=int(metrics["error_count"]),
                    error_rate=float(metrics["error_rate"]),
                    max_ms=float(metrics["max_ms"]),
                ),
                storage_uri=str(output_path),
                size_bytes=stat.st_size,
                sha256=digest,
                captured_at=datetime.now(UTC),
                notes=args.notes,
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_async_main(argv), loop_factory=_event_loop_factory)


def _event_loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


if __name__ == "__main__":
    raise SystemExit(main())
