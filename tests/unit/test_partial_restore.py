"""T-243 partial-restore planning (pure).

The live ``pg_restore --use-list`` flow needs a real corrupted dump and is integration-tested
in T-245. These cover the pure decisions: mapping ``dump/<id>.dat`` to a TOC dumpId, splitting
corrupted files into hard-fail (manifest/toc) vs. skippable data files, and commenting out the
corrupted entries in a ``pg_restore -l`` listing so only intact tables are restored.
"""

from __future__ import annotations

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
