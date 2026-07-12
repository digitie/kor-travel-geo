"""Real Dagster ``RunLivenessProbe`` + ``OrchestratorCancelHook`` implementations (T-290k §2g/§2h).

These wrap the raw GraphQL calls in :mod:`kortravelgeo.api._dagster_client` with the recovery
semantics the pure ``core.job_recovery`` seams describe but deliberately do not fabricate:

* the **liveness probe** never force-fails a live job on a Dagster *outage* — a transport or
  URL-config failure degrades to lease grace (``RUNNING`` while the lease is valid), so only a
  Dagster run that Dagster itself reports gone/terminal converges the ``load_jobs`` row;
* the **cancel hook** is best-effort — a failed ``terminateRun`` is logged, not raised, because
  ``load_jobs`` is the cancel authority and the periodic reconciler closes any residual
  one-sided divergence.

Wiring the real hooks (instead of the lease-only / noop defaults) is what closes the
split-brain the boundary doc forbids ("한쪽만 취소된 상태를 만들지 않는다").
"""

from __future__ import annotations

import logging

import httpx

from kortravelgeo.api._dagster_client import (
    DagsterTerminateError,
    DagsterUrlConfigurationError,
    fetch_run_state,
    terminate_run,
)
from kortravelgeo.core.job_recovery import (
    OrchestratorCancelHook,
    OrchestratorRunState,
    RunLivenessProbe,
)
from kortravelgeo.settings import Settings

logger = logging.getLogger(__name__)

_PROBE_DEGRADED_ERRORS = (DagsterUrlConfigurationError, httpx.HTTPError)
_CANCEL_BEST_EFFORT_ERRORS = (
    DagsterUrlConfigurationError,
    DagsterTerminateError,
    httpx.HTTPError,
)


def dagster_liveness_probe(settings: Settings) -> RunLivenessProbe:
    """Build the real :class:`RunLivenessProbe` bound to ``settings`` (GraphQL run status).

    ``orchestrator_run_id is None`` → ``MISSING`` (never launched / lost id). A reachable
    Dagster maps the run status onto :class:`OrchestratorRunState`. A Dagster *outage*
    (transport/URL-config error) degrades to lease grace so a monitoring blip never kills a
    healthy job — exactly the fallback the ``core`` probe protocol documents.
    """

    async def probe(
        *,
        orchestrator_run_id: str | None,
        lease_valid: bool,
    ) -> OrchestratorRunState:
        if orchestrator_run_id is None:
            return OrchestratorRunState.MISSING
        try:
            return await fetch_run_state(settings, run_id=orchestrator_run_id)
        except _PROBE_DEGRADED_ERRORS:
            logger.warning(
                "Dagster liveness probe degraded for run %s; falling back to lease grace",
                orchestrator_run_id,
            )
            return OrchestratorRunState.RUNNING if lease_valid else OrchestratorRunState.MISSING

    return probe


def dagster_orchestrator_cancel(settings: Settings) -> OrchestratorCancelHook:
    """Build the real :class:`OrchestratorCancelHook` bound to ``settings`` (``terminateRun``).

    Best-effort: a failed terminate is logged, not raised. ``load_jobs`` is already the cancel
    authority (the caller converges the row); the reconciler tick terminates any Dagster run
    that outlives an already-cancelled job, so a transient terminate failure self-heals.
    """

    async def cancel(*, job_id: str, orchestrator_run_id: str | None) -> None:
        if orchestrator_run_id is None:
            return
        try:
            await terminate_run(settings, run_id=orchestrator_run_id)
        except _CANCEL_BEST_EFFORT_ERRORS as exc:
            logger.warning(
                "Dagster terminateRun failed for job %s run %s (%s); reconciler will converge",
                job_id,
                orchestrator_run_id,
                exc,
            )

    return cancel
