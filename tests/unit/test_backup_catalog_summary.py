"""T-240 backup catalog manifest-derived fields (pure).

``backup_catalog_summary`` extracts source-set reference months and the (backup-time)
source-inventory status from a backup manifest for the ``GET /v1/admin/backups`` list,
degrading to ``None`` for legacy/skipped/missing data.
"""

from __future__ import annotations

from kortravelgeo.api.routers.admin import backup_catalog_summary


def test_extracts_source_set_and_inventory_ok() -> None:
    manifest = {
        "source_set": {"yyyymm_by_kind": {"juso": "202603"}, "mixed_yyyymm": True},
        "source_inventory_verification": {"ok": True, "missing": 0},
    }
    summary = backup_catalog_summary(manifest)
    assert summary["source_set_yyyymm"] == {"juso": "202603"}
    assert summary["source_set_mixed"] is True
    assert summary["source_inventory_ok"] is True


def test_inventory_not_ok_is_false() -> None:
    summary = backup_catalog_summary({"source_inventory_verification": {"ok": False, "missing": 2}})
    assert summary["source_inventory_ok"] is False


def test_skipped_inventory_is_none() -> None:
    summary = backup_catalog_summary(
        {"source_inventory_verification": {"skipped": True, "reason": "rustfs_unavailable"}}
    )
    assert summary["source_inventory_ok"] is None


def test_missing_manifest_is_graceful() -> None:
    assert backup_catalog_summary(None) == {
        "source_set_yyyymm": None,
        "source_set_mixed": None,
        "source_inventory_ok": None,
    }
    assert backup_catalog_summary({})["source_set_yyyymm"] is None
