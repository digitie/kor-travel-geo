"""Queue-free load-job cancel that closes both sides of the executor boundary (T-290k §2g).

``load_jobs`` is the cancel authority (``docs/backup-restore-orchestration.md`` "Cancel"): the
row is converged to ``cancelled`` for every executor, then the intent is mirrored onto the
long-running worker so we never leave a one-sided cancel:

* ``executor='dagster'`` → a real Dagster ``terminateRun`` via the injected
  :class:`~kortravelgeo.core.job_recovery.OrchestratorCancelHook`; the reconciler tick converges
  any residual gap if the terminate is best-effort-dropped.
* ``executor='api_in_process'`` → the in-process ``cancel_event`` is set through the optional
  ``in_process_cancel`` callback the still-present :class:`~kortravelgeo.api._jobs.JobQueue`
  provides during the T-290k transition (PR4 removes the in-process path and this callback).

Replaces ``JobQueue.cancel`` at the endpoint layer without depending on the drain, so PR4 can
delete the queue while cancel keeps working.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.job_recovery import (
    EXECUTOR_API_IN_PROCESS,
    EXECUTOR_DAGSTER,
    OrchestratorCancelHook,
)
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.load_job_executor import LoadJobExecutor


async def _executor_ref(engine: AsyncEngine, job_id: str) -> tuple[str, str | None]:
    """``(executor, orchestrator_run_id)`` for a job; defaults to the in-process executor when
    the row is absent so cancel stays total (never raises on a stale id)."""

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT executor, orchestrator_run_id FROM load_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            )
        ).mappings().first()
    if row is None:
        return (EXECUTOR_API_IN_PROCESS, None)
    return (str(row["executor"]), row.get("orchestrator_run_id"))


async def cancel_load_job_converged(
    engine: AsyncEngine,
    job_id: str,
    *,
    orchestrator_cancel: OrchestratorCancelHook,
    in_process_cancel: Callable[[str], bool] | None = None,
) -> None:
    """Cancel ``job_id`` and propagate the intent to whichever executor runs it.

    ``in_process_cancel`` (from the transitional JobQueue) sets the local cancel event for
    ``api_in_process`` rows; ``orchestrator_cancel`` issues ``terminateRun`` for ``dagster``
    rows. Both the row and its queued batch children converge to ``cancelled`` regardless.
    """

    executor, orchestrator_run_id = await _executor_ref(engine, job_id)
    if executor == EXECUTOR_API_IN_PROCESS and in_process_cancel is not None:
        in_process_cancel(job_id)
    repo = AdminRepository(engine)
    await repo.cancel_load_job(job_id)
    await repo.cancel_queued_batch_children(job_id)
    if executor == EXECUTOR_DAGSTER:
        await LoadJobExecutor(engine).set_progress(
            job_id, message="cancel requested; propagating to Dagster run"
        )
        await orchestrator_cancel(job_id=job_id, orchestrator_run_id=orchestrator_run_id)
