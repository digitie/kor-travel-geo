"""consistency_execute op wiring tests (T-290k): config -> bridge -> run_consistency_check leaf.

No DB — the bridge and the consistency leaf are faked so these assert only that the op
unwraps client/settings, threads the config, and drives the main-lib leaf with the load_jobs
id + run id.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from dagster import build_op_context
from kortravelgeo.settings import Settings

from kortravelgeo_dagster import consistency_execute


class _FakeClient:
    def __init__(self, engine: object) -> None:
        self._eng = engine

    def _engine(self) -> object:
        return self._eng


async def _noop_progress(*, progress=None, stage=None, message=None):
    return None


@pytest.mark.asyncio
async def test_run_consistency_check_op_wires_bridge_and_drives_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf, **kwargs):
        captured["job_id"] = job_id
        captured["orchestrator_run_id"] = orchestrator_run_id
        captured["engine"] = engine
        captured["lease_ttl_seconds"] = kwargs.get("lease_ttl_seconds")
        await leaf(asyncio.Event(), _noop_progress)

    async def fake_run_consistency_check(engine, *, payload, progress):
        captured["leaf_engine"] = engine
        captured["payload"] = payload

    monkeypatch.setattr(consistency_execute, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(consistency_execute, "run_consistency_check", fake_run_consistency_check)

    sentinel_engine = object()
    settings = Settings(_env_file=None)

    with build_op_context(
        resources={"client": _FakeClient(sentinel_engine), "settings": settings},
        op_config={"job_id": "cc-1", "payload": {"scope": "full"}},
    ) as ctx:
        result = await consistency_execute.run_consistency_check_op(ctx)

    assert result == {"job_id": "cc-1"}
    assert captured["job_id"] == "cc-1"
    assert captured["engine"] is sentinel_engine
    assert captured["leaf_engine"] is sentinel_engine
    assert captured["payload"] == {"scope": "full"}
    assert captured["orchestrator_run_id"]
    assert captured["lease_ttl_seconds"] == settings.dagster_lease_ttl_seconds


def test_consistency_check_job_registered_in_definitions() -> None:
    from kortravelgeo_dagster.definitions import defs

    assert "consistency_check" in {job.name for job in defs.resolve_all_job_defs()}
    assert defs.get_job_def("consistency_check").name == "consistency_check"
    # op name != job name (dagster-boundary §10)
    assert consistency_execute.run_consistency_check_op.name == "run_consistency_check"
