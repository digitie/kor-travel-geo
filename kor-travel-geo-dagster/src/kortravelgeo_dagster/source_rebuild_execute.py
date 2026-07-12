"""Dagster ``source_rebuild_db`` control execution op (T-290k).

Migrates the in-process ``source_rebuild_db`` CONTROL job (``app.py`` handler, retired in
T-290k) to Dagster. It materialises a source match set (precondition + pre-load integrity
gate + RustFS download/extract) under the SOURCE_REBUILD_DB **global** cross-process
advisory lock, then launches the downstream ``full_load_batch`` Dagster run and records the
rebuild -> batch provenance. The op calls the main-lib leaf
(:meth:`AsyncAddressClient.prepare_source_match_set_rebuild`) + the API launch helper; it is
bridged to its ``load_jobs`` control row via :func:`load_job_bridge.execute_load_job`.

**Single op, not two** (deviation from the blueprint's 2-op sketch): the rebuild control job
is ONE ``load_jobs`` row whose lifecycle spans *materialise → launch downstream → done*.
``execute_load_job`` adopts that row ``running`` and marks it terminal once, so splitting into
two ``execute_load_job``-wrapped ops would terminal-mark the row mid-job. Both phases run in
one op body, holding the advisory lock across both exactly like the in-process
``_locked_global_job_handler`` wrapped the whole handler.

**No RetryPolicy** — the downstream load mutates the serving dataset (non-idempotent).
This module imports the API launch helper (``kortravelgeo.api._full_load_launch``): the
Dagster code location is the orchestration layer that launches API-defined runs; that
dependency direction is intentional and not covered by the intra-``kortravelgeo`` layer
contract.

IMPORTANT (dagster-boundary §10): no ``from __future__ import annotations`` — Dagster
validates the ``@op`` ``context`` type at runtime.
"""

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast

from dagster import Field, OpExecutionContext, Permissive, String, job, op
from kortravelgeo.api._full_load_launch import launch_full_load_batch_dagster_run
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    cross_process_lock,
)

from .load_job_bridge import ProgressReporter, execute_load_job
from .resources import op_resource

if TYPE_CHECKING:
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.settings import Settings

__all__ = [
    "SOURCE_REBUILD_DB_JOB_TAGS",
    "SOURCE_REBUILD_JOBS",
    "run_source_rebuild_db_op",
    "source_rebuild_db_job",
]

SOURCE_REBUILD_DB_JOB_TAGS: Final[dict[str, str]] = {
    "kor_travel_geo.job_scope": "load",
    "kor_travel_geo.job_kind": "source_rebuild_db",
}

_CONFIG_SCHEMA: Final[dict[str, object]] = {
    "job_id": Field(
        String,
        description="The source_rebuild_db control load_jobs id the API created before launching.",
    ),
    "payload": Field(
        Permissive(),  # type: ignore[no-untyped-call]
        description=(
            "rebuild payload (source_match_set_id, actor, force_promotion, reason, "
            "download_concurrency, materialize_concurrency)."
        ),
    ),
}


def _payload_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _payload_bool(payload: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    return value if isinstance(value, bool) else default


def _payload_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@op(
    name="run_source_rebuild_db",
    description=(
        "Materialise a source match set (integrity gate + RustFS materialize under the "
        "SOURCE_REBUILD_DB global advisory lock) then launch the downstream full_load_batch "
        "Dagster run, bridged to the rebuild control load_jobs row. No RetryPolicy."
    ),
    required_resource_keys={"client", "settings"},
    config_schema=_CONFIG_SCHEMA,
)
async def run_source_rebuild_db_op(context: OpExecutionContext) -> dict[str, object]:
    """Run the source_rebuild_db control job as this Dagster run's body."""

    client = cast("AsyncAddressClient", op_resource(context, "client"))
    settings = cast("Settings", op_resource(context, "settings"))
    engine = client._engine()
    ttl = settings.dagster_lease_ttl_seconds

    config = cast("Mapping[str, Any]", context.op_config)
    job_id = str(config["job_id"])
    payload = dict(cast("Mapping[str, Any]", config["payload"]))

    source_match_set_id = _payload_str(payload, "source_match_set_id")
    if source_match_set_id is None:
        msg = "source_rebuild_db payload requires source_match_set_id"
        raise ValueError(msg)
    actor = _payload_str(payload, "actor")
    force_promotion = _payload_bool(payload, "force_promotion", default=False)
    reason = _payload_str(payload, "reason")
    download_concurrency = _payload_int(payload, "download_concurrency") or 3
    materialize_concurrency = _payload_int(payload, "materialize_concurrency") or 2

    lock_key = AdvisoryLockKey.global_key(AdvisoryLockNamespace.SOURCE_REBUILD_DB)

    async def leaf(cancel_event: asyncio.Event, progress: ProgressReporter) -> None:
        async with cross_process_lock(engine, lock_key):
            if cancel_event.is_set():
                raise asyncio.CancelledError
            response, batch_payload = await client.prepare_source_match_set_rebuild(
                source_match_set_id,
                actor=actor,
                force_promotion=force_promotion,
                typed_confirmation=None,
                reason=reason,
                download_concurrency=download_concurrency,
                materialize_concurrency=materialize_concurrency,
                progress=progress,
            )
            if batch_payload is None:
                await client.record_audit_event(
                    action="source.rebuild_db",
                    actor_type="ui",
                    actor_id=actor,
                    outcome="failed",
                    payload={"failed_group_ids": list(response.failed_group_ids)},
                    resource_type="source_match_set",
                    resource_id=source_match_set_id,
                    job_id=job_id,
                )
                msg = response.message or "pre-load integrity gate failed; groups quarantined"
                await progress(progress=1.0, stage="integrity_gate_failed", message=msg)
                raise RuntimeError(msg)
            if cancel_event.is_set():
                raise asyncio.CancelledError
            await progress(
                progress=0.80,
                stage="full_load_batch_launch",
                message="source rebuild materialized; launching full_load_batch",
            )
            batch_job_id = await launch_full_load_batch_dagster_run(engine, settings, batch_payload)
            await AdminRepository(engine).link_job_to_batch(job_id, batch_job_id)
            await client.record_rebuild_enqueued(
                source_match_set_id,
                actor=actor,
                job_id=batch_job_id,
                load_batch_id=batch_job_id,
                forced_promotion=force_promotion,
                reason=reason,
            )
            await progress(
                progress=1.0,
                stage="full_load_batch_launched",
                message=f"full_load_batch launched: {batch_job_id}",
            )

    await execute_load_job(
        job_id=job_id,
        orchestrator_run_id=context.run_id,
        engine=engine,
        leaf=leaf,
        lease_ttl_seconds=ttl,
    )
    context.add_output_metadata(
        {"job_id": job_id, "kind": "source_rebuild_db", "source_match_set_id": source_match_set_id}
    )
    return {"job_id": job_id}


@job(
    name="source_rebuild_db",
    tags=SOURCE_REBUILD_DB_JOB_TAGS,
    description="Rebuild the serving DB from a source match set as a Dagster run (T-290k).",
)
def source_rebuild_db_job() -> None:
    run_source_rebuild_db_op()


SOURCE_REBUILD_JOBS: Final = [source_rebuild_db_job]
