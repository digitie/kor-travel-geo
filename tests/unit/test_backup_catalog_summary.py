"""T-240 backup catalog manifest-derived fields (pure).

``backup_catalog_summary`` extracts source-set reference months and the (backup-time)
source-inventory status from a backup manifest for the ``GET /v1/admin/backups`` list,
degrading to ``None`` for legacy/skipped/missing data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from kortravelgeo.api.routers.admin import backup_catalog_summary, list_backups


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


class _RecordingClient:
    """Captures the kwargs ``list_backups`` forwards to ``client.list_artifacts``."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def list_artifacts(self, **kwargs: Any) -> list[Any]:
        self.calls.append(kwargs)
        return []


@pytest.mark.asyncio
async def test_list_backups_pushes_expiry_cutoff_into_query() -> None:
    # T-240 follow-up (Codex review): the expiry filter must be a SQL predicate so LIMIT
    # acts on the filtered set, not a Python filter applied after fetching the newest N.
    client = _RecordingClient()
    before = datetime.now(UTC) + timedelta(days=7)
    result = await list_backups(
        limit=50, state=None, expiring_within_days=7, client=client  # type: ignore[arg-type]
    )
    after = datetime.now(UTC) + timedelta(days=7)
    assert result == []
    call = client.calls[0]
    assert call["limit"] == 50
    assert call["expires_before"] is not None
    assert before <= call["expires_before"] <= after


@pytest.mark.asyncio
async def test_list_backups_without_filter_passes_no_cutoff() -> None:
    client = _RecordingClient()
    await list_backups(
        limit=50, state=None, expiring_within_days=None, client=client  # type: ignore[arg-type]
    )
    assert client.calls[0]["expires_before"] is None
