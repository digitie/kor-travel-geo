"""T-164 p99 regression gate for T-141 matrix reports."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

T164_SCHEMA_VERSION = 1
DEFAULT_MAX_P99_REGRESSION_RATIO = 0.20
DEFAULT_ABSOLUTE_TOLERANCE_MS = 25.0

GuardMode = Literal["report", "enforce"]


@dataclass(frozen=True, slots=True)
class MatrixP99Row:
    profile_id: str
    target: str
    workload: str
    phase: str
    concurrency: int
    worst_p99_ms: float | None
    errors: int
    soak_guard_passed: bool | None
    artifact_dir: str | None


@dataclass(frozen=True, slots=True)
class P99GuardThreshold:
    max_regression_ratio: float
    absolute_tolerance_ms: float
    require_zero_errors: bool
    require_soak_guard: bool


@dataclass(frozen=True, slots=True)
class P99ComparisonRow:
    profile_id: str
    target: str
    workload: str
    phase: str
    concurrency: int
    baseline_p99_ms: float | None
    current_p99_ms: float | None
    delta_ms: float | None
    regression_ratio: float | None
    allowed_p99_ms: float | None
    current_errors: int
    soak_guard_passed: bool | None
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class P99GuardReport:
    schema_version: int
    generated_at: str
    current_report: str
    baseline_report: str
    current_run_id: str | None
    baseline_run_id: str | None
    mode: GuardMode
    threshold: P99GuardThreshold
    workload_filter: tuple[str, ...]
    target_filter: tuple[str, ...]
    phase_filter: tuple[str, ...]
    compared_count: int
    passed_count: int
    failed_count: int
    passed: bool
    rows: tuple[P99ComparisonRow, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate T-141 matrix-report p99 regressions for T-164.",
    )
    parser.add_argument("--current-report", type=Path, required=True)
    parser.add_argument("--baseline-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--mode",
        choices=("report", "enforce"),
        default="enforce",
        help="report writes artifacts only; enforce exits 2 when the guard fails.",
    )
    parser.add_argument(
        "--max-p99-regression-ratio",
        type=float,
        default=DEFAULT_MAX_P99_REGRESSION_RATIO,
        help="Allowed relative p99 regression. 0.20 means +20%%.",
    )
    parser.add_argument(
        "--absolute-tolerance-ms",
        type=float,
        default=DEFAULT_ABSOLUTE_TOLERANCE_MS,
        help="Minimum allowed absolute p99 delta before a row fails.",
    )
    parser.add_argument(
        "--workload",
        action="append",
        help="Workload to include. May repeat. Default: all comparable workloads.",
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=("sql", "rest"),
        help="Target to include. May repeat. Default: sql and rest.",
    )
    parser.add_argument(
        "--phase",
        action="append",
        choices=("steady", "burst", "recovery", "soak"),
        help="Phase to include. May repeat. Default: all phases.",
    )
    parser.add_argument(
        "--allow-errors",
        action="store_true",
        help="Do not fail rows solely because current matrix reported errors.",
    )
    parser.add_argument(
        "--allow-missing-soak-guard",
        action="store_true",
        help="Do not require T-163 soak_guard.passed=true for soak rows.",
    )
    return parser


def evaluate_p99_regression(
    *,
    current_report: Mapping[str, Any],
    baseline_report: Mapping[str, Any],
    current_report_path: Path,
    baseline_report_path: Path,
    mode: GuardMode,
    threshold: P99GuardThreshold,
    workload_filter: Sequence[str] = (),
    target_filter: Sequence[str] = (),
    phase_filter: Sequence[str] = (),
) -> P99GuardReport:
    current_rows = _filter_rows(
        _matrix_rows(current_report),
        workloads=tuple(workload_filter),
        targets=tuple(target_filter),
        phases=tuple(phase_filter),
    )
    baseline_by_profile = {
        row.profile_id: row
        for row in _filter_rows(
            _matrix_rows(baseline_report),
            workloads=tuple(workload_filter),
            targets=tuple(target_filter),
            phases=tuple(phase_filter),
        )
    }
    comparisons = tuple(
        _compare_row(row, baseline_by_profile.get(row.profile_id), threshold)
        for row in current_rows
    )
    passed_count = sum(1 for row in comparisons if row.passed)
    failed_count = len(comparisons) - passed_count
    return P99GuardReport(
        schema_version=T164_SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        current_report=str(current_report_path),
        baseline_report=str(baseline_report_path),
        current_run_id=_optional_str(current_report.get("run_id")),
        baseline_run_id=_optional_str(baseline_report.get("run_id")),
        mode=mode,
        threshold=threshold,
        workload_filter=tuple(workload_filter),
        target_filter=tuple(target_filter),
        phase_filter=tuple(phase_filter),
        compared_count=len(comparisons),
        passed_count=passed_count,
        failed_count=failed_count,
        passed=failed_count == 0 and len(comparisons) > 0,
        rows=comparisons,
    )


def _matrix_rows(report: Mapping[str, Any]) -> tuple[MatrixP99Row, ...]:
    rows = cast("Sequence[Mapping[str, Any]]", report.get("results", ()))
    return tuple(_matrix_row(row) for row in rows)


def _matrix_row(row: Mapping[str, Any]) -> MatrixP99Row:
    soak_guard = row.get("soak_guard")
    soak_guard_passed: bool | None = None
    if isinstance(soak_guard, dict):
        passed = soak_guard.get("passed")
        soak_guard_passed = passed if isinstance(passed, bool) else None
    return MatrixP99Row(
        profile_id=str(row.get("profile_id", "")),
        target=str(row.get("target", "")),
        workload=str(row.get("workload", "")),
        phase=str(row.get("phase", "")),
        concurrency=_as_int(row.get("concurrency")),
        worst_p99_ms=_as_float(row.get("worst_p99_ms")),
        errors=_as_int(row.get("errors")),
        soak_guard_passed=soak_guard_passed,
        artifact_dir=_optional_str(row.get("artifact_dir")),
    )


def _filter_rows(
    rows: Sequence[MatrixP99Row],
    *,
    workloads: Sequence[str],
    targets: Sequence[str],
    phases: Sequence[str],
) -> tuple[MatrixP99Row, ...]:
    workload_set = set(workloads)
    target_set = set(targets)
    phase_set = set(phases)
    return tuple(
        row
        for row in rows
        if (not workload_set or row.workload in workload_set)
        and (not target_set or row.target in target_set)
        and (not phase_set or row.phase in phase_set)
    )


def _compare_row(
    current: MatrixP99Row,
    baseline: MatrixP99Row | None,
    threshold: P99GuardThreshold,
) -> P99ComparisonRow:
    failures: list[str] = []
    baseline_p99 = None if baseline is None else baseline.worst_p99_ms
    current_p99 = current.worst_p99_ms
    allowed_p99 = _allowed_p99_ms(baseline_p99, threshold)
    delta_ms = _delta(current_p99, baseline_p99)
    ratio = _regression_ratio(current_p99, baseline_p99)

    if baseline is None:
        failures.append("baseline_profile_missing")
    elif baseline_p99 is None:
        failures.append("baseline_p99_missing")
    if current_p99 is None:
        failures.append("current_p99_missing")
    elif allowed_p99 is not None and current_p99 > allowed_p99:
        failures.append(
            f"p99_ms={current_p99:.3f} > allowed={allowed_p99:.3f}"
        )
    if threshold.require_zero_errors and current.errors > 0:
        failures.append(f"errors={current.errors} > 0")
    if (
        threshold.require_soak_guard
        and current.phase == "soak"
        and current.soak_guard_passed is not True
    ):
        failures.append("soak_guard_not_passed")

    return P99ComparisonRow(
        profile_id=current.profile_id,
        target=current.target,
        workload=current.workload,
        phase=current.phase,
        concurrency=current.concurrency,
        baseline_p99_ms=baseline_p99,
        current_p99_ms=current_p99,
        delta_ms=delta_ms,
        regression_ratio=ratio,
        allowed_p99_ms=allowed_p99,
        current_errors=current.errors,
        soak_guard_passed=current.soak_guard_passed,
        passed=not failures,
        failures=tuple(failures),
    )


def write_p99_guard_report(report: P99GuardReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "p99-guard.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(_markdown(report), encoding="utf-8")


def _markdown(report: P99GuardReport) -> str:
    lines = [
        "# T-164 p99 regression guard",
        "",
        f"- current_report: `{report.current_report}`",
        f"- baseline_report: `{report.baseline_report}`",
        f"- current_run_id: `{report.current_run_id or 'unknown'}`",
        f"- baseline_run_id: `{report.baseline_run_id or 'unknown'}`",
        f"- mode: `{report.mode}`",
        f"- max_regression_ratio: `{report.threshold.max_regression_ratio}`",
        f"- absolute_tolerance_ms: `{report.threshold.absolute_tolerance_ms}`",
        f"- require_zero_errors: `{report.threshold.require_zero_errors}`",
        f"- require_soak_guard: `{report.threshold.require_soak_guard}`",
        f"- compared_count: `{report.compared_count}`",
        f"- failed_count: `{report.failed_count}`",
        "",
        "| profile | target | workload | phase | c | baseline p99 | current p99 | "
        "allowed p99 | delta | ratio | errors | soak guard | result | failures |",
        "|---------|--------|----------|-------|--:|-------------:|------------:|"
        "------------:|------:|------:|-------:|------------|--------|----------|",
    ]
    for row in report.rows:
        lines.append(
            f"| `{row.profile_id}` | `{row.target}` | `{row.workload}` | `{row.phase}` | "
            f"{row.concurrency} | {_md_num(row.baseline_p99_ms)} | "
            f"{_md_num(row.current_p99_ms)} | {_md_num(row.allowed_p99_ms)} | "
            f"{_md_num(row.delta_ms)} | {_md_ratio(row.regression_ratio)} | "
            f"{row.current_errors} | {_md_bool(row.soak_guard_passed)} | "
            f"{'pass' if row.passed else 'fail'} | {_md_failures(row.failures)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _load_json(path: Path) -> Mapping[str, Any]:
    return cast("Mapping[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _allowed_p99_ms(
    baseline_p99_ms: float | None,
    threshold: P99GuardThreshold,
) -> float | None:
    if baseline_p99_ms is None:
        return None
    relative_limit = baseline_p99_ms * (1.0 + threshold.max_regression_ratio)
    absolute_limit = baseline_p99_ms + threshold.absolute_tolerance_ms
    return round(max(relative_limit, absolute_limit), 3)


def _delta(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return round(current - baseline, 3)


def _regression_ratio(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline <= 0:
        return None
    return round((current - baseline) / baseline, 6)


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if value is None:
        return 0
    try:
        return int(str(value))
    except ValueError:
        return 0


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _md_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _md_ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3%}"


def _md_bool(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "pass" if value else "fail"


def _md_failures(failures: Sequence[str]) -> str:
    return "n/a" if not failures else "`" + "; ".join(failures) + "`"


def main() -> None:
    args = build_parser().parse_args()
    threshold = P99GuardThreshold(
        max_regression_ratio=_non_negative(
            "--max-p99-regression-ratio",
            args.max_p99_regression_ratio,
        ),
        absolute_tolerance_ms=_non_negative(
            "--absolute-tolerance-ms",
            args.absolute_tolerance_ms,
        ),
        require_zero_errors=not args.allow_errors,
        require_soak_guard=not args.allow_missing_soak_guard,
    )
    current_report = _load_json(args.current_report)
    baseline_report = _load_json(args.baseline_report)
    report = evaluate_p99_regression(
        current_report=current_report,
        baseline_report=baseline_report,
        current_report_path=args.current_report,
        baseline_report_path=args.baseline_report,
        mode=args.mode,
        threshold=threshold,
        workload_filter=tuple(args.workload or ()),
        target_filter=tuple(args.target or ()),
        phase_filter=tuple(args.phase or ()),
    )
    output_dir = args.output_dir or args.current_report.parent / "t164-p99-guard"
    write_p99_guard_report(report, output_dir)
    print(output_dir)
    if args.mode == "enforce" and not report.passed:
        for row in report.rows:
            if row.passed:
                continue
            print(
                f"p99 guard failed: {row.profile_id}: {'; '.join(row.failures)}",
                file=sys.stderr,
            )
        raise SystemExit(2)


def _non_negative(name: str, value: float) -> float:
    if value < 0:
        msg = f"{name} must be >= 0"
        raise ValueError(msg)
    return float(value)


if __name__ == "__main__":
    main()
