"""full_load / loader Dagster routing (T-290j): _full_load_launch helpers + the gate.

Fakes the repo / executor / launch so these assert only the routing + row bookkeeping (a
Dagster row is inserted with executor='dagster', the launchRun config names the right op, a
launch failure converges the row(s) and raises 502, and the shared gate picks Dagster vs the
in-process queue by ``dagster_executed_job_kinds``).
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from kortravelgeo.api import _full_load_launch as launch_mod
from kortravelgeo.api._dagster_client import DagsterLaunchError
from kortravelgeo.exceptions import KorTravelGeoError
from kortravelgeo.settings import Settings

_VALID_BATCH_PAYLOAD = {"children": [{"kind": "juso_text_load", "payload": {"path": "/data/juso"}}]}


def test_dagster_executed_job_kinds_includes_full_load_batch() -> None:
    routed = Settings(_env_file=None, dagster_executed_job_kinds="full_load_batch, locsum_load")
    assert "full_load_batch" in routed.dagster_executed_job_kinds
    assert "locsum_load" in routed.dagster_executed_job_kinds


class _FakeRow:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id


class _FakeRepo:
    inserted: ClassVar[dict] = {}
    cancelled: ClassVar[list] = []

    def __init__(self, _engine: object) -> None:
        pass

    async def insert_load_batch(self, *, payload, children, executor) -> _FakeRow:
        _FakeRepo.inserted = {
            "payload": payload,
            "children": list(children),
            "executor": executor,
        }
        return _FakeRow("batch-dag-1")

    async def insert_load_job(self, *, kind, payload, executor) -> _FakeRow:
        _FakeRepo.inserted = {"kind": kind, "payload": payload, "executor": executor}
        return _FakeRow("job-dag-1")

    async def cancel_queued_batch_children(self, batch_id: str) -> None:
        _FakeRepo.cancelled.append(batch_id)


class _FakeExecutor:
    failed: ClassVar[tuple] = ()

    def __init__(self, _engine: object) -> None:
        pass

    async def mark_failed(self, job_id: str, message: str) -> None:
        _FakeExecutor.failed = (job_id, message)


class _FakeQueue:
    def __init__(self) -> None:
        self.enqueued_batch: dict | None = None

    async def enqueue_batch(self, payload: dict) -> str:
        self.enqueued_batch = payload
        return "batch-inproc-1"


@pytest.fixture(autouse=True)
def _reset_fakes() -> None:
    _FakeRepo.inserted = {}
    _FakeRepo.cancelled = []
    _FakeExecutor.failed = ()


@pytest.mark.asyncio
async def test_launch_full_load_batch_inserts_dagster_batch_and_launches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: dict[str, Any] = {}

    async def fake_launch(settings, *, job_name, run_config, tags):
        launched.update(job_name=job_name, run_config=run_config, tags=tags)
        return "run-fl-1"

    monkeypatch.setattr(launch_mod, "AdminRepository", _FakeRepo)
    monkeypatch.setattr(launch_mod, "launch_dagster_run", fake_launch)

    batch_id = await launch_mod.launch_full_load_batch_dagster_run(
        object(), Settings(_env_file=None), _VALID_BATCH_PAYLOAD
    )

    assert batch_id == "batch-dag-1"
    assert _FakeRepo.inserted["executor"] == "dagster"
    assert _FakeRepo.inserted["children"]  # batch_children resolved before insert
    assert launched["job_name"] == "full_load_batch"
    op_config = launched["run_config"]["ops"]["run_full_load_batch"]["config"]
    assert op_config["job_id"] == "batch-dag-1"
    assert op_config["payload"] == _VALID_BATCH_PAYLOAD
    assert launched["tags"] == {"kor_travel_geo.job_id": "batch-dag-1"}


@pytest.mark.asyncio
async def test_launch_full_load_batch_failure_fails_root_cancels_children_and_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_launch(settings, *, job_name, run_config, tags):
        raise DagsterLaunchError("job not found")

    monkeypatch.setattr(launch_mod, "AdminRepository", _FakeRepo)
    monkeypatch.setattr(launch_mod, "LoadJobExecutor", _FakeExecutor)
    monkeypatch.setattr(launch_mod, "launch_dagster_run", fake_launch)

    with pytest.raises(KorTravelGeoError) as excinfo:
        await launch_mod.launch_full_load_batch_dagster_run(
            object(), Settings(_env_file=None), _VALID_BATCH_PAYLOAD
        )

    assert excinfo.value.http_status == 502
    assert _FakeExecutor.failed[0] == "batch-dag-1"
    assert "job not found" in _FakeExecutor.failed[1]
    # the queued dagster children were cancelled so no worker leaves them stuck
    assert _FakeRepo.cancelled == ["batch-dag-1"]


@pytest.mark.asyncio
async def test_launch_source_load_inserts_dagster_row_and_launches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: dict[str, Any] = {}

    async def fake_launch(settings, *, job_name, run_config, tags):
        launched.update(job_name=job_name, run_config=run_config, tags=tags)
        return "run-src-1"

    monkeypatch.setattr(launch_mod, "AdminRepository", _FakeRepo)
    monkeypatch.setattr(launch_mod, "launch_dagster_run", fake_launch)

    payload = {"path": "/data/navi", "source_yyyymm": "202606"}
    job_id = await launch_mod.launch_source_load_dagster_run(
        object(), Settings(_env_file=None), "navi_load", payload
    )

    assert job_id == "job-dag-1"
    assert _FakeRepo.inserted == {"kind": "navi_load", "payload": payload, "executor": "dagster"}
    assert launched["job_name"] == "load_source"
    op_config = launched["run_config"]["ops"]["run_source_load"]["config"]
    assert op_config == {"job_id": "job-dag-1", "kind": "navi_load", "payload": payload}
    assert launched["tags"] == {"kor_travel_geo.job_id": "job-dag-1"}


@pytest.mark.asyncio
async def test_launch_source_load_failure_marks_failed_and_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_launch(settings, *, job_name, run_config, tags):
        raise DagsterLaunchError("boom")

    monkeypatch.setattr(launch_mod, "AdminRepository", _FakeRepo)
    monkeypatch.setattr(launch_mod, "LoadJobExecutor", _FakeExecutor)
    monkeypatch.setattr(launch_mod, "launch_dagster_run", fake_launch)

    with pytest.raises(KorTravelGeoError) as excinfo:
        await launch_mod.launch_source_load_dagster_run(
            object(), Settings(_env_file=None), "navi_load", {"path": "/x"}
        )

    assert excinfo.value.http_status == 502
    assert _FakeExecutor.failed[0] == "job-dag-1"


@pytest.mark.asyncio
async def test_submit_full_load_batch_routes_to_dagster_when_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {}

    async def fake_dagster_launch(engine, settings, payload):
        called["payload"] = payload
        return "batch-dag-9"

    monkeypatch.setattr(launch_mod, "launch_full_load_batch_dagster_run", fake_dagster_launch)
    queue = _FakeQueue()
    settings = Settings(_env_file=None, dagster_executed_job_kinds="full_load_batch")

    batch_id = await launch_mod.submit_full_load_batch(
        object(), settings, _VALID_BATCH_PAYLOAD, queue=queue
    )

    assert batch_id == "batch-dag-9"
    assert called["payload"] == _VALID_BATCH_PAYLOAD
    assert queue.enqueued_batch is None  # in-process path was NOT taken


@pytest.mark.asyncio
async def test_submit_full_load_batch_falls_back_to_in_process_when_not_gated() -> None:
    queue = _FakeQueue()
    settings = Settings(_env_file=None)  # empty gate

    batch_id = await launch_mod.submit_full_load_batch(
        object(), settings, _VALID_BATCH_PAYLOAD, queue=queue
    )

    assert batch_id == "batch-inproc-1"
    assert queue.enqueued_batch == _VALID_BATCH_PAYLOAD
