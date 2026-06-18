from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from kortravelgeo.api import _jobs
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
