"""Dagster ``full_load_batch`` + ``load_source`` execution ops (T-290j).

Completes the execution move for the loader / full-load family (previously in-process
``JobQueue`` handlers): the ops call the main-lib leaves — the ADR-017 batch DAG
:func:`kortravelgeo.loaders.batch_dag.run_full_load_batch` and the per-kind
:func:`kortravelgeo.loaders.batch_dag.run_source_loader` — bridged to the ``load_jobs`` row
via :func:`load_job_bridge.execute_load_job` (adopt → progress/cancel/heartbeat → terminal).

The DAG logic (root/child rows, consistency gate, mv swap) stays in the main lib; Dagster is
the **1-op-in-job** caller + run store (dagster-boundary §4 / §71-72). The batch op adopts the
batch *root* row and :func:`run_full_load_batch` drives the child rows inline under the same
run id. **No RetryPolicy** — a full load mutates the serving dataset and swaps the MV; it is
non-idempotent (ADR-066 §4). The API keeps ownership of the ``load_jobs`` records.

IMPORTANT (dagster-boundary §10): this module must NOT use
``from __future__ import annotations`` — Dagster validates the ``@op`` ``context`` type at
runtime, which requires real (non-stringized) annotations.
"""

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import Field, OpExecutionContext, Permissive, String, job, op
from kortravelgeo.infra.scratch_db import scratch_database_dsn
from kortravelgeo.loaders.batch_dag import run_full_load_batch, run_source_loader
from sqlalchemy.ext.asyncio import create_async_engine

# Runtime imports: this module has no `from __future__ import annotations` (§10), so the
# nested leaf's `asyncio.Event` / `ProgressReporter` annotations are evaluated eagerly.
from .load_job_bridge import ProgressReporter, execute_load_job
from .resources import op_resource

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.settings import Settings

__all__ = [
    "FULL_LOAD_BATCH_JOB_TAGS",
    "FULL_LOAD_JOBS",
    "LOAD_SOURCE_JOB_TAGS",
    "full_load_batch_job",
    "load_source_job",
    "run_full_load_batch_op",
    "run_source_load_op",
]

FULL_LOAD_BATCH_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "load",
    "kor_travel_geo.job_kind": "full_load_batch",
}
LOAD_SOURCE_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "load",
    "kor_travel_geo.job_kind": "load_source",
}

_FULL_LOAD_BATCH_CONFIG_SCHEMA: Final[dict[str, object]] = {
    "job_id": Field(
        String,
        description="The full_load_batch root load_jobs id the API created before launching.",
    ),
    "payload": Field(
        Permissive(),  # type: ignore[no-untyped-call]
        description="full_load_batch payload (children/payloads, source_match_set_id, ...).",
    ),
}

_LOAD_SOURCE_CONFIG_SCHEMA: Final[dict[str, object]] = {
    "job_id": Field(
        String,
        description="The load_jobs id the API created before launching this run.",
    ),
    "kind": Field(
        String,
        description="Source loader kind (juso_text_load, locsum_load, navi_load, ...).",
    ),
    "payload": Field(
        Permissive(),  # type: ignore[no-untyped-call]
        description="Loader payload (path/source_path, source_yyyymm, limit_per_file, ...).",
    ),
}


@op(
    name="run_full_load_batch",
    description=(
        "Execute a full_load_batch by calling the main-lib run_full_load_batch DAG leaf "
        "(serial source loads -> consistency gate -> mv swap), bridged to the batch root "
        "load_jobs row. No RetryPolicy — non-idempotent."
    ),
    required_resource_keys={"client", "settings"},
    config_schema=_FULL_LOAD_BATCH_CONFIG_SCHEMA,
)
async def run_full_load_batch_op(context: OpExecutionContext) -> dict[str, object]:
    """Run the ADR-017 batch DAG as this Dagster run's body, driving its ``load_jobs`` rows."""

    client = cast("AsyncAddressClient", op_resource(context, "client"))
    settings = cast("Settings", op_resource(context, "settings"))
    ttl = settings.dagster_lease_ttl_seconds

    config = cast("Mapping[str, Any]", context.op_config)
    job_id = str(config["job_id"])
    payload = dict(cast("Mapping[str, Any]", config["payload"]))

    # Blue-green staging: when the payload names a target_database, run the WHOLE DAG
    # (control rows + data + MV swap) against a scratch engine so the serving DB is never
    # opened. The API launcher already created + schema-inited that DB and inserted the
    # root/child rows there; this op binds an engine to the same DSN and disposes it after.
    target_database = payload.get("target_database")
    if target_database:
        engine = create_async_engine(scratch_database_dsn(settings.pg_dsn, str(target_database)))
        dispose_engine = True
    else:
        engine = client._engine()
        dispose_engine = False

    try:

        async def leaf(cancel_event: asyncio.Event, progress: ProgressReporter) -> None:
            await run_full_load_batch(
                engine,
                batch_id=job_id,
                payload=payload,
                cancel_event=cancel_event,
                progress=progress,
                orchestrator_run_id=context.run_id,
                lease_ttl_seconds=ttl,
            )

        await execute_load_job(
            job_id=job_id,
            orchestrator_run_id=context.run_id,
            engine=engine,
            leaf=leaf,
            lease_ttl_seconds=ttl,
        )
    finally:
        if dispose_engine:
            await engine.dispose()
    context.add_output_metadata(
        {"job_id": job_id, "kind": "full_load_batch", "target_database": str(target_database or "")}
    )
    return {"job_id": job_id}


@op(
    name="run_source_load",
    description=(
        "Execute a single source loader by calling the main-lib run_source_loader leaf "
        "(under its per-path advisory lock), bridged to the load_jobs row. No RetryPolicy."
    ),
    required_resource_keys={"client", "settings"},
    config_schema=_LOAD_SOURCE_CONFIG_SCHEMA,
)
async def run_source_load_op(context: OpExecutionContext) -> dict[str, object]:
    """Run one source loader as this Dagster run's body, driving its ``load_jobs`` row."""

    client = cast("AsyncAddressClient", op_resource(context, "client"))
    settings = cast("Settings", op_resource(context, "settings"))
    engine = client._engine()
    ttl = settings.dagster_lease_ttl_seconds

    config = cast("Mapping[str, Any]", context.op_config)
    job_id = str(config["job_id"])
    kind = str(config["kind"])
    payload = dict(cast("Mapping[str, Any]", config["payload"]))

    async def leaf(cancel_event: asyncio.Event, progress: ProgressReporter) -> None:
        await run_source_loader(
            engine, kind=kind, payload=payload, cancel_event=cancel_event, progress=progress
        )

    await execute_load_job(
        job_id=job_id,
        orchestrator_run_id=context.run_id,
        engine=engine,
        leaf=leaf,
        lease_ttl_seconds=ttl,
    )
    context.add_output_metadata({"job_id": job_id, "kind": kind})
    return {"job_id": job_id}


@job(
    name="full_load_batch",
    tags=FULL_LOAD_BATCH_JOB_TAGS,
    description="Execute a full_load_batch as a Dagster run (T-290j).",
)
def full_load_batch_job() -> None:
    run_full_load_batch_op()


@job(
    name="load_source",
    tags=LOAD_SOURCE_JOB_TAGS,
    description="Execute one source loader as a Dagster run (T-290j).",
)
def load_source_job() -> None:
    run_source_load_op()


FULL_LOAD_JOBS: Final = [full_load_batch_job, load_source_job]
