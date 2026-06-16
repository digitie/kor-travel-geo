"""Evaluate T-162 cold-start p99 against a warmed REST benchmark run."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


RATIO_REPORT_SCHEMA_VERSION = 1
SummaryKey = tuple[str, str, int]


@dataclass(frozen=True, slots=True)
class ColdWarmComparison:
    group: str
    sql_name: str
    concurrency: int
    cold_p99_ms: float | None
    warm_p99_ms: float | None
    ratio: float | None
    threshold_ms: float | None
    cold_errors: int
    warm_errors: int | None
    passed: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class ColdWarmRatioReport:
    schema_version: int
    task_id: str
    cold_report: str
    warm_report: str
    max_ratio: float
    absolute_slack_ms: float
    passed: bool
    comparisons: tuple[ColdWarmComparison, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare post-restart cold REST p99 with warmed REST p99.",
    )
    parser.add_argument("--cold-report", type=Path, required=True)
    parser.add_argument("--warm-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Write JSON gate report to this path.")
    parser.add_argument(
        "--max-ratio",
        type=float,
        default=2.0,
        help="Cold p99 must be <= warm p99 * max_ratio + absolute slack.",
    )
    parser.add_argument(
        "--absolute-slack-ms",
        type=float,
        default=25.0,
        help="Small absolute slack added to the ratio threshold.",
    )
    parser.add_argument(
        "--mode",
        choices=("report", "enforce"),
        default="report",
        help="enforce exits 2 when the gate fails.",
    )
    return parser


def evaluate_cold_warm_ratio(
    *,
    cold_payload: Mapping[str, Any],
    warm_payload: Mapping[str, Any],
    cold_report: str,
    warm_report: str,
    max_ratio: float = 2.0,
    absolute_slack_ms: float = 25.0,
) -> ColdWarmRatioReport:
    cold_rows = _summary_rows(cold_payload)
    warm_rows = {_summary_key(row): row for row in _summary_rows(warm_payload)}
    comparisons = tuple(
        _compare_row(
            cold_row,
            warm_rows.get(_summary_key(cold_row)),
            max_ratio=max_ratio,
            absolute_slack_ms=absolute_slack_ms,
        )
        for cold_row in cold_rows
    )
    return ColdWarmRatioReport(
        schema_version=RATIO_REPORT_SCHEMA_VERSION,
        task_id="T-162",
        cold_report=cold_report,
        warm_report=warm_report,
        max_ratio=max_ratio,
        absolute_slack_ms=absolute_slack_ms,
        passed=bool(comparisons) and all(comparison.passed for comparison in comparisons),
        comparisons=comparisons,
    )


def report_to_dict(report: ColdWarmRatioReport) -> dict[str, Any]:
    return asdict(report)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cold_payload = _read_json(args.cold_report)
    warm_payload = _read_json(args.warm_report)
    report = evaluate_cold_warm_ratio(
        cold_payload=cold_payload,
        warm_payload=warm_payload,
        cold_report=str(args.cold_report),
        warm_report=str(args.warm_report),
        max_ratio=args.max_ratio,
        absolute_slack_ms=args.absolute_slack_ms,
    )
    payload = json.dumps(report_to_dict(report), ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if args.mode == "enforce" and not report.passed:
        return 2
    return 0


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"report must be a JSON object: {path}"
        raise ValueError(msg)
    return payload


def _summary_rows(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw = payload.get("summaries")
    if not isinstance(raw, list):
        msg = "REST benchmark report must contain a summaries array"
        raise ValueError(msg)
    return tuple(row for row in raw if isinstance(row, dict))


def _summary_key(row: Mapping[str, Any]) -> SummaryKey:
    return (
        str(row["group"]),
        str(row["sql_name"]),
        int(row["concurrency"]),
    )


def _compare_row(
    cold_row: Mapping[str, Any],
    warm_row: Mapping[str, Any] | None,
    *,
    max_ratio: float,
    absolute_slack_ms: float,
) -> ColdWarmComparison:
    group, sql_name, concurrency = _summary_key(cold_row)
    cold_p99 = _optional_float(cold_row.get("p99_ms"))
    cold_errors = int(cold_row.get("errors") or 0)
    if warm_row is None:
        return ColdWarmComparison(
            group=group,
            sql_name=sql_name,
            concurrency=concurrency,
            cold_p99_ms=cold_p99,
            warm_p99_ms=None,
            ratio=None,
            threshold_ms=None,
            cold_errors=cold_errors,
            warm_errors=None,
            passed=False,
            reason="missing_warm_summary",
        )
    warm_p99 = _optional_float(warm_row.get("p99_ms"))
    warm_errors = int(warm_row.get("errors") or 0)
    if cold_errors or warm_errors:
        reason = "errors_present"
    elif cold_p99 is None or warm_p99 is None:
        reason = "missing_p99"
    else:
        reason = None
    threshold = None if warm_p99 is None else warm_p99 * max_ratio + absolute_slack_ms
    ratio = None if not warm_p99 else (cold_p99 / warm_p99 if cold_p99 is not None else None)
    passed = (
        reason is None
        and cold_p99 is not None
        and threshold is not None
        and cold_p99 <= threshold
    )
    if reason is None and not passed:
        reason = "p99_ratio_exceeded"
    return ColdWarmComparison(
        group=group,
        sql_name=sql_name,
        concurrency=concurrency,
        cold_p99_ms=cold_p99,
        warm_p99_ms=warm_p99,
        ratio=round(ratio, 6) if ratio is not None else None,
        threshold_ms=round(threshold, 3) if threshold is not None else None,
        cold_errors=cold_errors,
        warm_errors=warm_errors,
        passed=passed,
        reason=reason,
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
