"""Restore hot-swap preflight, command planning, and execution (T-058 plan, T-241 execute)."""

from __future__ import annotations

import logging
import re
from collections.abc import Collection, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from kortravelgeo.dto.admin import (
    RestoreHotSwapExecuteRequest,
    RestoreHotSwapPlan,
    RestoreHotSwapPlanRequest,
    RestoreHotSwapResult,
)
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.backup import (
    _query_cluster_versions_for_dsn,
    restore_version_mismatch_blocker,
    smoke_test_restore,
)
from kortravelgeo.infra.concurrency import (
    AdvisoryLockKey,
    AdvisoryLockNamespace,
    cross_process_lock,
)
from kortravelgeo.settings import Settings

_LOGGER = logging.getLogger(__name__)
_DATABASE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_MAX_DATABASE_IDENTIFIER_LENGTH = 63


async def inspect_restore_hot_swap_plan(
    settings: Settings,
    req: RestoreHotSwapPlanRequest,
) -> RestoreHotSwapPlan:
    """Build a hot-swap plan after checking database existence in the current cluster."""

    current_database = _current_database(settings)
    restore_database = _validate_database_identifier(req.restore_database, "restore_database")
    generated_at = datetime.now(UTC)
    previous_alias = _resolve_previous_alias(
        current_database,
        req.previous_alias,
        generated_at=generated_at,
    )
    maintenance_database = _maintenance_database(current_database, req.maintenance_database)
    maintenance_dsn = _dsn_for_database(settings.pg_dsn, maintenance_database)

    engine = create_async_engine(maintenance_dsn)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
SELECT datname
  FROM pg_database
 WHERE datname IN (:current_database, :restore_database, :previous_alias)
"""
                    ),
                    {
                        "current_database": current_database,
                        "restore_database": restore_database,
                        "previous_alias": previous_alias,
                    },
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    return build_restore_hot_swap_plan(
        settings,
        req,
        existing_databases={str(row) for row in rows},
        generated_at=generated_at,
    )


def build_restore_hot_swap_plan(
    settings: Settings,
    req: RestoreHotSwapPlanRequest,
    *,
    existing_databases: Collection[str] | None = None,
    generated_at: datetime | None = None,
) -> RestoreHotSwapPlan:
    """Build a deterministic restore hot-swap plan.

    The plan deliberately does not execute `ALTER DATABASE`. It exists so UI/CLI
    callers can review typed confirmation, blockers, rollback alias, and exact
    SQL before opening a maintenance window.
    """

    current_database = _current_database(settings)
    restore_database = _validate_database_identifier(req.restore_database, "restore_database")
    previous_alias = _resolve_previous_alias(
        current_database,
        req.previous_alias,
        generated_at=generated_at,
    )
    maintenance_database = _maintenance_database(current_database, req.maintenance_database)
    blockers = _hot_swap_blockers(
        current_database=current_database,
        restore_database=restore_database,
        previous_alias=previous_alias,
        existing_databases=set(existing_databases) if existing_databases is not None else None,
    )
    sql = (
        _terminate_backends_sql(current_database),
        _terminate_backends_sql(restore_database),
        _rename_database_sql(current_database, previous_alias),
        _rename_database_sql(restore_database, current_database),
    )
    return RestoreHotSwapPlan(
        current_database=current_database,
        restore_database=restore_database,
        previous_alias=previous_alias,
        maintenance_database=maintenance_database,
        typed_confirmation=hot_swap_confirmation(current_database, restore_database),
        rollback_confirmation=rollback_confirmation(current_database, previous_alias),
        previous_alias_retention_days=req.previous_alias_retention_days,
        can_execute=not blockers,
        blockers=tuple(blockers),
        steps=(
            f"`{maintenance_database}` DB에 연결한 maintenance session을 연다.",
            "`ops.maintenance_windows(kind='restore')` active window와 "
            "typed confirmation을 확인한다.",
            f"`{current_database}`와 `{restore_database}`의 기존 connection을 종료한다.",
            f"`{current_database}`를 `{previous_alias}`로 rename한다.",
            f"`{restore_database}`를 `{current_database}`로 rename한다.",
            "application engine pool을 dispose/refresh하고 post-swap smoke test를 실행한다.",
            "`ops.serving_releases`와 `ops.audit_events`에 hot-swap 결과를 기록한다.",
        ),
        sql=sql,
    )


def hot_swap_confirmation(current_database: str, restore_database: str) -> str:
    return f"HOT_SWAP {current_database} FROM {restore_database}"


def rollback_confirmation(current_database: str, previous_alias: str) -> str:
    return f"ROLLBACK_HOT_SWAP {current_database} FROM {previous_alias}"


def _hot_swap_blockers(
    *,
    current_database: str,
    restore_database: str,
    previous_alias: str,
    existing_databases: set[str] | None,
) -> list[str]:
    blockers: list[str] = []
    if current_database == restore_database:
        blockers.append("restore_database must differ from current database")
    if current_database == previous_alias or restore_database == previous_alias:
        blockers.append("previous_alias must differ from current and restore database")
    if existing_databases is not None:
        if current_database not in existing_databases:
            blockers.append(f"current database does not exist in cluster: {current_database}")
        if restore_database not in existing_databases:
            blockers.append(f"restore database does not exist in cluster: {restore_database}")
        if previous_alias in existing_databases:
            blockers.append(f"previous alias already exists in cluster: {previous_alias}")
    return blockers


def _current_database(settings: Settings) -> str:
    current_database = make_url(settings.pg_dsn).database
    if current_database is None:
        msg = "current database name could not be resolved"
        raise InvalidInputError(msg)
    return _validate_database_identifier(current_database, "current_database")


def _maintenance_database(current_database: str, maintenance_database: str) -> str:
    validated = _validate_database_identifier(maintenance_database, "maintenance_database")
    if current_database == validated:
        msg = "current database cannot be the maintenance database for hot-swap"
        raise InvalidInputError(msg)
    return validated


def _dsn_for_database(dsn: str, database: str) -> str:
    return make_url(dsn).set(database=database).render_as_string(hide_password=False)


def _resolve_previous_alias(
    current_database: str,
    previous_alias: str | None,
    *,
    generated_at: datetime | None = None,
) -> str:
    if previous_alias is not None:
        return _validate_database_identifier(previous_alias, "previous_alias")
    timestamp = (generated_at or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    suffix = f"_previous_{timestamp}"
    max_prefix_length = _MAX_DATABASE_IDENTIFIER_LENGTH - len(suffix)
    alias = f"{current_database[:max_prefix_length]}{suffix}"
    return _validate_database_identifier(alias, "previous_alias")


def _validate_database_identifier(value: str, field_name: str) -> str:
    if not _DATABASE_IDENTIFIER_RE.fullmatch(value):
        msg = f"{field_name} must match {_DATABASE_IDENTIFIER_RE.pattern}"
        raise InvalidInputError(msg)
    return value


def _quote_ident(value: str) -> str:
    return f'"{_validate_database_identifier(value, "database")}"'


def _rename_database_sql(source: str, target: str) -> str:
    return f"ALTER DATABASE {_quote_ident(source)} RENAME TO {_quote_ident(target)};"


def _terminate_backends_sql(database: str) -> str:
    quoted_literal = _validate_database_identifier(database, "database").replace("'", "''")
    return (
        "SELECT pg_terminate_backend(pid)\n"
        "  FROM pg_stat_activity\n"
        f" WHERE datname = '{quoted_literal}'\n"
        "   AND pid <> pg_backend_pid();"
    )


# --- T-241 execution -------------------------------------------------------


def validate_hot_swap_confirmation(plan: RestoreHotSwapPlan, typed_confirmation: str) -> None:
    """Hard-fail unless the typed confirmation matches the plan exactly (acceptance gate)."""
    if typed_confirmation != plan.typed_confirmation:
        msg = f"typed_confirmation must be exactly '{plan.typed_confirmation}'"
        raise InvalidInputError(msg)


def build_hot_swap_swap_sql(
    current_database: str, restore_database: str, previous_alias: str
) -> tuple[str, ...]:
    """Forward swap: terminate both, rename current→previous, then restore→current."""
    return (
        _terminate_backends_sql(current_database),
        _terminate_backends_sql(restore_database),
        _rename_database_sql(current_database, previous_alias),
        _rename_database_sql(restore_database, current_database),
    )


def build_hot_swap_rollback_sql(
    current_database: str, restore_database: str, previous_alias: str
) -> tuple[str, ...]:
    """Reverse a completed swap: current(restored)→restore, previous(old)→current.

    Pure inverse of :func:`build_hot_swap_swap_sql`; used to auto-rollback after a failed
    post-swap smoke test so the original serving DB is restored under its own name.
    """
    return (
        _terminate_backends_sql(current_database),
        _terminate_backends_sql(previous_alias),
        _rename_database_sql(current_database, restore_database),
        _rename_database_sql(previous_alias, current_database),
    )


async def _run_rename_steps(engine: AsyncEngine, steps: tuple[str, ...]) -> None:
    async with engine.connect() as conn:
        for stmt in steps:
            await conn.execute(text(stmt))


async def _execute_swap_with_undo(
    engine: AsyncEngine, *, current: str, restore: str, previous: str
) -> None:
    """Run the forward rename; if the second rename fails, undo the first so no DB vanishes.

    The dangerous partial state is "current renamed to previous, restore not yet renamed to
    current" → the serving name would be missing. On failure we rename previous back to
    current (best-effort) before re-raising.
    """
    renamed_current_to_previous = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text(_terminate_backends_sql(current)))
            await conn.execute(text(_terminate_backends_sql(restore)))
            await conn.execute(text(_rename_database_sql(current, previous)))
            renamed_current_to_previous = True
            await conn.execute(text(_rename_database_sql(restore, current)))
    except Exception:
        if renamed_current_to_previous:
            with suppress(Exception):
                async with engine.connect() as undo_conn:
                    await undo_conn.execute(text(_rename_database_sql(previous, current)))
        raise


async def _active_serving_release_id(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text(
                """
SELECT serving_release_id::text
  FROM ops.serving_releases
 WHERE state = 'active'
 ORDER BY activated_at DESC NULLS LAST, created_at DESC
 LIMIT 1
"""
            )
        )
    return str(value) if value is not None else None


async def execute_restore_hot_swap(
    engine: AsyncEngine,
    settings: Settings,
    req: RestoreHotSwapExecuteRequest,
    *,
    actor: str | None = None,
    audit_meta: Mapping[str, Any] | None = None,
) -> RestoreHotSwapResult:
    """Execute the ADR-036 rename hot-swap (T-241; live execution, integration-tested T-246).

    Guard order (all BEFORE any rename): plan blockers → exact typed confirmation → active
    ``restore`` maintenance window → PG/PostGIS version compatibility → ``HOT_SWAP`` advisory
    lock (concurrent second call fails fast). Then it renames under the lock with partial-undo,
    refreshes the engine pool, runs a post-swap smoke test, and **auto-rolls-back on smoke
    failure**. Records 4 audit kinds (started/succeeded/failed/rolled_back) and an active
    ``ops.serving_releases`` row with ``previous_release_id`` lineage.
    """
    repo = AdminRepository(engine)
    plan = await inspect_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(
            restore_database=req.restore_database,
            previous_alias=req.previous_alias,
            previous_alias_retention_days=req.previous_alias_retention_days,
            maintenance_database=req.maintenance_database,
        ),
    )
    if not plan.can_execute:
        msg = "hot-swap blocked: " + "; ".join(plan.blockers)
        raise InvalidInputError(msg)
    validate_hot_swap_confirmation(plan, req.typed_confirmation)

    window = await repo.require_active_maintenance_window(
        kind="restore", confirmation=req.typed_confirmation
    )

    # Same cluster, so PostgreSQL major is identical; PostGIS major.minor can differ between
    # the current and restore databases. Hard-fail on a major mismatch unless overridden.
    current_pg, current_gis = await _query_cluster_versions_for_dsn(settings.pg_dsn)
    restore_pg, restore_gis = await _query_cluster_versions_for_dsn(
        _dsn_for_database(settings.pg_dsn, plan.restore_database)
    )
    version_block = restore_version_mismatch_blocker(
        manifest_postgres_version=restore_pg,
        manifest_postgis_version=restore_gis,
        target_postgres_version=current_pg,
        target_postgis_version=current_gis,
        allow_mismatch=req.allow_version_mismatch,
    )
    if version_block is not None:
        msg = (
            "hot-swap version mismatch (set allow_version_mismatch to override): "
            f"{version_block}"
        )
        raise InvalidInputError(msg)

    pre_swap_release_id = await _active_serving_release_id(engine)
    current = plan.current_database
    restore = plan.restore_database
    previous = plan.previous_alias
    meta = dict(audit_meta or {})

    async def audit(
        action: str, outcome: str, payload: dict[str, Any], *, resource_id: str | None
    ) -> None:
        # Best-effort: never let an audit hiccup break (or un-break) a live swap.
        try:
            await AdminRepository(engine).record_audit_event(
                action=action,
                actor_type="system",
                actor_id=actor,
                outcome=outcome,
                payload=payload,
                resource_type="serving_release",
                resource_id=resource_id,
                **meta,
            )
        except Exception:
            _LOGGER.warning("hot-swap audit %s/%s failed", action, outcome, exc_info=True)

    maintenance_dsn = _dsn_for_database(settings.pg_dsn, plan.maintenance_database)
    maintenance_engine = create_async_engine(maintenance_dsn, isolation_level="AUTOCOMMIT")
    lock_key = AdvisoryLockKey.global_key(AdvisoryLockNamespace.HOT_SWAP)
    base_payload = {
        "current_database": current,
        "restore_database": restore,
        "previous_alias": previous,
        "previous_release_id": pre_swap_release_id,
        "maintenance_window_id": window.maintenance_window_id,
    }
    try:
        # cross_process_lock raises ConcurrentExecutionError (409) if another hot-swap holds
        # the lock → the concurrent second call fails fast without touching any database.
        async with cross_process_lock(maintenance_engine, lock_key):
            await audit("serving_release.hot_swap", "started", dict(base_payload), resource_id=None)
            try:
                await _execute_swap_with_undo(
                    maintenance_engine, current=current, restore=restore, previous=previous
                )
            except Exception as exc:
                await audit(
                    "serving_release.hot_swap",
                    "failed",
                    {**base_payload, "reason": f"rename failed (undone): {exc}"},
                    resource_id=None,
                )
                msg = f"hot-swap rename failed and was undone: {exc}"
                raise InvalidInputError(msg) from exc

            # Refresh the app pool so connections reconnect to the swapped DB under its name.
            await engine.dispose()

            smoke_ok: bool | None = None
            if req.run_smoke_test:
                try:
                    await smoke_test_restore(settings.pg_dsn)
                    smoke_ok = True
                except Exception as exc:
                    await audit(
                        "serving_release.hot_swap",
                        "failed",
                        {**base_payload, "reason": f"smoke failed: {exc}"},
                        resource_id=None,
                    )
                    await _run_rename_steps(
                        maintenance_engine,
                        build_hot_swap_rollback_sql(current, restore, previous),
                    )
                    await engine.dispose()
                    await audit(
                        "serving_release.hot_swap_rollback",
                        "succeeded",
                        {**base_payload, "reason": f"smoke failed: {exc}"},
                        resource_id=None,
                    )
                    return RestoreHotSwapResult(
                        swapped=False,
                        rolled_back=True,
                        smoke_ok=False,
                        current_database=current,
                        restore_database=restore,
                        previous_alias=previous,
                        rollback_confirmation=plan.rollback_confirmation,
                        message=f"post-swap smoke test failed; rolled back: {exc}",
                    )

            release = await repo.record_hot_swap_release(
                current_database=current,
                restore_database=restore,
                previous_alias=previous,
                pre_swap_release_id=pre_swap_release_id,
                maintenance_window_id=window.maintenance_window_id,
            )
            await audit(
                "serving_release.hot_swap",
                "succeeded",
                {
                    **base_payload,
                    "serving_release_id": release.serving_release_id,
                    "smoke_ok": smoke_ok,
                },
                resource_id=release.serving_release_id,
            )
            return RestoreHotSwapResult(
                swapped=True,
                rolled_back=False,
                smoke_ok=smoke_ok,
                current_database=current,
                restore_database=restore,
                previous_alias=previous,
                serving_release_id=release.serving_release_id,
                previous_release_id=pre_swap_release_id,
                rollback_confirmation=plan.rollback_confirmation,
                message="hot-swap completed",
            )
    finally:
        await maintenance_engine.dispose()
