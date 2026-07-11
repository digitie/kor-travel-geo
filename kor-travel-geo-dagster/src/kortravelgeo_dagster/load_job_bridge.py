"""Drive a ``load_jobs`` row through a Dagster op (T-290g).

Wraps a main-lib leaf coroutine — ``run_backup_job`` / ``run_restore_job`` / a loader —
with the executor-side ``load_jobs`` lifecycle so a Dagster run maintains the same
progress / cancel / audit record the in-process ``JobQueue`` does (the 2-record boundary,
dagster-boundary §6):

    adopt (``executor='dagster'`` + run id + lease)
      → progress reporter (``set_progress`` + lease renew) and a background cancel poll
        (``load_jobs`` cancel authority → the leaf's local ``cancel_event``)
      → converge the terminal state (done / failed / cancelled), mirroring the in-process
        drain's ``try/except CancelledError/except Exception/else`` exactly.

The calling ``@op`` keeps **RetryPolicy off** — backup / restore / full-load are
non-idempotent (ADR-066 §4). This module has no ``@op`` decorator, so ``from __future__
import annotations`` is fine here (dagster-boundary §10 only forbids it in decorated
modules).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol

from dagster import Failure
from kortravelgeo.infra.load_job_executor import LoadJobExecutor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = ["ProgressReporter", "execute_load_job"]

#: Default interval between ``load_jobs`` cancel polls while the leaf runs.
DEFAULT_CANCEL_POLL_SECONDS = 3.0


class ProgressReporter(Protocol):
    """Structural match for the main-lib leaves' ``progress`` parameter."""

    async def __call__(
        self,
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None: ...


#: A leaf's ``(cancel_event, progress)`` tail — e.g. ``functools.partial(run_backup_job,
#: engine, settings, payload)`` bound down to these two arguments.
LeafRunner = Callable[[asyncio.Event, ProgressReporter], Awaitable[None]]


async def execute_load_job(
    *,
    job_id: str,
    orchestrator_run_id: str,
    engine: AsyncEngine,
    leaf: LeafRunner,
    executor: LoadJobExecutor | None = None,
    cancel_poll_seconds: float = DEFAULT_CANCEL_POLL_SECONDS,
    lease_ttl_seconds: float | None = None,
) -> None:
    """Run ``leaf`` as the Dagster-executed body of ``load_jobs`` row ``job_id``.

    Adopts the row into the ``dagster`` executor under this run, streams progress + renews
    the lease, bridges an app-side cancel onto the leaf's ``cancel_event``, and converges
    the terminal state. ``executor`` is injectable for tests; production passes ``None`` and
    a :class:`LoadJobExecutor` is built from ``engine``.
    """

    ttl = lease_ttl_seconds or 300.0
    executor = executor or LoadJobExecutor(engine, lease_ttl_seconds=ttl)
    await executor.adopt_dagster(job_id, orchestrator_run_id, ttl_seconds=lease_ttl_seconds)
    cancel_event = asyncio.Event()

    async def progress(
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None:
        await executor.set_progress(job_id, progress=progress, stage=stage, message=message)
        await executor.renew_lease(job_id, ttl_seconds=lease_ttl_seconds)

    poll = asyncio.create_task(
        _poll_cancel(executor, job_id, cancel_event, cancel_poll_seconds)
    )
    heartbeat = asyncio.create_task(_renew_lease_heartbeat(executor, job_id, ttl))
    try:
        await progress(progress=0.01, stage="running", message="job started")
        await leaf(cancel_event, progress)
    except asyncio.CancelledError:
        await executor.mark_cancelled(job_id)
        raise
    except Exception as exc:
        await executor.mark_failed(job_id, str(exc))
        raise Failure(description=f"load job {job_id} failed: {exc}") from exc
    else:
        await executor.mark_done(job_id)
    finally:
        poll.cancel()
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await poll
        with suppress(asyncio.CancelledError):
            await heartbeat


async def _poll_cancel(
    executor: LoadJobExecutor,
    job_id: str,
    cancel_event: asyncio.Event,
    interval: float,
) -> None:
    """Poll the ``load_jobs`` cancel authority and mirror it onto ``cancel_event``.

    ``load_jobs`` stays the cancel source of truth (ADR-066 §5): the admin cancel path sets
    the row to ``cancelled``; this poll surfaces that to the running leaf so it can stop.
    """

    while not cancel_event.is_set():
        if await executor.read_cancel_requested(job_id):
            cancel_event.set()
            return
        await asyncio.sleep(interval)


async def _renew_lease_heartbeat(
    executor: LoadJobExecutor,
    job_id: str,
    ttl_seconds: float,
) -> None:
    """Renew the ``load_jobs`` lease independently of the leaf's progress emission.

    The ``progress`` closure renews the lease, but a leaf can stay inside one long
    synchronous phase for minutes without emitting progress — e.g. ``pg_restore``'s
    data-load / index-build, or a full-load COPY. Without an independent heartbeat the
    lease (``ttl_seconds``) expires and the orphan reconciler kills a perfectly healthy
    run (the T-290i restore failure mode). Renew at ~1/3 the TTL and swallow transient
    write errors so a blip never tears down the run.
    """
    interval = ttl_seconds / 3.0
    while True:
        await asyncio.sleep(interval)
        with suppress(Exception):
            await executor.renew_lease(job_id, ttl_seconds=ttl_seconds)
