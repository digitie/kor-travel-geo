"""T-290k §2g cancel_load_job_converged: converge the row + real Dagster terminateRun (Dagster-only)."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from kortravelgeo.api import _cancel
from kortravelgeo.api._cancel import cancel_load_job_converged


class _FakeRepo:
    calls: ClassVar[dict[str, list[str]]] = {}

    def __init__(self, _engine: object) -> None:
        pass

    async def cancel_load_job(self, job_id: str) -> None:
        _FakeRepo.calls.setdefault("cancel_load_job", []).append(job_id)

    async def cancel_queued_batch_children(self, job_id: str) -> None:
        _FakeRepo.calls.setdefault("cancel_children", []).append(job_id)


class _FakeExecutor:
    progress: ClassVar[list[str]] = []

    def __init__(self, _engine: object) -> None:
        pass

    async def set_progress(self, job_id: str, *, message: str | None = None, **_: Any) -> None:
        _FakeExecutor.progress.append(job_id)


@pytest.fixture(autouse=True)
def _reset() -> None:
    _FakeRepo.calls = {}
    _FakeExecutor.progress = []


def _wire(monkeypatch: pytest.MonkeyPatch, executor: str, run_id: str | None) -> None:
    async def fake_ref(engine: object, job_id: str) -> tuple[str, str | None]:
        return (executor, run_id)

    monkeypatch.setattr(_cancel, "_executor_ref", fake_ref)
    monkeypatch.setattr(_cancel, "AdminRepository", _FakeRepo)
    monkeypatch.setattr(_cancel, "LoadJobExecutor", _FakeExecutor)


@pytest.mark.asyncio
async def test_dagster_row_terminates_run_and_converges(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire(monkeypatch, "dagster", "run-9")
    terminated: list[tuple[str, str | None]] = []

    async def orchestrator_cancel(*, job_id: str, orchestrator_run_id: str | None) -> None:
        terminated.append((job_id, orchestrator_run_id))

    await cancel_load_job_converged(object(), "j1", orchestrator_cancel=orchestrator_cancel)

    assert _FakeRepo.calls["cancel_load_job"] == ["j1"]
    assert _FakeRepo.calls["cancel_children"] == ["j1"]
    assert terminated == [("j1", "run-9")]
    assert _FakeExecutor.progress == ["j1"]


@pytest.mark.asyncio
async def test_non_dagster_row_converges_without_terminate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A historical/absent api_in_process row (no live Dagster run) still converges the
    # load_jobs row + queued children, but there is nothing to terminateRun (T-290k retired
    # the in-process drain, so there is no in-process cancel path either).
    _wire(monkeypatch, "api_in_process", None)
    terminated: list[str] = []

    async def orchestrator_cancel(*, job_id: str, orchestrator_run_id: str | None) -> None:
        terminated.append(job_id)

    await cancel_load_job_converged(object(), "j2", orchestrator_cancel=orchestrator_cancel)

    assert _FakeRepo.calls["cancel_load_job"] == ["j2"]
    assert _FakeRepo.calls["cancel_children"] == ["j2"]
    assert terminated == []  # no Dagster terminate for a non-dagster row
