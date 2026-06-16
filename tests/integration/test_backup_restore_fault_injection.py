"""T-245 restore fault-injection live integration tests (opt-in).

Reuses the T-244 round-trip fixture to create a real ``pg_dump -Fd`` backup, then
injects archive/checksum failures and proves ``run_restore_job`` refuses the restore
while dropping the job-owned target DB. The suite is skipped unless ``KTG_TEST_PG_DSN``
and the backup CLI tools are available, so regular CI stays green.

Run it with, e.g.:
    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo_rt \
        pytest tests/integration/test_backup_restore_fault_injection.py -q
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.dto.admin import MaintenanceWindowCreate
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra import backup as backup_module
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import (
    BACKUP_ARTIFACT_TYPE,
    build_tar_create_command,
    build_tar_extract_command,
    database_name_from_dsn,
    run_backup_job,
    run_restore_job,
)
from kortravelgeo.infra.engine import make_async_engine
from tests.integration._backup_roundtrip import (
    build_minimal_serving_schema,
    create_database,
    drop_database,
    make_backup,
    missing_requirement,
    roundtrip_settings,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine

    from kortravelgeo.settings import Settings


async def _noop_progress(
    *, progress: float | None = None, stage: str | None = None, message: str | None = None
) -> None:
    _ = (progress, stage, message)


def _skip_if_missing() -> None:
    skip_reason = missing_requirement()
    if skip_reason:
        pytest.skip(skip_reason)
    pytest.importorskip("psycopg")


def _target_dsn(source_dsn: str, database: str) -> str:
    return make_url(source_dsn).set(database=database).render_as_string(hide_password=False)


async def _database_exists(source_dsn: str, database: str) -> bool:
    engine = create_async_engine(
        _target_dsn(source_dsn, "postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as conn:
            value = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :database"),
                {"database": database},
            )
    finally:
        await engine.dispose()
    return value == 1


async def _run_archive_command(argv: tuple[str, ...]) -> None:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace")[:800]
        msg = f"archive command failed ({process.returncode}): {' '.join(argv)}\n{detail}"
        raise AssertionError(msg)


async def _extract_archive(archive_path: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True)
    await _run_archive_command(build_tar_extract_command(archive_path, extract_dir).argv)


async def _create_archive(work_dir: Path, archive_path: Path) -> None:
    await _run_archive_command(
        build_tar_create_command(archive_path, work_dir, compression_level=3).argv
    )


async def _create_archive_without_checksums(work_dir: Path, archive_path: Path) -> None:
    argv = (
        "tar",
        "--use-compress-program=zstd -T0 -3",
        "-cf",
        str(archive_path),
        "-C",
        str(work_dir),
        "manifest.json",
        "logs",
        "dump",
    )
    await _run_archive_command(argv)


async def _mutated_archive(
    source_archive: Path,
    work_root: Path,
    name: str,
    mutate: Callable[[Path], None],
    *,
    include_checksums: bool = True,
) -> Path:
    extract_dir = work_root / f"{name}_extract"
    archive_path = work_root / f"{name}.tar.zst"
    await _extract_archive(source_archive, extract_dir)
    mutate(extract_dir)
    if include_checksums:
        await _create_archive(extract_dir, archive_path)
    else:
        await _create_archive_without_checksums(extract_dir, archive_path)
    return archive_path


def _forge_manifest_checksum(extract_dir: Path) -> None:
    checksum_file = extract_dir / "checksums.sha256"
    lines = checksum_file.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.endswith("  manifest.json"):
            lines[index] = f"{'0' * 64}  manifest.json"
            replaced = True
            break
    if not replaced:
        msg = "manifest.json checksum line not found"
        raise AssertionError(msg)
    checksum_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _remove_internal_checksums(extract_dir: Path) -> None:
    (extract_dir / "checksums.sha256").unlink()


async def _expect_restore_failure_drops_target(
    engine: AsyncEngine,
    settings: Settings,
    *,
    source_dsn: str,
    payload: dict[str, object],
    target_database: str,
) -> None:
    await drop_database(source_dsn, target_database)
    await create_database(source_dsn, target_database)
    try:
        with pytest.raises(Exception) as exc_info:
            await run_restore_job(engine, settings, payload, asyncio.Event(), _noop_progress)
        assert not isinstance(exc_info.value, asyncio.CancelledError)
        assert await _database_exists(source_dsn, target_database) is False
    finally:
        await drop_database(source_dsn, target_database)


@pytest.mark.asyncio
async def test_restore_rejects_corrupt_archives_and_drops_target(tmp_path: Path) -> None:
    _skip_if_missing()

    import os

    source_dsn = os.environ["KTG_TEST_PG_DSN"]
    settings = roundtrip_settings(source_dsn, tmp_path).model_copy(
        update={"restore_failed_target_cleanup": "drop"}
    )
    engine = make_async_engine(settings)
    try:
        await build_minimal_serving_schema(engine)
        artifact_id = await make_backup(engine, settings)
        repo = AdminRepository(engine)
        artifact = await repo.get_artifact(artifact_id)
        assert artifact is not None
        assert artifact.storage_uri is not None
        source_archive = Path(artifact.storage_uri)

        await repo.update_artifact(artifact_id, sha256="0" * 64)
        await _expect_restore_failure_drops_target(
            engine,
            settings,
            source_dsn=source_dsn,
            payload={
                "artifact_id": artifact_id,
                "target_database": "ktg_t245_sha_flip",
                "mode": "new_database",
            },
            target_database="ktg_t245_sha_flip",
        )

        truncated_archive = tmp_path / "backups" / "t245_truncated.tar.zst"
        shutil.copyfile(source_archive, truncated_archive)
        truncated_archive.chmod(0o600)
        with truncated_archive.open("r+b") as fh:
            fh.truncate(max(1, source_archive.stat().st_size // 2))
        await _expect_restore_failure_drops_target(
            engine,
            settings,
            source_dsn=source_dsn,
            payload={
                "archive_path": str(truncated_archive),
                "target_database": "ktg_t245_truncated",
                "mode": "new_database",
            },
            target_database="ktg_t245_truncated",
        )

        forged_archive = await _mutated_archive(
            source_archive,
            tmp_path / "backups",
            "t245_internal_checksum_forged",
            _forge_manifest_checksum,
        )
        await _expect_restore_failure_drops_target(
            engine,
            settings,
            source_dsn=source_dsn,
            payload={
                "archive_path": str(forged_archive),
                "target_database": "ktg_t245_checksum_forged",
                "mode": "new_database",
            },
            target_database="ktg_t245_checksum_forged",
        )

        missing_checksum_archive = await _mutated_archive(
            source_archive,
            tmp_path / "backups",
            "t245_missing_internal_checksum",
            _remove_internal_checksums,
            include_checksums=False,
        )
        await _expect_restore_failure_drops_target(
            engine,
            settings,
            source_dsn=source_dsn,
            payload={
                "archive_path": str(missing_checksum_archive),
                "target_database": "ktg_t245_missing_checksum",
                "mode": "new_database",
            },
            target_database="ktg_t245_missing_checksum",
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_backup_marks_failed_and_removes_partials(tmp_path: Path) -> None:
    _skip_if_missing()

    import os

    source_dsn = os.environ["KTG_TEST_PG_DSN"]
    settings = roundtrip_settings(source_dsn, tmp_path)
    engine = make_async_engine(settings)
    display_name = f"t245_cancel_{uuid4().hex}.tar.zst"
    cancel_event = asyncio.Event()
    cancel_event.set()
    try:
        await build_minimal_serving_schema(engine)
        with pytest.raises(asyncio.CancelledError):
            await run_backup_job(
                engine,
                settings,
                {
                    "profile": "serving-ready",
                    "jobs": 1,
                    "compression_level": 3,
                    "display_name": display_name,
                },
                cancel_event,
                _noop_progress,
            )
        failed_artifacts = await AdminRepository(engine).list_artifacts(
            limit=20, artifact_type=BACKUP_ARTIFACT_TYPE, state="failed"
        )
        failed = [
            artifact
            for artifact in failed_artifacts
            if artifact.display_name == display_name
        ]
        assert len(failed) == 1
        assert failed[0].manifest == {"error": "cancelled"}

        archive_path = tmp_path / "backups" / display_name
        assert not archive_path.exists()
        assert not archive_path.with_name(f"{archive_path.name}.part").exists()
        tmp_dir = tmp_path / "tmp"
        assert not list(tmp_dir.glob("backup_*")) if tmp_dir.exists() else True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_replace_current_guards_reject_target_dsn_confirmation_and_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _skip_if_missing()

    import os

    source_dsn = os.environ["KTG_TEST_PG_DSN"]
    settings = roundtrip_settings(source_dsn, tmp_path)
    engine = make_async_engine(settings)
    try:
        await build_minimal_serving_schema(engine)
        artifact_id = await make_backup(engine, settings)
        current_database = database_name_from_dsn(settings.pg_dsn)
        assert current_database is not None
        expected_confirmation = f"RESTORE {current_database}"

        with pytest.raises(InvalidInputError, match="requires target_database"):
            await run_restore_job(
                engine,
                settings,
                {
                    "artifact_id": artifact_id,
                    "target_dsn": settings.pg_dsn,
                    "mode": "replace_current",
                    "confirmation": expected_confirmation,
                },
                asyncio.Event(),
                _noop_progress,
            )

        with pytest.raises(InvalidInputError, match="requires confirmation"):
            await run_restore_job(
                engine,
                settings,
                {
                    "artifact_id": artifact_id,
                    "target_database": current_database,
                    "mode": "replace_current",
                    "confirmation": "RESTORE wrong_database",
                },
                asyncio.Event(),
                _noop_progress,
            )

        repo = AdminRepository(engine)
        wrong_window_confirmation = f"RESTORE wrong_window_{uuid4().hex[:8]}"
        window = await repo.create_maintenance_window(
            MaintenanceWindowCreate(
                kind="restore",
                reason="T-245 wrong-confirmation maintenance window guard",
                confirmation=wrong_window_confirmation,
                requested_by="pytest",
                approved_by="pytest",
            )
        )
        try:
            def fail_if_restore_reaches_pg_restore(*_args: object, **_kwargs: object) -> None:
                msg = "replace_current window guard unexpectedly reached pg_restore"
                raise AssertionError(msg)

            monkeypatch.setattr(
                backup_module,
                "build_pg_restore_command",
                fail_if_restore_reaches_pg_restore,
            )
            with pytest.raises(
                InvalidInputError,
                match="active restore maintenance window with matching confirmation",
            ):
                await run_restore_job(
                    engine,
                    settings,
                    {
                        "artifact_id": artifact_id,
                        "target_database": current_database,
                        "mode": "replace_current",
                        "confirmation": expected_confirmation,
                    },
                    asyncio.Event(),
                    _noop_progress,
                )

            with pytest.raises(
                InvalidInputError,
                match="active restore maintenance window with matching confirmation",
            ):
                await repo.require_active_maintenance_window(
                    kind="restore",
                    confirmation=expected_confirmation,
                )
        finally:
            await repo.end_maintenance_window(
                maintenance_window_id=window.maintenance_window_id,
                confirmation=wrong_window_confirmation,
            )
    finally:
        await engine.dispose()
