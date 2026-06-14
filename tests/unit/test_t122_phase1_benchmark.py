from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from scripts.benchmark_phase1_augment_performance import (
    BenchmarkSummary,
    CaseBenchmark,
    PreparationBenchmark,
    ResourceSnapshot,
    ResourceUsage,
    benchmark_markdown,
    build_parser,
    diff_proc_io,
    human_bytes,
    parse_proc_io,
    parse_proc_status,
    write_benchmark,
)
from scripts.run_phase1_augment_reports import SourceInput


def test_t122_parser_accepts_case_and_sampling_options() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "--case",
            "C11",
            "--case",
            "C14",
            "--sido",
            "세종특별자치시",
            "--run-id",
            "t122-smoke",
            "--sample-interval-s",
            "0.25",
            "--no-materialize-electronic-map",
            "--materialize-navi-7z",
            "--git-repo",
            "F:/dev/kor-travel-geo-codex",
        ]
    )

    assert args.cases == ["C11", "C14"]
    assert args.sido == ["세종특별자치시"]
    assert args.run_id == "t122-smoke"
    assert args.sample_interval_s == 0.25
    assert args.materialize_electronic_map is False
    assert args.materialize_navi_7z is True
    assert args.git_repo.as_posix() == "F:/dev/kor-travel-geo-codex"
    assert args.allow_without_slow_real_data is False


def test_proc_parsers_and_delta_helpers() -> None:
    rss, hwm = parse_proc_status(
        """
Name:\tpython
VmHWM:\t    2048 kB
VmRSS:\t    1024 kB
"""
    )
    io_started = parse_proc_io(
        """
rchar: 100
wchar: 200
read_bytes: 4096
write_bytes: 8192
cancelled_write_bytes: 0
"""
    )
    io_finished = parse_proc_io(
        """
rchar: 356
wchar: 712
read_bytes: 12288
write_bytes: 8192
cancelled_write_bytes: 0
"""
    )

    assert rss == 1024 * 1024
    assert hwm == 2048 * 1024
    assert diff_proc_io(io_started, io_finished)["rchar"] == 256
    assert diff_proc_io(io_started, io_finished)["wchar"] == 512
    assert diff_proc_io(io_started, io_finished)["read_bytes"] == 8192
    assert diff_proc_io(io_started, io_finished)["write_bytes"] == 0


def test_human_bytes_formats_nullable_values() -> None:
    assert human_bytes(None) == "n/a"
    assert human_bytes(0) == "0 B"
    assert human_bytes(1024) == "1.0 KiB"
    assert human_bytes(1536 * 1024) == "1.5 MiB"


def test_write_benchmark_outputs_json_and_markdown(tmp_path: Path) -> None:
    usage = _usage(rss_peak=64 * 1024 * 1024, rchar=2 * 1024 * 1024)
    summary = BenchmarkSummary(
        schema_version=1,
        run_id="t122-test",
        started_at="2026-06-14T00:00:00+00:00",
        finished_at="2026-06-14T00:00:10+00:00",
        total_seconds=10.0,
        data_root="/data/juso",
        output_dir=str(tmp_path),
        git_commit="abc123",
        git_branch="agent/codex-t122",
        sample_interval_s=1.0,
        measurement_scope="runner process RSS and /proc/self/io",
        preparation=PreparationBenchmark(
            phase_id="preparation",
            seconds=1.25,
            resource=usage,
            sources_by_case={
                "C11": (SourceInput("electronic_map", "/data/electronic", "202604"),),
            },
        ),
        cases=(
            CaseBenchmark(
                phase_id="C11",
                task_id="T-111",
                output_path=str(tmp_path / "reports" / "c11-t-111.json"),
                seconds=8.75,
                resource=usage,
                report_summary={
                    "task_id": "T-111",
                    "title": "C11",
                    "used": 17,
                    "failed": 0,
                },
                sources=(SourceInput("electronic_map", "/data/electronic", "202604"),),
            ),
        ),
    )

    write_benchmark(summary, tmp_path)
    payload = json.loads((tmp_path / "benchmark.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "summary.md").read_text(encoding="utf-8")

    assert payload["schema_version"] == 1
    assert payload["cases"][0]["resource"]["rss_peak_bytes"] == 64 * 1024 * 1024
    assert "| C11 | T-111 | 17 | 0 | 8.750 | 64.0 MiB | 2.0 MiB |" in markdown
    assert benchmark_markdown(summary).startswith("# T-122 phase 1 보강 성능 벤치")


def _usage(*, rss_peak: int, rchar: int) -> ResourceUsage:
    empty_io = {
        "rchar": 0,
        "wchar": 0,
        "syscr": 0,
        "syscw": 0,
        "read_bytes": 0,
        "write_bytes": 0,
        "cancelled_write_bytes": 0,
    }
    snapshot = ResourceSnapshot(
        rss_bytes=rss_peak,
        rss_hwm_bytes=rss_peak,
        proc_io=empty_io,
        child_max_rss_bytes=0,
        child_inblock=0,
        child_oublock=0,
    )
    return ResourceUsage(
        started=snapshot,
        finished=snapshot,
        rss_peak_bytes=rss_peak,
        proc_io_delta={**empty_io, "rchar": rchar},
        child_inblock_delta=0,
        child_oublock_delta=0,
    )
