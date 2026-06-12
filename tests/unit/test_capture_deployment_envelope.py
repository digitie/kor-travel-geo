from __future__ import annotations

from datetime import UTC, datetime

from scripts.capture_deployment_envelope import (
    CommandResult,
    CommandSpec,
    DeploymentEnvelope,
    build_parser,
    build_probe_plan,
    default_output_dir,
    render_markdown,
    run_command,
)


def test_capture_deployment_envelope_parser_defaults() -> None:
    args = build_parser().parse_args([])

    assert args.env_label == "unknown"
    assert args.data_dir.as_posix() == "data"
    assert args.run_probes is False
    assert args.fio_runtime_s == 30
    assert args.sysbench_threads == 4


def test_default_output_dir_uses_safe_label_and_date() -> None:
    path = default_output_dir("N150 box", datetime(2026, 5, 29, tzinfo=UTC))

    assert path.as_posix() == "artifacts/perf/n150-vs-odroid-20260529/N150-box"


def test_run_command_marks_missing_executable() -> None:
    result = run_command(CommandSpec("missing", ("kor-travel-geo-missing-command",)))

    assert result.available is False
    assert result.returncode is None
    assert "not found" in result.stderr


def test_probe_plan_keeps_bounded_default_commands(tmp_path) -> None:
    plan = build_probe_plan(tmp_path, fio_runtime_s=5, fio_size="16M", sysbench_time_s=3)

    assert plan[0].name == "fio_randread_8k"
    assert "--runtime=5" in plan[0].command
    assert "--size=16M" in plan[0].command
    assert plan[1].command == ("sysbench", "cpu", "--threads=4", "--time=3", "run")


def test_render_markdown_summarizes_commands_and_probe_plan(tmp_path) -> None:
    envelope = DeploymentEnvelope(
        schema_version=1,
        env_label="n150",
        collected_at="2026-05-29T00:00:00+00:00",
        git_commit="abc123",
        git_branch="codex/t055",
        python_version="3.12",
        platform="Linux",
        cpu_count=4,
        cwd="/work",
        data_dir="/data",
        output_dir=tmp_path.as_posix(),
        run_probes=False,
        system_commands=(
            CommandResult(
                name="uname",
                command=("uname", "-a"),
                available=True,
                returncode=0,
                elapsed_ms=1.0,
                stdout="Linux",
                stderr="",
            ),
        ),
        probe_plan=build_probe_plan(tmp_path),
        probe_results=(),
    )

    markdown = render_markdown(envelope)

    assert "# T-055 배포 환경 envelope: n150" in markdown
    assert "`abc123`" in markdown
    assert "`uname`" in markdown
    assert "fio_randread_8k" in markdown
