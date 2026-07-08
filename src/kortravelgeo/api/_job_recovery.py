"""Executor-aware recovery + Dagster↔``load_jobs`` reconciliation primitives (T-290c).

This module holds the *pure* convergence logic and the pluggable seams that let the
in-process :class:`~kortravelgeo.api._jobs.JobQueue` become executor-aware *before*
Dagster is wired in as an actual executor (ADR-066 §5, ``docs/architecture/
dagster-boundary.md`` §6). It is the gate that must land before M3+.

Design constraints:

* **No Dagster import, no I/O.** Nothing here talks to Dagster. The source of Dagster
  run state is injected as a :class:`RunLivenessProbe` seam, and cancel propagation is
  an :class:`OrchestratorCancelHook` seam. The real GraphQL implementations land with a
  later milestone; the defaults here fabricate no client.
* **Additive / behavior-preserving.** Every existing ``load_jobs`` row is
  ``executor='api_in_process'`` and never takes a lease, so all in-process code paths
  behave exactly as before.

State boundary recap (2 sources of truth, dagster-boundary §6):

* Dagster run store  — run/event/schedule/retry history (authoritative for *runs*).
* app ``load_jobs``  — admin progress/cancel/audit (authoritative for *job state*).

The reconciler converges ``load_jobs`` toward the observed Dagster run state per the
review's table (``docs/backup-restore-orchestration.md`` "Reconcile").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, assert_never

from kortravelgeo.dto.admin import LoadJobState

#: ``load_jobs.executor`` value for the historical in-process worker (the default).
EXECUTOR_API_IN_PROCESS = "api_in_process"
#: ``load_jobs.executor`` value for jobs whose long-running work is a Dagster run.
EXECUTOR_DAGSTER = "dagster"
#: Every value ``load_jobs.executor`` may hold. Kept in lockstep with the DB CHECK
#: constraint (``infra/sql.py`` SCHEMA_SQL + alembic ``0023``).
EXECUTORS: tuple[str, ...] = (EXECUTOR_API_IN_PROCESS, EXECUTOR_DAGSTER)

#: Fallback lease TTL (seconds) when no :class:`~kortravelgeo.settings.Settings` value is
#: supplied. Mirrors ``Settings.dagster_lease_ttl_seconds`` so callers without a Settings
#: instance (unit tests, standalone helpers) still get a sane grace window.
DEFAULT_LEASE_TTL_SECONDS = 300.0


class OrchestratorRunState(StrEnum):
    """Normalized Dagster run state, as resolved by a :class:`RunLivenessProbe`.

    The real GraphQL probe maps Dagster ``RunStatus`` onto these members; the default
    lease-only probe emits only :attr:`RUNNING` / :attr:`MISSING`.
    """

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RUNNING = "running"
    #: No live run reference could be resolved (unknown/purged run id, or no probe wired).
    MISSING = "missing"


class ReconcileOutcome(StrEnum):
    """What the reconciler decided to do with a single ``load_jobs`` row."""

    KEEP_RUNNING = "keep_running"
    CONVERGE_DONE = "converge_done"
    CONVERGE_FAILED = "converge_failed"
    CONVERGE_CANCELLED = "converge_cancelled"
    #: Dagster still running but ``load_jobs`` is already failed/cancelled. The operator
    #: (or the cancel seam) must terminate the Dagster run so both sides agree — the
    #: split-brain the boundary doc forbids ("한쪽만 취소된 상태를 만들지 않는다").
    FLAG_ORPHAN = "flag_orphan"
    #: Already consistent; nothing to write.
    NOOP = "noop"


#: Outcomes that carry a terminal ``load_jobs.state`` to write.
_TERMINAL_TARGET: dict[ReconcileOutcome, LoadJobState] = {
    ReconcileOutcome.CONVERGE_DONE: "done",
    ReconcileOutcome.CONVERGE_FAILED: "failed",
    ReconcileOutcome.CONVERGE_CANCELLED: "cancelled",
}


@dataclass(frozen=True, slots=True)
class ReconcileAction:
    """Immutable decision produced by :func:`reconcile_load_job`."""

    outcome: ReconcileOutcome
    reason: str

    @property
    def target_state(self) -> LoadJobState | None:
        """The terminal ``load_jobs.state`` to converge to, or ``None`` to leave as-is."""

        return _TERMINAL_TARGET.get(self.outcome)

    @property
    def converges(self) -> bool:
        """``True`` when this action writes a terminal ``load_jobs.state``."""

        return self.outcome in _TERMINAL_TARGET


def reconcile_load_job(
    *,
    run_state: OrchestratorRunState,
    job_state: LoadJobState,
    lease_valid: bool,
) -> ReconcileAction:
    """Pure convergence of one ``load_jobs`` row against its Dagster run state.

    This is the reconciler table (``docs/backup-restore-orchestration.md`` "Reconcile"
    + dagster-boundary §6). ``job_state`` and ``lease_valid`` fully describe the row for
    reconciliation; ``run_state`` is what the injected probe observed for the run.

    ===========================  ==============  ==========================================
    Dagster run (``run_state``)  ``job_state``   result
    ===========================  ==============  ==========================================
    success                      running         converge → ``done``
    failed                       running         converge → ``failed``
    cancelled                    running         converge → ``cancelled``
    running                      running         keep running
    missing + lease valid        running         keep running (grace: run may be starting,
                                                 or probe degraded — never kill a live job)
    missing + lease expired      running         converge → ``failed``
    running                      failed         flag orphan (terminate the Dagster run)
    running                      cancelled      flag orphan (terminate the Dagster run)
    (any)                        terminal        noop (already consistent)
    ===========================  ==============  ==========================================

    The function is total and side-effect free so it can be exhaustively unit-tested and
    reused unchanged by both startup recovery and the periodic reconciler tick.
    """

    if job_state != "running":
        # load_jobs is already terminal. The actionable divergence is a live Dagster run
        # behind an already failed/cancelled job (the reverse split-brain).
        if job_state in {"failed", "cancelled"} and run_state is OrchestratorRunState.RUNNING:
            return ReconcileAction(
                ReconcileOutcome.FLAG_ORPHAN,
                f"load_jobs {job_state} but Dagster run still running; terminate run",
            )
        return ReconcileAction(ReconcileOutcome.NOOP, "load_jobs already terminal")

    if run_state is OrchestratorRunState.SUCCESS:
        return ReconcileAction(ReconcileOutcome.CONVERGE_DONE, "Dagster run succeeded")
    if run_state is OrchestratorRunState.FAILED:
        return ReconcileAction(ReconcileOutcome.CONVERGE_FAILED, "Dagster run failed")
    if run_state is OrchestratorRunState.CANCELLED:
        return ReconcileAction(ReconcileOutcome.CONVERGE_CANCELLED, "Dagster run cancelled")
    if run_state is OrchestratorRunState.RUNNING:
        return ReconcileAction(ReconcileOutcome.KEEP_RUNNING, "Dagster run alive")
    if run_state is OrchestratorRunState.MISSING:
        if lease_valid:
            return ReconcileAction(
                ReconcileOutcome.KEEP_RUNNING,
                "no live run reference but lease still valid; grace",
            )
        return ReconcileAction(
            ReconcileOutcome.CONVERGE_FAILED,
            "no live run reference and lease expired",
        )
    assert_never(run_state)  # pragma: no cover - exhaustiveness guard


class RunLivenessProbe(Protocol):
    """Seam that resolves the current Dagster run state for a ``load_jobs`` row.

    The real implementation (later milestone) POSTs a GraphQL query to the Dagster
    webserver, maps ``RunStatus`` → :class:`OrchestratorRunState`, and falls back to
    ``lease_valid`` when Dagster is unreachable (so a Dagster *outage* never force-fails a
    live job). See :func:`lease_only_liveness_probe` for the no-client default.
    """

    async def __call__(
        self,
        *,
        orchestrator_run_id: str | None,
        lease_valid: bool,
    ) -> OrchestratorRunState: ...


async def lease_only_liveness_probe(
    *,
    orchestrator_run_id: str | None,
    lease_valid: bool,
) -> OrchestratorRunState:
    """Default :class:`RunLivenessProbe`, used until a Dagster client is wired.

    With no way to query Dagster, a *valid lease* is treated as "still alive" and an
    *expired lease* (or a missing run id) as gone. This encodes the recovery rule from
    dagster-boundary §6 ("살아 있으면 유지 … lease 만료 + run 없음이면 failed") without
    fabricating a Dagster client — the real GraphQL check replaces this probe later.
    """

    if orchestrator_run_id is None:
        return OrchestratorRunState.MISSING
    return OrchestratorRunState.RUNNING if lease_valid else OrchestratorRunState.MISSING


class OrchestratorCancelHook(Protocol):
    """Seam that propagates an app-side cancel to the Dagster run (bidirectional cancel).

    ``load_jobs`` remains the cancel authority (``docs/backup-restore-orchestration.md``
    "Cancel"); this hook mirrors the intent onto the Dagster run so we never leave a
    one-sided cancel. The real hook issues a ``terminateRun`` GraphQL mutation; the
    reconciler then guarantees residual divergence converges. Default:
    :func:`noop_orchestrator_cancel`.
    """

    async def __call__(
        self,
        *,
        job_id: str,
        orchestrator_run_id: str | None,
    ) -> None: ...


async def noop_orchestrator_cancel(
    *,
    job_id: str,
    orchestrator_run_id: str | None,
) -> None:
    """Default :class:`OrchestratorCancelHook`: no Dagster client yet, so cancel intent is
    only recorded by the caller (job log tail). Real run termination lands with the
    GraphQL wiring; until then the reconciler closes the loop from the Dagster side."""

    return None


def compute_lease_expiry(
    *,
    now: datetime,
    ttl_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
) -> datetime:
    """Absolute expiry for a freshly set or renewed lease."""

    return now + timedelta(seconds=ttl_seconds)


def is_lease_valid(*, lease_expires_at: datetime | None, now: datetime) -> bool:
    """``True`` when the lease exists and has not yet expired at ``now``."""

    return lease_expires_at is not None and lease_expires_at > now
