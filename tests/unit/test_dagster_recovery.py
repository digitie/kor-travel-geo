"""T-290k §2g/§2h real seams: liveness probe (outage grace) + cancel hook (best-effort)."""

from __future__ import annotations

import httpx
import pytest

from kortravelgeo.api import _dagster_recovery
from kortravelgeo.core.job_recovery import (
    OrchestratorRunState,
    ReconcileOutcome,
    reconcile_load_job,
)
from kortravelgeo.settings import Settings


def _settings() -> Settings:
    return Settings(_env_file=None)


@pytest.mark.asyncio
async def test_liveness_probe_none_run_id_is_missing() -> None:
    probe = _dagster_recovery.dagster_liveness_probe(_settings())
    assert await probe(orchestrator_run_id=None, lease_valid=True) is OrchestratorRunState.MISSING


@pytest.mark.asyncio
async def test_liveness_probe_returns_observed_state(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(settings: Settings, *, run_id: str) -> OrchestratorRunState:
        return OrchestratorRunState.SUCCESS

    monkeypatch.setattr(_dagster_recovery, "fetch_run_state", fake_fetch)
    probe = _dagster_recovery.dagster_liveness_probe(_settings())
    assert await probe(orchestrator_run_id="r1", lease_valid=False) is OrchestratorRunState.SUCCESS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lease_valid", "expected"),
    [(True, OrchestratorRunState.UNKNOWN), (False, OrchestratorRunState.UNKNOWN)],
)
async def test_liveness_probe_outage_remains_unknown(
    monkeypatch: pytest.MonkeyPatch, lease_valid: bool, expected: OrchestratorRunState
) -> None:
    async def boom(settings: Settings, *, run_id: str) -> OrchestratorRunState:
        raise httpx.ConnectError("dagster down")

    monkeypatch.setattr(_dagster_recovery, "fetch_run_state", boom)
    probe = _dagster_recovery.dagster_liveness_probe(_settings())
    # 조회 장애와 실행 부재는 lease 만료 뒤에도 구별한다.
    assert await probe(orchestrator_run_id="r1", lease_valid=lease_valid) is expected


@pytest.mark.asyncio
async def test_cancel_hook_none_run_id_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_terminate(settings: Settings, *, run_id: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(_dagster_recovery, "terminate_run", fake_terminate)
    cancel = _dagster_recovery.dagster_orchestrator_cancel(_settings())
    await cancel(job_id="j1", orchestrator_run_id=None)
    assert called is False


@pytest.mark.asyncio
async def test_cancel_hook_terminates_run(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def fake_terminate(settings: Settings, *, run_id: str) -> None:
        seen.append(run_id)

    monkeypatch.setattr(_dagster_recovery, "terminate_run", fake_terminate)
    cancel = _dagster_recovery.dagster_orchestrator_cancel(_settings())
    await cancel(job_id="j1", orchestrator_run_id="r1")
    assert seen == ["r1"]


@pytest.mark.asyncio
async def test_cancel_hook_is_best_effort_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(settings: Settings, *, run_id: str) -> None:
        raise httpx.ConnectError("dagster down")

    monkeypatch.setattr(_dagster_recovery, "terminate_run", boom)
    cancel = _dagster_recovery.dagster_orchestrator_cancel(_settings())
    # Must not raise — load_jobs is the cancel authority; the reconciler converges residue.
    await cancel(job_id="j1", orchestrator_run_id="r1")


@pytest.mark.asyncio
@pytest.mark.parametrize("lease_valid", [True, False])
async def test_outage_never_reaps_a_worker_even_after_lease_expiry(
    monkeypatch: pytest.MonkeyPatch, lease_valid: bool
) -> None:
    async def unavailable(settings: Settings, *, run_id: str) -> OrchestratorRunState:
        raise httpx.ConnectError("metadata unavailable")

    monkeypatch.setattr(_dagster_recovery, "fetch_run_state", unavailable)
    probe = _dagster_recovery.dagster_liveness_probe(_settings())
    observed = await probe(orchestrator_run_id="r1", lease_valid=lease_valid)
    action = reconcile_load_job(
        run_state=observed, job_state="running", lease_valid=lease_valid
    )
    assert action.outcome is ReconcileOutcome.KEEP_RUNNING
    assert action.target_state is None


@pytest.mark.parametrize(
    "payload",
    [
        {"errors": [{"message": "query failed"}]},
        {"data": {"runOrError": {"__typename": "PythonError"}}},
        {"data": {"runOrError": {"__typename": "UnauthorizedError"}}},
        {"data": {"runOrError": {"__typename": "Run"}}},
        None,
    ],
)
def test_unconfirmed_graphql_result_never_means_worker_missing(payload: object) -> None:
    from kortravelgeo.api._dagster_client import _parse_run_state

    action = reconcile_load_job(
        run_state=_parse_run_state(payload), job_state="running", lease_valid=False
    )
    assert action.outcome is ReconcileOutcome.KEEP_RUNNING
