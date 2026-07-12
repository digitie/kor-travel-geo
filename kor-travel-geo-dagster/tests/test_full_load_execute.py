"""full_load_execute op wiring tests (T-290j): op config -> bridge -> main-lib leaf.

No DB, no real load — the bridge and the batch/loader leaves are faked so these assert only
that the ops unwrap the ``client``/``settings`` resources, thread the config, and call the
right main-lib entrypoint with the load_jobs id + Dagster run id.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from dagster import build_op_context
from kortravelgeo.settings import Settings

from kortravelgeo_dagster import full_load_execute


class _FakeClient:
    def __init__(self, engine: object) -> None:
        self._eng = engine

    def _engine(self) -> object:
        return self._eng


async def _noop_progress(*, progress=None, stage=None, message=None):
    return None


@pytest.mark.asyncio
async def test_run_full_load_batch_op_wires_bridge_and_drives_batch_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf, **kwargs):
        captured["job_id"] = job_id
        captured["orchestrator_run_id"] = orchestrator_run_id
        captured["engine"] = engine
        captured["lease_ttl_seconds"] = kwargs.get("lease_ttl_seconds")
        await leaf(asyncio.Event(), _noop_progress)

    async def fake_run_full_load_batch(
        engine, *, batch_id, payload, cancel_event, progress, orchestrator_run_id, lease_ttl_seconds
    ):
        captured["leaf_engine"] = engine
        captured["batch_id"] = batch_id
        captured["payload"] = payload
        captured["leaf_run_id"] = orchestrator_run_id
        captured["leaf_ttl"] = lease_ttl_seconds

    monkeypatch.setattr(full_load_execute, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(full_load_execute, "run_full_load_batch", fake_run_full_load_batch)

    sentinel_engine = object()
    settings = Settings(_env_file=None)

    with build_op_context(
        resources={"client": _FakeClient(sentinel_engine), "settings": settings},
        op_config={"job_id": "batch-1", "payload": {"payloads": {"juso_text_load": {}}}},
    ) as ctx:
        result = await full_load_execute.run_full_load_batch_op(ctx)

    assert result == {"job_id": "batch-1"}
    assert captured["job_id"] == "batch-1"
    assert captured["engine"] is sentinel_engine
    assert captured["leaf_engine"] is sentinel_engine
    # the root job_id IS the batch id the leaf drives, and the run id + lease TTL flow through.
    assert captured["batch_id"] == "batch-1"
    assert captured["orchestrator_run_id"]
    assert captured["leaf_run_id"] == captured["orchestrator_run_id"]
    assert captured["lease_ttl_seconds"] == settings.dagster_lease_ttl_seconds
    assert captured["leaf_ttl"] == settings.dagster_lease_ttl_seconds
    assert captured["payload"] == {"payloads": {"juso_text_load": {}}}


@pytest.mark.asyncio
async def test_run_full_load_batch_op_target_database_uses_disposable_scratch_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Staging: a target_database routes the bridge AND leaf to a scratch engine, disposed after."""
    captured: dict[str, Any] = {}
    disposed = {"count": 0}

    class _FakeScratchEngine:
        async def dispose(self) -> None:
            disposed["count"] += 1

    scratch_engine = _FakeScratchEngine()

    def fake_scratch_dsn(pg_dsn, db_name):
        captured["scratch_dsn_args"] = (pg_dsn, db_name)
        return f"scratch-dsn::{db_name}"

    def fake_create_engine(dsn):
        captured["create_engine_dsn"] = dsn
        return scratch_engine

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf, **kwargs):
        captured["engine"] = engine
        await leaf(asyncio.Event(), _noop_progress)

    async def fake_run_full_load_batch(engine, **kwargs):
        captured["leaf_engine"] = engine

    monkeypatch.setattr(full_load_execute, "scratch_database_dsn", fake_scratch_dsn)
    monkeypatch.setattr(full_load_execute, "create_async_engine", fake_create_engine)
    monkeypatch.setattr(full_load_execute, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(full_load_execute, "run_full_load_batch", fake_run_full_load_batch)

    serving_engine = object()
    settings = Settings(_env_file=None)

    with build_op_context(
        resources={"client": _FakeClient(serving_engine), "settings": settings},
        op_config={
            "job_id": "batch-2",
            "payload": {
                "target_database": "kor_travel_geo_fullload_e2e",
                "payloads": {"juso_text_load": {}},
            },
        },
    ) as ctx:
        result = await full_load_execute.run_full_load_batch_op(ctx)

    assert result == {"job_id": "batch-2"}
    # scratch engine drives BOTH the bridge and the DAG leaf; serving engine never used
    assert captured["engine"] is scratch_engine
    assert captured["leaf_engine"] is scratch_engine
    assert captured["engine"] is not serving_engine
    assert captured["scratch_dsn_args"] == (settings.pg_dsn, "kor_travel_geo_fullload_e2e")
    assert captured["create_engine_dsn"] == "scratch-dsn::kor_travel_geo_fullload_e2e"
    # the per-run scratch engine is disposed exactly once
    assert disposed["count"] == 1


@pytest.mark.asyncio
async def test_run_source_load_op_wires_bridge_and_drives_loader_leaf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf, **kwargs):
        captured["job_id"] = job_id
        captured["engine"] = engine
        await leaf(asyncio.Event(), _noop_progress)

    async def fake_run_source_loader(engine, *, kind, payload, cancel_event, progress):
        captured["leaf_engine"] = engine
        captured["kind"] = kind
        captured["payload"] = payload

    monkeypatch.setattr(full_load_execute, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(full_load_execute, "run_source_loader", fake_run_source_loader)

    sentinel_engine = object()
    settings = Settings(_env_file=None)

    with build_op_context(
        resources={"client": _FakeClient(sentinel_engine), "settings": settings},
        op_config={
            "job_id": "job-7",
            "kind": "locsum_load",
            "payload": {"path": "/data/locsum"},
        },
    ) as ctx:
        result = await full_load_execute.run_source_load_op(ctx)

    assert result == {"job_id": "job-7"}
    assert captured["job_id"] == "job-7"
    assert captured["engine"] is sentinel_engine
    assert captured["leaf_engine"] is sentinel_engine
    assert captured["kind"] == "locsum_load"
    assert captured["payload"] == {"path": "/data/locsum"}


def test_full_load_jobs_are_registered_in_definitions() -> None:
    from kortravelgeo_dagster.definitions import defs

    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "full_load_batch" in job_names
    assert "load_source" in job_names
    assert defs.get_job_def("full_load_batch").name == "full_load_batch"
    assert defs.get_job_def("load_source").name == "load_source"
