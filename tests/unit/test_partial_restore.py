"""T-243 partial-restore planning (pure).

The live ``pg_restore --use-list`` flow needs a real corrupted dump and is integration-tested
in T-245. These cover the pure decisions: mapping ``dump/<id>.dat`` to a TOC dumpId, splitting
corrupted files into hard-fail (manifest/toc) vs. skippable data files, and commenting out the
corrupted entries in a ``pg_restore -l`` listing so only intact tables are restored.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.backup import _plan_partial_restore

if TYPE_CHECKING:
    from pathlib import Path
from kortravelgeo.infra.partial_restore import (
    build_partial_restore_uselist,
    partial_restore_block,
    partial_restore_data_id,
    partition_checksum_failures,
)


def test_data_id_only_for_table_data_files() -> None:
    assert partial_restore_data_id("dump/2841.dat") == "2841"
    assert partial_restore_data_id("dump/2841.dat.gz") == "2841"
    assert partial_restore_data_id("manifest.json") is None
    assert partial_restore_data_id("dump/toc.dat") is None
    assert partial_restore_data_id("dump/blobs.toc") is None


def test_partition_all_data_files_is_partial_restorable() -> None:
    part = partition_checksum_failures(["dump/2.dat", "dump/1.dat"])
    assert part.critical == ()
    assert part.skippable_data_ids == ("1", "2")  # sorted
    assert part.can_partial_restore is True


def test_partition_with_critical_file_blocks_partial() -> None:
    part = partition_checksum_failures(["manifest.json", "dump/1.dat"])
    assert "manifest.json" in part.critical
    assert part.can_partial_restore is False


def test_partition_corrupt_toc_blocks_partial() -> None:
    part = partition_checksum_failures(["dump/toc.dat"])
    assert part.critical == ("dump/toc.dat",)
    assert part.can_partial_restore is False


def test_partition_no_failures_is_not_partial() -> None:
    # nothing corrupted → there is nothing to "partially" recover from
    assert partition_checksum_failures([]).can_partial_restore is False


def test_uselist_comments_only_corrupted_entries() -> None:
    toc = [
        ";",
        "; Selected TOC Entries:",
        ";",
        "2840; 1262 16384 DATABASE - kor_travel_geo owner",
        "2841; 0 16385 TABLE DATA public roads owner",
        "2842; 0 16386 TABLE DATA public buildings owner",
    ]
    result = build_partial_restore_uselist(toc, {"2842"})
    # the corrupted data entry is commented out; everything else is verbatim
    assert ";2842; 0 16386 TABLE DATA public buildings owner" in result.lines
    assert "2841; 0 16385 TABLE DATA public roads owner" in result.lines
    assert "2840; 1262 16384 DATABASE - kor_travel_geo owner" in result.lines
    assert result.skipped_ids == ("2842",)
    assert any("buildings" in entry for entry in result.skipped_entries)
    # comment/header lines are preserved untouched
    assert "; Selected TOC Entries:" in result.lines


def test_uselist_keeps_all_when_nothing_corrupted() -> None:
    toc = ["2841; 0 16385 TABLE DATA public roads owner"]
    result = build_partial_restore_uselist(toc, set())
    assert result.lines == ("2841; 0 16385 TABLE DATA public roads owner",)
    assert result.skipped_ids == ()


def test_partial_restore_block_records_skips() -> None:
    part = partition_checksum_failures(["dump/2842.dat"])
    use_list = build_partial_restore_uselist(
        ["2842; 0 16386 TABLE DATA public buildings owner"], {"2842"}
    )
    block = partial_restore_block(part, use_list)
    assert block["enabled"] is True
    assert block["skipped_count"] == 1
    assert block["skipped_data_ids"] == ["2842"]
    assert block["skipped_files"] == ["dump/2842.dat"]


# --- T-243 fix (Codex H review): the downgraded archive-level sha256 mismatch must reach
# per-file partition planning, and corrupt critical files must still hard-fail. Filesystem
# only (no DB / pg_restore), exercising _plan_partial_restore's pre-pg_restore branches.


async def _noop_progress(
    *, progress: float | None = None, stage: str | None = None, message: str | None = None
) -> None:
    return None


def _write_extract(
    extract: Path, files: dict[str, bytes], *, corrupt: set[str] | None = None
) -> None:
    (extract / "dump").mkdir(parents=True)
    lines = []
    for rel, content in files.items():
        (extract / rel).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        if corrupt and rel in corrupt:
            digest = "0" * 64  # recorded digest no longer matches the file → "corrupted"
        lines.append(f"{digest}  {rel}")
    (extract / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_plan_partial_restore_records_archive_warning_when_internals_ok(
    tmp_path: Path,
) -> None:
    # artifact_id restore with a recorded archive sha256: bit rot fails the archive check,
    # but if every internal checksum still passes the dump is intact → proceed (full restore)
    # and record the downgraded warning instead of hard-failing before the partial path.
    extract = tmp_path / "extract"
    _write_extract(
        extract,
        {"manifest.json": b'{"database":{}}', "dump/toc.dat": b"toc", "dump/2841.dat": b"data"},
    )
    block, use_list = await _plan_partial_restore(
        extract,
        extract / "dump",
        tmp_path / "work",
        cancel_event=asyncio.Event(),
        progress=_noop_progress,
        archive_checksum_warning="archive sha256 mismatch",
    )
    assert use_list is None
    assert block == {
        "enabled": False,
        "skipped_count": 0,
        "archive_sha256_warning": "archive sha256 mismatch",
    }


@pytest.mark.asyncio
async def test_plan_partial_restore_hard_fails_on_corrupt_manifest(tmp_path: Path) -> None:
    extract = tmp_path / "extract"
    _write_extract(
        extract,
        {"manifest.json": b'{"database":{}}', "dump/toc.dat": b"toc"},
        corrupt={"manifest.json"},
    )
    with pytest.raises(InvalidInputError, match="critical files corrupted"):
        await _plan_partial_restore(
            extract,
            extract / "dump",
            tmp_path / "work",
            cancel_event=asyncio.Event(),
            progress=_noop_progress,
        )
