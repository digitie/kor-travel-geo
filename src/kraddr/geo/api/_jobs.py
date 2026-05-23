"""Small persistent load job queue used by admin API."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.infra.admin_repo import AdminRepository

JobHandler = Callable[[dict[str, Any], asyncio.Event], Awaitable[None]]
ADVISORY_SLOT_LOAD_QUEUE = 470017


class JobQueue:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._semaphore = asyncio.Semaphore(1)
        self._handlers: dict[str, JobHandler] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def register(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    async def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        job_id: str | None = None,
    ) -> str:
        row = await AdminRepository(self.engine).insert_load_job(
            kind=kind,
            payload=payload,
            job_id=job_id,
        )
        self._spawn_drain()
        return row.job_id

    async def cancel(self, job_id: str) -> None:
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()
        await AdminRepository(self.engine).cancel_load_job(job_id)

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
        task = asyncio.create_task(self._drain_once())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _drain_once(self) -> None:
        async with self._semaphore:
            while True:
                row = await self._claim_one()
                if row is None:
                    return
                job_id, kind, payload = row
                handler = self._handlers.get(kind)
                if handler is None:
                    await self._fail(job_id, f"no handler registered for load kind: {kind}")
                    continue
                cancel_event = asyncio.Event()
                self._cancel_events[job_id] = cancel_event
                try:
                    await handler(payload, cancel_event)
                except asyncio.CancelledError:
                    await self._cancelled(job_id)
                except Exception as exc:
                    await self._fail(job_id, str(exc))
                else:
                    await self._done(job_id)
                finally:
                    self._cancel_events.pop(job_id, None)

    async def _claim_one(self) -> tuple[str, str, dict[str, Any]] | None:
        async with self.engine.begin() as conn:
            locked = await conn.scalar(
                text("SELECT pg_try_advisory_xact_lock(:slot)"),
                {"slot": ADVISORY_SLOT_LOAD_QUEUE},
            )
            if not locked:
                return None
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
   SET state = 'done', progress = 1.0, finished_at = now(), heartbeat_at = now()
 WHERE job_id = :job_id AND state <> 'cancelled'
"""
                ),
                {"job_id": job_id},
            )

    async def _cancelled(self, job_id: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'cancelled', finished_at = now(), heartbeat_at = now()
 WHERE job_id = :job_id
"""
                ),
                {"job_id": job_id},
            )

    async def _fail(self, job_id: str, message: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """
UPDATE load_jobs
   SET state = 'failed',
       error_message = :message,
       finished_at = now(),
       heartbeat_at = now()
 WHERE job_id = :job_id
"""
                ),
                {"job_id": job_id, "message": message},
            )
