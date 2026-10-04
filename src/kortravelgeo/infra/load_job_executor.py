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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.core.job_recovery import DEFAULT_LEASE_TTL_SECONDS, compute_lease_expiry

#: Cap the persisted ``log_tail`` at the most recent N lines (matches the historical
#: in-process behavior so admin log tails do not grow unbounded).
LOG_TAIL_CAP = 200


class LoadJobAdoptionError(RuntimeError):
    """Raised when a Dagster run must not execute the requested ``load_jobs`` row."""


class LoadJobLeaseLostError(LoadJobAdoptionError):
    """회수·취소되거나 다른 run으로 넘어간 행에 worker가 다시 기록할 수 없다."""


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
        orchestrator_run_id: str | None = None,
    ) -> None:
        self.engine = engine
        self._lease_ttl_seconds = lease_ttl_seconds
        self._orchestrator_run_id = orchestrator_run_id

    def _owner_predicate(self) -> str:
        if self._orchestrator_run_id is None:
            return ""
        return (
            " AND state = 'running' AND executor = 'dagster'"
            " AND orchestrator_run_id = :owner_run_id"
        )

    def _owner_params(self) -> dict[str, str]:
        if self._orchestrator_run_id is None:
            return {}
        return {"owner_run_id": self._orchestrator_run_id}

    def _require_owner(self, result: Any, job_id: str) -> None:
        if self._orchestrator_run_id is not None and result.rowcount != 1:
            raise LoadJobLeaseLostError(f"load job {job_id} 실행 소유권이 만료되었습니다.")

    def lease_expiry(self, ttl_seconds: float | None = None) -> datetime:
        """Absolute expiry for a freshly set / renewed lease (default TTL when ``None``)."""

        ttl = self._lease_ttl_seconds if ttl_seconds is None else ttl_seconds
        return compute_lease_expiry(now=datetime.now(UTC), ttl_seconds=ttl)

    @asynccontextmanager
    async def _begin_bounded(self) -> AsyncIterator[AsyncConnection]:
        """상태·heartbeat 기록도 잠금 5초와 SQL 60초를 넘기지 않는 짧은 transaction."""

        async with self.engine.begin() as conn:
            # 진행·취소·회수 경쟁에도 무한 잠금 대기를 만들지 않는다.
            await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            await conn.execute(text("SET LOCAL statement_timeout = '60s'"))
            yield conn

    async def adopt_dagster(
        self,
        job_id: str,
        orchestrator_run_id: str,
        *,
        ttl_seconds: float | None = None,
    ) -> datetime:
        """Adopt a row into the Dagster executor: set ``executor='dagster'``, record the
        backing run id and an initial lease, and move ``queued`` → ``running``. A same-run
        ``running`` row may renew/re-adopt defensively, but terminal rows or rows owned by
        another Dagster run are rejected so a cancelled job never starts leaf execution.
        Returns the new lease expiry."""

        expires_at = self.lease_expiry(ttl_seconds)
        async with self._begin_bounded() as conn:
            result = await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET executor = 'dagster',
       orchestrator_run_id = :orchestrator_run_id,
       lease_expires_at = :expires_at,
       state = 'running',
       started_at = COALESCE(started_at, now()),
       heartbeat_at = now()
 WHERE job_id = :job_id
   AND (
     state = 'queued'
     OR (
       state = 'running'
       AND executor = 'dagster'
       AND orchestrator_run_id = :orchestrator_run_id
     )
   )
 RETURNING job_id
"""
                ),
                {
                    "job_id": job_id,
                    "orchestrator_run_id": orchestrator_run_id,
                    "expires_at": expires_at,
                },
            )
            if result.scalar_one_or_none() is None:
                row = (
                    (
                        await conn.execute(
                            text(
                                """
SELECT state, executor, orchestrator_run_id
  FROM load_jobs
 WHERE job_id = :job_id
"""
                            ),
                            {"job_id": job_id},
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    msg = f"cannot adopt missing load job: {job_id}"
                else:
                    msg = (
                        "cannot adopt load job for Dagster execution: "
                        f"job_id={job_id} state={row['state']} "
                        f"executor={row['executor']} "
                        f"orchestrator_run_id={row['orchestrator_run_id']}"
                    )
                raise LoadJobAdoptionError(msg)
        return expires_at

    async def renew_lease(self, job_id: str, *, ttl_seconds: float | None = None) -> datetime:
        """Renew ``lease_expires_at`` (and heartbeat) for a Dagster-executed job. Returns
        the new lease expiry. Called periodically by the op as it makes progress."""

        expires_at = self.lease_expiry(ttl_seconds)
        async with self._begin_bounded() as conn:
            result = await conn.execute(
                text(
                    f"""
UPDATE load_jobs
   SET lease_expires_at = :expires_at,
       heartbeat_at = now()
 WHERE job_id = :job_id{self._owner_predicate()}
"""
                ),
                {"job_id": job_id, "expires_at": expires_at, **self._owner_params()},
            )
            self._require_owner(result, job_id)
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
            async with self._begin_bounded() as conn:
                existing = await conn.scalar(
                    text("SELECT log_tail FROM load_jobs WHERE job_id = :job_id"),
                    {"job_id": job_id},
                )
            log_tail = [str(line) for line in (existing or [])]
            log_tail.append(f"{prefix}{label} {message}")
            log_tail = log_tail[-LOG_TAIL_CAP:]

        params: dict[str, Any] = {"job_id": job_id, **self._owner_params()}
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
        stmt = text(
            f"UPDATE load_jobs SET {', '.join(assignments)} WHERE job_id = :job_id"
            f"{self._owner_predicate()}"
        )
        if log_tail is not None:
            stmt = stmt.bindparams(bindparam("log_tail", type_=JSONB))
        async with self._begin_bounded() as conn:
            result = await conn.execute(stmt, params)
            self._require_owner(result, job_id)

    async def mark_done(self, job_id: str) -> None:
        """현재 소유한 running 행만 완료한다. 늦은 worker는 terminal 상태를 되돌리지 않는다."""

        async with self._begin_bounded() as conn:
            result = await conn.execute(
                text(
                    f"""
UPDATE load_jobs
   SET state = 'done',
       progress = 1.0,
       current_stage = 'done',
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :job_id AND state = 'running'{self._owner_predicate()}
"""
                ),
                {"job_id": job_id, **self._owner_params()},
            )
            self._require_owner(result, job_id)

    async def mark_failed(self, job_id: str, message: str) -> None:
        """Converge a row to ``failed`` with ``error_message``."""

        async with self._begin_bounded() as conn:
            await conn.execute(
                text(
                    f"""
UPDATE load_jobs
   SET state = 'failed',
       current_stage = 'failed',
       error_message = :message,
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :job_id AND state IN ('queued', 'running'){self._owner_predicate()}
"""
                ),
                {"job_id": job_id, "message": message, **self._owner_params()},
            )

    async def reconcile_transition(
        self,
        job_id: str,
        *,
        state: str,
        orchestrator_run_id: str | None,
        lease_expires_at: datetime | None,
        reason: str,
    ) -> bool:
        """조회한 소유권·lease가 그대로일 때만 running 행을 terminal로 바꾼다."""
        if state not in {"done", "failed", "cancelled"}:
            raise ValueError("회수 대상 상태는 terminal이어야 합니다.")
        async with self._begin_bounded() as conn:
            result = await conn.execute(
                text("""
UPDATE load_jobs
   SET state = :state, current_stage = :state,
       error_message = CASE WHEN :state = 'failed' THEN :reason ELSE error_message END,
       progress = CASE WHEN :state = 'done' THEN 1.0 ELSE progress END,
       finished_at = now(), heartbeat_at = now()
 WHERE job_id = :job_id AND state = 'running' AND executor = 'dagster'
   AND orchestrator_run_id IS NOT DISTINCT FROM :observed_run_id
   AND lease_expires_at IS NOT DISTINCT FROM :observed_lease
 RETURNING job_id
"""),
                {
                    "job_id": job_id,
                    "state": state,
                    "reason": reason,
                    "observed_run_id": orchestrator_run_id,
                    "observed_lease": lease_expires_at,
                },
            )
            return result.first() is not None

    async def mark_launch_failed(self, job_id: str, message: str) -> bool:
        """Fail a row whose Dagster launch errored — only while it is still ``queued``.

        A launch error can be ambiguous (e.g. a timeout after Dagster already accepted the
        run). If the run adopted the row first (``queued`` → ``running``), overwriting it to
        ``failed`` would make the reconciler terminate a run doing real work. Returns ``True``
        when the row was failed, ``False`` when the run already owns it (T-318)."""

        async with self._begin_bounded() as conn:
            result = await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'failed',
       current_stage = 'failed',
       error_message = :message,
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :job_id AND state = 'queued'
RETURNING job_id
"""
                ),
                {"job_id": job_id, "message": message},
            )
            return result.first() is not None

    async def mark_cancelled(self, job_id: str) -> None:
        """Converge a row to ``cancelled``."""

        async with self._begin_bounded() as conn:
            await conn.execute(
                text(
                    f"""
UPDATE load_jobs
   SET state = 'cancelled',
       current_stage = 'cancelled',
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :job_id AND state IN ('queued', 'running'){self._owner_predicate()}
"""
                ),
                {"job_id": job_id, **self._owner_params()},
            )

    async def read_cancel_requested(self, job_id: str) -> bool:
        """``True`` when the row has been converged to ``cancelled`` (the cancel authority).

        The Dagster op polls this to bridge an app-side cancel onto its local
        ``cancel_event`` (``load_jobs`` stays the cancel source of truth, ADR-066 §5)."""

        async with self._begin_bounded() as conn:
            if self._orchestrator_run_id is not None:
                active = await conn.scalar(
                    text(
                        "SELECT job_id FROM load_jobs WHERE job_id = :job_id"
                        f"{self._owner_predicate()}"
                    ),
                    {"job_id": job_id, **self._owner_params()},
                )
                return active is None
            state = await conn.scalar(
                text("SELECT state FROM load_jobs WHERE job_id = :job_id"),
                {"job_id": job_id},
            )
        return bool(state == "cancelled")
