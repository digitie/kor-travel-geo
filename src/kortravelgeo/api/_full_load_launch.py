"""Launch ``full_load_batch`` / source loaders as Dagster runs (T-290j).

The loader/full-load analogue of the ``db_backup`` / ``db_restore`` launch helpers in
``routers/admin.py``: create the ``load_jobs`` row(s) with ``executor='dagster'`` (so the
in-process drain never claims them), then launch the Dagster run whose op adopts and drives
them. A launch failure converges the row(s) to a terminal state and surfaces a 502 rather
than leaving queued rows no worker will ever claim.

Shared by the admin ``POST /loads`` endpoint AND the ``source_rebuild_db`` control job (which
materialises a rebuild then submits a ``full_load_batch``), so both reach Dagster through the
same gate — :func:`submit_full_load_batch` routes to Dagster only when ``full_load_batch`` is
listed in ``settings.dagster_executed_job_kinds`` and otherwise falls back to the in-process
:meth:`JobQueue.enqueue_batch` (T-290k retires that fallback).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from kortravelgeo.api._dagster_client import (
    DagsterLaunchError,
    DagsterUrlConfigurationError,
    launch_dagster_run,
)
from kortravelgeo.exceptions import KorTravelGeoError
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.batch import batch_children
from kortravelgeo.infra.load_job_executor import LoadJobExecutor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kortravelgeo.api._jobs import JobQueue
    from kortravelgeo.settings import Settings

__all__ = [
    "FULL_LOAD_BATCH_KIND",
    "launch_full_load_batch_dagster_run",
    "launch_source_load_dagster_run",
    "submit_full_load_batch",
]

FULL_LOAD_BATCH_KIND = "full_load_batch"

_LAUNCH_ERRORS = (DagsterUrlConfigurationError, DagsterLaunchError, httpx.HTTPError)


async def launch_full_load_batch_dagster_run(
    engine: AsyncEngine,
    settings: Settings,
    payload: dict[str, Any],
) -> str:
    """Create a Dagster-executed ``full_load_batch`` (root + source children) and launch it.

    ``batch_children`` validates the payload *before* any row is written, so a malformed
    batch surfaces a 4xx without leaving orphan rows. On launch failure the root is failed and
    the queued children cancelled (they carry ``executor='dagster'`` — no worker would claim
    them), and a 502 is raised.
    """

    children = batch_children(payload)
    root = await AdminRepository(engine).insert_load_batch(
        payload=payload, children=children, executor="dagster"
    )
    batch_id = root.job_id
    run_config = {
        "ops": {"run_full_load_batch": {"config": {"job_id": batch_id, "payload": payload}}}
    }
    try:
        await launch_dagster_run(
            settings,
            job_name="full_load_batch",
            run_config=run_config,
            tags={"kor_travel_geo.job_id": batch_id},
        )
    except _LAUNCH_ERRORS as exc:
        await LoadJobExecutor(engine).mark_failed(batch_id, f"Dagster launch failed: {exc}")
        await AdminRepository(engine).cancel_queued_batch_children(batch_id)
        raise KorTravelGeoError("Dagster full-load launch failed", http_status=502) from exc
    return batch_id


async def launch_source_load_dagster_run(
    engine: AsyncEngine,
    settings: Settings,
    kind: str,
    payload: dict[str, Any],
) -> str:
    """Create a Dagster-executed source-loader row and launch its ``load_source`` run."""

    row = await AdminRepository(engine).insert_load_job(
        kind=kind, payload=payload, executor="dagster"
    )
    job_id = row.job_id
    run_config = {
        "ops": {"run_source_load": {"config": {"job_id": job_id, "kind": kind, "payload": payload}}}
    }
    try:
        await launch_dagster_run(
            settings,
            job_name="load_source",
            run_config=run_config,
            tags={"kor_travel_geo.job_id": job_id},
        )
    except _LAUNCH_ERRORS as exc:
        await LoadJobExecutor(engine).mark_failed(job_id, f"Dagster launch failed: {exc}")
        raise KorTravelGeoError("Dagster loader launch failed", http_status=502) from exc
    return job_id


async def submit_full_load_batch(
    engine: AsyncEngine,
    settings: Settings,
    payload: dict[str, Any],
    *,
    queue: JobQueue,
) -> str:
    """Submit a ``full_load_batch`` to Dagster (when routed) or the in-process queue.

    The single gate the API endpoint and the ``source_rebuild_db`` control job share so a
    rebuild-driven batch takes the same executor as an operator-submitted one.
    """

    if FULL_LOAD_BATCH_KIND in settings.dagster_executed_job_kinds:
        return await launch_full_load_batch_dagster_run(engine, settings, payload)
    return await queue.enqueue_batch(payload)
