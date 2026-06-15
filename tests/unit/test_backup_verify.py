"""T-231 on-demand backup integrity verification (quick mode).

``verify_backup_artifact`` is non-destructive and returns a structured result —
corruption is ``ok=False`` with ``errors``, never an exception — so an operator can
probe bit rot without attempting a restore. Quick mode only recomputes the archive
sha256, so these tests need no ``tar``/``zstd`` (deep mode is covered by the fault
-injection integration in T-245).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.dto.admin import OpsArtifact
from kortravelgeo.infra.backup import sha256_file, verify_backup_artifact
from kortravelgeo.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


def _artifact(storage_uri: str | None, *, sha256: str | None = None) -> OpsArtifact:
    return OpsArtifact(
        artifact_id="b1",
        artifact_type="db_backup",
        state="available",
        storage_kind="local_file",
        storage_uri=storage_uri,
        sha256=sha256,
        created_at=datetime.now(UTC),
    )


async def _hash(path: Path) -> str:
    return await sha256_file(path, cancel_event=asyncio.Event())


def _settings(root: Path) -> Settings:
    return Settings(backup_allowed_dirs=(root,))


@pytest.mark.asyncio
async def test_quick_ok_when_sha256_matches(tmp_path: Path) -> None:
    archive = tmp_path / "backup.tar.zst"
    archive.write_bytes(b"hello backup")
    digest = await _hash(archive)
    result = await verify_backup_artifact(
        _artifact(str(archive), sha256=digest), _settings(tmp_path), mode="quick"
    )
    assert result.ok is True
    assert result.archive_sha256 == digest
    assert result.archive_sha256_matches is True
    assert result.errors == ()


@pytest.mark.asyncio
async def test_quick_reports_mismatch_without_raising(tmp_path: Path) -> None:
    archive = tmp_path / "backup.tar.zst"
    archive.write_bytes(b"hello backup")
    result = await verify_backup_artifact(
        _artifact(str(archive), sha256="0" * 64), _settings(tmp_path), mode="quick"
    )
    assert result.ok is False
    assert result.archive_sha256_matches is False
    assert any("sha256 mismatch" in err for err in result.errors)


@pytest.mark.asyncio
async def test_missing_storage_uri_is_not_ok(tmp_path: Path) -> None:
    result = await verify_backup_artifact(_artifact(None), _settings(tmp_path), mode="quick")
    assert result.ok is False
    assert any("storage_uri" in err for err in result.errors)


@pytest.mark.asyncio
async def test_missing_archive_file_is_not_ok(tmp_path: Path) -> None:
    result = await verify_backup_artifact(
        _artifact(str(tmp_path / "nope.tar.zst")), _settings(tmp_path), mode="quick"
    )
    assert result.ok is False
    assert any("unavailable" in err for err in result.errors)


@pytest.mark.asyncio
async def test_no_recorded_sha256_is_unknown_not_failure(tmp_path: Path) -> None:
    # legacy backup without a recorded sha256: quick can't compare but it isn't a fail.
    archive = tmp_path / "backup.tar.zst"
    archive.write_bytes(b"x")
    result = await verify_backup_artifact(
        _artifact(str(archive), sha256=None), _settings(tmp_path), mode="quick"
    )
    assert result.ok is True
    assert result.archive_sha256_matches is None
    assert result.archive_sha256 is not None
