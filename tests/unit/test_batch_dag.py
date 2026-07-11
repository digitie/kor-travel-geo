"""run_full_load_batch orchestration (T-290j): ADR-017 DAG control flow with fakes.

The batch orchestrator is exercised with a fake ``LoadJobExecutor`` / ``AdminRepository`` and
monkeypatched leaves (source loader / consistency / mv) so the ordering, the promotion GATE,
the forced-promotion bypass, sibling cancellation on failure, and cancel propagation are all
asserted deterministically without a database. The real SQL is covered by the file-driven
full-load e2e (opt-in) and the M5 live e2e.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from kortravelgeo.loaders import batch_dag
from kortravelgeo.loaders.batch_dag import FullLoadBatchGateError, run_full_load_batch

_SOURCE_CHILDREN = [
    ("child-juso", "juso_text_load", {"path": "/data/juso"}),
    ("child-locsum", "locsum_load", {"path": "/data/locsum"}),
]


class _FakeExecutor:
    events: ClassVar[list[tuple]] = []

    def __init__(self, _engine: object, *, lease_ttl_seconds: float = 300.0) -> None:
        self.ttl = lease_ttl_seconds

    async def adopt_dagster(self, job_id, orchestrator_run_id, *, ttl_seconds=None):
        _FakeExecutor.events.append(("adopt", job_id, orchestrator_run_id))

    async def set_progress(self, job_id, *, progress=None, stage=None, message=None):
        _FakeExecutor.events.append(("progress", job_id, stage))

    async def renew_lease(self, job_id, *, ttl_seconds=None):
        return None

    async def mark_done(self, job_id):
        _FakeExecutor.events.append(("done", job_id))

    async def mark_failed(self, job_id, message):
        _FakeExecutor.events.append(("failed", job_id, message))

    async def mark_cancelled(self, job_id):
        _FakeExecutor.events.append(("cancelled", job_id))


class _FakeRow:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id


class _FakeRepo:
    inserts: ClassVar[list[tuple[str, dict]]] = []
    cancelled: ClassVar[list[str]] = []

    def __init__(self, _engine: object) -> None:
        pass

    async def insert_load_job(
        self, *, kind, payload, load_batch_id=None, parent_job_id=None, executor="api_in_process"
    ) -> _FakeRow:
        _FakeRepo.inserts.append((kind, payload))
        assert executor == "dagster"
        assert load_batch_id == "batch-1"
        assert parent_job_id == "batch-1"
        return _FakeRow(f"{kind}-child")

    async def cancel_queued_batch_children(self, batch_id: str) -> None:
        _FakeRepo.cancelled.append(batch_id)


async def _noop_progress(*, progress=None, stage=None, message=None):
    return None


class _Harness:
    """Records the leaf calls the orchestrator makes and lets a test inject failures."""

    def __init__(self, *, severity: str = "WARN") -> None:
        self.severity = severity
        self.source_calls: list[str] = []
        self.mv_payloads: list[dict[str, Any]] = []
        self.consistency_payloads: list[dict[str, Any]] = []
        self.fail_source: str | None = None
        self.cancel_source: str | None = None

    async def run_source_loader(self, engine, *, kind, payload, cancel_event, progress):
        self.source_calls.append(kind)
        if self.cancel_source == kind:
            raise asyncio.CancelledError
        if self.fail_source == kind:
            raise RuntimeError(f"{kind} boom")

    async def run_consistency_check(self, engine, *, payload, progress):
        self.consistency_payloads.append(payload)
        return SimpleNamespace(severity_max=self.severity, report_id="rep-1")

    async def run_mv_refresh(self, engine, *, payload, job_id, progress):
        self.mv_payloads.append(payload)


@pytest.fixture(autouse=True)
def _wire_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeExecutor.events = []
    _FakeRepo.inserts = []
    _FakeRepo.cancelled = []
    monkeypatch.setattr(batch_dag, "LoadJobExecutor", _FakeExecutor)
    monkeypatch.setattr(batch_dag, "AdminRepository", _FakeRepo)

    async def fake_fetch(engine, batch_id):
        assert batch_id == "batch-1"
        return list(_SOURCE_CHILDREN)

    monkeypatch.setattr(batch_dag, "_fetch_source_children", fake_fetch)


def _install_harness(monkeypatch: pytest.MonkeyPatch, harness: _Harness) -> None:
    monkeypatch.setattr(batch_dag, "run_source_loader", harness.run_source_loader)
    monkeypatch.setattr(batch_dag, "run_consistency_check", harness.run_consistency_check)
    monkeypatch.setattr(batch_dag, "run_mv_refresh", harness.run_mv_refresh)


async def _run(payload: dict[str, Any]) -> Any:
    return await run_full_load_batch(
        object(),
        batch_id="batch-1",
        payload=payload,
        cancel_event=asyncio.Event(),
        progress=_noop_progress,
        orchestrator_run_id="run-1",
        lease_ttl_seconds=300.0,
    )


@pytest.mark.asyncio
async def test_happy_path_runs_sources_then_consistency_then_mv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness(severity="WARN")
    _install_harness(monkeypatch, harness)

    result = await _run({})

    # sources ran in submission order, then consistency, then mv swap.
    assert harness.source_calls == ["juso_text_load", "locsum_load"]
    assert len(harness.consistency_payloads) == 1
    assert harness.mv_payloads == [{"strategy": "swap", "load_batch_id": "batch-1"}]
    # consistency + mv child rows were created (executor='dagster', parented to the root).
    assert [kind for kind, _ in _FakeRepo.inserts] == ["consistency_check", "mv_refresh"]
    # every driven child was adopted under the batch run and converged to done.
    adopted = [job_id for ev, job_id, *_ in _FakeExecutor.events if ev == "adopt"]
    assert adopted == ["child-juso", "child-locsum", "consistency_check-child", "mv_refresh-child"]
    done = [job_id for ev, job_id in (e[:2] for e in _FakeExecutor.events) if ev == "done"]
    assert done == ["child-juso", "child-locsum", "consistency_check-child", "mv_refresh-child"]
    assert result["consistency_report_id"] == "rep-1"
    assert result["source_children"] == 2


@pytest.mark.asyncio
async def test_gate_blocks_mv_on_consistency_error(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _Harness(severity="ERROR")
    _install_harness(monkeypatch, harness)

    with pytest.raises(FullLoadBatchGateError):
        await _run({})

    # consistency ran, but the ERROR gate blocked mv: no mv child inserted, no mv leaf call.
    assert harness.mv_payloads == []
    assert [kind for kind, _ in _FakeRepo.inserts] == ["consistency_check"]


@pytest.mark.asyncio
async def test_forced_promotion_bypasses_error_gate_and_threads_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness(severity="ERROR")
    _install_harness(monkeypatch, harness)

    result = await _run(
        {
            "forced_promotion": True,
            "source_match_set_id": "sms-1",
            "forced_promotion_actor": "ui:admin",
            "forced_promotion_reason": "known source-quality gap",
        }
    )

    assert len(harness.mv_payloads) == 1
    mv = harness.mv_payloads[0]
    assert mv["forced_promotion"] is True
    assert mv["source_match_set_id"] == "sms-1"
    assert mv["forced_promotion_metadata"]["consistency_severity"] == "ERROR"
    assert mv["forced_promotion_metadata"]["forced_promotion_actor"] == "ui:admin"
    assert result["forced_promotion"] is True


@pytest.mark.asyncio
async def test_source_failure_fails_child_and_cancels_siblings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.fail_source = "juso_text_load"  # first source fails
    _install_harness(monkeypatch, harness)

    with pytest.raises(RuntimeError, match="juso_text_load boom"):
        await _run({})

    # the failed child was marked failed; the queued siblings were cancelled; no consistency ran.
    assert ("failed", "child-juso", "juso_text_load boom") in _FakeExecutor.events
    assert _FakeRepo.cancelled == ["batch-1"]
    assert harness.source_calls == ["juso_text_load"]  # stopped at the failure
    assert harness.consistency_payloads == []


@pytest.mark.asyncio
async def test_source_cancel_marks_cancelled_and_cancels_siblings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    harness.cancel_source = "juso_text_load"
    _install_harness(monkeypatch, harness)

    with pytest.raises(asyncio.CancelledError):
        await _run({})

    assert ("cancelled", "child-juso") in _FakeExecutor.events
    assert _FakeRepo.cancelled == ["batch-1"]


@pytest.mark.asyncio
async def test_precancelled_batch_raises_before_any_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    _install_harness(monkeypatch, harness)

    cancel_event = asyncio.Event()
    cancel_event.set()
    with pytest.raises(asyncio.CancelledError):
        await run_full_load_batch(
            object(),
            batch_id="batch-1",
            payload={},
            cancel_event=cancel_event,
            progress=_noop_progress,
            orchestrator_run_id="run-1",
            lease_ttl_seconds=300.0,
        )

    assert harness.source_calls == []
