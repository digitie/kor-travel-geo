"""Evaluate REST benchmark output against the T-144 API contract budgets."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


API_CONTRACT_REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ApiContractSummaryCheck:
    group: str
    sql_name: str
    concurrency: int
    samples: int
    errors: int
    p99_ms: float | None
    avg_response_bytes: float | None
    p99_budget_ms: float
    avg_response_budget_bytes: int
    passed: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class ApiContractEvaluationReport:
    schema_version: int
    task_id: str
    benchmark_report: str
    p99_budget_ms: float
    avg_response_budget_bytes: int
    passed: bool
    summary_checks: tuple[ApiContractSummaryCheck, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate T-144 API contract latency and payload budgets.",
    )
    parser.add_argument("--api-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    parser.add_argument(
        "--p99-budget-ms",
        type=float,
        default=500.0,
        help="Per summary-row p99 budget.",
    )
    parser.add_argument(
        "--avg-response-budget-bytes",
        type=int,
        default=64 * 1024,
        help="Per summary-row average response size budget.",
    )
    parser.add_argument(
        "--mode",
        choices=("report", "enforce"),
        default="report",
        help="enforce exits 2 when any budget fails.",
    )
    return parser


def evaluate_api_contract_report(
    *,
    payload: Mapping[str, Any],
    benchmark_report: str,
    p99_budget_ms: float = 500.0,
    avg_response_budget_bytes: int = 64 * 1024,
) -> ApiContractEvaluationReport:
    checks = tuple(
        _check_summary_row(
            row,
            p99_budget_ms=p99_budget_ms,
            avg_response_budget_bytes=avg_response_budget_bytes,
        )
        for row in _summary_rows(payload)
    )
    return ApiContractEvaluationReport(
        schema_version=API_CONTRACT_REPORT_SCHEMA_VERSION,
        task_id="T-144",
        benchmark_report=benchmark_report,
        p99_budget_ms=p99_budget_ms,
        avg_response_budget_bytes=avg_response_budget_bytes,
        passed=bool(checks) and all(check.passed for check in checks),
        summary_checks=checks,
    )


def report_to_dict(report: ApiContractEvaluationReport) -> dict[str, Any]:
    return asdict(report)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = _read_json(args.api_report)
    report = evaluate_api_contract_report(
        payload=payload,
        benchmark_report=str(args.api_report),
        p99_budget_ms=args.p99_budget_ms,
        avg_response_budget_bytes=args.avg_response_budget_bytes,
    )
    encoded = json.dumps(report_to_dict(report), ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
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


def _check_summary_row(
    row: Mapping[str, Any],
    *,
    p99_budget_ms: float,
    avg_response_budget_bytes: int,
) -> ApiContractSummaryCheck:
    errors = int(row.get("errors") or 0)
    p99_ms = _optional_float(row.get("p99_ms"))
    avg_response_bytes = _optional_float(row.get("avg_response_bytes"))
    reasons: list[str] = []
    if errors:
        reasons.append("errors_present")
    if p99_ms is None:
        reasons.append("missing_p99")
    elif p99_ms > p99_budget_ms:
        reasons.append("p99_budget_exceeded")
    if avg_response_bytes is None:
        reasons.append("missing_avg_response_bytes")
    elif avg_response_bytes > avg_response_budget_bytes:
        reasons.append("avg_response_budget_exceeded")
    return ApiContractSummaryCheck(
        group=str(row["group"]),
        sql_name=str(row["sql_name"]),
        concurrency=int(row["concurrency"]),
        samples=int(row.get("samples") or 0),
        errors=errors,
        p99_ms=p99_ms,
        avg_response_bytes=avg_response_bytes,
        p99_budget_ms=p99_budget_ms,
        avg_response_budget_bytes=avg_response_budget_bytes,
        passed=not reasons,
        reason=",".join(reasons) if reasons else None,
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
