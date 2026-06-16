from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.evaluate_t164_p99_regression import (
    P99GuardThreshold,
    evaluate_p99_regression,
    write_p99_guard_report,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_p99_guard_passes_with_relative_or_absolute_tolerance(tmp_path: Path) -> None:
    baseline = _report("baseline", [_row("sql-adversarial_fuzzy-steady-c64", 100.0)])
    current = _report("current", [_row("sql-adversarial_fuzzy-steady-c64", 124.0)])

    report = evaluate_p99_regression(
        current_report=current,
        baseline_report=baseline,
        current_report_path=tmp_path / "current.json",
        baseline_report_path=tmp_path / "baseline.json",
        mode="enforce",
        threshold=_threshold(),
        workload_filter=("adversarial_fuzzy",),
    )

    assert report.passed is True
    assert report.compared_count == 1
    row = report.rows[0]
    assert row.allowed_p99_ms == 125.0
    assert row.delta_ms == 24.0
    assert row.failures == ()


def test_p99_guard_fails_on_regression_and_errors(tmp_path: Path) -> None:
    baseline = _report("baseline", [_row("rest-worst_case_mix-burst-c128", 200.0)])
    current = _report(
        "current",
        [_row("rest-worst_case_mix-burst-c128", 280.0, errors=1)],
    )

    report = evaluate_p99_regression(
        current_report=current,
        baseline_report=baseline,
        current_report_path=tmp_path / "current.json",
        baseline_report_path=tmp_path / "baseline.json",
        mode="enforce",
        threshold=_threshold(),
        workload_filter=("worst_case_mix",),
    )

    assert report.passed is False
    row = report.rows[0]
    assert row.allowed_p99_ms == 240.0
    assert row.regression_ratio == 0.4
    assert any(failure.startswith("p99_ms=") for failure in row.failures)
    assert "errors=1 > 0" in row.failures


def test_p99_guard_requires_t163_soak_guard_for_soak_rows(tmp_path: Path) -> None:
    baseline = _report(
        "baseline",
        [_row("sql-actual_mix-soak-c64", 300.0, phase="soak", soak_guard_passed=True)],
    )
    current = _report(
        "current",
        [_row("sql-actual_mix-soak-c64", 310.0, phase="soak", soak_guard_passed=False)],
    )

    report = evaluate_p99_regression(
        current_report=current,
        baseline_report=baseline,
        current_report_path=tmp_path / "current.json",
        baseline_report_path=tmp_path / "baseline.json",
        mode="enforce",
        threshold=_threshold(),
    )

    assert report.passed is False
    assert "soak_guard_not_passed" in report.rows[0].failures


def test_write_p99_guard_report_writes_json_and_markdown(tmp_path: Path) -> None:
    baseline = _report("baseline", [_row("sql-adversarial_fuzzy-steady-c64", 100.0)])
    current = _report("current", [_row("sql-adversarial_fuzzy-steady-c64", 110.0)])
    report = evaluate_p99_regression(
        current_report=current,
        baseline_report=baseline,
        current_report_path=tmp_path / "current.json",
        baseline_report_path=tmp_path / "baseline.json",
        mode="report",
        threshold=_threshold(),
    )

    write_p99_guard_report(report, tmp_path / "guard")

    assert (tmp_path / "guard" / "p99-guard.json").exists()
    assert "T-164 p99 regression guard" in (
        tmp_path / "guard" / "summary.md"
    ).read_text(encoding="utf-8")


def _threshold() -> P99GuardThreshold:
    return P99GuardThreshold(
        max_regression_ratio=0.20,
        absolute_tolerance_ms=25.0,
        require_zero_errors=True,
        require_soak_guard=True,
    )


def _report(run_id: str, rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "results": rows,
    }


def _row(
    profile_id: str,
    p99_ms: float,
    *,
    errors: int = 0,
    phase: str = "steady",
    soak_guard_passed: bool | None = None,
) -> dict[str, object]:
    _, workload, _, concurrency = profile_id.split("-", maxsplit=3)
    return {
        "profile_id": profile_id,
        "target": profile_id.split("-", maxsplit=1)[0],
        "workload": workload,
        "phase": phase,
        "concurrency": int(concurrency.removeprefix("c")),
        "worst_p99_ms": p99_ms,
        "errors": errors,
        "artifact_dir": f"artifacts/{profile_id}",
        "soak_guard": None
        if soak_guard_passed is None
        else {"passed": soak_guard_passed},
    }
