"""run_db_backup_op wiring test (T-290g): op config -> bridge, no DB / no real backup."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from dagster import build_op_context
from kortravelgeo.settings import Settings

from kortravelgeo_dagster import backup_execute


class _FakeClient:
    def __init__(self, engine: object) -> None:
        self._eng = engine

    def _engine(self) -> object:
        return self._eng


async def _noop_progress(*, progress=None, stage=None, message=None):
    return None


@pytest.mark.asyncio
async def test_run_db_backup_op_wires_bridge_and_injects_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf):
        captured["job_id"] = job_id
        captured["orchestrator_run_id"] = orchestrator_run_id
        captured["engine"] = engine
        # Drive the leaf to confirm it wraps run_backup_job with the injected payload.
        await leaf(asyncio.Event(), _noop_progress)

    async def fake_run_backup_job(engine, settings, payload, cancel_event, progress):
        captured["payload"] = payload
        captured["settings"] = settings
        captured["leaf_engine"] = engine

    monkeypatch.setattr(backup_execute, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(backup_execute, "run_backup_job", fake_run_backup_job)

    sentinel_engine = object()
    settings = Settings(_env_file=None)

    with build_op_context(
        resources={"client": _FakeClient(sentinel_engine), "settings": settings},
        op_config={"job_id": "job-9", "payload": {"jobs": ["addr"]}},
    ) as ctx:
        result = await backup_execute.run_db_backup_op(ctx)

    assert result == {"job_id": "job-9"}
    assert captured["job_id"] == "job-9"
    assert captured["engine"] is sentinel_engine
    assert captured["leaf_engine"] is sentinel_engine
    assert captured["orchestrator_run_id"]  # a Dagster run id was passed through
    # The leaf injected the load_jobs id (_job_id) and preserved the request payload.
    assert captured["payload"]["_job_id"] == "job-9"
    assert captured["payload"]["jobs"] == ["addr"]
    assert captured["settings"] is settings


def test_db_backup_job_is_registered_in_definitions() -> None:
    from kortravelgeo_dagster.definitions import defs

    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "db_backup" in job_names
    assert defs.get_job_def("db_backup").name == "db_backup"
