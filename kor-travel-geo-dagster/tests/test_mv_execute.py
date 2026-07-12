"""mv op wiring tests (T-290k): config -> bridge -> run_mv_refresh leaf (release-gated).

Asserts the rebuilt mv_refresh op drives the main-lib ``run_mv_refresh`` leaf (which does
resolve_text_geometry_links -> release gate -> swap -> record_mv_refresh_release) rather than
the old wiring-proof ``refresh_mv``-only body that dropped the release/gate semantics.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from dagster import build_op_context
from kortravelgeo.settings import Settings

from kortravelgeo_dagster import mv


class _FakeClient:
    def __init__(self, engine: object) -> None:
        self._eng = engine

    def _engine(self) -> object:
        return self._eng


async def _noop_progress(*, progress=None, stage=None, message=None):
    return None


@pytest.mark.asyncio
async def test_run_mv_refresh_op_drives_release_gated_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf, **kwargs):
        captured["job_id"] = job_id
        captured["engine"] = engine
        captured["lease_ttl_seconds"] = kwargs.get("lease_ttl_seconds")
        await leaf(asyncio.Event(), _noop_progress)

    async def fake_run_mv_refresh(engine, *, payload, job_id, progress):
        # This is the release-gated leaf (not the bare refresh_mv); assert it is the one called.
        captured["leaf_engine"] = engine
        captured["leaf_payload"] = payload
        captured["leaf_job_id"] = job_id

    monkeypatch.setattr(mv, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(mv, "run_mv_refresh", fake_run_mv_refresh)

    sentinel_engine = object()
    settings = Settings(_env_file=None)

    with build_op_context(
        resources={"client": _FakeClient(sentinel_engine), "settings": settings},
        op_config={"job_id": "mv-1", "payload": {"strategy": "swap", "load_batch_id": "batch-9"}},
    ) as ctx:
        result = await mv.run_mv_refresh_op(ctx)

    assert result == {"job_id": "mv-1"}
    assert captured["job_id"] == "mv-1"
    assert captured["engine"] is sentinel_engine
    # the load_jobs id the bridge adopts IS the job_id the release-record leaf uses
    assert captured["leaf_engine"] is sentinel_engine
    assert captured["leaf_job_id"] == "mv-1"
    assert captured["leaf_payload"] == {"strategy": "swap", "load_batch_id": "batch-9"}
    assert captured["lease_ttl_seconds"] == settings.dagster_lease_ttl_seconds


def test_mv_refresh_job_registered_and_op_name_differs() -> None:
    from kortravelgeo_dagster.definitions import defs

    assert "mv_refresh" in {job.name for job in defs.resolve_all_job_defs()}
    assert mv.run_mv_refresh_op.name == "run_mv_refresh"
    assert mv.mv_refresh_job.name == "mv_refresh"
