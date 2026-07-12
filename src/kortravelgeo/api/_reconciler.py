"""Standalone executor-aware Dagster↔``load_jobs`` reconciler (T-290k §2h).

Extracted from :class:`~kortravelgeo.api._jobs.JobQueue` so reconciliation no longer depends
on the in-process drain (which T-290k PR4 deletes). It owns only the *Dagster* half of the old
``recover_startup``; the queue keeps ``_recover_in_process_running`` until the drain is gone.

Both entry points — startup convergence and the periodic ``app.py`` tick — share
:meth:`reconcile_once`, which resolves the pure decision
:func:`~kortravelgeo.core.job_recovery.reconcile_load_job`.

Terminal writes go straight through :class:`~kortravelgeo.infra.load_job_executor.LoadJobExecutor`
(``mark_done``/``mark_failed``/``mark_cancelled`` + ``set_progress``); the in-process batch-root
aggregation the old ``JobQueue._done``/``_fail`` also did does NOT apply here — a Dagster
``full_load_batch`` drives + aggregates its own children inside the op via the load-job bridge,
so the reconciler only ever converges the root/child rows it directly observes.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.job_recovery import (
    OrchestratorCancelHook,
    ReconcileAction,
    ReconcileOutcome,
    RunLivenessProbe,
    is_lease_valid,
    reconcile_load_job,
)
from kortravelgeo.dto.admin import LoadJobState
from kortravelgeo.infra.load_job_executor import LoadJobExecutor

logger = logging.getLogger(__name__)


class DagsterJobReconciler:
    """Converge ``executor='dagster'`` ``load_jobs`` rows toward their real Dagster run state.

    Stateless over ``(engine, executor, liveness_probe, orchestrator_cancel)``; safe to call
    ``reconcile_once`` from both startup and a periodic tick. The liveness probe does the
    network I/O and is invoked *outside* any DB transaction, so rows are snapshotted first and
    converged one at a time.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        executor: LoadJobExecutor,
        liveness_probe: RunLivenessProbe,
        orchestrator_cancel: OrchestratorCancelHook,
    ) -> None:
        self._engine = engine
        self._executor = executor
        self._liveness_probe = liveness_probe
        self._orchestrator_cancel = orchestrator_cancel

    async def reconcile_once(self) -> list[tuple[str, ReconcileAction]]:
        """Snapshot the reconcilable dagster rows, probe each run, and apply the decision.

        Returns the ``(job_id, action)`` decisions for observability/testing.
        """

        rows = await self._reconcile_rows()
        now = datetime.now(UTC)
        results: list[tuple[str, ReconcileAction]] = []
        for row in rows:
            job_id = str(row["job_id"])
            job_state = cast("LoadJobState", row["state"])
            lease_valid = is_lease_valid(lease_expires_at=row.get("lease_expires_at"), now=now)
            run_state = await self._liveness_probe(
                orchestrator_run_id=row.get("orchestrator_run_id"),
                lease_valid=lease_valid,
            )
            action = reconcile_load_job(
                run_state=run_state,
                job_state=job_state,
                lease_valid=lease_valid,
            )
            await self._apply(job_id, action, orchestrator_run_id=row.get("orchestrator_run_id"))
            results.append((job_id, action))
        return results

    async def _reconcile_rows(self) -> list[dict[str, Any]]:
        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT job_id, state, orchestrator_run_id, lease_expires_at
  FROM load_jobs
 WHERE executor = 'dagster'
   AND (
     state = 'running'
     OR (
       state IN ('failed','cancelled')
       AND orchestrator_run_id IS NOT NULL
     )
   )
 ORDER BY created_at
"""
                    )
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    async def _apply(
        self,
        job_id: str,
        action: ReconcileAction,
        *,
        orchestrator_run_id: str | None,
    ) -> None:
        """Apply a :class:`ReconcileAction`. ``KEEP_RUNNING``/``NOOP`` write nothing."""

        if action.outcome is ReconcileOutcome.CONVERGE_DONE:
            await self._executor.mark_done(job_id)
            await self._executor.set_progress(
                job_id, progress=1.0, stage="done", message=f"reconciled: {action.reason}"
            )
        elif action.outcome is ReconcileOutcome.CONVERGE_FAILED:
            await self._executor.mark_failed(job_id, f"reconciled: {action.reason}")
            await self._executor.set_progress(
                job_id, stage="failed", message=f"reconciled: {action.reason}"
            )
        elif action.outcome is ReconcileOutcome.CONVERGE_CANCELLED:
            await self._executor.mark_cancelled(job_id)
            await self._executor.set_progress(
                job_id, stage="cancelled", message=f"reconciled: {action.reason}"
            )
        elif action.outcome is ReconcileOutcome.FLAG_ORPHAN:
            # Reverse split-brain: Dagster run alive but load_jobs already terminal. Record it
            # and terminate the run so both sides agree (the boundary doc's forbidden state).
            await self._executor.set_progress(job_id, message=f"orphan: {action.reason}")
            await self._orchestrator_cancel(
                job_id=job_id, orchestrator_run_id=orchestrator_run_id
            )
