"""Restore hot-swap preflight and command planning."""

from __future__ import annotations

import re
from collections.abc import Collection
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from kraddr.geo.dto.admin import RestoreHotSwapPlan, RestoreHotSwapPlanRequest
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.settings import Settings

_DATABASE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_DEFAULT_MAINTENANCE_DATABASE = "postgres"


async def inspect_restore_hot_swap_plan(
    settings: Settings,
    req: RestoreHotSwapPlanRequest,
) -> RestoreHotSwapPlan:
    """Build a hot-swap plan after checking database existence in the current cluster."""

    current_database = _current_database(settings)
    restore_database = _validate_database_identifier(req.restore_database, "restore_database")
    previous_alias = _resolve_previous_alias(current_database, req.previous_alias)
    maintenance_database = _maintenance_database(current_database)
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
    )


def build_restore_hot_swap_plan(
    settings: Settings,
    req: RestoreHotSwapPlanRequest,
    *,
    existing_databases: Collection[str] = (),
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
    maintenance_database = _maintenance_database(current_database)
    blockers = _hot_swap_blockers(
        current_database=current_database,
        restore_database=restore_database,
        previous_alias=previous_alias,
        existing_databases=set(existing_databases),
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
    existing_databases: set[str],
) -> list[str]:
    blockers: list[str] = []
    if current_database == restore_database:
        blockers.append("restore_database must differ from current database")
    if current_database == previous_alias or restore_database == previous_alias:
        blockers.append("previous_alias must differ from current and restore database")
    if existing_databases:
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


def _maintenance_database(current_database: str) -> str:
    if current_database == _DEFAULT_MAINTENANCE_DATABASE:
        msg = "current database cannot be the maintenance database for hot-swap"
        raise InvalidInputError(msg)
    return _DEFAULT_MAINTENANCE_DATABASE


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
    alias = f"{current_database}_previous_{timestamp}"
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
