"""T-290k §2h DagsterJobReconciler: pure reconcile_once over stubbed rows/probe/executor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from kortravelgeo.api._reconciler import DagsterJobReconciler
from kortravelgeo.core.job_recovery import OrchestratorRunState, ReconcileOutcome, RunLivenessProbe


class _FakeExecutor:
    def __init__(self) -> None:
        self.done: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self.progress: list[tuple[str, str | None, str | None]] = []

    async def mark_done(self, job_id: str) -> None:
        self.done.append(job_id)

    async def mark_failed(self, job_id: str, message: str) -> None:
        self.failed.append((job_id, message))

    async def mark_cancelled(self, job_id: str) -> None:
        self.cancelled.append(job_id)

    async def set_progress(
        self,
        job_id: str,
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None:
        self.progress.append((job_id, stage, message))


def _probe(state: OrchestratorRunState) -> RunLivenessProbe:
    async def probe(*, orchestrator_run_id: str | None, lease_valid: bool) -> OrchestratorRunState:
        return state

    return probe


class _StubReconciler(DagsterJobReconciler):
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        executor: _FakeExecutor,
        liveness_probe: RunLivenessProbe,
        orchestrator_cancel: Any,
    ) -> None:
        super().__init__(
            cast("Any", None),
            executor=cast("Any", executor),
            liveness_probe=liveness_probe,
            orchestrator_cancel=orchestrator_cancel,
        )
        self._rows = rows

    async def _reconcile_rows(self) -> list[dict[str, Any]]:
        return self._rows


def _row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "job_id": "j1",
        "state": "running",
        "orchestrator_run_id": "r1",
        "lease_expires_at": datetime.now(UTC) + timedelta(hours=1),
    }
    base.update(over)
    return base


async def _noop_cancel(*, job_id: str, orchestrator_run_id: str | None) -> None:
    return None


@pytest.mark.asyncio
async def test_success_run_converges_done() -> None:
    ex = _FakeExecutor()
    rec = _StubReconciler(
        [_row()], executor=ex, liveness_probe=_probe(OrchestratorRunState.SUCCESS),
        orchestrator_cancel=_noop_cancel,
    )
    results = await rec.reconcile_once()
    assert ex.done == ["j1"]
    assert results[0][1].outcome is ReconcileOutcome.CONVERGE_DONE


@pytest.mark.asyncio
async def test_failed_run_converges_failed() -> None:
    ex = _FakeExecutor()
    rec = _StubReconciler(
        [_row()], executor=ex, liveness_probe=_probe(OrchestratorRunState.FAILED),
        orchestrator_cancel=_noop_cancel,
    )
    await rec.reconcile_once()
    assert ex.failed and ex.failed[0][0] == "j1"


@pytest.mark.asyncio
async def test_missing_run_expired_lease_fails() -> None:
    ex = _FakeExecutor()
    rec = _StubReconciler(
        [_row(orchestrator_run_id=None, lease_expires_at=None)],
        executor=ex,
        liveness_probe=_probe(OrchestratorRunState.MISSING),
        orchestrator_cancel=_noop_cancel,
    )
    await rec.reconcile_once()
    assert ex.failed and "lease expired" in ex.failed[0][1]


@pytest.mark.asyncio
async def test_missing_run_valid_lease_keeps_running() -> None:
    ex = _FakeExecutor()
    rec = _StubReconciler(
        [_row()],  # lease is 1h out
        executor=ex,
        liveness_probe=_probe(OrchestratorRunState.MISSING),
        orchestrator_cancel=_noop_cancel,
    )
    results = await rec.reconcile_once()
    assert not ex.done and not ex.failed and not ex.cancelled
    assert results[0][1].outcome is ReconcileOutcome.KEEP_RUNNING


@pytest.mark.asyncio
async def test_live_run_but_terminal_job_flags_orphan_and_terminates() -> None:
    ex = _FakeExecutor()
    cancelled: list[tuple[str, str | None]] = []

    async def cancel(*, job_id: str, orchestrator_run_id: str | None) -> None:
        cancelled.append((job_id, orchestrator_run_id))

    rec = _StubReconciler(
        [_row(state="failed")],
        executor=ex,
        liveness_probe=_probe(OrchestratorRunState.RUNNING),
        orchestrator_cancel=cancel,
    )
    results = await rec.reconcile_once()
    assert results[0][1].outcome is ReconcileOutcome.FLAG_ORPHAN
    assert cancelled == [("j1", "r1")]
    assert any("orphan" in (msg or "") for _, _, msg in ex.progress)
