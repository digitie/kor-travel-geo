"""Dagster ``db_backup`` execution op (T-290g).

Moves ``db_backup`` EXECUTION into Dagster (previously an in-process ``JobQueue`` handler):
the op calls the main-lib leaf ``run_backup_job`` with the ``client`` resource's engine,
bridged to the ``load_jobs`` row via :func:`load_job_bridge.execute_load_job`
(adopt → progress/cancel → terminal). **No RetryPolicy** — a backup creates an artifact and
is non-idempotent (ADR-066 §4). The API keeps ownership of the ``load_jobs`` record; the op
only drives it while the run is live.

IMPORTANT (dagster-boundary §10): this module must NOT use
``from __future__ import annotations`` — Dagster validates the ``@op`` ``context`` type at
runtime, which requires real (non-stringized) annotations.
"""

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import Field, OpExecutionContext, Permissive, String, job, op
from kortravelgeo.infra.backup import run_backup_job

# Runtime imports: this module has no `from __future__ import annotations` (§10), so the
# nested leaf's `asyncio.Event` / `ProgressReporter` annotations are evaluated eagerly.
from .load_job_bridge import ProgressReporter, execute_load_job

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.settings import Settings

__all__ = [
    "DB_BACKUP_JOBS",
    "DB_BACKUP_JOB_TAGS",
    "db_backup_job",
    "run_db_backup_op",
]

DB_BACKUP_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "maintenance",
    "kor_travel_geo.job_kind": "db_backup",
}

_DB_BACKUP_CONFIG_SCHEMA: Final[dict[str, object]] = {
    "job_id": Field(
        String,
        description="The load_jobs id the API created before launching this run.",
    ),
    "payload": Field(
        Permissive(),  # type: ignore[no-untyped-call]
        description="BackupCreateRequest payload (jobs, compression_level, destination_dir, ...).",
    ),
}


@op(
    name="run_db_backup",
    description=(
        "Execute a db_backup by calling the main-lib run_backup_job leaf, bridged to the "
        "load_jobs row (adopt/progress/cancel/terminal). No RetryPolicy — non-idempotent."
    ),
    required_resource_keys={"client", "settings"},
    config_schema=_DB_BACKUP_CONFIG_SCHEMA,
)
async def run_db_backup_op(context: OpExecutionContext) -> dict[str, object]:
    """Run the db_backup leaf as this Dagster run's body, driving its ``load_jobs`` row."""

    client = cast("AsyncAddressClient", _resource_object(context, "client"))
    settings = cast("Settings", _resource_object(context, "settings"))
    engine = client._engine()

    config = cast("Mapping[str, Any]", context.op_config)
    job_id = str(config["job_id"])
    payload = dict(cast("Mapping[str, Any]", config["payload"]))

    async def leaf(cancel_event: asyncio.Event, progress: ProgressReporter) -> None:
        # run_backup_job takes the load_jobs id explicitly (no _job_id payload smuggling).
        await run_backup_job(engine, settings, payload, cancel_event, progress, job_id=job_id)

    await execute_load_job(
        job_id=job_id,
        orchestrator_run_id=context.run_id,
        engine=engine,
        leaf=leaf,
    )
    context.add_output_metadata({"job_id": job_id, "kind": "db_backup"})
    return {"job_id": job_id}


@job(
    name="db_backup",
    tags=DB_BACKUP_JOB_TAGS,
    description="Execute a db_backup as a Dagster run (T-290g). Launched by the geo admin API.",
)
def db_backup_job() -> None:
    run_db_backup_op()


DB_BACKUP_JOBS: Final = [db_backup_job]


def _resource_object(context: OpExecutionContext, name: str) -> object:
    resources = cast("Any", context.resources)
    if not hasattr(resources, name):
        raise AttributeError(f"Dagster resource missing: {name}")
    return getattr(resources, name)
