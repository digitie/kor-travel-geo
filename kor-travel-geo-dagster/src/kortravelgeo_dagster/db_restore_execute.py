"""Dagster ``db_restore`` execution op (T-290i).

Mirrors T-290g's ``db_backup`` op: moves ``db_restore`` EXECUTION into Dagster
(previously an in-process ``JobQueue`` handler). The op calls the main-lib leaf
``run_restore_job`` with the ``client`` resource's engine, bridged to the
``load_jobs`` row via :func:`load_job_bridge.execute_load_job`
(adopt → progress/cancel → terminal). Restore targets a NEW empty DB; the final
hot-swap stays a MANUAL operator step (ADR-036). **No RetryPolicy** — a restore is
non-idempotent and, on failure in ``new_database`` mode, drops/quarantines the
target, so a retry must never re-run (ADR-066 §4). The API keeps ownership of the
``load_jobs`` record; the op only drives it while the run is live.

IMPORTANT (dagster-boundary §10): this module must NOT use
``from __future__ import annotations`` — Dagster validates the ``@op`` ``context``
type at runtime, which requires real (non-stringized) annotations.
"""

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import Field, OpExecutionContext, Permissive, String, job, op
from kortravelgeo.infra.backup import run_restore_job

# Runtime imports: this module has no `from __future__ import annotations` (§10), so the
# nested leaf's `asyncio.Event` / `ProgressReporter` annotations are evaluated eagerly.
from .load_job_bridge import ProgressReporter, execute_load_job
from .resources import op_resource

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.settings import Settings

__all__ = [
    "DB_RESTORE_JOBS",
    "DB_RESTORE_JOB_TAGS",
    "db_restore_job",
    "run_db_restore_op",
]

DB_RESTORE_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "maintenance",
    "kor_travel_geo.job_kind": "db_restore",
}

_DB_RESTORE_CONFIG_SCHEMA: Final[dict[str, object]] = {
    "job_id": Field(
        String,
        description="The load_jobs id the API created before launching this run.",
    ),
    "payload": Field(
        Permissive(),  # type: ignore[no-untyped-call]
        description=(
            "RestoreCreateRequest payload (source artifact_id/archive, target_database, "
            "mode=new_database, jobs, ...)."
        ),
    ),
}


@op(
    name="run_db_restore",
    description=(
        "Execute a db_restore by calling the main-lib run_restore_job leaf, bridged to the "
        "load_jobs row (adopt/progress/cancel/terminal). Restores into a new empty DB; the "
        "hot-swap stays manual. No RetryPolicy — non-idempotent."
    ),
    required_resource_keys={"client", "settings"},
    config_schema=_DB_RESTORE_CONFIG_SCHEMA,
)
async def run_db_restore_op(context: OpExecutionContext) -> dict[str, object]:
    """Run the db_restore leaf as this Dagster run's body, driving its ``load_jobs`` row."""

    client = cast("AsyncAddressClient", op_resource(context, "client"))
    settings = cast("Settings", op_resource(context, "settings"))
    engine = client._engine()

    config = cast("Mapping[str, Any]", context.op_config)
    job_id = str(config["job_id"])
    payload = dict(cast("Mapping[str, Any]", config["payload"]))

    async def leaf(cancel_event: asyncio.Event, progress: ProgressReporter) -> None:
        # run_restore_job takes the load_jobs id explicitly (no _job_id payload smuggling).
        await run_restore_job(engine, settings, payload, cancel_event, progress, job_id=job_id)

    await execute_load_job(
        job_id=job_id,
        orchestrator_run_id=context.run_id,
        engine=engine,
        leaf=leaf,
    )
    context.add_output_metadata({"job_id": job_id, "kind": "db_restore"})
    return {"job_id": job_id}


@job(
    name="db_restore",
    tags=DB_RESTORE_JOB_TAGS,
    description="Execute a db_restore as a Dagster run (T-290i). Launched by the geo admin API.",
)
def db_restore_job() -> None:
    run_db_restore_op()


DB_RESTORE_JOBS: Final = [db_restore_job]
