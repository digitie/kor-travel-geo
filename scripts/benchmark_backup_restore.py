"""T-247 backup/restore wall-clock and archive-size benchmark runner."""

from __future__ import annotations

# ruff: noqa: ASYNC240
import argparse
import asyncio
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kortravelgeo.infra.admin_repo import AdminRepository  # noqa: E402
from kortravelgeo.infra.backup import (  # noqa: E402
    BACKUP_ARTIFACT_TYPE,
    build_tar_extract_command,
    database_name_from_dsn,
    normalize_sqlalchemy_dsn,
    path_size_bytes,
    quote_database_identifier,
    redact_dsn,
    run_backup_job,
    run_restore_job,
    validate_database_identifier,
)
from kortravelgeo.infra.engine import make_async_engine  # noqa: E402
from kortravelgeo.settings import Settings, get_settings  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncEngine

    from kortravelgeo.dto.admin import OpsArtifact

BackupProfileName = Literal["serving-ready", "lean-serving", "forensic"]

T247_SCHEMA_VERSION = 1
DEFAULT_PROFILES: tuple[BackupProfileName, ...] = (
    "serving-ready",
    "lean-serving",
    "forensic",
)
DEFAULT_JOBS = (1, 2, 4)
DEFAULT_COMPRESSION_LEVELS = (3, 9, 19)
REQUIRED_TOOLS = ("pg_dump", "pg_restore", "tar", "zstd")


@dataclass(frozen=True, slots=True)
class BackupRestorePlanItem:
    profile_id: str
    profile: BackupProfileName
    jobs: int
    compression_level: int
    target_database: str


@dataclass(frozen=True, slots=True)
class BackupRestoreResult:
    profile_id: str
    profile: BackupProfileName
    jobs: int
    compression_level: int
    target_database: str
    ok: bool
    error: str | None
    artifact_id: str | None
    archive_path: str | None
    backup_seconds: float | None
    restore_seconds: float | None
    size_probe_seconds: float | None
    dump_bytes: int | None
    archive_bytes: int | None
    compression_ratio: float | None
    archive_to_dump_ratio: float | None


@dataclass(frozen=True, slots=True)
class BackupRestoreProfileSummary:
    profile: BackupProfileName
    result_count: int
    fastest_total_profile_id: str | None
    fastest_total_seconds: float | None
    fastest_backup_profile_id: str | None
    fastest_backup_seconds: float | None
    fastest_restore_profile_id: str | None
    fastest_restore_seconds: float | None
    smallest_archive_profile_id: str | None
    smallest_archive_bytes: int | None
    best_compression_ratio_profile_id: str | None
    best_compression_ratio: float | None
    low_power_note: str


@dataclass(frozen=True, slots=True)
class BackupRestoreEnvironment:
    run_id: str
    started_at: str
    git_commit: str | None
    git_branch: str | None
    python_version: str
    platform: str
    cpu_count: int | None
    cwd: str
    mode: Literal["plan", "execute"]
    pg_dsn: str
    current_database: str | None
    database_size_bytes: int | None
    backup_allowed_dir: str
    backup_temp_dir: str
    include_materialized_views: bool
    run_analyze: bool
    run_smoke_test: bool
    run_row_count_check: bool


@dataclass(frozen=True, slots=True)
class BackupRestoreBenchmarkReport:
    schema_version: int
    task_id: str
    run_id: str
    started_at: str
    finished_at: str
    mode: Literal["plan", "execute"]
    plan: tuple[BackupRestorePlanItem, ...]
    results: tuple[BackupRestoreResult, ...]
    summaries: tuple[BackupRestoreProfileSummary, ...]
    environment: BackupRestoreEnvironment


async def _noop_progress(
    *, progress: float | None = None, stage: str | None = None, message: str | None = None
) -> None:
    _ = (progress, stage, message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark backup/restore time, dump size, archive size, and ratio.",
    )
    parser.add_argument("--pg-dsn", help="PostgreSQL DSN. Defaults to KTG_PG_DSN/settings.")
    parser.add_argument("--run-id", help="Stable run id. Defaults to timestamp.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Artifact directory. Defaults to artifacts/perf/<run-id>.",
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=DEFAULT_PROFILES,
        help="Backup profile. May be repeated. Default: all profiles.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        action="append",
        help="pg_dump/pg_restore jobs. May be repeated. Default: 1, 2, 4.",
    )
    parser.add_argument(
        "--compression-level",
        type=int,
        action="append",
        help="zstd compression level. May be repeated. Default: 3, 9, 19.",
    )
    parser.add_argument("--target-prefix", default="ktg_t247_restore")
    parser.add_argument("--backup-dir", type=Path, help="Backup archive directory.")
    parser.add_argument("--temp-dir", type=Path, help="Temporary work directory.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the benchmark. Omit for plan-only JSON/summary.",
    )
    parser.add_argument(
        "--confirmation",
        help="Required with --execute: RUN-T247-BENCHMARK <current_database>",
    )
    parser.add_argument(
        "--skip-free-space-check",
        action="store_true",
        help="Disable backup free-space preflight for benchmark-only runs.",
    )
    parser.add_argument(
        "--exclude-materialized-view-data",
        action="store_true",
        help="Pass include_materialized_views=false to backup jobs.",
    )
    parser.add_argument("--no-analyze", action="store_true", help="Skip ANALYZE after restore.")
    parser.add_argument(
        "--no-smoke-test",
        action="store_true",
        help="Skip restore smoke test.",
    )
    parser.add_argument(
        "--no-row-count-check",
        action="store_true",
        help="Skip restore row-count reconcile.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Record failed matrix rows and continue. Default stops on first failure.",
    )
    parser.add_argument(
        "--connect-timeout-s",
        type=int,
        default=10,
        help="PostgreSQL connection timeout for benchmark connections.",
    )
    return parser


def build_matrix(
    *,
    profiles: Sequence[BackupProfileName] = DEFAULT_PROFILES,
    jobs: Sequence[int] = DEFAULT_JOBS,
    compression_levels: Sequence[int] = DEFAULT_COMPRESSION_LEVELS,
    target_prefix: str = "ktg_t247_restore",
) -> tuple[BackupRestorePlanItem, ...]:
    items: list[BackupRestorePlanItem] = []
    for profile in profiles:
        for job_count in jobs:
            _validate_jobs(job_count)
            for level in compression_levels:
                _validate_compression_level(level)
                profile_id = f"{_slug(profile)}_j{job_count}_z{level}"
                items.append(
                    BackupRestorePlanItem(
                        profile_id=profile_id,
                        profile=profile,
                        jobs=job_count,
                        compression_level=level,
                        target_database=target_database_name(target_prefix, profile_id),
                    )
                )
    return tuple(items)


def target_database_name(prefix: str, profile_id: str) -> str:
    raw = f"{_slug(prefix)}_{profile_id}"
    if len(raw) <= 63:
        return validate_database_identifier(raw, "target_database")
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    max_base = 63 - len(digest) - 1
    return validate_database_identifier(f"{raw[:max_base]}_{digest}", "target_database")


def required_confirmation(database: str | None) -> str:
    if database is None:
        return "RUN-T247-BENCHMARK <database>"
    return f"RUN-T247-BENCHMARK {database}"


def validate_execute_confirmation(
    *,
    execute: bool,
    database: str | None,
    confirmation: str | None,
) -> None:
    if not execute:
        return
    expected = required_confirmation(database)
    if confirmation != expected:
        msg = f"--execute requires --confirmation {expected!r}"
        raise ValueError(msg)


def summarize_results(
    results: Sequence[BackupRestoreResult],
) -> tuple[BackupRestoreProfileSummary, ...]:
    summaries: list[BackupRestoreProfileSummary] = []
    profiles = sorted({row.profile for row in results})
    for profile in profiles:
        rows = [
            row
            for row in results
            if row.profile == profile
            and row.ok
            and row.backup_seconds is not None
            and row.restore_seconds is not None
        ]
        fastest_total = min(
            rows,
            key=lambda row: (row.backup_seconds or 0) + (row.restore_seconds or 0),
            default=None,
        )
        fastest_backup = min(rows, key=lambda row: row.backup_seconds or 0, default=None)
        fastest_restore = min(rows, key=lambda row: row.restore_seconds or 0, default=None)
        rows_with_archive = [row for row in rows if row.archive_bytes is not None]
        smallest_archive = min(
            rows_with_archive,
            key=lambda row: row.archive_bytes or 0,
            default=None,
        )
        rows_with_ratio = [row for row in rows if row.compression_ratio is not None]
        best_ratio = max(rows_with_ratio, key=lambda row: row.compression_ratio or 0, default=None)
        summaries.append(
            BackupRestoreProfileSummary(
                profile=profile,
                result_count=len(rows),
                fastest_total_profile_id=fastest_total.profile_id if fastest_total else None,
                fastest_total_seconds=_total_seconds(fastest_total),
                fastest_backup_profile_id=fastest_backup.profile_id if fastest_backup else None,
                fastest_backup_seconds=fastest_backup.backup_seconds if fastest_backup else None,
                fastest_restore_profile_id=fastest_restore.profile_id if fastest_restore else None,
                fastest_restore_seconds=(
                    fastest_restore.restore_seconds if fastest_restore else None
                ),
                smallest_archive_profile_id=(
                    smallest_archive.profile_id if smallest_archive else None
                ),
                smallest_archive_bytes=smallest_archive.archive_bytes if smallest_archive else None,
                best_compression_ratio_profile_id=best_ratio.profile_id if best_ratio else None,
                best_compression_ratio=best_ratio.compression_ratio if best_ratio else None,
                low_power_note=_low_power_note(profile, fastest_total, smallest_archive),
            )
        )
    return tuple(summaries)


def report_to_json(report: BackupRestoreBenchmarkReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2)


async def _async_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = args.run_id or datetime.now(UTC).strftime("t247-backup-restore-%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or Path("artifacts") / "perf" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = args.backup_dir or output_dir / "backups"
    temp_dir = args.temp_dir or output_dir / "tmp"
    settings = _settings_for_run(
        args,
        backup_dir=backup_dir,
        temp_dir=temp_dir,
    )
    current_database = database_name_from_dsn(settings.pg_dsn)
    validate_execute_confirmation(
        execute=args.execute,
        database=current_database,
        confirmation=args.confirmation,
    )
    plan = build_matrix(
        profiles=tuple(args.profile or DEFAULT_PROFILES),
        jobs=tuple(args.jobs or DEFAULT_JOBS),
        compression_levels=tuple(args.compression_level or DEFAULT_COMPRESSION_LEVELS),
        target_prefix=args.target_prefix,
    )
    (output_dir / "matrix-plan.json").write_text(
        json.dumps([asdict(item) for item in plan], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    started_at = datetime.now(UTC).isoformat()
    results: tuple[BackupRestoreResult, ...] = ()
    database_size_bytes: int | None = None
    mode: Literal["plan", "execute"] = "execute" if args.execute else "plan"
    if args.execute:
        _require_tools()
        engine = make_async_engine(
            settings,
            connect_args={"connect_timeout": args.connect_timeout_s},
        )
        try:
            database_size_bytes = await _database_size_bytes(engine)
            results = await _execute_matrix(
                engine,
                settings,
                plan,
                run_id=run_id,
                output_dir=output_dir,
                include_materialized_views=not args.exclude_materialized_view_data,
                run_analyze=not args.no_analyze,
                run_smoke_test=not args.no_smoke_test,
                run_row_count_check=not args.no_row_count_check,
                continue_on_error=args.continue_on_error,
            )
        finally:
            await engine.dispose()
    report = BackupRestoreBenchmarkReport(
        schema_version=T247_SCHEMA_VERSION,
        task_id="T-247",
        run_id=run_id,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        mode=mode,
        plan=plan,
        results=results,
        summaries=summarize_results(results),
        environment=BackupRestoreEnvironment(
            run_id=run_id,
            started_at=started_at,
            git_commit=_git_output("rev-parse", "HEAD"),
            git_branch=_git_output("branch", "--show-current"),
            python_version=platform.python_version(),
            platform=platform.platform(),
            cpu_count=os.cpu_count(),
            cwd=str(Path.cwd()),
            mode=mode,
            pg_dsn=redact_dsn(settings.pg_dsn),
            current_database=current_database,
            database_size_bytes=database_size_bytes,
            backup_allowed_dir=str(backup_dir),
            backup_temp_dir=str(temp_dir),
            include_materialized_views=not args.exclude_materialized_view_data,
            run_analyze=not args.no_analyze,
            run_smoke_test=not args.no_smoke_test,
            run_row_count_check=not args.no_row_count_check,
        ),
    )
    (output_dir / "benchmark-report.json").write_text(
        report_to_json(report) + "\n",
        encoding="utf-8",
    )
    write_summary_markdown(report, output_dir / "summary.md")
    print(output_dir)
    return 0


async def _execute_matrix(
    engine: AsyncEngine,
    settings: Settings,
    plan: Sequence[BackupRestorePlanItem],
    *,
    run_id: str,
    output_dir: Path,
    include_materialized_views: bool,
    run_analyze: bool,
    run_smoke_test: bool,
    run_row_count_check: bool,
    continue_on_error: bool,
) -> tuple[BackupRestoreResult, ...]:
    results: list[BackupRestoreResult] = []
    for item in plan:
        try:
            results.append(
                await _execute_item(
                    engine,
                    settings,
                    item,
                    run_id=run_id,
                    output_dir=output_dir,
                    include_materialized_views=include_materialized_views,
                    run_analyze=run_analyze,
                    run_smoke_test=run_smoke_test,
                    run_row_count_check=run_row_count_check,
                )
            )
        except Exception as exc:
            if not continue_on_error:
                raise
            results.append(_failed_result(item, str(exc)))
    return tuple(results)


async def _execute_item(
    engine: AsyncEngine,
    settings: Settings,
    item: BackupRestorePlanItem,
    *,
    run_id: str,
    output_dir: Path,
    include_materialized_views: bool,
    run_analyze: bool,
    run_smoke_test: bool,
    run_row_count_check: bool,
) -> BackupRestoreResult:
    repo = AdminRepository(engine)
    display_name = f"{run_id}_{item.profile_id}_{uuid4().hex[:8]}.tar.zst"
    backup_payload = {
        "profile": item.profile,
        "jobs": item.jobs,
        "compression_level": item.compression_level,
        "display_name": display_name,
        "include_materialized_views": include_materialized_views,
    }
    started = time.perf_counter()
    await run_backup_job(engine, settings, backup_payload, asyncio.Event(), _noop_progress)
    backup_seconds = time.perf_counter() - started
    artifact = await _find_artifact(repo, display_name)
    if artifact.storage_uri is None:
        msg = f"backup artifact has no storage_uri: {artifact.artifact_id}"
        raise RuntimeError(msg)
    archive_path = Path(artifact.storage_uri)
    archive_bytes = archive_path.stat().st_size
    size_started = time.perf_counter()
    dump_bytes = await _dump_size_from_archive(
        archive_path,
        output_dir / "size-probe" / item.profile_id,
    )
    size_probe_seconds = time.perf_counter() - size_started
    await drop_database(settings.pg_dsn, item.target_database)
    await create_database(settings.pg_dsn, item.target_database)
    try:
        restore_payload = {
            "artifact_id": artifact.artifact_id,
            "target_database": item.target_database,
            "mode": "new_database",
            "jobs": item.jobs,
            "run_analyze": run_analyze,
            "run_smoke_test": run_smoke_test,
            "run_row_count_check": run_row_count_check,
        }
        restore_started = time.perf_counter()
        await run_restore_job(engine, settings, restore_payload, asyncio.Event(), _noop_progress)
        restore_seconds = time.perf_counter() - restore_started
    finally:
        await drop_database(settings.pg_dsn, item.target_database)
    return BackupRestoreResult(
        profile_id=item.profile_id,
        profile=item.profile,
        jobs=item.jobs,
        compression_level=item.compression_level,
        target_database=item.target_database,
        ok=True,
        error=None,
        artifact_id=artifact.artifact_id,
        archive_path=str(archive_path),
        backup_seconds=round(backup_seconds, 3),
        restore_seconds=round(restore_seconds, 3),
        size_probe_seconds=round(size_probe_seconds, 3),
        dump_bytes=dump_bytes,
        archive_bytes=archive_bytes,
        compression_ratio=round(dump_bytes / archive_bytes, 4) if archive_bytes else None,
        archive_to_dump_ratio=round(archive_bytes / dump_bytes, 4) if dump_bytes else None,
    )


async def _find_artifact(repo: AdminRepository, display_name: str) -> OpsArtifact:
    artifacts = await repo.list_artifacts(
        limit=50,
        artifact_type=BACKUP_ARTIFACT_TYPE,
        state="available",
    )
    for artifact in artifacts:
        if artifact.display_name == display_name:
            return artifact
    msg = f"backup artifact not found for display_name={display_name}"
    raise RuntimeError(msg)


async def _dump_size_from_archive(archive_path: Path, work_dir: Path) -> int:
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    try:
        await _run_command(build_tar_extract_command(archive_path, work_dir).argv)
        return path_size_bytes(work_dir / "dump")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


async def create_database(dsn: str, database: str) -> None:
    database = validate_database_identifier(database, "target_database")
    await _admin_exec(dsn, f"CREATE DATABASE {quote_database_identifier(database)}")


async def drop_database(dsn: str, database: str) -> None:
    database = validate_database_identifier(database, "target_database")
    await _admin_exec(
        dsn,
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = :database AND pid <> pg_backend_pid()",
        {"database": database},
    )
    await _admin_exec(dsn, f"DROP DATABASE IF EXISTS {quote_database_identifier(database)}")


async def _admin_exec(dsn: str, statement: str, params: dict[str, object] | None = None) -> None:
    url = make_url(dsn)
    engine = create_async_engine(
        str(url.set(database="postgres")),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement), params or {})
    finally:
        await engine.dispose()


async def _run_command(argv: tuple[str, ...]) -> None:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace")[:800]
        msg = f"command failed ({process.returncode}): {' '.join(argv)}\n{detail}"
        raise RuntimeError(msg)


async def _database_size_bytes(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        value = await conn.scalar(text("SELECT pg_database_size(current_database())::bigint"))
    return int(value or 0)


def write_summary_markdown(report: BackupRestoreBenchmarkReport, output_path: Path) -> None:
    lines = [
        f"# T-247 백업/복원 벤치마크: {report.run_id}",
        "",
        "## 계획",
        "",
        f"- mode: `{report.mode}`",
        f"- current_database: `{report.environment.current_database}`",
        f"- pg_dsn: `{report.environment.pg_dsn}`",
        f"- include_materialized_views: `{report.environment.include_materialized_views}`",
        f"- run_analyze: `{report.environment.run_analyze}`",
        f"- run_smoke_test: `{report.environment.run_smoke_test}`",
        f"- run_row_count_check: `{report.environment.run_row_count_check}`",
        "",
        "| profile_id | profile | jobs | compression | target_database |",
        "|------------|---------|-----:|------------:|-----------------|",
    ]
    for item in report.plan:
        lines.append(
            f"| `{item.profile_id}` | `{item.profile}` | {item.jobs} | "
            f"{item.compression_level} | `{item.target_database}` |"
        )
    lines.extend(["", "## 결과", ""])
    if not report.results:
        lines.append(
            "계획 전용 실행입니다. 실제 벤치마크를 실행하려면 `--execute --confirmation "
            f"'{required_confirmation(report.environment.current_database)}'`를 사용합니다."
        )
    else:
        lines.extend(
            [
                "| profile_id | ok | 백업 s | 복원 s | dump | archive | ratio | "
                "archive/dump | error |",
                "|------------|----|---------:|----------:|------:|--------:|------:|"
                "-------------:|-------|",
            ]
        )
        for result in report.results:
            lines.append(
                f"| `{result.profile_id}` | `{result.ok}` | "
                f"{_md_num(result.backup_seconds)} | "
                f"{_md_num(result.restore_seconds)} | {_md_bytes(result.dump_bytes)} | "
                f"{_md_bytes(result.archive_bytes)} | "
                f"{_md_num(result.compression_ratio)} | "
                f"{_md_num(result.archive_to_dump_ratio)} | {result.error or ''} |"
            )
    lines.extend(
        [
            "",
            "## N150/Odroid 해석 가이드",
            "",
            "- `jobs=1`: 온도/RAM 여유가 가장 보수적인 저전력 기준값이다.",
            "- `jobs=2`: 4코어 N150/Odroid급 호스트에서 우선 보는 균형 후보인 경우가 많다.",
            "- `jobs=4`: 소요시간은 줄일 수 있지만 CPU, 저장장치 queue, "
            "zstd thread를 포화시킬 수 있다.",
            "- `compression=3`: CPU 비용이 가장 낮아 예약된 로컬 백업의 기본 후보로 본다.",
            "- `compression=9`: 외부 복사 크기와 실행시간의 중간점이다.",
            "- `compression=19`: 아카이브 크기가 가장 중요할 때만 채택 후보로 본다.",
            "",
            "## 최적 행",
            "",
        ]
    )
    if not report.summaries:
        lines.append("아직 실행된 행이 없습니다.")
    else:
        lines.extend(
            [
                "| profile | 총합 최단 | 총합 s | 백업 최단 | 백업 s | "
                "복원 최단 | 복원 s | 최소 archive | archive | 최고 ratio | ratio |",
                "|---------|---------------|--------:|----------------|---------:|"
                "-----------------|----------:|------------------|--------:|------------|------:|",
            ]
        )
        for summary in report.summaries:
            lines.append(
                f"| `{summary.profile}` | `{summary.fastest_total_profile_id}` | "
                f"{_md_num(summary.fastest_total_seconds)} | "
                f"`{summary.fastest_backup_profile_id}` | "
                f"{_md_num(summary.fastest_backup_seconds)} | "
                f"`{summary.fastest_restore_profile_id}` | "
                f"{_md_num(summary.fastest_restore_seconds)} | "
                f"`{summary.smallest_archive_profile_id}` | "
                f"{_md_bytes(summary.smallest_archive_bytes)} | "
                f"`{summary.best_compression_ratio_profile_id}` | "
                f"{_md_num(summary.best_compression_ratio)} |"
            )
        lines.extend(["", "## 절충 메모", ""])
        for summary in report.summaries:
            lines.append(f"- `{summary.profile}`: {summary.low_power_note}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _settings_for_run(
    args: argparse.Namespace,
    *,
    backup_dir: Path,
    temp_dir: Path,
) -> Settings:
    settings = get_settings()
    pg_dsn = normalize_sqlalchemy_dsn(args.pg_dsn) if args.pg_dsn else settings.pg_dsn
    return settings.model_copy(
        update={
            "pg_dsn": pg_dsn,
            "backup_allowed_dirs": (backup_dir,),
            "backup_temp_dir": temp_dir,
            "backup_require_free_space_check": (
                False if args.skip_free_space_check else settings.backup_require_free_space_check
            ),
            "restore_failed_target_cleanup": "drop",
        }
    )


def _validate_jobs(value: int) -> None:
    if value < 1 or value > 64:
        msg = "jobs must be between 1 and 64"
        raise ValueError(msg)


def _validate_compression_level(value: int) -> None:
    if value < 1 or value > 19:
        msg = "compression level must be between 1 and 19"
        raise ValueError(msg)


def _require_tools() -> None:
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        msg = f"missing required backup tools: {', '.join(missing)}"
        raise RuntimeError(msg)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip().lower()).strip("_")
    return slug or "item"


def _total_seconds(row: BackupRestoreResult | None) -> float | None:
    if row is None or row.backup_seconds is None or row.restore_seconds is None:
        return None
    return round(row.backup_seconds + row.restore_seconds, 3)


def _low_power_note(
    profile: BackupProfileName,
    fastest_total: BackupRestoreResult | None,
    smallest_archive: BackupRestoreResult | None,
) -> str:
    if fastest_total is None or smallest_archive is None:
        return (
            "plan-only 또는 실패만 있는 결과다. N150/Odroid에서는 먼저 jobs=1/2와 "
            "compression=3/9의 성공 여부를 확인한다."
        )
    return (
        f"총 소요시간 최단은 `{fastest_total.profile_id}` "
        f"(jobs={fastest_total.jobs}, zstd={fastest_total.compression_level}); "
        f"최소 아카이브는 `{smallest_archive.profile_id}` "
        f"(jobs={smallest_archive.jobs}, zstd={smallest_archive.compression_level}). "
        f"`{profile}`에서는 외부 보관 비용 때문에 더 작은 아카이브가 필요한 경우가 아니면 "
        "총 소요시간 최단 행을 우선 후보로 본다."
    )


def _failed_result(item: BackupRestorePlanItem, error: str) -> BackupRestoreResult:
    return BackupRestoreResult(
        profile_id=item.profile_id,
        profile=item.profile,
        jobs=item.jobs,
        compression_level=item.compression_level,
        target_database=item.target_database,
        ok=False,
        error=error,
        artifact_id=None,
        archive_path=None,
        backup_seconds=None,
        restore_seconds=None,
        size_probe_seconds=None,
        dump_bytes=None,
        archive_bytes=None,
        compression_ratio=None,
        archive_to_dump_ratio=None,
    )


def _git_output(*args: str) -> str | None:
    try:
        return subprocess.check_output(("git", *args), text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _md_num(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.3f}"


def _md_bytes(value: int | None) -> str:
    if value is None:
        return ""
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
