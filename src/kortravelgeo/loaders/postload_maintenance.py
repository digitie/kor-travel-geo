"""Post-load read-optimized maintenance planning and reporting."""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.loaders.postload import refresh_mv, resolve_text_geometry_links

MaintenanceMode = Literal["plan", "execute_safe"]
MaintenanceStrategy = Literal["concurrent", "swap"]
MaintenanceStepMode = Literal["automatic", "manual"]
MaintenanceSeverity = Literal["info", "warn", "error"]

MAINTENANCE_REPORT_SCHEMA_VERSION = 1
DEFAULT_INDEX_BUDGET_BYTES = 32 * 1024 * 1024 * 1024
DEFAULT_DEAD_TUPLE_RATIO_WARN = 0.10
DEFAULT_DEAD_TUPLE_COUNT_WARN = 100_000

POSTLOAD_SOURCE_RELATIONS: tuple[str, ...] = (
    "tl_juso_text",
    "tl_juso_parcel_link",
    "tl_locsum_entrc",
    "tl_roadaddr_entrc",
    "tl_navi_buld_centroid",
    "tl_navi_entrc",
    "tl_spbd_buld_polygon",
    "tl_spbd_eqb",
    "tl_sppn_makarea",
    "postal_pobox",
    "postal_bulk_delivery",
)
POSTLOAD_SERVING_RELATIONS: tuple[str, ...] = (
    "mv_geocode_target",
    "mv_geocode_text_search",
    "region_radius_parts",
)
POSTLOAD_MAINTENANCE_RELATIONS: tuple[str, ...] = (
    *POSTLOAD_SOURCE_RELATIONS,
    *POSTLOAD_SERVING_RELATIONS,
)


@dataclass(frozen=True, slots=True)
class MaintenanceStep:
    step_id: str
    phase: str
    mode: MaintenanceStepMode
    required: bool
    command: str
    reason: str
    lock_impact: str
    rollback: str
    notes: str


@dataclass(frozen=True, slots=True)
class MaintenanceExecution:
    step_id: str
    status: Literal["planned", "skipped", "succeeded"]
    seconds: float | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class MaintenanceObjectStat:
    schema_name: str
    object_name: str
    object_kind: str
    parent_object_name: str | None
    estimated_rows: int | None
    total_bytes: int
    table_bytes: int | None
    index_bytes: int | None
    toast_bytes: int | None
    live_tuples: int | None
    dead_tuples: int | None
    dead_tuple_ratio: float | None
    last_vacuum: str | None
    last_analyze: str | None
    index_valid: bool | None
    index_ready: bool | None


@dataclass(frozen=True, slots=True)
class MaintenanceWarning:
    code: str
    severity: MaintenanceSeverity
    object_name: str | None
    message: str
    value: float | int | str | None = None
    threshold: float | int | str | None = None


@dataclass(frozen=True, slots=True)
class MaintenanceReport:
    schema_version: int
    task_id: str
    mode: MaintenanceMode
    strategy: MaintenanceStrategy
    started_at: str
    finished_at: str
    settings: Mapping[str, Any]
    steps: tuple[MaintenanceStep, ...]
    executions: tuple[MaintenanceExecution, ...]
    before: tuple[MaintenanceObjectStat, ...]
    after: tuple[MaintenanceObjectStat, ...]
    warnings: tuple[MaintenanceWarning, ...]


def build_postload_maintenance_plan(
    *,
    strategy: MaintenanceStrategy = "swap",
    vacuum_analyze: bool = False,
    include_prewarm_note: bool = True,
) -> tuple[MaintenanceStep, ...]:
    """Return the standard T-146 maintenance sequence.

    The plan deliberately separates safe automated steps from operations that
    need an operator decision. ``CLUSTER`` and broad ``REINDEX CONCURRENTLY``
    are represented as manual steps because their lock and IO envelope depends
    on the live DB and hardware.
    """

    vacuum_command = "VACUUM (ANALYZE) " + ", ".join(
        _quote_relation(name) for name in POSTLOAD_SOURCE_RELATIONS
    )
    steps: list[MaintenanceStep] = [
        MaintenanceStep(
            step_id="catalog.before",
            phase="preflight",
            mode="automatic",
            required=True,
            command="collect_postload_object_stats()",
            reason="post-load relation size, last analyze, dead tuple, index state baseline",
            lock_impact="read-only catalog query",
            rollback="none",
            notes="uses pg_class, pg_stat_user_tables, pg_index, pg_total_relation_size",
        ),
        MaintenanceStep(
            step_id="source.vacuum_analyze",
            phase="source_stats",
            mode="automatic",
            required=vacuum_analyze,
            command=vacuum_command,
            reason="fresh planner stats and removable dead tuples after large COPY/UPSERT loads",
            lock_impact="VACUUM SHARE UPDATE EXCLUSIVE per relation; enabled only by option",
            rollback="none; rerun ANALYZE/VACUUM if interrupted",
            notes=(
                "plain ANALYZE is already run inside several loaders; "
                "this is for full post-load sweep"
            ),
        ),
        MaintenanceStep(
            step_id="links.resolve",
            phase="serving_rebuild",
            mode="automatic",
            required=True,
            command="resolve_text_geometry_links(statement_timeout_ms=1800000)",
            reason="derive serving keys before MV refresh",
            lock_impact="writes resolved link columns on loaded source tables",
            rollback="restore from pre-load backup or rerun loaders",
            notes="same helper used by API job and ktgctl full-load path",
        ),
        MaintenanceStep(
            step_id="serving.refresh",
            phase="serving_rebuild",
            mode="automatic",
            required=True,
            command=f"refresh_mv(strategy={strategy!r})",
            reason=(
                "refresh mv_geocode_target, mv_geocode_text_search, "
                "region_radius_parts as one serving generation"
            ),
            lock_impact=(
                "short rename lock for swap; longer read/write contention for concurrent refresh"
                if strategy == "swap"
                else "REFRESH CONCURRENTLY keeps reads online but consumes temp IO"
            ),
            rollback=(
                "previous DB backup/restore or serving hot-swap rollback; "
                "MV old copy is not retained"
            ),
            notes="refresh_mv() also ANALYZEes live MVs and clears geo_cache after success",
        ),
        MaintenanceStep(
            step_id="stats.capture",
            phase="observability",
            mode="automatic",
            required=True,
            command="AdminRepository.capture_table_stats_snapshots()",
            reason="persist after-maintenance relation size, bloat proxy, analyze timestamps",
            lock_impact="read-only catalog query plus ops.table_stats_snapshots insert",
            rollback="delete snapshot rows only if an operator deliberately wants to hide the run",
            notes="linked to the active serving release when one exists",
        ),
        MaintenanceStep(
            step_id="budget.check",
            phase="observability",
            mode="automatic",
            required=True,
            command="build_postload_maintenance_warnings()",
            reason=(
                "flag invalid indexes, dead tuple ratio, missing analyze, "
                "and index budget drift"
            ),
            lock_impact="read-only in plan mode",
            rollback="none",
            notes="budget is advisory; change requires a follow-up task or operator decision",
        ),
        MaintenanceStep(
            step_id="manual.reindex_concurrently",
            phase="manual_remediation",
            mode="manual",
            required=False,
            command="REINDEX INDEX CONCURRENTLY <index_name>",
            reason="repair invalid or clearly bloated indexes without blocking ordinary reads",
            lock_impact="high IO; brief locks at start/end; cannot run inside a transaction block",
            rollback="cancel and rerun; use backup/restore for severe catalog corruption",
            notes="not run automatically by T-146 because index bloat needs per-index evidence",
        ),
        MaintenanceStep(
            step_id="manual.cluster_or_repack",
            phase="manual_remediation",
            mode="manual",
            required=False,
            command="CLUSTER <relation> USING <index> or pg_repack/shadow table rebuild",
            reason=(
                "physical ordering can help read-mostly scans but takes exclusive lock "
                "without repack"
            ),
            lock_impact=(
                "CLUSTER blocks reads/writes; shadow/repack needs extra disk "
                "and operator window"
            ),
            rollback="restore backup or swap back to previous relation/database",
            notes="prefer shadow rebuild or pg_repack over raw CLUSTER on live serving DB",
        ),
    ]
    if include_prewarm_note:
        steps.append(
            MaintenanceStep(
                step_id="manual.pg_prewarm",
                phase="runtime_warm",
                mode="manual",
                required=False,
                command="pg_prewarm(...) / hot query warm script",
                reason="reduce cold-start spike after restart or swap",
                lock_impact="read IO and shared buffer pressure",
                rollback="none; buffers naturally age out",
                notes="automation belongs to T-162; T-146 only records the runbook boundary",
            )
        )
    return tuple(steps)


async def collect_postload_object_stats(
    engine: AsyncEngine,
    *,
    relation_names: Sequence[str] = POSTLOAD_MAINTENANCE_RELATIONS,
) -> tuple[MaintenanceObjectStat, ...]:
    relation_tuple = tuple(dict.fromkeys(relation_names))
    relation_stats_sql = text(
        """
SELECT n.nspname AS schema_name,
       c.relname AS object_name,
       CASE c.relkind
         WHEN 'r' THEN 'table'
         WHEN 'p' THEN 'table'
         WHEN 'm' THEN 'materialized_view'
         ELSE 'other'
       END AS object_kind,
       NULL::text AS parent_object_name,
       GREATEST(c.reltuples, 0)::bigint AS estimated_rows,
       pg_total_relation_size(c.oid)::bigint AS total_bytes,
       pg_relation_size(c.oid)::bigint AS table_bytes,
       pg_indexes_size(c.oid)::bigint AS index_bytes,
       GREATEST(
         pg_total_relation_size(c.oid) - pg_relation_size(c.oid) - pg_indexes_size(c.oid),
         0
       )::bigint AS toast_bytes,
       GREATEST(COALESCE(s.n_live_tup, 0), 0)::bigint AS live_tuples,
       GREATEST(COALESCE(s.n_dead_tup, 0), 0)::bigint AS dead_tuples,
       s.last_vacuum::text AS last_vacuum,
       GREATEST(
         COALESCE(s.last_analyze, '-infinity'::timestamptz),
         COALESCE(s.last_autoanalyze, '-infinity'::timestamptz)
       )::text AS last_analyze,
       NULL::boolean AS index_valid,
       NULL::boolean AS index_ready
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
 WHERE n.nspname = 'public'
   AND c.relkind IN ('r','p','m')
   AND c.relname IN :relation_names
UNION ALL
SELECT ni.nspname AS schema_name,
       i.relname AS object_name,
       'index' AS object_kind,
       t.relname AS parent_object_name,
       NULL::bigint AS estimated_rows,
       pg_total_relation_size(i.oid)::bigint AS total_bytes,
       NULL::bigint AS table_bytes,
       pg_relation_size(i.oid)::bigint AS index_bytes,
       NULL::bigint AS toast_bytes,
       NULL::bigint AS live_tuples,
       NULL::bigint AS dead_tuples,
       NULL::text AS last_vacuum,
       NULL::text AS last_analyze,
       ix.indisvalid AS index_valid,
       ix.indisready AS index_ready
  FROM pg_class i
  JOIN pg_namespace ni ON ni.oid = i.relnamespace
  JOIN pg_index ix ON ix.indexrelid = i.oid
  JOIN pg_class t ON t.oid = ix.indrelid
  JOIN pg_namespace nt ON nt.oid = t.relnamespace
 WHERE ni.nspname = 'public'
   AND nt.nspname = 'public'
   AND t.relname IN :relation_names
 ORDER BY schema_name, object_kind, object_name
"""
    ).bindparams(bindparam("relation_names", expanding=True))
    async with engine.connect() as conn:
        result = await conn.execute(relation_stats_sql, {"relation_names": relation_tuple})
        rows = result.mappings()
        return tuple(_object_stat(dict(row)) for row in rows)


def build_postload_maintenance_warnings(
    stats: Iterable[MaintenanceObjectStat],
    *,
    index_budget_bytes: int = DEFAULT_INDEX_BUDGET_BYTES,
    dead_tuple_ratio_warn: float = DEFAULT_DEAD_TUPLE_RATIO_WARN,
    dead_tuple_count_warn: int = DEFAULT_DEAD_TUPLE_COUNT_WARN,
) -> tuple[MaintenanceWarning, ...]:
    warnings: list[MaintenanceWarning] = []
    stats_tuple = tuple(stats)
    index_bytes_total = sum(stat.total_bytes for stat in stats_tuple if stat.object_kind == "index")
    if index_budget_bytes > 0 and index_bytes_total > index_budget_bytes:
        warnings.append(
            MaintenanceWarning(
                code="index_budget_exceeded",
                severity="warn",
                object_name=None,
                message="post-load index footprint exceeds configured budget",
                value=index_bytes_total,
                threshold=index_budget_bytes,
            )
        )
    for stat in stats_tuple:
        if stat.object_kind == "index" and (stat.index_valid is False or stat.index_ready is False):
            warnings.append(
                MaintenanceWarning(
                    code="index_invalid",
                    severity="error",
                    object_name=stat.object_name,
                    message="index is not valid or not ready; consider REINDEX CONCURRENTLY",
                    value=f"valid={stat.index_valid}, ready={stat.index_ready}",
                )
            )
            continue
        if stat.object_kind not in {"table", "materialized_view"}:
            continue
        if stat.last_analyze in {None, "-infinity"}:
            warnings.append(
                MaintenanceWarning(
                    code="missing_analyze",
                    severity="warn",
                    object_name=stat.object_name,
                    message="relation has no visible analyze timestamp",
                )
            )
        if (
            stat.dead_tuple_ratio is not None
            and stat.dead_tuples is not None
            and stat.dead_tuples >= dead_tuple_count_warn
            and stat.dead_tuple_ratio >= dead_tuple_ratio_warn
        ):
            warnings.append(
                MaintenanceWarning(
                    code="dead_tuple_ratio_high",
                    severity="warn",
                    object_name=stat.object_name,
                    message="dead tuple ratio is above post-load maintenance threshold",
                    value=round(stat.dead_tuple_ratio, 6),
                    threshold=dead_tuple_ratio_warn,
                )
            )
    return tuple(warnings)


async def run_postload_maintenance(
    engine: AsyncEngine,
    *,
    mode: MaintenanceMode = "plan",
    strategy: MaintenanceStrategy = "swap",
    vacuum_analyze: bool = False,
    capture_stats: bool = True,
    index_budget_bytes: int = DEFAULT_INDEX_BUDGET_BYTES,
    dead_tuple_ratio_warn: float = DEFAULT_DEAD_TUPLE_RATIO_WARN,
    dead_tuple_count_warn: int = DEFAULT_DEAD_TUPLE_COUNT_WARN,
) -> MaintenanceReport:
    started_at = _utc_now()
    steps = build_postload_maintenance_plan(strategy=strategy, vacuum_analyze=vacuum_analyze)
    before = await collect_postload_object_stats(engine)
    executions: list[MaintenanceExecution] = [
        MaintenanceExecution(step_id="catalog.before", status="succeeded", detail="catalog read")
    ]
    if mode == "execute_safe":
        if vacuum_analyze:
            executions.append(
                await _execute_timed(
                    "source.vacuum_analyze",
                    _vacuum_analyze_sources(engine),
                )
            )
        else:
            executions.append(
                MaintenanceExecution(
                    step_id="source.vacuum_analyze",
                    status="skipped",
                    detail="enable with --vacuum-analyze",
                )
            )
        executions.append(
            await _execute_timed("links.resolve", resolve_text_geometry_links(engine))
        )
        executions.append(
            await _execute_timed(
                "serving.refresh",
                refresh_mv(engine, concurrently=strategy != "swap", strategy=strategy),
            )
        )
        if capture_stats:
            executions.append(
                await _execute_timed(
                    "stats.capture",
                    AdminRepository(engine).capture_table_stats_snapshots(),
                )
            )
        else:
            executions.append(
                MaintenanceExecution(
                    step_id="stats.capture",
                    status="skipped",
                    detail="disabled by option",
                )
            )
    else:
        executions.extend(
            MaintenanceExecution(
                step_id=step.step_id,
                status="planned" if step.mode == "automatic" else "skipped",
                detail="plan mode" if step.mode == "automatic" else "manual-only",
            )
            for step in steps
            if step.step_id != "catalog.before"
        )
    after = (
        await collect_postload_object_stats(engine)
        if mode == "execute_safe"
        else before
    )
    warnings = build_postload_maintenance_warnings(
        after or before,
        index_budget_bytes=index_budget_bytes,
        dead_tuple_ratio_warn=dead_tuple_ratio_warn,
        dead_tuple_count_warn=dead_tuple_count_warn,
    )
    return MaintenanceReport(
        schema_version=MAINTENANCE_REPORT_SCHEMA_VERSION,
        task_id="T-146",
        mode=mode,
        strategy=strategy,
        started_at=started_at,
        finished_at=_utc_now(),
        settings={
            "vacuum_analyze": vacuum_analyze,
            "capture_stats": capture_stats,
            "index_budget_bytes": index_budget_bytes,
            "dead_tuple_ratio_warn": dead_tuple_ratio_warn,
            "dead_tuple_count_warn": dead_tuple_count_warn,
        },
        steps=steps,
        executions=tuple(executions),
        before=before,
        after=after,
        warnings=warnings,
    )


def maintenance_report_to_dict(report: MaintenanceReport) -> dict[str, Any]:
    return asdict(report)


def maintenance_report_metrics(report: MaintenanceReport) -> dict[str, int | float]:
    index_bytes_total = sum(
        stat.total_bytes for stat in report.after if stat.object_kind == "index"
    )
    total_bytes = sum(
        stat.total_bytes for stat in report.after if stat.object_kind != "index"
    )
    return {
        "samples": len(report.after),
        "error_count": sum(1 for warning in report.warnings if warning.severity == "error"),
        "error_rate": 0.0 if not report.warnings else (
            sum(1 for warning in report.warnings if warning.severity == "error")
            / len(report.warnings)
        ),
        "max_ms": round(
            max((execution.seconds or 0.0 for execution in report.executions), default=0.0)
            * 1000,
            3,
        ),
        "total_relation_bytes": total_bytes,
        "total_index_bytes": index_bytes_total,
        "warning_count": len(report.warnings),
    }


async def _execute_timed(step_id: str, awaitable: Any) -> MaintenanceExecution:
    start = time.perf_counter()
    await awaitable
    return MaintenanceExecution(
        step_id=step_id,
        status="succeeded",
        seconds=time.perf_counter() - start,
    )


async def _vacuum_analyze_sources(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        autocommit_conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        for relation in POSTLOAD_SOURCE_RELATIONS:
            await autocommit_conn.execute(text(f"VACUUM (ANALYZE) {_quote_relation(relation)}"))


def _object_stat(row: Mapping[str, Any]) -> MaintenanceObjectStat:
    live_tuples = _optional_int(row.get("live_tuples"))
    dead_tuples = _optional_int(row.get("dead_tuples"))
    dead_count = dead_tuples or 0
    denominator = (live_tuples or 0) + dead_count
    return MaintenanceObjectStat(
        schema_name=str(row["schema_name"]),
        object_name=str(row["object_name"]),
        object_kind=str(row["object_kind"]),
        parent_object_name=_optional_str(row.get("parent_object_name")),
        estimated_rows=_optional_int(row.get("estimated_rows")),
        total_bytes=int(row["total_bytes"] or 0),
        table_bytes=_optional_int(row.get("table_bytes")),
        index_bytes=_optional_int(row.get("index_bytes")),
        toast_bytes=_optional_int(row.get("toast_bytes")),
        live_tuples=live_tuples,
        dead_tuples=dead_tuples,
        dead_tuple_ratio=(dead_count / denominator if denominator else None),
        last_vacuum=_normalize_optional_ts(row.get("last_vacuum")),
        last_analyze=_normalize_optional_ts(row.get("last_analyze")),
        index_valid=_optional_bool(row.get("index_valid")),
        index_ready=_optional_bool(row.get("index_ready")),
    )


def _quote_relation(value: str) -> str:
    return "public." + _quote_identifier(value)


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_bool(value: Any) -> bool | None:
    return bool(value) if value is not None else None


def _normalize_optional_ts(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value)
    return None if text_value == "-infinity" else text_value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
