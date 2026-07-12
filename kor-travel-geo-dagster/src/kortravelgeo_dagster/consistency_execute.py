"""Dagster standalone ``consistency_check`` execution op (T-290k).

Wraps the SAME main-lib leaf :func:`kortravelgeo.loaders.batch_dag.run_consistency_check`
that the ``full_load_batch`` DAG runs as its consistency child, but as a top-level
``@op``/``@job`` so an operator-triggered consistency run (``POST /consistency/run``) can
execute via Dagster instead of the retired in-process queue. Bridged to the ``load_jobs``
row via :func:`load_job_bridge.execute_load_job`.

A STANDALONE run (no ``load_batch_id`` in the payload) follows the leaf's own contract:
``severity_max == 'ERROR'`` raises → the run/row fails (byte-for-byte the in-process
``consistency`` handler). In-batch promotion gating stays inside ``run_full_load_batch``.

IMPORTANT (dagster-boundary §10): no ``from __future__ import annotations`` — Dagster
validates the ``@op`` ``context`` type at runtime.
"""

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import Field, OpExecutionContext, Permissive, String, job, op
from kortravelgeo.loaders.batch_dag import run_consistency_check

from .load_job_bridge import ProgressReporter, execute_load_job
from .resources import op_resource

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.settings import Settings

__all__ = [
    "CONSISTENCY_CHECK_JOB_TAGS",
    "CONSISTENCY_JOBS",
    "consistency_check_job",
    "run_consistency_check_op",
]

CONSISTENCY_CHECK_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "validation",
    "kor_travel_geo.job_kind": "consistency_check",
}

_CONFIG_SCHEMA: Final[dict[str, object]] = {
    "job_id": Field(
        String,
        description="The consistency_check load_jobs id the API created before launching.",
    ),
    "payload": Field(
        Permissive(),  # type: ignore[no-untyped-call]
        description="Consistency payload (scope, cases, source_set, load_batch_id?).",
    ),
}


@op(
    name="run_consistency_check",
    description=(
        "Run the registry consistency cases via the main-lib run_consistency_check leaf, "
        "bridged to the load_jobs row. No RetryPolicy — records a report + may raise on "
        "ERROR (standalone). Op name != job name."
    ),
    required_resource_keys={"client", "settings"},
    config_schema=_CONFIG_SCHEMA,
)
async def run_consistency_check_op(context: OpExecutionContext) -> dict[str, object]:
    """Run a standalone consistency check as this Dagster run's body."""

    client = cast("AsyncAddressClient", op_resource(context, "client"))
    settings = cast("Settings", op_resource(context, "settings"))
    engine = client._engine()
    ttl = settings.dagster_lease_ttl_seconds

    config = cast("Mapping[str, Any]", context.op_config)
    job_id = str(config["job_id"])
    payload = dict(cast("Mapping[str, Any]", config["payload"]))

    async def leaf(cancel_event: asyncio.Event, progress: ProgressReporter) -> None:
        await run_consistency_check(engine, payload=payload, progress=progress)

    await execute_load_job(
        job_id=job_id,
        orchestrator_run_id=context.run_id,
        engine=engine,
        leaf=leaf,
        lease_ttl_seconds=ttl,
    )
    context.add_output_metadata({"job_id": job_id, "kind": "consistency_check"})
    return {"job_id": job_id}


@job(
    name="consistency_check",
    tags=CONSISTENCY_CHECK_JOB_TAGS,
    description="Run a standalone registry consistency check as a Dagster run (T-290k).",
)
def consistency_check_job() -> None:
    run_consistency_check_op()


CONSISTENCY_JOBS: Final = [consistency_check_job]
