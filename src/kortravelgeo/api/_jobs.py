"""Small persistent load job queue used by admin API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import Enum
from time import perf_counter
from typing import Any, Protocol

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.batch import batch_children
from kortravelgeo.infra.metrics import record_load_job_duration, record_load_job_stage_duration


class ProgressCallback(Protocol):
    async def __call__(
        self,
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None: ...


JobHandler = Callable[[dict[str, Any], asyncio.Event, ProgressCallback], Awaitable[None]]
ADVISORY_SLOT_LOAD_QUEUE = 470017
_CONTROL_KINDS = {
    "full_load_batch",
    "source_rebuild_db",
    "consistency_check",
    "mv_refresh",
    "db_backup",
    "db_restore",
}
_CONTROL_KIND_SQL = ", ".join(f"'{kind}'" for kind in sorted(_CONTROL_KINDS))
_FINAL_STAGES = {"done", "failed", "cancelled"}
_DRAIN_NUDGE_DELAY_S = 0.25
_DRAIN_LOCK_RETRY_DELAY_S = 0.25
logger = logging.getLogger(__name__)


type _ClaimRow = tuple[str, str, dict[str, Any]]


class _ClaimState(Enum):
    BUSY = "busy"


class JobQueue:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._semaphore = asyncio.Semaphore(1)
        self._handlers: dict[str, JobHandler] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._stage_timers: dict[str, tuple[str, str, float]] = {}

    def register(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    async def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        job_id: str | None = None,
        load_batch_id: str | None = None,
        parent_job_id: str | None = None,
    ) -> str:
        row = await AdminRepository(self.engine).insert_load_job(
            kind=kind,
            payload=payload,
            job_id=job_id,
            load_batch_id=load_batch_id,
            parent_job_id=parent_job_id,
        )
        self._spawn_drain()
        return row.job_id

    async def enqueue_batch(
        self,
        payload: dict[str, Any],
        *,
        job_id: str | None = None,
    ) -> str:
        children = batch_children(payload)
        row = await AdminRepository(self.engine).insert_load_batch(
            payload=payload,
            children=children,
            job_id=job_id,
        )
        await self._record_progress(
            row.job_id,
            progress=0.0,
            stage="source_loads",
            message=f"batch queued with {len(children)} source jobs",
        )
        self._spawn_drain()
        return row.job_id

    async def cancel(self, job_id: str) -> None:
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()
        await AdminRepository(self.engine).cancel_load_job(job_id)
        await self._cancel_batch_children(job_id)

    async def link_job_to_batch(self, job_id: str, load_batch_id: str) -> None:
        """Record the downstream full-load batch id on a control job."""

        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET load_batch_id = :load_batch_id,
       heartbeat_at = now()
 WHERE job_id = :job_id
"""
                ),
                {"job_id": job_id, "load_batch_id": load_batch_id},
            )

    async def recover_startup(self) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'failed',
       error_message = COALESCE(error_message || E'\n', '') || 'recovered: process restart',
       finished_at = now(),
       heartbeat_at = now()
 WHERE state = 'running'
"""
                )
            )
            queued = (
                await conn.execute(
                    text("SELECT job_id FROM load_jobs WHERE state = 'queued' ORDER BY created_at")
                )
            ).scalars().all()
        if queued:
            self._spawn_drain()

    def _spawn_drain(self) -> None:
        self._start_drain_task(delay_s=0.0)
        self._start_drain_task(delay_s=_DRAIN_NUDGE_DELAY_S)

    def _start_drain_task(self, *, delay_s: float) -> None:
        task = asyncio.create_task(self._drain_after_delay(delay_s))
        self._tasks.add(task)
        task.add_done_callback(self._on_drain_done)

    async def _drain_after_delay(self, delay_s: float) -> None:
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        await self._drain_once()

    def _on_drain_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("load job queue drain task failed")

    async def _drain_once(self) -> None:
        async with self._semaphore:
            while True:
                row = await self._claim_one()
                if row is _ClaimState.BUSY:
                    await asyncio.sleep(_DRAIN_LOCK_RETRY_DELAY_S)
                    continue
                if row is None:
                    return
                job_id, kind, payload = row
                job_started_at = perf_counter()
                final_state = "failed"
                handler = self._handlers.get(kind)
                if handler is None:
                    await self._fail(job_id, f"no handler registered for load kind: {kind}")
                    record_load_job_duration(
                        kind=kind,
                        state="failed",
                        elapsed_s=perf_counter() - job_started_at,
                    )
                    continue
                payload_with_job = dict(payload)
                payload_with_job.setdefault("_job_id", job_id)
                cancel_event = asyncio.Event()
                self._cancel_events[job_id] = cancel_event
                progress = self._progress_callback(job_id, kind)
                try:
                    await progress(progress=0.01, stage="running", message="job started")
                    await handler(payload_with_job, cancel_event, progress)
                except asyncio.CancelledError:
                    final_state = "cancelled"
                    await self._cancelled(job_id)
                except Exception as exc:
                    final_state = "failed"
                    await self._fail(job_id, str(exc))
                else:
                    final_state = "done"
                    await self._done(job_id)
                    await self._enqueue_batch_successors(job_id)
                finally:
                    self._cancel_events.pop(job_id, None)
                    self._finish_stage(job_id, outcome=final_state)
                    record_load_job_duration(
                        kind=kind,
                        state=final_state,
                        elapsed_s=perf_counter() - job_started_at,
                    )

    async def _claim_one(self) -> _ClaimRow | _ClaimState | None:
        async with self.engine.begin() as conn:
            locked = await conn.scalar(
                text("SELECT pg_try_advisory_xact_lock(:slot)"),
                {"slot": ADVISORY_SLOT_LOAD_QUEUE},
            )
            if not locked:
                return _ClaimState.BUSY
            row = (
                await conn.execute(
                    text(
                        """
SELECT job_id, kind, payload
  FROM load_jobs
 WHERE state = 'queued'
 ORDER BY created_at
 FOR UPDATE SKIP LOCKED
 LIMIT 1
"""
                    )
                )
            ).mappings().first()
            if row is None:
                return None
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'running',
       started_at = COALESCE(started_at, now()),
       heartbeat_at = now(),
       current_stage = COALESCE(current_stage, 'starting')
 WHERE job_id = :job_id
"""
                ),
                {"job_id": row["job_id"]},
            )
        return (row["job_id"], row["kind"], row["payload"])

    async def _done(self, job_id: str) -> None:
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
        await self._record_progress(job_id, progress=1.0, stage="done", message="job completed")
        await self._refresh_batch_root(job_id)

    async def _cancelled(self, job_id: str) -> None:
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
        await self._record_progress(job_id, stage="cancelled", message="job cancelled")
        await self._mark_batch_failed(job_id, "child job cancelled")

    async def _fail(self, job_id: str, message: str) -> None:
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
        await self._record_progress(job_id, stage="failed", message=message)
        await self._mark_batch_failed(job_id, message)

    def _progress_callback(self, job_id: str, kind: str) -> ProgressCallback:
        async def report(
            *,
            progress: float | None = None,
            stage: str | None = None,
            message: str | None = None,
        ) -> None:
            if stage is not None:
                self._record_stage_transition(job_id, kind=kind, stage=stage)
            await self._record_progress(job_id, progress=progress, stage=stage, message=message)

        return report

    def _record_stage_transition(self, job_id: str, *, kind: str, stage: str) -> None:
        now = perf_counter()
        current = self._stage_timers.get(job_id)
        if current is not None:
            current_kind, current_stage, started_at = current
            if current_stage == stage:
                return
            outcome = stage if stage in {"failed", "cancelled"} else "completed"
            record_load_job_stage_duration(
                kind=current_kind,
                stage=current_stage,
                outcome=outcome,
                elapsed_s=now - started_at,
            )
        if stage in _FINAL_STAGES:
            self._stage_timers.pop(job_id, None)
            return
        self._stage_timers[job_id] = (kind, stage, now)

    def _finish_stage(self, job_id: str, *, outcome: str) -> None:
        current = self._stage_timers.pop(job_id, None)
        if current is None:
            return
        kind, stage, started_at = current
        record_load_job_stage_duration(
            kind=kind,
            stage=stage,
            outcome=outcome,
            elapsed_s=perf_counter() - started_at,
        )

    async def _record_progress(
        self,
        job_id: str,
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None:
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
            log_tail = log_tail[-200:]

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

    async def _enqueue_batch_successors(self, job_id: str) -> None:
        row = await self._job_batch_row(job_id)
        if row is None:
            return
        kind = str(row["kind"])
        batch_id = row["load_batch_id"]
        parent_job_id = row["parent_job_id"]
        if batch_id is None or kind == "full_load_batch":
            return
        if kind not in _CONTROL_KINDS:
            await self._maybe_enqueue_consistency(str(batch_id), str(parent_job_id or batch_id))
        elif kind == "consistency_check":
            await self._maybe_enqueue_mv_refresh(str(batch_id), str(parent_job_id or batch_id))
        elif kind == "mv_refresh":
            await self._mark_batch_done(str(batch_id))

    async def _maybe_enqueue_consistency(self, batch_id: str, parent_job_id: str) -> None:
        async with self.engine.connect() as conn:
            stats = (
                await conn.execute(
                    text(
                        f"""
SELECT
  count(*) FILTER (WHERE kind NOT IN ({_CONTROL_KIND_SQL})) AS total,
  count(*) FILTER (WHERE kind NOT IN ({_CONTROL_KIND_SQL}) AND state = 'done') AS done,
  count(*) FILTER (WHERE state IN ('failed','cancelled')) AS failed,
  count(*) FILTER (WHERE kind = 'consistency_check') AS consistency_count
  FROM load_jobs
 WHERE load_batch_id = :batch_id
"""
                    ),
                    {"batch_id": batch_id},
                )
            ).mappings().one()
        if stats["failed"] or stats["total"] == 0 or stats["total"] != stats["done"]:
            return
        if stats["consistency_count"]:
            return
        await self.enqueue(
            "consistency_check",
            {"scope": "full", "load_batch_id": batch_id},
            load_batch_id=batch_id,
            parent_job_id=parent_job_id,
        )
        await self._record_progress(
            parent_job_id,
            stage="consistency_check",
            message="all source jobs done; consistency_check queued",
        )

    async def _maybe_enqueue_mv_refresh(self, batch_id: str, parent_job_id: str) -> None:
        async with self.engine.connect() as conn:
            severity = await conn.scalar(
                text(
                    """
SELECT severity_max
  FROM load_consistency_reports
 WHERE source_set ->> 'load_batch_id' = :batch_id
 ORDER BY started_at DESC
 LIMIT 1
"""
                ),
                {"batch_id": batch_id},
            )
            exists = await conn.scalar(
                text(
                    """
SELECT count(*)
  FROM load_jobs
 WHERE load_batch_id = :batch_id
   AND kind = 'mv_refresh'
"""
                ),
                {"batch_id": batch_id},
            )
            # rebuild-db (T-205b) provenance on the batch root: source_match_set_id
            # is the 정본 FK to write; forced_promotion arms the consistency-ERROR
            # bypass (ONLY the ERROR gate — the source integrity gate already ran
            # before any child was enqueued).
            root_payload = await conn.scalar(
                text("SELECT payload FROM load_jobs WHERE job_id = :batch_id"),
                {"batch_id": batch_id},
            )
        if exists:
            return
        root = root_payload if isinstance(root_payload, dict) else {}
        source_match_set_id = root.get("source_match_set_id")
        forced_promotion = bool(root.get("forced_promotion"))
        if severity is None:
            await self._mark_batch_failed(
                batch_id,
                "consistency report missing; mv_refresh blocked",
            )
            return
        if severity == "ERROR" and not forced_promotion:
            await self._mark_batch_failed(
                batch_id,
                "consistency report severity ERROR; mv_refresh blocked",
            )
            return
        mv_payload: dict[str, Any] = {"strategy": "swap", "load_batch_id": batch_id}
        if isinstance(source_match_set_id, str) and source_match_set_id:
            mv_payload["source_match_set_id"] = source_match_set_id
        if forced_promotion:
            mv_payload["forced_promotion"] = True
            mv_payload["forced_promotion_metadata"] = {
                k: root.get(k)
                for k in ("forced_promotion_actor", "forced_promotion_reason")
                if root.get(k) is not None
            }
            mv_payload["forced_promotion_metadata"]["consistency_severity"] = severity
        await self.enqueue(
            "mv_refresh",
            mv_payload,
            load_batch_id=batch_id,
            parent_job_id=parent_job_id,
        )
        await self._record_progress(
            parent_job_id,
            stage="mv_refresh",
            message="consistency gate passed; mv_refresh swap queued",
        )

    async def _refresh_batch_root(self, child_job_id: str) -> None:
        row = await self._job_batch_row(child_job_id)
        if row is None:
            return
        batch_id = row["load_batch_id"]
        parent_job_id = row["parent_job_id"]
        if batch_id is None or parent_job_id is None:
            return
        async with self.engine.connect() as conn:
            stats = (
                await conn.execute(
                    text(
                        """
SELECT count(*) AS total,
       count(*) FILTER (WHERE state = 'done') AS done
  FROM load_jobs
 WHERE load_batch_id = :batch_id
   AND job_id <> :batch_id
"""
                    ),
                    {"batch_id": batch_id},
                )
            ).mappings().one()
        total = int(stats["total"] or 0)
        if total == 0:
            return
        progress = min(0.98, int(stats["done"] or 0) / total)
        await self._record_progress(str(parent_job_id), progress=progress)

    async def _mark_batch_done(self, batch_id: str) -> None:
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
 WHERE job_id = :batch_id
   AND kind = 'full_load_batch'
   AND state <> 'failed'
"""
                ),
                {"batch_id": batch_id},
            )
        await self._record_progress(batch_id, progress=1.0, stage="done", message="batch completed")

    async def _mark_batch_failed(self, job_id: str, message: str) -> None:
        row = await self._job_batch_row(job_id)
        if row is None:
            return
        batch_id = row["load_batch_id"]
        if batch_id is None:
            return
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'failed',
       current_stage = 'failed',
       error_message = COALESCE(error_message || E'\n', '') || :message,
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :batch_id
   AND kind = 'full_load_batch'
   AND state <> 'done'
"""
                ),
                {"batch_id": batch_id, "message": message},
            )
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'cancelled',
       current_stage = 'cancelled',
       error_message = COALESCE(error_message || E'\n', '') || 'cancelled after batch failure',
       finished_at = now(),
       heartbeat_at = now()
 WHERE load_batch_id = :batch_id
   AND job_id <> :batch_id
   AND state = 'queued'
"""
                ),
                {"batch_id": batch_id},
            )

    async def _cancel_batch_children(self, job_id: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'cancelled',
       current_stage = 'cancelled',
       finished_at = now(),
       heartbeat_at = now()
 WHERE parent_job_id = :job_id
   AND state IN ('queued','running')
"""
                ),
                {"job_id": job_id},
            )

    async def _job_batch_row(self, job_id: str) -> dict[str, Any] | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
SELECT job_id, kind, load_batch_id, parent_job_id
  FROM load_jobs
 WHERE job_id = :job_id
"""
                    ),
                    {"job_id": job_id},
                )
            ).mappings().first()
        return dict(row) if row else None
