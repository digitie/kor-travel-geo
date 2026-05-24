"""Post-load maintenance helpers."""

from __future__ import annotations

import warnings
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from kraddr.geo.infra.sql import MV_SQL, POSTLOAD_SQL, iter_sql_statements

MV_NEXT_INDEX_RENAMES: tuple[tuple[str, str], ...] = (
    ("idx_mv_next_geocode_target_next_pk", "idx_mv_geocode_target_pk"),
    ("idx_mv_next_road", "idx_mv_road"),
    ("idx_mv_next_jibun", "idx_mv_jibun"),
    ("idx_mv_next_rn_trgm", "idx_mv_rn_trgm"),
    ("idx_mv_next_buld_nm_trgm", "idx_mv_buld_nm_trgm"),
    ("idx_mv_next_geom5179", "idx_mv_geom5179"),
    ("idx_mv_next_geom4326", "idx_mv_geom4326"),
    ("idx_mv_next_pt_source", "idx_mv_pt_source"),
)


async def resolve_text_geometry_links(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
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
        await conn.execute(text("ANALYZE mv_geocode_target"))


async def rebuild_mv_next(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        for sql in iter_sql_statements(_mv_next_sql()):
            await conn.execute(text(sql))


def _mv_next_sql() -> str:
    sql = MV_SQL.replace("mv_geocode_target", "mv_geocode_target_next")
    sql = sql.replace("CREATE UNIQUE INDEX idx_mv_", "CREATE UNIQUE INDEX idx_mv_next_")
    sql = sql.replace("CREATE INDEX idx_mv_", "CREATE INDEX idx_mv_next_")
    return sql


async def normalize_mv_index_names(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await _rename_mv_next_indexes(conn)


async def _rename_mv_next_indexes(conn: Any) -> None:
    for next_name, target_name in MV_NEXT_INDEX_RENAMES:
        next_exists = await conn.scalar(
            text("SELECT to_regclass(:index_name)"),
            {"index_name": next_name},
        )
        if next_exists is None:
            continue
        target_exists = await conn.scalar(
            text("SELECT to_regclass(:index_name)"),
            {"index_name": target_name},
        )
        if target_exists is not None:
            warnings.warn(
                f"stale MV index {target_name} already exists; dropping {next_name} "
                "to avoid the next shadow rebuild name collision",
                RuntimeWarning,
                stacklevel=2,
            )
            await conn.execute(text(f"DROP INDEX {next_name}"))
            continue
        await conn.execute(text(f"ALTER INDEX {next_name} RENAME TO {target_name}"))
