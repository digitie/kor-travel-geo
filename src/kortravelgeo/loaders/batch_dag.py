"""Full-load batch DAG orchestration (main lib, Dagster-free) — T-290j.

ADR-017's ``full_load_batch`` DAG — serial source loads → consistency check →
promotion GATE → ``mv_refresh`` swap — used to live *implicitly* in the in-process
:class:`~kortravelgeo.api._jobs.JobQueue` drain loop (claim child → run handler →
``_enqueue_batch_successors`` → gate → swap). To run the same batch as a service-
independent Dagster run (dagster-boundary §4 / §71-72: "DAG logic in main lib, Dagster
calls it 1-op-in-job"), that orchestration is extracted here as one Dagster-free
coroutine :func:`run_full_load_batch` plus the per-kind loader dispatch
:func:`run_source_loader` (and :func:`run_consistency_check` / :func:`run_mv_refresh`).

The semantics are a 1:1 port of the in-process DAG so both executors converge the same
``load_jobs`` rows and audit trail (the in-process path stays intact and is retired later
in T-290k):

* The batch root row + its source-loader child rows are created up front by
  :meth:`AdminRepository.insert_load_batch` (``executor='dagster'`` so the in-process
  drain — which claims only ``executor='api_in_process'`` — never double-runs them).
* The Dagster op adopts the *root* row (lease + cancel bridge + heartbeat) via the
  ``load_job_bridge`` and calls :func:`run_full_load_batch`, which drives the *child*
  rows inline and serially: each source loader, then a dynamically-created
  ``consistency_check`` child, the ERROR gate, then an ``mv_refresh`` child.
* Every child is driven with the same adopt → progress + lease heartbeat → terminal
  lifecycle (:func:`_drive_child`) under the *root's* Dagster run id, so an API restart
  mid-batch reconciles children against the live run rather than force-failing them.
* Cancel is single-sourced on ``load_jobs`` (ADR-066 §5): the root's cancel bridge sets
  the shared ``cancel_event``; children observe it directly (no per-child poll needed).

This module imports only ``loaders`` + ``infra`` (never ``dagster`` and never ``api``),
so it stays inside the import-linter ``loaders`` layer and keeps the one-way
``kortravelgeo_dagster -> kortravelgeo`` dependency (dagster-boundary §1).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import text

from kortravelgeo.dto.admin import ConsistencyReport
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    ConcurrentExecutionError,
    cross_process_lock,
)
from kortravelgeo.infra.load_job_executor import LoadJobExecutor
from kortravelgeo.loaders.bulk_loader import load_bulk_delivery
from kortravelgeo.loaders.consistency import DEFAULT_CASES, run_all_cases
from kortravelgeo.loaders.pobox_loader import load_pobox
from kortravelgeo.loaders.postload import (
    refresh_mv,
    refresh_region_radius_parts,
    resolve_text_geometry_links,
)
from kortravelgeo.loaders.shp.polygons_loader import load_shp_polygons
from kortravelgeo.loaders.sppn_makarea_loader import load_sppn_makarea
from kortravelgeo.loaders.text.daily_juso_loader import load_daily_juso_delta
from kortravelgeo.loaders.text.juso_hangul_loader import load_juso_hangul
from kortravelgeo.loaders.text.locsum_loader import load_locsum
from kortravelgeo.loaders.text.navi_loader import load_navi
from kortravelgeo.loaders.text.parcel_link_loader import (
    load_daily_parcel_link_delta,
    load_juso_parcel_link_snapshot,
)
from kortravelgeo.loaders.text.roadaddr_entrance_loader import load_roadaddr_entrances

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

__all__ = [
    "FullLoadBatchGateError",
    "ProgressReporter",
    "run_consistency_check",
    "run_full_load_batch",
    "run_mv_refresh",
    "run_source_loader",
]

#: Default lease TTL for Dagster-driven batch child rows (seconds). Mirrors the API
#: ``dagster_lease_ttl_seconds`` default; the op passes the configured value through.
_DEFAULT_LEASE_TTL_SECONDS = 300.0


class ProgressReporter(Protocol):
    """Structural match for the ``progress`` callback the in-process queue passes leaves."""

    async def __call__(
        self,
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None: ...


class FullLoadBatchGateError(RuntimeError):
    """The consistency promotion GATE blocked ``mv_refresh`` (ADR-017).

    Raised when the batch consistency report is ``severity_max == 'ERROR'`` and the batch
    was not armed with ``forced_promotion`` — the serving MV must NOT be swapped onto a
    dataset that failed integrity. The Dagster op converges the root row to ``failed``.
    """


# --------------------------------------------------------------------------------------
# payload helpers (self-contained; a small port of the api/app.py ``_payload_*`` helpers
# so this module needs no dependency on the ``api`` layer)
# --------------------------------------------------------------------------------------


def _payload_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _payload_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def _payload_bool(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    return value if isinstance(value, bool) else default


def _payload_path(payload: dict[str, Any]) -> Path:
    value = payload.get("path") or payload.get("source_path")
    if not isinstance(value, str) or not value:
        msg = "load payload requires 'path' or 'source_path'"
        raise ValueError(msg)
    return Path(value)


def _payload_lock_path(payload: dict[str, Any]) -> str:
    return str(_payload_path(payload).expanduser().resolve(strict=False))


# --------------------------------------------------------------------------------------
# per-kind source loaders (1:1 with the api/app.py loader handler closures)
# --------------------------------------------------------------------------------------
#
# Each ``_load_*`` is a straight port of the corresponding ``_register_default_handlers``
# closure body: emit a start stage, run the main-lib leaf, emit a completion message. The
# heavy loaders run off the event loop (``_run_off_event_loop``) so the op's lease
# heartbeat / cancel bridge tasks keep getting scheduled while a multi-minute COPY runs
# (the same reason the in-process handlers use ``_run_loader_off_event_loop``). ``shp`` /
# ``sppn_makarea`` await directly, exactly as the in-process handlers do.


async def _run_off_event_loop[T](factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run an awaitable-returning factory to completion on a worker thread.

    Mirrors ``api/app.py::_run_loader_off_event_loop`` (T-193): a synchronous-heavy loader
    would otherwise starve the op's ``asyncio`` tasks (lease heartbeat, cancel poll). The
    ``cancel_event`` the loader reads is only ever *polled* (``is_set()``), which is safe
    across the thread boundary.
    """

    def run() -> T:
        return asyncio.run(factory())

    return await asyncio.to_thread(run)


async def _load_juso(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="juso_text_load", message="도로명주소 한글 적재 시작")
    count = await _run_off_event_loop(
        lambda: load_juso_hangul(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
    )
    await progress(progress=1.0, stage="juso_text_load", message=f"{count} rows loaded")


async def _load_locsum(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="locsum_load", message="위치정보요약DB 적재 시작")
    count = await _run_off_event_loop(
        lambda: load_locsum(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
    )
    await progress(progress=1.0, stage="locsum_load", message=f"{count} rows loaded")


async def _load_daily_juso(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="daily_juso_delta", message="도로명주소 일변동 적재 시작")
    result = await _run_off_event_loop(
        lambda: load_daily_juso_delta(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
    )
    await progress(
        progress=1.0,
        stage="daily_juso_delta",
        message=(
            f"{result.processed_rows} rows processed, "
            f"{result.upserted_rows} upserted, {result.deleted_rows} deleted"
        ),
    )


async def _load_parcel_links(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="juso_parcel_link_load", message="건물-지번 링크 적재 시작")
    result = await _run_off_event_loop(
        lambda: load_juso_parcel_link_snapshot(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            replace=_payload_bool(payload, "replace", default=True),
            cancel_event=cancel_event,
        )
    )
    await progress(
        progress=1.0,
        stage="juso_parcel_link_load",
        message=f"{result.processed_rows} rows processed, {result.upserted_rows} upserted",
    )


async def _load_daily_parcel_links(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="juso_parcel_link_delta", message="건물-지번 일변동 적재 시작")
    result = await _run_off_event_loop(
        lambda: load_daily_parcel_link_delta(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
    )
    await progress(
        progress=1.0,
        stage="juso_parcel_link_delta",
        message=(
            f"{result.processed_rows} rows processed, "
            f"{result.upserted_rows} upserted, {result.deleted_rows} deleted"
        ),
    )


async def _load_roadaddr_entrances(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="roadaddr_entrance_load", message="도로명주소 출입구 정보 적재 시작")
    result = await _run_off_event_loop(
        lambda: load_roadaddr_entrances(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            replace=_payload_bool(payload, "replace", default=True),
            cancel_event=cancel_event,
        )
    )
    await progress(
        progress=1.0,
        stage="roadaddr_entrance_load",
        message=f"{result.processed_rows} rows processed, {result.upserted_rows} upserted",
    )


async def _load_navi(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="navi_load", message="내비게이션용DB 적재 시작")
    build_count, entrance_count = await _run_off_event_loop(
        lambda: load_navi(
            engine,
            _payload_path(payload),
            source_yyyymm=_payload_str(payload, "source_yyyymm"),
            limit_per_file=_payload_int(payload, "limit_per_file"),
            cancel_event=cancel_event,
        )
    )
    await progress(
        progress=1.0,
        stage="navi_load",
        message=f"{build_count} centroids, {entrance_count} entrances loaded",
    )


async def _load_shp(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="shp_polygons_load", message="SHP 보조 레이어 적재 시작")
    count = await load_shp_polygons(
        engine,
        _payload_path(payload),
        mode=_payload_str(payload, "mode") or "full",
        source_yyyymm=_payload_str(payload, "source_yyyymm"),
        cancel_event=cancel_event,
    )
    await refresh_region_radius_parts(engine)
    await progress(progress=1.0, stage="shp_polygons_load", message=f"{count} layers loaded")


async def _load_sppn_makarea(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="sppn_makarea_load", message="국가지점번호 표기 의무지역 적재 시작")
    count = await load_sppn_makarea(
        engine,
        _payload_path(payload),
        mode=_payload_str(payload, "mode") or "full",
        source_yyyymm=_payload_str(payload, "source_yyyymm"),
        cancel_event=cancel_event,
    )
    await progress(progress=1.0, stage="sppn_makarea_load", message=f"{count} rows loaded")


async def _load_pobox(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="pobox_load", message="사서함 우편번호 적재 시작")
    count = await _run_off_event_loop(
        lambda: load_pobox(engine, _payload_path(payload), cancel_event=cancel_event)
    )
    await progress(progress=1.0, stage="pobox_load", message=f"{count} rows loaded")


async def _load_bulk(
    engine: AsyncEngine,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    await progress(stage="bulk_load", message="대량배달처 우편번호 적재 시작")
    count = await _run_off_event_loop(
        lambda: load_bulk_delivery(engine, _payload_path(payload), cancel_event=cancel_event)
    )
    await progress(progress=1.0, stage="bulk_load", message=f"{count} rows loaded")


_SourceLoader = Callable[
    ["AsyncEngine", dict[str, Any], asyncio.Event, ProgressReporter], Awaitable[None]
]


#: kind -> (per-path advisory-lock namespace, loader). The namespace + per-path key mirror
#: the ``queue.register(...)`` wiring in ``api/app.py`` exactly so a Dagster-driven load and
#: an in-process load contend on the same cross-process lock during the transition.
_LOADER_DISPATCH: dict[str, tuple[AdvisoryLockNamespace, _SourceLoader]] = {
    "juso_text_load": (AdvisoryLockNamespace.LOAD_JUSO_TEXT, _load_juso),
    "daily_juso_delta": (AdvisoryLockNamespace.LOAD_DAILY_JUSO, _load_daily_juso),
    "juso_parcel_link_load": (AdvisoryLockNamespace.LOAD_PARCEL_LINK, _load_parcel_links),
    "juso_parcel_link_delta": (AdvisoryLockNamespace.LOAD_DAILY_PARCEL, _load_daily_parcel_links),
    "roadaddr_entrance_load": (
        AdvisoryLockNamespace.LOAD_ROADADDR_ENTRANCES,
        _load_roadaddr_entrances,
    ),
    "locsum_load": (AdvisoryLockNamespace.LOAD_LOCSUM, _load_locsum),
    "navi_load": (AdvisoryLockNamespace.LOAD_NAVI, _load_navi),
    "shp_polygons_load": (AdvisoryLockNamespace.LOAD_SHP_POLYGONS, _load_shp),
    "sppn_makarea_load": (AdvisoryLockNamespace.LOAD_SPPN_MAKAREA, _load_sppn_makarea),
    "pobox_load": (AdvisoryLockNamespace.LOAD_POBOX, _load_pobox),
    "bulk_load": (AdvisoryLockNamespace.LOAD_BULK, _load_bulk),
}


async def run_source_loader(
    engine: AsyncEngine,
    *,
    kind: str,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
) -> None:
    """Run a single source loader ``kind`` under its per-path advisory lock.

    The Dagster-executed equivalent of one ``queue.register(kind, _locked_job_handler(...))``
    entry: it acquires the same cross-process lock keyed on the payload path, then runs the
    main-lib leaf. A lock conflict surfaces as a ``lock_conflict`` stage and re-raises
    (ConcurrentExecutionError → the child row fails), exactly as the in-process handler does.
    """

    try:
        namespace, loader = _LOADER_DISPATCH[kind]
    except KeyError as exc:
        msg = f"no source loader registered for kind: {kind}"
        raise ValueError(msg) from exc
    key = AdvisoryLockKey.for_resource(namespace, _payload_lock_path(payload))
    try:
        async with cross_process_lock(engine, key):
            await loader(engine, payload, cancel_event, progress)
    except ConcurrentExecutionError as exc:
        await progress(stage="lock_conflict", message=f"{exc.code}: {exc.message}")
        raise


# --------------------------------------------------------------------------------------
# consistency + mv_refresh leaves (1:1 with the api/app.py control-job closures)
# --------------------------------------------------------------------------------------


def _source_set(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("source_set")
    result = {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}
    batch_id = payload.get("load_batch_id")
    if isinstance(batch_id, str):
        result["load_batch_id"] = batch_id
    return result


async def run_consistency_check(
    engine: AsyncEngine,
    *,
    payload: dict[str, Any],
    progress: ProgressReporter,
) -> ConsistencyReport:
    """Run the batch consistency check and return its report (port of the ``consistency``
    handler). In batch context (``load_batch_id`` present) an ``ERROR`` severity is
    *recorded, not raised* — the promotion GATE in :func:`run_full_load_batch` decides."""

    async def case_progress(value: float, code: str) -> None:
        await progress(progress=value, stage=f"consistency:{code}", message=f"{code} checked")

    raw_cases = payload.get("cases")
    cases = tuple(raw_cases) if isinstance(raw_cases, list) and raw_cases else DEFAULT_CASES
    report = await run_all_cases(
        engine,
        scope=_payload_str(payload, "scope") or "full",
        cases=cases,
        generated_by="api",
        source_set=_source_set(payload),
        on_progress=case_progress,
    )
    await progress(
        progress=1.0,
        stage="consistency_check",
        message=f"{report.report_id} severity={report.severity_max}",
    )
    load_batch_id = _payload_str(payload, "load_batch_id")
    if report.severity_max == "ERROR" and not load_batch_id:
        msg = f"consistency report failed: {report.report_id}"
        raise RuntimeError(msg)
    if report.severity_max == "ERROR":
        await progress(
            stage="consistency_check",
            message="consistency ERROR 기록됨; batch promotion gate에서 처리",
        )
    return report


async def run_mv_refresh(
    engine: AsyncEngine,
    *,
    payload: dict[str, Any],
    job_id: str,
    progress: ProgressReporter,
) -> None:
    """Resolve text↔geometry links, swap-refresh the serving MVs, and record the serving
    release (port of the ``mv_refresh`` handler). ``forced_promotion`` bypasses ONLY the
    consistency-ERROR release gate; the source-archive integrity gate already ran upstream."""

    strategy = _payload_str(payload, "strategy") or "concurrent"
    await progress(stage="mv_refresh", message=f"MV refresh 시작: {strategy}")
    await resolve_text_geometry_links(engine)
    repo = AdminRepository(engine)
    load_batch_id = _payload_str(payload, "load_batch_id")
    forced_promotion = _payload_bool(payload, "forced_promotion", default=False)
    if not forced_promotion:
        await repo.ensure_load_batch_release_gate(load_batch_id)
    await refresh_mv(
        engine,
        concurrently=strategy != "swap",
        strategy="swap" if strategy == "swap" else "concurrent",
    )
    forced_metadata = payload.get("forced_promotion_metadata")
    snapshot, release = await repo.record_mv_refresh_release(
        job_id=job_id,
        load_batch_id=load_batch_id,
        strategy=strategy,
        source_match_set_id=_payload_str(payload, "source_match_set_id"),
        forced_promotion=forced_promotion,
        forced_promotion_metadata=(forced_metadata if isinstance(forced_metadata, dict) else None),
    )
    await progress(progress=1.0, stage="mv_refresh", message="MV refresh 완료")
    await progress(
        stage="serving_release",
        message=(
            f"serving release 활성화: {release.serving_release_id} "
            f"snapshot={snapshot.dataset_snapshot_id}"
        ),
    )


# --------------------------------------------------------------------------------------
# child-row driver + batch orchestrator
# --------------------------------------------------------------------------------------

_ChildLeaf = Callable[[asyncio.Event, ProgressReporter], Awaitable[Any]]


def _source_leaf(engine: AsyncEngine, kind: str, payload: dict[str, Any]) -> _ChildLeaf:
    """Bind one source loader to the ``(cancel_event, progress)`` child-leaf shape."""

    async def _leaf(cancel_event: asyncio.Event, progress: ProgressReporter) -> None:
        await run_source_loader(
            engine, kind=kind, payload=payload, cancel_event=cancel_event, progress=progress
        )

    return _leaf


async def _lease_heartbeat(executor: LoadJobExecutor, job_id: str, ttl_seconds: float) -> None:
    """Renew a child row's lease at ~1/3 the TTL, independent of progress emission.

    A source loader can stay inside one long COPY without emitting progress; without this
    the child's lease expires and (on an API restart mid-batch) the orphan reconciler would
    force-fail a perfectly healthy child. Transient write errors are swallowed so a blip
    never tears the batch down (same shape as the ``load_job_bridge`` root heartbeat)."""

    interval = ttl_seconds / 3.0
    while True:
        await asyncio.sleep(interval)
        with suppress(Exception):
            await executor.renew_lease(job_id, ttl_seconds=ttl_seconds)


async def _drive_child(
    executor: LoadJobExecutor,
    *,
    child_id: str,
    orchestrator_run_id: str,
    cancel_event: asyncio.Event,
    ttl_seconds: float,
    leaf: _ChildLeaf,
) -> Any:
    """Adopt a child row under the batch's Dagster run, drive its lifecycle, return the
    leaf result. Adopt (``queued`` → ``running`` + run id + lease) → progress + lease
    heartbeat → terminal (done / failed / cancelled). Cancel is observed through the shared
    ``cancel_event`` the leaf reads; failures re-raise so the batch orchestrator can cancel
    the remaining siblings and converge the root."""

    await executor.adopt_dagster(child_id, orchestrator_run_id, ttl_seconds=ttl_seconds)

    async def child_progress(
        *,
        progress: float | None = None,
        stage: str | None = None,
        message: str | None = None,
    ) -> None:
        await executor.set_progress(child_id, progress=progress, stage=stage, message=message)
        await executor.renew_lease(child_id, ttl_seconds=ttl_seconds)

    heartbeat = asyncio.create_task(_lease_heartbeat(executor, child_id, ttl_seconds))
    try:
        await child_progress(progress=0.01, stage="running", message="job started")
        result = await leaf(cancel_event, child_progress)
    except asyncio.CancelledError:
        await executor.mark_cancelled(child_id)
        raise
    except Exception as exc:
        await executor.mark_failed(child_id, str(exc))
        raise
    else:
        await executor.mark_done(child_id)
        return result
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def _fetch_source_children(
    engine: AsyncEngine, batch_id: str
) -> list[tuple[str, str, dict[str, Any]]]:
    """The batch's source-loader child rows in submission order (root excluded)."""

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
SELECT job_id, kind, payload
  FROM load_jobs
 WHERE load_batch_id = :batch_id
   AND job_id <> :batch_id
 ORDER BY created_at
"""
                ),
                {"batch_id": batch_id},
            )
        ).mappings().all()
    return [
        (str(row["job_id"]), str(row["kind"]), dict(row["payload"] or {})) for row in rows
    ]


async def _cancel_queued_children(engine: AsyncEngine, batch_id: str) -> None:
    """Cancel the batch's not-yet-started children after a mid-DAG failure (delegates to
    the shared repo writer so the in-process and Dagster fan-outs stay one source of truth)."""

    await AdminRepository(engine).cancel_queued_batch_children(batch_id)


async def run_full_load_batch(
    engine: AsyncEngine,
    *,
    batch_id: str,
    payload: dict[str, Any],
    cancel_event: asyncio.Event,
    progress: ProgressReporter,
    orchestrator_run_id: str,
    lease_ttl_seconds: float = _DEFAULT_LEASE_TTL_SECONDS,
) -> dict[str, Any]:
    """Drive the ADR-017 ``full_load_batch`` DAG inline as one Dagster run's body.

    ``batch_id`` is the pre-created batch root row (its source-loader children already exist
    with ``executor='dagster'``). ``progress`` writes the *root* row (it is the op's bridge
    reporter, which also renews the root lease). Order of operations, a 1:1 port of the
    in-process ``JobQueue`` successor chain:

    1. Run each source loader child serially. On any child failure/cancel, cancel the
       remaining queued children and re-raise so the op converges the root to failed/cancelled.
    2. Create + run a ``consistency_check`` child (batch mode — ERROR is recorded, not raised).
    3. GATE: if the report is ``ERROR`` and the batch was not armed with ``forced_promotion``,
       raise :class:`FullLoadBatchGateError` (root fails; the serving MV is NOT swapped).
    4. Create + run an ``mv_refresh`` child (swap strategy) that resolves links, swaps the MVs
       and records the serving release. ``source_match_set_id`` / ``forced_promotion`` metadata
       is threaded from the batch root payload (rebuild-db provenance, T-205b).

    Returns a small metadata summary for ``context.add_output_metadata``. The op marks the
    root ``done`` on normal return.
    """

    executor = LoadJobExecutor(engine, lease_ttl_seconds=lease_ttl_seconds)
    repo = AdminRepository(engine)

    children = await _fetch_source_children(engine, batch_id)
    if not children:
        msg = f"full_load_batch {batch_id} has no source children"
        raise FullLoadBatchGateError(msg)
    total_stages = len(children) + 2  # sources + consistency + mv_refresh
    completed = 0

    def _root_progress(stage: str, message: str) -> Awaitable[None]:
        fraction = min(0.98, completed / total_stages)
        return progress(progress=fraction, stage=stage, message=message)

    # 1. source loads (serial) ---------------------------------------------------------
    for child_id, kind, child_payload in children:
        if cancel_event.is_set():
            raise asyncio.CancelledError
        try:
            await _drive_child(
                executor,
                child_id=child_id,
                orchestrator_run_id=orchestrator_run_id,
                cancel_event=cancel_event,
                ttl_seconds=lease_ttl_seconds,
                leaf=_source_leaf(engine, kind, child_payload),
            )
        except (Exception, asyncio.CancelledError):
            await _cancel_queued_children(engine, batch_id)
            raise
        completed += 1
        await _root_progress("source_loads", f"{kind} done ({completed}/{len(children)} sources)")

    # 2. consistency check -------------------------------------------------------------
    if cancel_event.is_set():
        raise asyncio.CancelledError
    consistency_payload: dict[str, Any] = {"scope": "full", "load_batch_id": batch_id}
    if isinstance(payload.get("source_set"), dict):
        consistency_payload["source_set"] = payload["source_set"]
    consistency_child = await repo.insert_load_job(
        kind="consistency_check",
        payload=consistency_payload,
        load_batch_id=batch_id,
        parent_job_id=batch_id,
        executor="dagster",
    )
    await progress(
        stage="consistency_check", message="all source jobs done; consistency_check running"
    )

    async def _consistency_leaf(_ce: asyncio.Event, pr: ProgressReporter) -> ConsistencyReport:
        return await run_consistency_check(engine, payload=consistency_payload, progress=pr)

    try:
        report = await _drive_child(
            executor,
            child_id=consistency_child.job_id,
            orchestrator_run_id=orchestrator_run_id,
            cancel_event=cancel_event,
            ttl_seconds=lease_ttl_seconds,
            leaf=_consistency_leaf,
        )
    except (Exception, asyncio.CancelledError):
        await _cancel_queued_children(engine, batch_id)
        raise
    completed += 1

    # 3. promotion GATE (ADR-017) ------------------------------------------------------
    source_match_set_id = _payload_str(payload, "source_match_set_id")
    forced_promotion = _payload_bool(payload, "forced_promotion", default=False)
    if report.severity_max == "ERROR" and not forced_promotion:
        msg = (
            f"consistency report severity ERROR; mv_refresh blocked "
            f"(report {report.report_id})"
        )
        raise FullLoadBatchGateError(msg)

    # 4. mv_refresh swap ---------------------------------------------------------------
    if cancel_event.is_set():
        raise asyncio.CancelledError
    mv_payload: dict[str, Any] = {"strategy": "swap", "load_batch_id": batch_id}
    if source_match_set_id:
        mv_payload["source_match_set_id"] = source_match_set_id
    if forced_promotion:
        mv_payload["forced_promotion"] = True
        forced_metadata = {
            key: payload[key]
            for key in ("forced_promotion_actor", "forced_promotion_reason")
            if payload.get(key) is not None
        }
        forced_metadata["consistency_severity"] = report.severity_max
        mv_payload["forced_promotion_metadata"] = forced_metadata
    mv_child = await repo.insert_load_job(
        kind="mv_refresh",
        payload=mv_payload,
        load_batch_id=batch_id,
        parent_job_id=batch_id,
        executor="dagster",
    )
    await progress(stage="mv_refresh", message="consistency gate passed; mv_refresh swap running")

    async def _mv_leaf(_ce: asyncio.Event, pr: ProgressReporter) -> None:
        await run_mv_refresh(engine, payload=mv_payload, job_id=mv_child.job_id, progress=pr)

    await _drive_child(
        executor,
        child_id=mv_child.job_id,
        orchestrator_run_id=orchestrator_run_id,
        cancel_event=cancel_event,
        ttl_seconds=lease_ttl_seconds,
        leaf=_mv_leaf,
    )
    completed += 1
    await progress(progress=1.0, stage="done", message="full_load_batch completed")

    return {
        "batch_id": batch_id,
        "source_children": len(children),
        "consistency_report_id": report.report_id,
        "consistency_severity": report.severity_max,
        "forced_promotion": forced_promotion,
    }
