"""Run or plan the T-162 runtime warm pass."""

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
from kortravelgeo.loaders.runtime_warm import (  # noqa: E402
    DEFAULT_RUNTIME_WARM_PREWARM_RELATIONS,
    DEFAULT_RUNTIME_WARM_QUERY_LIMIT,
    DEFAULT_RUNTIME_WARM_STATEMENT_TIMEOUT_MS,
    run_runtime_warm,
    runtime_warm_report_metrics,
    runtime_warm_report_to_dict,
)
from kortravelgeo.settings import get_settings  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="T-162 runtime cache/buffer warm plan/report.",
    )
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    parser.add_argument(
        "--mode",
        choices=("plan", "execute"),
        default="plan",
        help="plan is offline; execute runs bounded read-only warm queries.",
    )
    parser.add_argument(
        "--query-limit",
        type=int,
        help=f"Representative warm probe limit. Default {DEFAULT_RUNTIME_WARM_QUERY_LIMIT}.",
    )
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        help=(
            "Transaction-local statement timeout for warm probes. "
            f"Default {DEFAULT_RUNTIME_WARM_STATEMENT_TIMEOUT_MS}."
        ),
    )
    parser.add_argument(
        "--prewarm",
        dest="prewarm_enabled",
        action="store_true",
        default=None,
        help="Enable optional pg_prewarm pass for configured relations.",
    )
    parser.add_argument(
        "--no-prewarm",
        dest="prewarm_enabled",
        action="store_false",
        help="Disable optional pg_prewarm pass even if the environment enables it.",
    )
    parser.add_argument(
        "--prewarm-relations",
        help=(
            "Comma-separated pg_prewarm relation list. Default uses "
            "KTG_RUNTIME_WARM_PREWARM_RELATIONS or built-in serving relations."
        ),
    )
    parser.add_argument(
        "--connect-timeout-s",
        type=int,
        default=10,
        help="PostgreSQL connection timeout for execute runs.",
    )
    parser.add_argument(
        "--register-artifact",
        action="store_true",
        help="Register the report as an ops benchmark artifact. Requires --output.",
    )
    parser.add_argument("--display-name", default="T-162 runtime warm report")
    parser.add_argument("--run-id", help="Artifact run id. Default uses UTC timestamp.")
    parser.add_argument("--notes", help="Optional artifact notes.")
    return parser


async def _async_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.register_artifact and args.output is None:
        raise SystemExit("--register-artifact requires --output")
    settings = get_settings()
    prewarm_enabled = (
        settings.runtime_warm_prewarm_enabled
        if args.prewarm_enabled is None
        else bool(args.prewarm_enabled)
    )
    prewarm_relations = (
        _parse_csv(args.prewarm_relations)
        if args.prewarm_relations is not None
        else settings.runtime_warm_prewarm_relations
        or DEFAULT_RUNTIME_WARM_PREWARM_RELATIONS
    )
    query_limit = args.query_limit or settings.runtime_warm_query_limit
    statement_timeout_ms = (
        args.statement_timeout_ms or settings.runtime_warm_statement_timeout_ms
    )

    if args.mode == "plan":
        report = await run_runtime_warm(
            _PlanModeEngine(),
            mode="plan",
            prewarm_enabled=prewarm_enabled,
            prewarm_relations=prewarm_relations,
            query_limit=query_limit,
            statement_timeout_ms=statement_timeout_ms,
        )
    else:
        engine = make_async_engine(
            settings,
            connect_args={"connect_timeout": args.connect_timeout_s},
        )
        try:
            report = await run_runtime_warm(
                engine,
                mode="execute",
                prewarm_enabled=prewarm_enabled,
                prewarm_relations=prewarm_relations,
                query_limit=query_limit,
                statement_timeout_ms=statement_timeout_ms,
            )
        finally:
            await engine.dispose()

    payload = json.dumps(runtime_warm_report_to_dict(report), ensure_ascii=False, indent=2)
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
    metrics = runtime_warm_report_metrics(report)
    run_id = args.run_id or datetime.now(UTC).strftime("t162-%Y%m%dT%H%M%SZ")
    async with AsyncAddressClient() as client:
        await client.register_benchmark_artifact(
            BenchmarkArtifactRegisterRequest(
                run_id=run_id,
                kind="other",
                display_name=args.display_name,
                profile=(
                    "runtime-warm/prewarm"
                    if report.settings["prewarm_enabled"]
                    else "runtime-warm/query"
                ),
                workload="runtime_warm",
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


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


class _PlanModeEngine:
    """Sentinel object; plan mode never opens a database connection."""


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_async_main(argv), loop_factory=_event_loop_factory)


def _event_loop_factory() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


if __name__ == "__main__":
    raise SystemExit(main())
