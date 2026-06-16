from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts import benchmark_backup_restore as bench

if TYPE_CHECKING:
    from pathlib import Path


def test_default_matrix_covers_profiles_jobs_and_compression() -> None:
    plan = bench.build_matrix()

    assert len(plan) == 27
    assert {item.profile for item in plan} == {"serving-ready", "lean-serving", "forensic"}
    assert {item.jobs for item in plan} == {1, 2, 4}
    assert {item.compression_level for item in plan} == {3, 9, 19}
    assert plan[0].profile_id == "serving_ready_j1_z3"
    assert all(len(item.target_database) <= 63 for item in plan)


def test_execute_requires_typed_confirmation() -> None:
    with pytest.raises(ValueError, match="RUN-T247-BENCHMARK kor_travel_geo"):
        bench.validate_execute_confirmation(
            execute=True,
            database="kor_travel_geo",
            confirmation=None,
        )

    bench.validate_execute_confirmation(
        execute=True,
        database="kor_travel_geo",
        confirmation="RUN-T247-BENCHMARK kor_travel_geo",
    )
    bench.validate_execute_confirmation(
        execute=False,
        database="kor_travel_geo",
        confirmation=None,
    )


def test_plan_only_main_writes_report_and_summary(tmp_path: Path) -> None:
    assert bench.main(["--run-id", "t247-plan-test", "--output-dir", str(tmp_path)]) == 0

    report = json.loads((tmp_path / "benchmark-report.json").read_text(encoding="utf-8"))
    plan = json.loads((tmp_path / "matrix-plan.json").read_text(encoding="utf-8"))
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")

    assert report["schema_version"] == 1
    assert report["task_id"] == "T-247"
    assert report["mode"] == "plan"
    assert report["results"] == []
    assert len(report["plan"]) == 27
    assert len(plan) == 27
    assert "계획 전용 실행" in summary
    assert "N150/Odroid 해석 가이드" in summary


def test_summarize_results_picks_fastest_and_smallest_archive() -> None:
    results = (
        _result(
            "serving_ready_j1_z3",
            jobs=1,
            compression=3,
            backup=10.0,
            restore=20.0,
            dump_bytes=1_000,
            archive_bytes=500,
        ),
        _result(
            "serving_ready_j2_z9",
            jobs=2,
            compression=9,
            backup=8.0,
            restore=15.0,
            dump_bytes=1_000,
            archive_bytes=300,
        ),
        _result(
            "serving_ready_j4_z19",
            jobs=4,
            compression=19,
            backup=30.0,
            restore=12.0,
            dump_bytes=1_000,
            archive_bytes=250,
        ),
    )

    summary = bench.summarize_results(results)

    assert len(summary) == 1
    row = summary[0]
    assert row.fastest_total_profile_id == "serving_ready_j2_z9"
    assert row.fastest_backup_profile_id == "serving_ready_j2_z9"
    assert row.fastest_restore_profile_id == "serving_ready_j4_z19"
    assert row.smallest_archive_profile_id == "serving_ready_j4_z19"
    assert row.best_compression_ratio_profile_id == "serving_ready_j4_z19"
    assert "총 소요시간 최단" in row.low_power_note


def _result(
    profile_id: str,
    *,
    jobs: int,
    compression: int,
    backup: float,
    restore: float,
    dump_bytes: int,
    archive_bytes: int,
) -> bench.BackupRestoreResult:
    return bench.BackupRestoreResult(
        profile_id=profile_id,
        profile="serving-ready",
        jobs=jobs,
        compression_level=compression,
        target_database=f"target_{profile_id}",
        ok=True,
        error=None,
        artifact_id=f"artifact_{profile_id}",
        archive_path=f"/tmp/{profile_id}.tar.zst",
        backup_seconds=backup,
        restore_seconds=restore,
        size_probe_seconds=1.0,
        dump_bytes=dump_bytes,
        archive_bytes=archive_bytes,
        compression_ratio=round(dump_bytes / archive_bytes, 4),
        archive_to_dump_ratio=round(archive_bytes / dump_bytes, 4),
    )
