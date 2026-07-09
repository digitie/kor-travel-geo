"""Atomic ``load_jobs`` state-transition primitives (T-290g).

Engine-level writers for a single ``load_jobs`` row's lifecycle — progress + log tail,
terminal state, Dagster-executor adoption, lease renewal, and the cancel-state read. This
lives in ``infra`` (below ``api``) so BOTH the api in-process
:class:`~kortravelgeo.api._jobs.JobQueue` AND the out-of-process Dagster ``db_backup`` op
can drive ``load_jobs`` without the op importing ``kortravelgeo.api`` (dagster-boundary §6:
the op executes leaves one-way and never calls back into the web layer).

Deliberately pure SQL: no batch-DAG orchestration and no in-memory stage-duration metrics.
Those remain in the ``JobQueue`` wrappers, which delegate their single-row writes here so
the two executors share one source of truth for the ``load_jobs`` transitions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.core.job_recovery import DEFAULT_LEASE_TTL_SECONDS, compute_lease_expiry

#: Cap the persisted ``log_tail`` at the most recent N lines (matches the historical
#: in-process behavior so admin log tails do not grow unbounded).
LOG_TAIL_CAP = 200


class LoadJobExecutor:
    """Single-row ``load_jobs`` writers shared by the api queue and the Dagster op.

    Bound to an :class:`AsyncEngine`; every method is one short autonomous transaction so
    it is safe to call from either the in-process drain loop or a Dagster op without
    holding a wider transaction open.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        lease_ttl_seconds: float = DEFAULT_LEASE_TTL_SECONDS,
    ) -> None:
        self.engine = engine
        self._lease_ttl_seconds = lease_ttl_seconds

    def lease_expiry(self, ttl_seconds: float | None = None) -> datetime:
        """Absolute expiry for a freshly set / renewed lease (default TTL when ``None``)."""

        ttl = self._lease_ttl_seconds if ttl_seconds is None else ttl_seconds
        return compute_lease_expiry(now=datetime.now(UTC), ttl_seconds=ttl)

    async def adopt_dagster(
        self,
        job_id: str,
        orchestrator_run_id: str,
        *,
        ttl_seconds: float | None = None,
    ) -> datetime:
        """Adopt a row into the Dagster executor: set ``executor='dagster'``, record the
        backing run id and an initial lease, and move ``queued`` → ``running`` (leaving an
        already-terminal state untouched). Returns the new lease expiry."""

        expires_at = self.lease_expiry(ttl_seconds)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET executor = 'dagster',
       orchestrator_run_id = :orchestrator_run_id,
       lease_expires_at = :expires_at,
       state = CASE WHEN state = 'queued' THEN 'running' ELSE state END,
       started_at = COALESCE(started_at, now()),
       heartbeat_at = now()
 WHERE job_id = :job_id
"""
                ),
                {
                    "job_id": job_id,
                    "orchestrator_run_id": orchestrator_run_id,
                    "expires_at": expires_at,
                },
            )
        return expires_at

    async def renew_lease(self, job_id: str, *, ttl_seconds: float | None = None) -> datetime:
        """Renew ``lease_expires_at`` (and heartbeat) for a Dagster-executed job. Returns
        the new lease expiry. Called periodically by the op as it makes progress."""

        expires_at = self.lease_expiry(ttl_seconds)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET lease_expires_at = :expires_at,
       heartbeat_at = now()
 WHERE job_id = :job_id
"""
                ),
                {"job_id": job_id, "expires_at": expires_at},
            )
        return expires_at

    async def set_progress(
        self,
        job_id: str,
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None:
        """Update progress / current stage / heartbeat and append ``message`` to the
        capped ``log_tail``. Every argument is optional; ``heartbeat_at`` is always bumped."""

        log_tail: list[str] | None = None
        if message is not None:
            prefix = datetime.now(UTC).isoformat(timespec="seconds")
            label = f" [{stage}]" if stage else ""
            async with self.engine.connect() as conn:
                existing = await conn.scalar(
                    text("SELECT log_tail FROM load_jobs WHERE job_id = :job_id"),
                    {"job_id": job_id},
                )
            log_tail = [str(line) for line in (existing or [])]
            log_tail.append(f"{prefix}{label} {message}")
            log_tail = log_tail[-LOG_TAIL_CAP:]

        params: dict[str, Any] = {"job_id": job_id}
        assignments = ["heartbeat_at = now()"]
        if progress is not None:
            params["progress"] = max(0.0, min(1.0, progress))
            assignments.append("progress = :progress")
        if stage is not None:
            params["stage"] = stage
            assignments.append("current_stage = :stage")
        if log_tail is not None:
            params["log_tail"] = log_tail
            assignments.append("log_tail = :log_tail")
        stmt = text(f"UPDATE load_jobs SET {', '.join(assignments)} WHERE job_id = :job_id")
        if log_tail is not None:
            stmt = stmt.bindparams(bindparam("log_tail", type_=JSONB))
        async with self.engine.begin() as conn:
            await conn.execute(stmt, params)

    async def mark_done(self, job_id: str) -> None:
        """Converge a row to ``done`` (progress 1.0). A row already ``cancelled`` is left
        as-is so a late completion never overrides an operator cancel."""

        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'done',
       progress = 1.0,
       current_stage = 'done',
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :job_id AND state <> 'cancelled'
"""
                ),
                {"job_id": job_id},
            )

    async def mark_failed(self, job_id: str, message: str) -> None:
        """Converge a row to ``failed`` with ``error_message``."""

        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'failed',
       current_stage = 'failed',
       error_message = :message,
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :job_id
"""
                ),
                {"job_id": job_id, "message": message},
            )

    async def mark_cancelled(self, job_id: str) -> None:
        """Converge a row to ``cancelled``."""

        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'cancelled',
       current_stage = 'cancelled',
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :job_id
"""
                ),
                {"job_id": job_id},
            )

    async def read_cancel_requested(self, job_id: str) -> bool:
        """``True`` when the row has been converged to ``cancelled`` (the cancel authority).

        The Dagster op polls this to bridge an app-side cancel onto its local
        ``cancel_event`` (``load_jobs`` stays the cancel source of truth, ADR-066 §5)."""

        async with self.engine.connect() as conn:
            state = await conn.scalar(
                text("SELECT state FROM load_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            )
        return bool(state == "cancelled")
