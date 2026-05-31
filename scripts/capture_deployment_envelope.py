"""Capture host envelope artifacts for N150/Odroid deployment benchmarks."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    command: tuple[str, ...]
    timeout_s: int = 10


@dataclass(frozen=True, slots=True)
class CommandResult:
    name: str
    command: tuple[str, ...]
    available: bool
    returncode: int | None
    elapsed_ms: float | None
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class DeploymentEnvelope:
    schema_version: int
    env_label: str
    collected_at: str
    git_commit: str | None
    git_branch: str | None
    python_version: str
    platform: str
    cpu_count: int | None
    cwd: str
    data_dir: str
    output_dir: str
    run_probes: bool
    system_commands: tuple[CommandResult, ...]
    probe_plan: tuple[CommandSpec, ...]
    probe_results: tuple[CommandResult, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture system envelope for N150/Odroid benchmark runs.",
    )
    parser.add_argument(
        "--env-label",
        default="unknown",
        help="Environment label, e.g. n150, odroid-h4, wsl-baseline.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact directory. Defaults to artifacts/perf/n150-vs-odroid-<date>/<env-label>.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Data directory used by full-load tests. Recorded and passed to df.",
    )
    parser.add_argument(
        "--run-probes",
        action="store_true",
        help="Run bounded fio/sysbench probes. Default only records commands and availability.",
    )
    parser.add_argument(
        "--probe-dir",
        type=Path,
        help="Directory for fio temporary/output files. Defaults to <output-dir>/probes.",
    )
    parser.add_argument("--fio-runtime-s", type=int, default=30)
    parser.add_argument("--fio-size", default="1G")
    parser.add_argument("--sysbench-time-s", type=int, default=30)
    parser.add_argument("--sysbench-threads", type=int, default=4)
    parser.add_argument("--probe-timeout-s", type=int, default=120)
    return parser


def default_output_dir(env_label: str, now: datetime) -> Path:
    safe_label = _safe_label(env_label)
    return Path("artifacts") / "perf" / f"n150-vs-odroid-{now:%Y%m%d}" / safe_label


def build_system_commands(data_dir: Path) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec("uname", ("uname", "-a")),
        CommandSpec("os_release", ("cat", "/etc/os-release")),
        CommandSpec("lscpu", ("lscpu",)),
        CommandSpec("memory", ("free", "-b")),
        CommandSpec("lsblk", ("lsblk", "-J", "-o", "NAME,MODEL,SIZE,ROTA,TYPE,FSTYPE,MOUNTPOINTS")),
        CommandSpec("df_root", ("df", "-B1", "/")),
        CommandSpec("df_data_dir", ("df", "-B1", str(data_dir))),
        CommandSpec("swapon", ("swapon", "--show", "--bytes")),
        CommandSpec("docker", ("docker", "--version")),
        CommandSpec("docker_compose", ("docker", "compose", "version")),
        CommandSpec("gdalinfo", ("gdalinfo", "--version")),
        CommandSpec("psql", ("psql", "--version")),
        CommandSpec("fio", ("fio", "--version")),
        CommandSpec("sysbench", ("sysbench", "--version")),
        CommandSpec("iostat", ("iostat", "-V")),
        CommandSpec("zstd", ("zstd", "--version")),
    )


def build_probe_plan(
    probe_dir: Path,
    *,
    fio_runtime_s: int = 30,
    fio_size: str = "1G",
    sysbench_time_s: int = 30,
    sysbench_threads: int = 4,
    timeout_s: int = 120,
) -> tuple[CommandSpec, ...]:
    fio_file = probe_dir / "fio-randread-8k.tmp"
    fio_output = probe_dir / "fio-randread-8k.json"
    return (
        CommandSpec(
            "fio_randread_8k",
            (
                "fio",
                "--name=kraddr_geo_randread_8k",
                f"--filename={fio_file}",
                "--rw=randread",
                "--bs=8k",
                "--iodepth=32",
                "--numjobs=4",
                f"--runtime={fio_runtime_s}",
                "--time_based",
                f"--size={fio_size}",
                "--direct=1",
                "--group_reporting",
                "--unlink=1",
                "--output-format=json",
                f"--output={fio_output}",
            ),
            timeout_s=timeout_s,
        ),
        CommandSpec(
            "sysbench_cpu",
            (
                "sysbench",
                "cpu",
                f"--threads={sysbench_threads}",
                f"--time={sysbench_time_s}",
                "run",
            ),
            timeout_s=timeout_s,
        ),
        CommandSpec(
            "sysbench_memory",
            (
                "sysbench",
                "memory",
                f"--threads={sysbench_threads}",
                f"--time={sysbench_time_s}",
                "run",
            ),
            timeout_s=timeout_s,
        ),
    )


def run_command(spec: CommandSpec) -> CommandResult:
    if not spec.command:
        msg = "command must not be empty"
        raise ValueError(msg)
    executable = spec.command[0]
    if shutil.which(executable) is None:
        return CommandResult(
            name=spec.name,
            command=spec.command,
            available=False,
            returncode=None,
            elapsed_ms=None,
            stdout="",
            stderr=f"{executable} not found",
        )
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            spec.command,
            capture_output=True,
            check=False,
            text=True,
            timeout=spec.timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            name=spec.name,
            command=spec.command,
            available=True,
            returncode=None,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            stdout=_decode_timeout_output(exc.stdout),
            stderr=_decode_timeout_output(exc.stderr),
            timed_out=True,
        )
    return CommandResult(
        name=spec.name,
        command=spec.command,
        available=True,
        returncode=completed.returncode,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def collect_envelope(
    *,
    env_label: str,
    data_dir: Path,
    output_dir: Path,
    run_probes: bool,
    probe_dir: Path,
    fio_runtime_s: int,
    fio_size: str,
    sysbench_time_s: int,
    sysbench_threads: int,
    probe_timeout_s: int,
    now: datetime | None = None,
) -> DeploymentEnvelope:
    collected_at = (now or datetime.now(UTC)).isoformat()
    system_results = tuple(run_command(spec) for spec in build_system_commands(data_dir))
    probe_plan = build_probe_plan(
        probe_dir,
        fio_runtime_s=fio_runtime_s,
        fio_size=fio_size,
        sysbench_time_s=sysbench_time_s,
        sysbench_threads=sysbench_threads,
        timeout_s=probe_timeout_s,
    )
    probe_results: tuple[CommandResult, ...] = ()
    if run_probes:
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_results = tuple(run_command(spec) for spec in probe_plan)
    return DeploymentEnvelope(
        schema_version=SCHEMA_VERSION,
        env_label=env_label,
        collected_at=collected_at,
        git_commit=_git_value("rev-parse", "HEAD"),
        git_branch=_git_value("branch", "--show-current"),
        python_version=platform.python_version(),
        platform=platform.platform(),
        cpu_count=os.cpu_count(),
        cwd=str(Path.cwd()),
        data_dir=str(data_dir),
        output_dir=str(output_dir),
        run_probes=run_probes,
        system_commands=system_results,
        probe_plan=probe_plan,
        probe_results=probe_results,
    )


def write_outputs(envelope: DeploymentEnvelope, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "system-envelope.json").write_text(
        json.dumps(asdict(envelope), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "system-envelope.md").write_text(
        render_markdown(envelope),
        encoding="utf-8",
    )


def render_markdown(envelope: DeploymentEnvelope) -> str:
    lines = [
        f"# T-055 배포 환경 envelope: {envelope.env_label}",
        "",
        "| 항목 | 값 |",
        "|------|----|",
        f"| collected_at | `{envelope.collected_at}` |",
        f"| git_commit | `{envelope.git_commit or 'unknown'}` |",
        f"| git_branch | `{envelope.git_branch or 'unknown'}` |",
        f"| platform | `{envelope.platform}` |",
        f"| cpu_count | `{envelope.cpu_count}` |",
        f"| data_dir | `{envelope.data_dir}` |",
        f"| output_dir | `{envelope.output_dir}` |",
        f"| run_probes | `{envelope.run_probes}` |",
        "",
        "## 시스템 명령",
        "",
        "| name | available | returncode | timed_out | elapsed_ms |",
        "|------|-----------|------------|-----------|------------|",
    ]
    for result in envelope.system_commands:
        lines.append(
            "| "
            f"`{result.name}` | `{result.available}` | `{result.returncode}` | "
            f"`{result.timed_out}` | `{result.elapsed_ms}` |"
        )
    lines.extend(["", "## Probe 계획", ""])
    for spec in envelope.probe_plan:
        lines.extend(
            [
                f"### {spec.name}",
                "",
                "```bash",
                _shell_join(spec.command),
                "```",
                "",
            ]
        )
    if envelope.probe_results:
        lines.extend(
            [
                "## Probe 결과",
                "",
                "| name | available | returncode | timed_out | elapsed_ms |",
                "|------|-----------|------------|-----------|------------|",
            ]
        )
        for result in envelope.probe_results:
            lines.append(
                "| "
                f"`{result.name}` | `{result.available}` | `{result.returncode}` | "
                f"`{result.timed_out}` | `{result.elapsed_ms}` |"
            )
    lines.extend(
        [
            "",
            "자세한 stdout/stderr 원문은 같은 디렉터리의 `system-envelope.json`을 기준으로 본다.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = build_parser().parse_args()
    now = datetime.now(UTC)
    output_dir = args.output_dir or default_output_dir(args.env_label, now)
    probe_dir = args.probe_dir or output_dir / "probes"
    envelope = collect_envelope(
        env_label=args.env_label,
        data_dir=args.data_dir,
        output_dir=output_dir,
        run_probes=args.run_probes,
        probe_dir=probe_dir,
        fio_runtime_s=args.fio_runtime_s,
        fio_size=args.fio_size,
        sysbench_time_s=args.sysbench_time_s,
        sysbench_threads=args.sysbench_threads,
        probe_timeout_s=args.probe_timeout_s,
        now=now,
    )
    write_outputs(envelope, output_dir)
    print(output_dir)


def _git_value(*args: str) -> str | None:
    git_repo = _git_repo()
    command = _git_command(git_repo, *args)
    result = run_command(CommandSpec(args[0], command))
    if not result.available or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_command(git_repo: str | None, *args: str) -> tuple[str, ...]:
    if git_repo is None:
        return ("git", *args)
    if _is_windows_path(git_repo):
        return (_windows_git_executable(), "-C", git_repo, *args)
    return ("git", "-C", git_repo, *args)


def _git_repo() -> str | None:
    env_repo = os.environ.get("KRADDR_GEO_GIT_REPO")
    if env_repo:
        return _as_windows_path(env_repo)
    cwd = Path.cwd()
    if cwd.name.startswith("python-kraddr-geo-") and cwd.name.endswith("-test"):
        return f"F:/dev/{cwd.name.removesuffix('-test')}"
    if (Path("/mnt/f/dev/python-kraddr-geo-codex") / ".git").exists():
        return "F:/dev/python-kraddr-geo-codex"
    return None


def _as_windows_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("/mnt/") and len(normalized) > 6 and normalized[6] == "/":
        drive = normalized[5].upper()
        return f"{drive}:{normalized[6:]}"
    return normalized


def _is_windows_path(path: str) -> bool:
    return len(path) >= 3 and path[1:3] == ":/"


def _windows_git_executable() -> str:
    env_git = os.environ.get("KRADDR_GEO_GIT_EXE")
    if env_git:
        return env_git
    for candidate in (
        "/mnt/c/Program Files/Git/cmd/git.exe",
        "/mnt/c/Program Files/Git/bin/git.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return shutil.which("git.exe") or "git.exe"


def _decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _safe_label(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip())
    return cleaned or "unknown"


def _shell_join(command: Sequence[str]) -> str:
    return " ".join(_quote(part) for part in command)


def _quote(value: str) -> str:
    if value and all(ch.isalnum() or ch in {"-", "_", ".", "/", "=", ":"} for ch in value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


if __name__ == "__main__":
    main()
