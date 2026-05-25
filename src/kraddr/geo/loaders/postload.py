"""Post-load maintenance helpers."""

from __future__ import annotations

import logging
import warnings
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.infra.sql import MV_SQL, POSTLOAD_SQL, iter_sql_statements

LOGGER = logging.getLogger(__name__)


async def resolve_text_geometry_links(
    engine: AsyncEngine,
    *,
    statement_timeout_ms: int | None = 1_800_000,
) -> None:
    """Resolve text master rows to entrance and navigation geometry rows.

    This is a post-load maintenance step, not an online lookup path. The default
    transaction-local statement timeout is therefore 30 minutes so large
    two-sido or nationwide link updates do not inherit the 5 second API query
    timeout. Pass None when the caller deliberately wants to keep the current
    connection/session timeout unchanged.
    """
    async with engine.begin() as conn:
        if statement_timeout_ms is not None:
            await conn.execute(
                text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
                {"timeout_ms": str(statement_timeout_ms)},
            )
        for sql in iter_sql_statements(POSTLOAD_SQL):
            await conn.execute(text(sql))


async def refresh_mv(
    engine: AsyncEngine,
    *,
    concurrently: bool = True,
    strategy: Literal["concurrent", "swap"] = "concurrent",
) -> None:
    if strategy == "swap":
        await normalize_mv_index_names(engine)
        await rebuild_mv_next(engine)
        await shadow_swap_mv(engine)
        return
    statement = "REFRESH MATERIALIZED VIEW"
    if concurrently:
        statement += " CONCURRENTLY"
    statement += " mv_geocode_target"
    async with engine.begin() as conn:
        await conn.execute(text(statement))
        await conn.execute(text("ANALYZE mv_geocode_target"))


async def rebuild_mv(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in iter_sql_statements(MV_SQL):
            await conn.execute(text(sql))


async def shadow_swap_mv(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
        current_mv = await conn.scalar(text("SELECT to_regclass('mv_geocode_target')"))
        if current_mv is not None:
            await conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target_old"))
            await conn.execute(
                text("ALTER MATERIALIZED VIEW mv_geocode_target RENAME TO mv_geocode_target_old")
            )
        await conn.execute(
            text("ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target")
        )
        if current_mv is not None:
            await conn.execute(text("DROP MATERIALIZED VIEW mv_geocode_target_old"))
        await _rename_mv_next_indexes(conn)
    async with engine.begin() as conn:
        await conn.execute(text("ANALYZE mv_geocode_target"))


async def rebuild_mv_next(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in iter_sql_statements(build_mv_next_sql()):
            await conn.execute(text(sql))


def build_mv_next_sql() -> str:
    sql = MV_SQL.replace("mv_geocode_target", "mv_geocode_target_next")
    sql = sql.replace("CREATE UNIQUE INDEX idx_mv_", "CREATE UNIQUE INDEX idx_mv_next_")
    sql = sql.replace("CREATE INDEX idx_mv_", "CREATE INDEX idx_mv_next_")
    return sql


async def normalize_mv_index_names(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await _rename_mv_next_indexes(conn)


async def _rename_mv_next_indexes(conn: Any) -> None:
    for next_name, target_name in await _mv_next_index_renames(conn):
        target_exists = await conn.scalar(
            text("SELECT to_regclass(:index_name)"),
            {"index_name": target_name},
        )
        if target_exists is not None:
            message = (
                f"stale MV index {target_name} already exists; dropping {next_name} "
                "to avoid the next shadow rebuild name collision"
            )
            LOGGER.warning(message)
            warnings.warn(message, RuntimeWarning, stacklevel=2)
            await conn.execute(text(f"DROP INDEX {_quote_identifier(next_name)}"))
            continue
        await conn.execute(
            text(
                f"ALTER INDEX {_quote_identifier(next_name)} "
                f"RENAME TO {_quote_identifier(target_name)}"
            )
        )


async def _mv_next_index_renames(conn: Any) -> tuple[tuple[str, str], ...]:
    result = await conn.execute(
        text(
            """
SELECT i.relname AS index_name
  FROM pg_class i
  JOIN pg_index ix ON ix.indexrelid = i.oid
  JOIN pg_class t ON t.oid = ix.indrelid
  JOIN pg_namespace n ON n.oid = i.relnamespace
 WHERE n.nspname = current_schema()
   AND t.relname IN ('mv_geocode_target', 'mv_geocode_target_next')
   AND i.relname LIKE 'idx_mv_next_%'
 ORDER BY i.relname
"""
        )
    )
    names = tuple(str(row[0]) for row in result)
    return tuple((name, _mv_target_index_name(name)) for name in names)


def _mv_target_index_name(next_name: str) -> str:
    suffix = next_name.removeprefix("idx_mv_next_")
    suffix = suffix.replace("geocode_target_next", "geocode_target")
    return f"idx_mv_{suffix}"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
