"""T-237 backup source-inventory verification (pure summary).

``summarize_source_inventory`` compares the active match set's expected objects to
what RustFS actually has (presence + size); ``_iter_match_set_files`` extracts the
per-file entries from a nested manifest block. Both are pure (no RustFS/DB), and the
summary never records secrets.
"""

from __future__ import annotations

from kortravelgeo.infra.backup import _iter_match_set_files, summarize_source_inventory


def _file(key: str, size: int) -> dict[str, object]:
    return {"object_key": key, "size_bytes": size}


def test_all_present_and_matching_is_ok() -> None:
    files = [_file("a", 10), _file("b", 20)]
    summary = summarize_source_inventory(files, {"a": 10, "b": 20})
    assert summary["ok"] is True
    assert summary["present"] == 2
    assert summary["missing"] == 0
    assert summary["size_mismatch"] == 0


def test_missing_object_is_flagged() -> None:
    files = [_file("a", 10), _file("b", 20)]
    summary = summarize_source_inventory(files, {"a": 10})  # b absent in storage
    assert summary["ok"] is False
    assert summary["missing"] == 1
    assert any(i["object_key"] == "b" and i["status"] == "missing" for i in summary["items"])


def test_size_mismatch_is_flagged() -> None:
    summary = summarize_source_inventory([_file("a", 10)], {"a": 99})
    assert summary["ok"] is False
    assert summary["size_mismatch"] == 1
    assert summary["present"] == 1


def test_summary_never_records_secrets() -> None:
    assert summarize_source_inventory([], {})["secret_included"] is False


def test_iter_match_set_files_walks_nested_block() -> None:
    block = {
        "source_match_set_id": "ms1",
        "items": [{"role": "x", "groups": [{"files": [_file("k1", 1), _file("k2", 2)]}]}],
    }
    keys = {f["object_key"] for f in _iter_match_set_files(block)}
    assert keys == {"k1", "k2"}
    assert _iter_match_set_files(None) == []
