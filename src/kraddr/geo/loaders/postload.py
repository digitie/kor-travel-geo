"""Post-load maintenance helpers."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.infra.sql import MV_SQL, POSTLOAD_SQL, iter_sql_statements


async def resolve_text_geometry_links(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in iter_sql_statements(POSTLOAD_SQL):
            await conn.execute(text(sql))


async def refresh_mv(engine: AsyncEngine, *, concurrently: bool = True) -> None:
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
        await conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target_old"))
        await conn.execute(
            text("ALTER MATERIALIZED VIEW mv_geocode_target RENAME TO mv_geocode_target_old")
        )
        await conn.execute(
            text("ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target")
        )
        await conn.execute(text("DROP MATERIALIZED VIEW mv_geocode_target_old"))
