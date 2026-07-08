from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from kortravelgeo.api import _jobs
from kortravelgeo.api._job_recovery import (
    OrchestratorRunState,
    ReconcileAction,
    ReconcileOutcome,
)
from kortravelgeo.api._jobs import JobQueue


@pytest.mark.asyncio
async def test_spawn_drain_adds_delayed_nudge(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = JobQueue(cast("Any", object()))
    calls = 0

    async def fake_drain_once() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(queue, "_drain_once", fake_drain_once)

    queue._spawn_drain()
    await asyncio.sleep(0.35)

    assert calls == 2
    assert not queue._tasks


@pytest.mark.asyncio
async def test_spawn_drain_consumes_task_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = JobQueue(cast("Any", object()))
    messages: list[str] = []

    async def fake_drain_once() -> None:
        raise RuntimeError("boom")

    def fake_exception(message: str) -> None:
        messages.append(message)

    monkeypatch.setattr(queue, "_drain_once", fake_drain_once)
    monkeypatch.setattr("kortravelgeo.api._jobs.logger.exception", fake_exception)

    queue._start_drain_task(delay_s=0.0)
    await asyncio.sleep(0.01)

    assert messages == ["load job queue drain task failed"]
    assert not queue._tasks


@pytest.mark.asyncio
async def test_drain_retries_after_busy_queue_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = JobQueue(cast("Any", object()))
    claims: list[object] = [_jobs._ClaimState.BUSY, ("job-1", "demo", {"value": 1}), None]
    handled: list[dict[str, Any]] = []

    async def fake_claim_one() -> object:
        return claims.pop(0)

    async def fake_handler(
        payload: dict[str, Any],
        _cancel_event: asyncio.Event,
        _progress: _jobs.ProgressCallback,
    ) -> None:
        handled.append(payload)

    async def noop_async(*_args: object, **_kwargs: object) -> None:
        return None

    def noop_sync(*_args: object, **_kwargs: object) -> None:
        return None

    queue.register("demo", fake_handler)
    monkeypatch.setattr(queue, "_claim_one", fake_claim_one)
    monkeypatch.setattr(queue, "_record_progress", noop_async)
    monkeypatch.setattr(queue, "_done", noop_async)
    monkeypatch.setattr(queue, "_enqueue_batch_successors", noop_async)
    monkeypatch.setattr(queue, "_finish_stage", noop_sync)
    monkeypatch.setattr(_jobs, "_DRAIN_LOCK_RETRY_DELAY_S", 0)
    monkeypatch.setattr(_jobs, "record_load_job_duration", noop_sync)

    await queue._drain_once()

    assert handled == [{"value": 1, "_job_id": "job-1"}]
    assert claims == []


# --- T-290c executor-aware recovery / reconciler / bidirectional cancel ---


@pytest.mark.asyncio
async def test_recover_startup_fails_in_process_then_reconciles_dagster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = JobQueue(cast("Any", object()))
    order: list[str] = []
    spawned: list[bool] = []

    async def fake_recover_in_process() -> list[str]:
        order.append("in_process")
        return []

    async def fake_reconcile() -> list[object]:
        order.append("reconcile")
        return []

    monkeypatch.setattr(queue, "_recover_in_process_running", fake_recover_in_process)
    monkeypatch.setattr(queue, "reconcile_dagster_jobs", fake_reconcile)
    monkeypatch.setattr(queue, "_spawn_drain", lambda: spawned.append(True))

    await queue.recover_startup()

    # in-process force-fail runs first, then the dagster reconciler; no queued -> no drain
    assert order == ["in_process", "reconcile"]
    assert spawned == []


@pytest.mark.asyncio
async def test_recover_startup_spawns_drain_when_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = JobQueue(cast("Any", object()))
    spawned: list[bool] = []

    async def fake_recover_in_process() -> list[str]:
        return ["job-1"]

    async def fake_reconcile() -> list[object]:
        return []

    monkeypatch.setattr(queue, "_recover_in_process_running", fake_recover_in_process)
    monkeypatch.setattr(queue, "reconcile_dagster_jobs", fake_reconcile)
    monkeypatch.setattr(queue, "_spawn_drain", lambda: spawned.append(True))

    await queue.recover_startup()

    assert spawned == [True]


@pytest.mark.asyncio
async def test_reconcile_dagster_jobs_applies_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = JobQueue(cast("Any", object()))
    rows: list[dict[str, Any]] = [
        {"job_id": "j-done", "orchestrator_run_id": "r1", "lease_expires_at": None},
        {"job_id": "j-fail", "orchestrator_run_id": None, "lease_expires_at": None},
        {"job_id": "j-keep", "orchestrator_run_id": "r3", "lease_expires_at": None},
    ]
    done: list[str] = []
    failed: list[tuple[str, str]] = []
    cancelled: list[str] = []

    async def fake_rows() -> list[dict[str, Any]]:
        return rows

    async def fake_probe(
        *, orchestrator_run_id: str | None, lease_valid: bool
    ) -> OrchestratorRunState:
        if orchestrator_run_id == "r1":
            return OrchestratorRunState.SUCCESS
        if orchestrator_run_id == "r3":
            return OrchestratorRunState.RUNNING
        return OrchestratorRunState.MISSING  # r=None + expired lease -> failed

    async def fake_done(job_id: str) -> None:
        done.append(job_id)

    async def fake_fail(job_id: str, message: str) -> None:
        failed.append((job_id, message))

    async def fake_cancelled(job_id: str) -> None:
        cancelled.append(job_id)

    monkeypatch.setattr(queue, "_dagster_running_rows", fake_rows)
    monkeypatch.setattr(queue, "_liveness_probe", fake_probe)
    monkeypatch.setattr(queue, "_done", fake_done)
    monkeypatch.setattr(queue, "_fail", fake_fail)
    monkeypatch.setattr(queue, "_cancelled", fake_cancelled)

    results = await queue.reconcile_dagster_jobs()

    assert done == ["j-done"]
    assert [job_id for job_id, _ in failed] == ["j-fail"]
    assert cancelled == []
    assert [(job_id, action.outcome) for job_id, action in results] == [
        ("j-done", ReconcileOutcome.CONVERGE_DONE),
        ("j-fail", ReconcileOutcome.CONVERGE_FAILED),
        ("j-keep", ReconcileOutcome.KEEP_RUNNING),
    ]


class _FakeAdminRepo:
    def __init__(self, engine: object) -> None:
        self.engine = engine

    async def cancel_load_job(self, job_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_cancel_dagster_job_propagates_to_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    propagated: list[tuple[str, str | None]] = []

    async def recording_cancel(*, job_id: str, orchestrator_run_id: str | None) -> None:
        propagated.append((job_id, orchestrator_run_id))

    queue = JobQueue(cast("Any", object()), orchestrator_cancel=recording_cancel)

    async def fake_ref(job_id: str) -> tuple[str, str | None]:
        return ("dagster", "run-9")

    messages: list[str | None] = []

    async def fake_record_progress(job_id: str, **kwargs: Any) -> None:
        messages.append(kwargs.get("message"))

    async def fake_cancel_children(job_id: str) -> None:
        return None

    monkeypatch.setattr(queue, "_executor_ref", fake_ref)
    monkeypatch.setattr(_jobs, "AdminRepository", _FakeAdminRepo)
    monkeypatch.setattr(queue, "_record_progress", fake_record_progress)
    monkeypatch.setattr(queue, "_cancel_batch_children", fake_cancel_children)

    await queue.cancel("job-x")

    assert propagated == [("job-x", "run-9")]
    assert any("propagating to Dagster run" in (m or "") for m in messages)


@pytest.mark.asyncio
async def test_cancel_in_process_job_does_not_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    propagated: list[tuple[str, str | None]] = []

    async def recording_cancel(*, job_id: str, orchestrator_run_id: str | None) -> None:
        propagated.append((job_id, orchestrator_run_id))

    queue = JobQueue(cast("Any", object()), orchestrator_cancel=recording_cancel)

    async def fake_ref(job_id: str) -> tuple[str, str | None]:
        return ("api_in_process", None)

    async def fake_cancel_children(job_id: str) -> None:
        return None

    monkeypatch.setattr(queue, "_executor_ref", fake_ref)
    monkeypatch.setattr(_jobs, "AdminRepository", _FakeAdminRepo)
    monkeypatch.setattr(queue, "_cancel_batch_children", fake_cancel_children)

    await queue.cancel("job-y")

    assert propagated == []


@pytest.mark.asyncio
async def test_apply_reconcile_orphan_requests_orchestrator_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reverse split-brain: Dagster run alive but load_jobs already failed. The reconciler
    # records the orphan and asks the cancel seam to terminate the Dagster run so both
    # sides converge (bidirectional cancel).
    propagated: list[tuple[str, str | None]] = []

    async def recording_cancel(*, job_id: str, orchestrator_run_id: str | None) -> None:
        propagated.append((job_id, orchestrator_run_id))

    queue = JobQueue(cast("Any", object()), orchestrator_cancel=recording_cancel)
    messages: list[str | None] = []

    async def fake_record_progress(job_id: str, **kwargs: Any) -> None:
        messages.append(kwargs.get("message"))

    monkeypatch.setattr(queue, "_record_progress", fake_record_progress)

    action = ReconcileAction(ReconcileOutcome.FLAG_ORPHAN, "Dagster run still running")
    await queue._apply_reconcile("job-z", action, orchestrator_run_id="run-7")

    assert propagated == [("job-z", "run-7")]
    assert any("orphan" in (m or "") for m in messages)
