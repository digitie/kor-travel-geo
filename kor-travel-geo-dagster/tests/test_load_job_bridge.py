"""load_job_bridge tests (T-290g): adopt / progress / terminal / cancel-poll branches.

The bridge is exercised with an injected fake LoadJobExecutor (no DB), mirroring the repo's
JobQueue unit style — the real SQL is covered by the integration backup roundtrip.
"""

from __future__ import annotations

import asyncio

import pytest
from dagster import Failure

from kortravelgeo_dagster.load_job_bridge import execute_load_job


class _FakeExecutor:
    """Records lifecycle calls; ``cancel_after_reads`` flips read_cancel_requested True."""

    def __init__(self, *, cancel_after_reads: int | None = None) -> None:
        self.calls: list[tuple] = []
        self._reads = 0
        self._cancel_after = cancel_after_reads

    async def adopt_dagster(self, job_id, orchestrator_run_id, *, ttl_seconds=None):
        self.calls.append(("adopt", job_id, orchestrator_run_id))
        return None

    async def set_progress(self, job_id, *, progress=None, stage=None, message=None):
        self.calls.append(("progress", progress, stage, message))

    async def renew_lease(self, job_id, *, ttl_seconds=None):
        self.calls.append(("renew", job_id))
        return None

    async def mark_done(self, job_id):
        self.calls.append(("done", job_id))

    async def mark_failed(self, job_id, message):
        self.calls.append(("failed", job_id, message))

    async def mark_cancelled(self, job_id):
        self.calls.append(("cancelled", job_id))

    async def read_cancel_requested(self, job_id):
        self._reads += 1
        return self._cancel_after is not None and self._reads >= self._cancel_after

    def kinds(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.mark.asyncio
async def test_bridge_success_adopts_reports_and_marks_done() -> None:
    ex = _FakeExecutor()

    async def leaf(cancel_event, progress):
        await progress(progress=0.5, stage="dumping", message="halfway")

    await execute_load_job(
        job_id="j1", orchestrator_run_id="run-1", engine=object(),  # type: ignore[arg-type]
        leaf=leaf, executor=ex, cancel_poll_seconds=0.01,  # type: ignore[arg-type]
    )

    assert ex.calls[0] == ("adopt", "j1", "run-1")
    assert ("progress", 0.01, "running", "job started") in ex.calls
    assert ("progress", 0.5, "dumping", "halfway") in ex.calls
    assert ("renew", "j1") in ex.calls  # lease renewed on each progress
    assert "done" in ex.kinds()
    assert "failed" not in ex.kinds() and "cancelled" not in ex.kinds()


@pytest.mark.asyncio
async def test_bridge_leaf_exception_marks_failed_and_raises_failure() -> None:
    ex = _FakeExecutor()

    async def leaf(cancel_event, progress):
        raise RuntimeError("boom")

    with pytest.raises(Failure):
        await execute_load_job(
            job_id="j1", orchestrator_run_id="r", engine=object(),  # type: ignore[arg-type]
            leaf=leaf, executor=ex, cancel_poll_seconds=0.01,  # type: ignore[arg-type]
        )

    assert ("failed", "j1", "boom") in ex.calls
    assert "done" not in ex.kinds()


@pytest.mark.asyncio
async def test_bridge_cancelled_error_marks_cancelled_and_reraises() -> None:
    ex = _FakeExecutor()

    async def leaf(cancel_event, progress):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await execute_load_job(
            job_id="j1", orchestrator_run_id="r", engine=object(),  # type: ignore[arg-type]
            leaf=leaf, executor=ex, cancel_poll_seconds=0.01,  # type: ignore[arg-type]
        )

    assert "cancelled" in ex.kinds()
    assert "done" not in ex.kinds()


@pytest.mark.asyncio
async def test_bridge_poll_bridges_load_jobs_cancel_to_event() -> None:
    # load_jobs reports cancelled on the first poll -> the leaf's cancel_event flips.
    ex = _FakeExecutor(cancel_after_reads=1)
    observed: dict[str, bool] = {}

    async def leaf(cancel_event, progress):
        for _ in range(200):
            if cancel_event.is_set():
                observed["saw_cancel"] = True
                return
            await asyncio.sleep(0.005)

    await execute_load_job(
        job_id="j1", orchestrator_run_id="r", engine=object(),  # type: ignore[arg-type]
        leaf=leaf, executor=ex, cancel_poll_seconds=0.005,  # type: ignore[arg-type]
    )

    assert observed.get("saw_cancel") is True
