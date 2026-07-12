"""Launch ``full_load_batch`` / source loaders as Dagster runs (T-290j).

The loader/full-load analogue of the ``db_backup`` / ``db_restore`` launch helpers in
``routers/admin.py``: create the ``load_jobs`` row(s) with ``executor='dagster'`` (so the
in-process drain never claims them), then launch the Dagster run whose op adopts and drives
them. A launch failure converges the row(s) to a terminal state and surfaces a 502 rather
than leaving queued rows no worker will ever claim.

Since T-290k PR3 every execution kind routes here unconditionally (the
``dagster_executed_job_kinds`` opt-in gate and the in-process ``JobQueue`` fallback are gone),
so a rebuild-driven batch and an operator-submitted one both run as ``executor='dagster'``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy.ext.asyncio import create_async_engine

from kortravelgeo.api._dagster_client import (
    DagsterLaunchError,
    DagsterUrlConfigurationError,
    launch_dagster_run,
)
from kortravelgeo.exceptions import KorTravelGeoError
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.batch import batch_children
from kortravelgeo.infra.load_job_executor import LoadJobExecutor
from kortravelgeo.infra.scratch_db import ensure_scratch_database, scratch_database_dsn

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

    from kortravelgeo.dto.admin import LoadJobStatus
    from kortravelgeo.settings import Settings


@asynccontextmanager
async def _control_engine(
    engine: AsyncEngine, settings: Settings, payload: dict[str, Any]
) -> AsyncIterator[AsyncEngine]:
    """The engine the batch *control* rows (``load_jobs``) live in.

    Blue-green staging (``payload.target_database`` set): provision + fresh-init the scratch
    DB, then yield a dedicated engine bound to it so the root/child rows the op adopts are
    created there — the serving DB is never opened. Otherwise yield the serving ``engine``.
    """
    target_database = payload.get("target_database")
    if not target_database:
        yield engine
        return
    await ensure_scratch_database(settings, str(target_database))
    scratch_dsn = scratch_database_dsn(settings.pg_dsn, str(target_database))
    scratch_engine = create_async_engine(scratch_dsn)
    try:
        yield scratch_engine
    finally:
        await scratch_engine.dispose()


async def blue_green_load_status(
    settings: Settings, target_database: str, job_id: str
) -> LoadJobStatus:
    """Read a blue-green ``full_load_batch``'s status from its scratch DB.

    When ``payload.target_database`` is set the batch's control rows live in the scratch DB
    (see :func:`_control_engine`), never serving — so the serving-bound ``client.load_status``
    would 404. This binds a throwaway client to the scratch engine so the submit endpoint can
    return the real initial status instead of a spurious not-found.
    """
    from kortravelgeo.client import AsyncAddressClient  # local import breaks an import cycle

    scratch_engine = create_async_engine(scratch_database_dsn(settings.pg_dsn, target_database))
    try:
        return await AsyncAddressClient(settings=settings, engine=scratch_engine).load_status(
            job_id
        )
    finally:
        await scratch_engine.dispose()


__all__ = [
    "FULL_LOAD_BATCH_KIND",
    "blue_green_load_status",
    "launch_consistency_check_dagster_run",
    "launch_full_load_batch_dagster_run",
    "launch_mv_refresh_dagster_run",
    "launch_source_load_dagster_run",
    "launch_source_rebuild_dagster_run",
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

    When ``payload.target_database`` is set (blue-green staging) the root/child ``load_jobs``
    rows are created in a freshly schema-initialised scratch DB (see :func:`_control_engine`);
    the op resolves the same scratch engine from the payload and runs the whole DAG there, so
    the serving DB is never opened.
    """

    children = batch_children(payload)
    async with _control_engine(engine, settings, payload) as control_engine:
        root = await AdminRepository(control_engine).insert_load_batch(
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
            await LoadJobExecutor(control_engine).mark_failed(
                batch_id, f"Dagster launch failed: {exc}"
            )
            await AdminRepository(control_engine).cancel_queued_batch_children(batch_id)
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
) -> str:
    """Submit a ``full_load_batch`` — always via Dagster (T-290k PR3).

    Routing is unconditional now that every loader kind executes as a Dagster op; the
    in-process ``JobQueue.enqueue_batch`` fallback is gone (PR4 deletes the drain).
    """

    return await launch_full_load_batch_dagster_run(engine, settings, payload)


async def _launch_control_job(
    engine: AsyncEngine,
    settings: Settings,
    *,
    kind: str,
    op_name: str,
    job_name: str,
    payload: dict[str, Any],
) -> str:
    """Insert a single ``executor='dagster'`` control row and launch its 1-op Dagster job.

    Shared by the ``source_rebuild_db`` / ``consistency_check`` / ``mv_refresh`` launchers —
    each is a ``{job_id, payload}``-config 1-op job (T-290k PR1). On launch failure the row is
    marked failed (so no worker leaves it queued) and a 502 surfaces.
    """

    row = await AdminRepository(engine).insert_load_job(
        kind=kind, payload=payload, executor="dagster"
    )
    job_id = row.job_id
    run_config = {"ops": {op_name: {"config": {"job_id": job_id, "payload": payload}}}}
    try:
        await launch_dagster_run(
            settings,
            job_name=job_name,
            run_config=run_config,
            tags={"kor_travel_geo.job_id": job_id},
        )
    except _LAUNCH_ERRORS as exc:
        await LoadJobExecutor(engine).mark_failed(job_id, f"Dagster launch failed: {exc}")
        raise KorTravelGeoError(f"Dagster {job_name} launch failed", http_status=502) from exc
    return job_id


async def launch_source_rebuild_dagster_run(
    engine: AsyncEngine, settings: Settings, payload: dict[str, Any]
) -> str:
    """Launch the ``source_rebuild_db`` control job (integrity gate + materialize + downstream
    full-load) as a Dagster run (T-290k PR3, replaces the in-process control job)."""

    return await _launch_control_job(
        engine,
        settings,
        kind="source_rebuild_db",
        op_name="run_source_rebuild_db",
        job_name="source_rebuild_db",
        payload=payload,
    )


async def launch_consistency_check_dagster_run(
    engine: AsyncEngine, settings: Settings, payload: dict[str, Any]
) -> str:
    """Launch a standalone ``consistency_check`` as a Dagster run (T-290k PR3)."""

    return await _launch_control_job(
        engine,
        settings,
        kind="consistency_check",
        op_name="run_consistency_check",
        job_name="consistency_check",
        payload=payload,
    )


async def launch_mv_refresh_dagster_run(
    engine: AsyncEngine, settings: Settings, payload: dict[str, Any]
) -> str:
    """Launch a release-gated ``mv_refresh`` as a Dagster run (T-290k PR3)."""

    return await _launch_control_job(
        engine,
        settings,
        kind="mv_refresh",
        op_name="run_mv_refresh",
        job_name="mv_refresh",
        payload=payload,
    )
