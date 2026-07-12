"""source_rebuild_execute op wiring tests (T-290k): materialize -> launch downstream -> link.

No DB / no RustFS — the leaf (prepare_source_match_set_rebuild), the downstream launch, the
advisory lock, and the repo link writer are faked so these assert only the control flow:
success threads the launched batch id into link_job_to_batch + record_rebuild_enqueued, and
an integrity-gate failure audits + raises.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, ClassVar

import pytest
from dagster import build_op_context
from kortravelgeo.settings import Settings

from kortravelgeo_dagster import source_rebuild_execute


async def _noop_progress(*, progress=None, stage=None, message=None):
    return None


class _FakeResponse:
    def __init__(self, *, failed_group_ids=(), message=None) -> None:
        self.failed_group_ids = failed_group_ids
        self.message = message


class _FakeClient:
    def __init__(self, engine: object, *, batch_payload: dict[str, Any] | None) -> None:
        self._eng = engine
        self._batch_payload = batch_payload
        self.calls: dict[str, Any] = {}

    def _engine(self) -> object:
        return self._eng

    async def prepare_source_match_set_rebuild(self, source_match_set_id, **kwargs):
        self.calls["prepare"] = {"source_match_set_id": source_match_set_id, **kwargs}
        return _FakeResponse(message="gate failed"), self._batch_payload

    async def record_rebuild_enqueued(self, source_match_set_id, **kwargs):
        self.calls["record_enqueued"] = {"source_match_set_id": source_match_set_id, **kwargs}

    async def record_audit_event(self, **kwargs):
        self.calls["audit"] = kwargs


class _FakeRepo:
    calls: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, _engine: object) -> None:
        pass

    async def link_job_to_batch(self, job_id: str, load_batch_id: str) -> None:
        _FakeRepo.calls.append((job_id, load_batch_id))


def _patch_common(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def fake_lock(_engine, _key):
        yield

    async def fake_execute_load_job(*, job_id, orchestrator_run_id, engine, leaf, **kwargs):
        await leaf(asyncio.Event(), _noop_progress)

    monkeypatch.setattr(source_rebuild_execute, "cross_process_lock", fake_lock)
    monkeypatch.setattr(source_rebuild_execute, "execute_load_job", fake_execute_load_job)
    monkeypatch.setattr(source_rebuild_execute, "AdminRepository", _FakeRepo)


@pytest.mark.asyncio
async def test_source_rebuild_op_materializes_launches_and_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeRepo.calls = []
    _patch_common(monkeypatch)

    launched: dict[str, Any] = {}

    async def fake_launch(engine, settings, payload):
        launched["payload"] = payload
        return "batch-downstream-1"

    monkeypatch.setattr(
        source_rebuild_execute, "launch_full_load_batch_dagster_run", fake_launch
    )

    client = _FakeClient(object(), batch_payload={"children": [{"kind": "juso_text_load"}]})
    settings = Settings(_env_file=None)

    with build_op_context(
        resources={"client": client, "settings": settings},
        op_config={
            "job_id": "rebuild-1",
            "payload": {"source_match_set_id": "sms-1", "actor": "op", "force_promotion": False},
        },
    ) as ctx:
        result = await source_rebuild_execute.run_source_rebuild_db_op(ctx)

    assert result == {"job_id": "rebuild-1"}
    assert client.calls["prepare"]["source_match_set_id"] == "sms-1"
    assert launched["payload"] == {"children": [{"kind": "juso_text_load"}]}
    # the launched batch id is linked onto the rebuild control row + audited as enqueued
    assert _FakeRepo.calls == [("rebuild-1", "batch-downstream-1")]
    assert client.calls["record_enqueued"]["job_id"] == "batch-downstream-1"
    assert client.calls["record_enqueued"]["load_batch_id"] == "batch-downstream-1"
    assert "audit" not in client.calls  # no failure audit on the happy path


@pytest.mark.asyncio
async def test_source_rebuild_op_integrity_gate_failure_audits_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeRepo.calls = []
    _patch_common(monkeypatch)

    async def fake_launch(engine, settings, payload):  # pragma: no cover - must not be called
        raise AssertionError("downstream launch must not run when the integrity gate fails")

    monkeypatch.setattr(
        source_rebuild_execute, "launch_full_load_batch_dagster_run", fake_launch
    )

    client = _FakeClient(object(), batch_payload=None)  # None = integrity gate failed
    settings = Settings(_env_file=None)

    with (
        build_op_context(
            resources={"client": client, "settings": settings},
            op_config={
                "job_id": "rebuild-2",
                "payload": {"source_match_set_id": "sms-2", "actor": "op"},
            },
        ) as ctx,
        pytest.raises(RuntimeError),
    ):
        await source_rebuild_execute.run_source_rebuild_db_op(ctx)

    assert client.calls["audit"]["outcome"] == "failed"
    assert client.calls["audit"]["resource_id"] == "sms-2"
    assert _FakeRepo.calls == []  # nothing linked


def test_source_rebuild_db_job_registered_and_op_name_differs() -> None:
    from kortravelgeo_dagster.definitions import defs

    assert "source_rebuild_db" in {job.name for job in defs.resolve_all_job_defs()}
    assert source_rebuild_execute.run_source_rebuild_db_op.name == "run_source_rebuild_db"
    assert source_rebuild_execute.source_rebuild_db_job.name == "source_rebuild_db"
