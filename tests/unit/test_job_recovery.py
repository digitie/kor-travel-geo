from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kortravelgeo.api._job_recovery import (
    DEFAULT_LEASE_TTL_SECONDS,
    EXECUTORS,
    OrchestratorRunState,
    ReconcileOutcome,
    compute_lease_expiry,
    is_lease_valid,
    lease_only_liveness_probe,
    reconcile_load_job,
)

_NOW = datetime(2026, 7, 8, 12, 0, 0, tzinfo=UTC)


# --- pure reconciler table (backup-restore-orchestration.md "Reconcile" + boundary §6) ---
@pytest.mark.parametrize(
    ("run_state", "job_state", "lease_valid", "expected", "target"),
    [
        (OrchestratorRunState.SUCCESS, "running", True, ReconcileOutcome.CONVERGE_DONE, "done"),
        (OrchestratorRunState.SUCCESS, "running", False, ReconcileOutcome.CONVERGE_DONE, "done"),
        (OrchestratorRunState.FAILED, "running", True, ReconcileOutcome.CONVERGE_FAILED, "failed"),
        (
            OrchestratorRunState.CANCELLED,
            "running",
            True,
            ReconcileOutcome.CONVERGE_CANCELLED,
            "cancelled",
        ),
        (OrchestratorRunState.RUNNING, "running", False, ReconcileOutcome.KEEP_RUNNING, None),
        # missing run reference: lease grace keeps it running, expiry converges to failed
        (OrchestratorRunState.MISSING, "running", True, ReconcileOutcome.KEEP_RUNNING, None),
        (
            OrchestratorRunState.MISSING,
            "running",
            False,
            ReconcileOutcome.CONVERGE_FAILED,
            "failed",
        ),
        # reverse split-brain: run alive but load_jobs already failed -> orphan
        (OrchestratorRunState.RUNNING, "failed", False, ReconcileOutcome.FLAG_ORPHAN, None),
        # already-terminal load_jobs -> noop (no false convergence)
        (OrchestratorRunState.SUCCESS, "done", True, ReconcileOutcome.NOOP, None),
        (OrchestratorRunState.FAILED, "failed", False, ReconcileOutcome.NOOP, None),
        (OrchestratorRunState.MISSING, "cancelled", False, ReconcileOutcome.NOOP, None),
    ],
)
def test_reconcile_load_job_table(
    run_state: OrchestratorRunState,
    job_state: str,
    lease_valid: bool,
    expected: ReconcileOutcome,
    target: str | None,
) -> None:
    action = reconcile_load_job(
        run_state=run_state,
        job_state=job_state,  # type: ignore[arg-type]
        lease_valid=lease_valid,
    )
    assert action.outcome is expected
    assert action.target_state == target
    assert action.converges is (target is not None)
    assert action.reason  # always a human-readable reason


def test_executors_tuple_matches_boundary_values() -> None:
    assert EXECUTORS == ("api_in_process", "dagster")


# --- lease helpers ---
def test_compute_lease_expiry_adds_ttl() -> None:
    assert compute_lease_expiry(now=_NOW, ttl_seconds=120.0) == _NOW + timedelta(seconds=120)
    # default TTL when unspecified
    assert compute_lease_expiry(now=_NOW) == _NOW + timedelta(seconds=DEFAULT_LEASE_TTL_SECONDS)


@pytest.mark.parametrize(
    ("lease_expires_at", "expected"),
    [
        (None, False),
        (_NOW + timedelta(seconds=1), True),
        (_NOW - timedelta(seconds=1), False),
        (_NOW, False),  # strictly-after: exactly-now is expired
    ],
)
def test_is_lease_valid(lease_expires_at: datetime | None, expected: bool) -> None:
    assert is_lease_valid(lease_expires_at=lease_expires_at, now=_NOW) is expected


# --- default lease-only liveness probe (no Dagster client) ---
@pytest.mark.asyncio
async def test_lease_only_probe_missing_when_no_run_id() -> None:
    state = await lease_only_liveness_probe(orchestrator_run_id=None, lease_valid=True)
    assert state is OrchestratorRunState.MISSING


@pytest.mark.asyncio
async def test_lease_only_probe_running_when_lease_valid() -> None:
    state = await lease_only_liveness_probe(orchestrator_run_id="run-1", lease_valid=True)
    assert state is OrchestratorRunState.RUNNING


@pytest.mark.asyncio
async def test_lease_only_probe_missing_when_lease_expired() -> None:
    state = await lease_only_liveness_probe(orchestrator_run_id="run-1", lease_valid=False)
    assert state is OrchestratorRunState.MISSING
