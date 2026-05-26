from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from kraddr.geo.client import AsyncAddressClient
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra.admin_repo import LoadJobRow


def _fake_row(kind: str) -> LoadJobRow:
    return LoadJobRow(
        job_id="batch_test",
        kind=kind,
        state="running" if kind == "full_load_batch" else "queued",
        load_batch_id="batch_test",
        parent_job_id=None,
        progress=0.0,
        current_stage="source_loads" if kind == "full_load_batch" else None,
        source_yyyymm=None,
        source_set=None,
        started_at=None,
        finished_at=None,
        heartbeat_at=None,
        error_message=None,
        log_tail=[],
        payload_summary=None,
    )


@pytest.mark.asyncio
async def test_submit_load_full_load_batch_dispatches_batch_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Library batch submission must go through ``insert_load_batch``.

    Otherwise REST and library surfaces diverge: REST routes ``full_load_batch``
    through the JobQueue (root + children), but the library would silently
    create only the root row, leaving the DAG un-runnable.
    """

    insert_batch = AsyncMock(return_value=_fake_row("full_load_batch"))
    insert_job = AsyncMock(return_value=_fake_row("juso_text_load"))
    monkeypatch.setattr(
        "kraddr.geo.client.AdminRepository.insert_load_batch", insert_batch
    )
    monkeypatch.setattr(
        "kraddr.geo.client.AdminRepository.insert_load_job", insert_job
    )

    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    payload: dict[str, Any] = {
        "source_yyyymm": "202604",
        "payloads": {
            "juso_text_load": {"path": "/data/juso"},
            "juso_parcel_link_load": {"path": "/data/juso"},
            "locsum_load": {"path": "/data/locsum"},
            "navi_load": {"path": "/data/navi"},
            "shp_polygons_load": {"path": "/data/shp"},
            "pobox_load": {"path": "/data/pobox.zip"},
        },
    }
    await client.submit_load("full_load_batch", payload)

    insert_batch.assert_awaited_once()
    insert_job.assert_not_awaited()
    kwargs = insert_batch.await_args.kwargs
    assert kwargs["payload"] is payload
    children_by_kind = dict(kwargs["children"])
    assert children_by_kind["juso_text_load"] == {"path": "/data/juso"}
    assert children_by_kind["juso_parcel_link_load"] == {"path": "/data/juso"}
    assert children_by_kind["locsum_load"] == {"path": "/data/locsum"}
    assert children_by_kind["shp_polygons_load"] == {"path": "/data/shp"}


@pytest.mark.asyncio
async def test_submit_load_full_load_batch_rejects_incomplete_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insert_batch = AsyncMock(return_value=_fake_row("full_load_batch"))
    insert_job = AsyncMock(return_value=_fake_row("juso_text_load"))
    monkeypatch.setattr(
        "kraddr.geo.client.AdminRepository.insert_load_batch", insert_batch
    )
    monkeypatch.setattr(
        "kraddr.geo.client.AdminRepository.insert_load_job", insert_job
    )

    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    with pytest.raises(InvalidInputError, match="juso_parcel_link_load"):
        await client.submit_load(
            "full_load_batch",
            {"payloads": {"juso_text_load": {"path": "/data/juso"}}},
        )

    insert_batch.assert_not_awaited()
    insert_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_load_non_batch_uses_insert_load_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insert_batch = AsyncMock(return_value=_fake_row("full_load_batch"))
    insert_job = AsyncMock(return_value=_fake_row("juso_text_load"))
    monkeypatch.setattr(
        "kraddr.geo.client.AdminRepository.insert_load_batch", insert_batch
    )
    monkeypatch.setattr(
        "kraddr.geo.client.AdminRepository.insert_load_job", insert_job
    )

    client = AsyncAddressClient(engine=object())  # type: ignore[arg-type]
    await client.submit_load("juso_text_load", {"path": "/data/juso"})

    insert_job.assert_awaited_once()
    insert_batch.assert_not_awaited()
