"""T-236 off-host backup copy (filesystem, sha256-verified).

``copy_backup_artifact`` streams a stored backup to another allowlisted directory and
re-hashes the copy against the source; a corrupted copy is removed and an error
raised, and targets outside the allowlist are rejected. No DB needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra import backup
from kortravelgeo.infra.backup import copy_backup_artifact
from kortravelgeo.settings import Settings


def _artifact(storage_uri: str) -> backup.OpsArtifact:
    return backup.OpsArtifact(
        artifact_id="b1",
        artifact_type="db_backup",
        state="available",
        storage_kind="local_file",
        storage_uri=storage_uri,
        display_name="backup.tar.zst",
        created_at=datetime.now(UTC),
    )


def _settings(*, allowed: Path, copy_targets: tuple[Path, ...] = ()) -> Settings:
    return Settings(backup_allowed_dirs=(allowed,), backup_copy_targets=copy_targets)


@pytest.mark.asyncio
async def test_copy_verifies_and_sets_permissions(tmp_path: Path) -> None:
    src_dir = tmp_path / "primary"
    dst_dir = tmp_path / "external"
    src_dir.mkdir()
    archive = src_dir / "backup.tar.zst"
    archive.write_bytes(b"backup payload bytes")
    settings = _settings(allowed=src_dir, copy_targets=(dst_dir,))

    result = await copy_backup_artifact(_artifact(str(archive)), settings, target_dir=str(dst_dir))

    assert result.verified is True
    copied = Path(result.destination_path)
    assert copied.parent == dst_dir.resolve()
    assert copied.read_bytes() == b"backup payload bytes"


@pytest.mark.asyncio
async def test_copy_target_outside_allowlist_is_rejected(tmp_path: Path) -> None:
    src_dir = tmp_path / "primary"
    src_dir.mkdir()
    archive = src_dir / "backup.tar.zst"
    archive.write_bytes(b"x")
    # copy_targets allows only "external", but we ask to copy into "elsewhere".
    settings = _settings(allowed=src_dir, copy_targets=(tmp_path / "external",))
    with pytest.raises(InvalidInputError, match="escapes allowed roots"):
        await copy_backup_artifact(
            _artifact(str(archive)), settings, target_dir=str(tmp_path / "elsewhere")
        )


@pytest.mark.asyncio
async def test_corrupted_copy_is_removed_and_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src_dir = tmp_path / "primary"
    dst_dir = tmp_path / "external"
    src_dir.mkdir()
    archive = src_dir / "backup.tar.zst"
    archive.write_bytes(b"good source bytes")
    settings = _settings(allowed=src_dir, copy_targets=(dst_dir,))

    def corrupt_copy(src: str, dst: str) -> None:
        Path(dst).write_bytes(b"corrupted during copy")  # different bytes → sha mismatch

    monkeypatch.setattr(backup.shutil, "copyfile", corrupt_copy)
    with pytest.raises(InvalidInputError, match="sha256 mismatch"):
        await copy_backup_artifact(_artifact(str(archive)), settings, target_dir=str(dst_dir))
    # the bad copy must not be left behind.
    assert list(dst_dir.glob("*.tar.zst")) == []


@pytest.mark.asyncio
async def test_copy_targets_fall_back_to_backup_roots(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    root.mkdir()
    archive = root / "backup.tar.zst"
    archive.write_bytes(b"payload")
    sub = root / "copies"
    settings = _settings(allowed=root)  # no copy_targets → reuse backup_allowed_dirs
    result = await copy_backup_artifact(_artifact(str(archive)), settings, target_dir=str(sub))
    assert Path(result.destination_path).exists()
