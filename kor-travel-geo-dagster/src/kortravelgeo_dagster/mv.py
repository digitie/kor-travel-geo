"""Dagster materialized-view refresh job (T-290k — release-gated, load_jobs-bridged).

Runs the geo serving MV refresh as a Dagster op by calling the main-lib leaf
:func:`kortravelgeo.loaders.batch_dag.run_mv_refresh`, which performs the FULL serving
sequence the in-process ``mv_refresh`` handler did (``resolve_text_geometry_links`` ->
``ensure_load_batch_release_gate`` (unless ``forced_promotion``) -> MV swap ->
``record_mv_refresh_release`` + serving-release write). The earlier T-290a wiring proof
called ``refresh_mv`` alone and silently dropped the link-resolution, release gate and
serving-release record; routing the operator endpoint at it would have lost those semantics.
Bridged to the ``load_jobs`` row via :func:`load_job_bridge.execute_load_job`.

IMPORTANT (dagster-boundary §10): this module must NOT use
``from __future__ import annotations`` — Dagster validates the ``@op`` ``context`` type at
runtime, which requires real (non-stringized) annotations.
"""

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import Field, OpExecutionContext, Permissive, String, job, op
from kortravelgeo.loaders.batch_dag import run_mv_refresh

from .load_job_bridge import ProgressReporter, execute_load_job
from .resources import op_resource

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.settings import Settings

__all__ = [
    "MV_REFRESH_JOBS",
    "MV_REFRESH_JOB_TAGS",
    "mv_refresh_job",
    "run_mv_refresh_op",
]

MV_REFRESH_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "maintenance",
    "kor_travel_geo.job_kind": "mv_refresh",
}
"""Common tags for the mv_refresh Dagster job."""

_MV_REFRESH_CONFIG_SCHEMA: Final[dict[str, object]] = {
    "job_id": Field(
        String,
        description="The mv_refresh load_jobs id the API created before launching.",
    ),
    "payload": Field(
        Permissive(),  # type: ignore[no-untyped-call]
        description=(
            "mv_refresh payload: strategy ('concurrent'|'swap'), load_batch_id, "
            "source_match_set_id, forced_promotion, forced_promotion_metadata."
        ),
    ),
}


@op(
    name="run_mv_refresh",
    description=(
        "Refresh the geo serving MVs via the main-lib run_mv_refresh leaf (resolve links -> "
        "release gate -> swap -> record serving release), bridged to the load_jobs row. "
        "No RetryPolicy — the swap performs DROP/RENAME (non-idempotent). Op name != job name."
    ),
    required_resource_keys={"client", "settings"},
    config_schema=_MV_REFRESH_CONFIG_SCHEMA,
)
async def run_mv_refresh_op(context: OpExecutionContext) -> dict[str, object]:
    """Run the release-gated MV refresh as this Dagster run's body."""

    client = cast("AsyncAddressClient", op_resource(context, "client"))
    settings = cast("Settings", op_resource(context, "settings"))
    engine = client._engine()
    ttl = settings.dagster_lease_ttl_seconds

    config = cast("Mapping[str, Any]", context.op_config)
    job_id = str(config["job_id"])
    payload = dict(cast("Mapping[str, Any]", config["payload"]))

    async def leaf(cancel_event: asyncio.Event, progress: ProgressReporter) -> None:
        await run_mv_refresh(engine, payload=payload, job_id=job_id, progress=progress)

    await execute_load_job(
        job_id=job_id,
        orchestrator_run_id=context.run_id,
        engine=engine,
        leaf=leaf,
        lease_ttl_seconds=ttl,
    )
    context.add_output_metadata({"job_id": job_id, "kind": "mv_refresh"})
    return {"job_id": job_id}


@job(
    name="mv_refresh",
    tags=MV_REFRESH_JOB_TAGS,
    description="Refresh the geo serving materialized views, release-gated (T-290k).",
)
def mv_refresh_job() -> None:
    """Operator-facing mv_refresh job (note: op name != job name)."""
    run_mv_refresh_op()


MV_REFRESH_JOBS: Final = [mv_refresh_job]
"""Job list aggregated by ``definitions.py``."""
