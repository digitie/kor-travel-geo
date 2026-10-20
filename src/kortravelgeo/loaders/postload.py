"""Post-load maintenance helpers."""

from __future__ import annotations

import asyncio
import logging
import time
import warnings
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.cache import GeoCacheRepository
from kortravelgeo.infra.engine import (
    MAINTENANCE_STATEMENT_TIMEOUT,
    MAINTENANCE_STATEMENT_TIMEOUT_MS,
)
from kortravelgeo.infra.publication import PublicationGuard
from kortravelgeo.infra.sql import (
    MV_SQL,
    POSTLOAD_SQL,
    REGION_RADIUS_PARTS_REFRESH_SQL,
    TEXT_SEARCH_MV_SQL,
    iter_sql_statements,
)

LOGGER = logging.getLogger(__name__)

_SET_MAINTENANCE_TIMEOUT = text(f"SET LOCAL statement_timeout = '{MAINTENANCE_STATEMENT_TIMEOUT}'")


async def resolve_text_geometry_links(
    engine: AsyncEngine,
    *,
    statement_timeout_ms: int | None = MAINTENANCE_STATEMENT_TIMEOUT_MS,
) -> None:
    """Resolve text master rows to entrance and navigation geometry rows.

    This is a post-load maintenance step, not an online lookup path. The default
    transaction-local statement timeout is therefore the maintenance ceiling
    (``MAINTENANCE_STATEMENT_TIMEOUT``, 6 h) so large two-sido or nationwide link
    updates do not inherit the 5 second API query timeout. ``0`` disables it for the
    transaction. Pass None when the caller deliberately wants to keep the current
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
    publication_guard: PublicationGuard | None = None,
) -> None:
    if strategy == "swap":
        await normalize_mv_index_names(engine)
        await rebuild_mv_next(engine)
        await rebuild_text_search_mv_next(engine)
        if publication_guard is None:
            await shadow_swap_mv(engine)
        else:
            await shadow_swap_mv(engine, publication_guard=publication_guard)
        if publication_guard is None:
            await refresh_region_radius_parts(engine)
        else:
            await refresh_region_radius_parts(engine, publication_guard=publication_guard)
        await GeoCacheRepository(engine).clear()
        return
    statement = "REFRESH MATERIALIZED VIEW"
    if concurrently:
        statement += " CONCURRENTLY"
    statement += " mv_geocode_target"
    async with engine.begin() as conn:
        # 긴 build 동안 소유 행을 잠그지 않는다. commit 직전 검증 실패는 refresh를 rollback한다.
        await conn.execute(_SET_MAINTENANCE_TIMEOUT)
        await conn.execute(text(statement))
        text_search_exists = await conn.scalar(text("SELECT to_regclass('mv_geocode_text_search')"))
        if text_search_exists is None:
            for sql in iter_sql_statements(TEXT_SEARCH_MV_SQL):
                await conn.execute(text(sql))
        else:
            text_search_statement = "REFRESH MATERIALIZED VIEW"
            if concurrently:
                text_search_statement += " CONCURRENTLY"
            text_search_statement += " mv_geocode_text_search"
            await conn.execute(text(text_search_statement))
        await conn.execute(text("ANALYZE mv_geocode_target"))
        await conn.execute(text("ANALYZE mv_geocode_text_search"))
        if publication_guard is not None:
            await publication_guard(conn)
    if publication_guard is None:
        await refresh_region_radius_parts(engine)
    else:
        await refresh_region_radius_parts(engine, publication_guard=publication_guard)
    await GeoCacheRepository(engine).clear()


#: Lock-wait cap for the ``region_radius_parts`` swap (G-01 follow-up a/a2). The rebuild fills
#: ``region_radius_parts_next`` without touching the live table, then swaps it in under ACCESS
#: EXCLUSIVE. While that request waits behind a long reader (e.g. ``pg_dump``) every new radius
#: lookup queues behind it, so the lock is taken explicitly with a short wait; a lost wait rolls
#: back to a savepoint (the built ``_next`` is kept) and retries until a budget long enough to
#: outlast a backup. Only that lock wait is retried — any other error propagates.
REGION_RADIUS_LOCK_TIMEOUT = "2s"
REGION_RADIUS_LOCK_RETRY_DELAY_S = 30.0
REGION_RADIUS_LOCK_BUDGET_S = 3600.0
_LOCK_NOT_AVAILABLE = "55P03"
_RADIUS_LIVE = "region_radius_parts"
_RADIUS_NEXT = "region_radius_parts_next"
#: Serializes rebuilds: two concurrent rebuilds would otherwise race on the ``_next`` name.
_RADIUS_REBUILD_LOCK_KEY = "kortravelgeo:region_radius_parts:rebuild"

#: The swap drops the live table, so whatever hangs off it and is not recreated by the build SQL
#: would be lost silently (grants, owner, triggers, RLS) or block the DROP (views, foreign keys —
#: any normal dependency). Checked under ACCESS EXCLUSIVE, so nothing can change in between.
_RADIUS_SWAP_CHECK_SQL = text(
    """
SELECT l.relowner = n.relowner AS same_owner,
       l.relacl IS NOT DISTINCT FROM n.relacl AS same_grants,
       NOT (l.relhastriggers OR l.relrowsecurity) AS no_triggers_or_rls,
       NOT EXISTS (
         SELECT 1 FROM pg_depend d
          WHERE d.refclassid = 'pg_class'::regclass
            AND d.refobjid = l.oid
            AND d.deptype = 'n'
       ) AS no_dependents
  FROM pg_class l, pg_class n
 WHERE l.oid = to_regclass('region_radius_parts')
   AND n.oid = to_regclass('region_radius_parts_next')
"""
)


class _RegionRadiusLockBusyError(Exception):
    def __init__(self, cause: DBAPIError) -> None:
        super().__init__(str(cause))
        self.cause = cause


def build_region_radius_parts_next_sql() -> str:
    """``REGION_RADIUS_PARTS_REFRESH_SQL`` retargeted at ``region_radius_parts_next``.

    One definition serves both the migration (in place, first build) and the swap. Index and
    constraint names follow the table name (``idx_region_radius_parts_next_*``,
    ``region_radius_parts_next_pkey``) and the swap renames them back.
    """
    sql = REGION_RADIUS_PARTS_REFRESH_SQL
    truncate = f"TRUNCATE TABLE {_RADIUS_LIVE};"
    if sql.count(truncate) != 1:
        raise RuntimeError("REGION_RADIUS_PARTS_REFRESH_SQL no longer has exactly one TRUNCATE")
    sql = sql.replace(truncate, "").replace(_RADIUS_LIVE, _RADIUS_NEXT)
    return f"DROP TABLE IF EXISTS {_RADIUS_NEXT};\n{sql}"


async def _lock_region_radius_parts(
    conn: Any, *, deadline: float | None = None, last_lock_error: DBAPIError | None = None
) -> bool:
    """Take ACCESS EXCLUSIVE on the live table with a short wait. False: there is none yet."""
    if await conn.scalar(text("SELECT to_regclass('region_radius_parts')")) is None:
        return False  # first build: nobody can be reading it
    original_timeout = await conn.scalar(text("SELECT current_setting('lock_timeout')"))
    await conn.execute(text(f"SET LOCAL lock_timeout = '{REGION_RADIUS_LOCK_TIMEOUT}'"))
    # relation 조회와 GUC 준비 await도 예산을 소비하므로 실제 LOCK 직전에 검사한다.
    if last_lock_error is not None and deadline is not None and time.monotonic() >= deadline:
        raise last_lock_error from None
    try:
        await conn.execute(text("LOCK TABLE region_radius_parts IN ACCESS EXCLUSIVE MODE"))
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == _LOCK_NOT_AVAILABLE:
            raise _RegionRadiusLockBusyError(exc) from exc
        raise
    await conn.execute(
        text("SELECT set_config('lock_timeout', :lock_timeout, true)"),
        {"lock_timeout": original_timeout},
    )
    return True


async def _swap_region_radius_parts(conn: Any, *, live_exists: bool) -> None:
    """Replace the live table with ``_next``. The caller holds ACCESS EXCLUSIVE on it."""
    if live_exists:
        row = (await conn.execute(_RADIUS_SWAP_CHECK_SQL)).mappings().one()
        lost = sorted(name for name, ok in row.items() if not ok)
        if lost:
            raise RuntimeError(
                f"region_radius_parts swap refused ({', '.join(lost)}): the live table carries "
                "state the rebuild does not recreate — handle it in the build SQL first"
            )
        # No CASCADE: an unexpected dependent makes this fail (and roll back), not vanish.
        await conn.execute(text(f"DROP TABLE {_RADIUS_LIVE}"))
    await conn.execute(text(f"ALTER TABLE {_RADIUS_NEXT} RENAME TO {_RADIUS_LIVE}"))
    # Constraints first: renaming the primary key also renames its index.
    constraints = await conn.execute(
        text(
            "SELECT conname FROM pg_constraint"
            " WHERE conrelid = 'region_radius_parts'::regclass AND conname LIKE :pattern"
        ),
        {"pattern": f"{_RADIUS_NEXT}%"},
    )
    for name in [str(r[0]) for r in constraints]:
        target = name.replace(_RADIUS_NEXT, _RADIUS_LIVE, 1)
        await conn.execute(
            text(
                f"ALTER TABLE {_RADIUS_LIVE} RENAME CONSTRAINT "
                f"{_quote_identifier(name)} TO {_quote_identifier(target)}"
            )
        )
    indexes = await conn.execute(
        text(
            "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid"
            " WHERE i.indrelid = 'region_radius_parts'::regclass AND c.relname LIKE :pattern"
        ),
        {"pattern": f"%{_RADIUS_NEXT}%"},
    )
    for name in [str(r[0]) for r in indexes]:
        target = name.replace(_RADIUS_NEXT, _RADIUS_LIVE, 1)
        await conn.execute(
            text(f"ALTER INDEX {_quote_identifier(name)} RENAME TO {_quote_identifier(target)}")
        )


async def refresh_region_radius_parts(
    engine: AsyncEngine, *, publication_guard: PublicationGuard | None = None
) -> None:
    """Rebuild subdivided administrative-region geometry for radius lookup.

    One transaction: build ``region_radius_parts_next`` (the long part — the live table is not
    touched, readers keep going), then take ACCESS EXCLUSIVE on the live table with a short wait
    (``REGION_RADIUS_LOCK_TIMEOUT``, retried from a savepoint for up to
    ``REGION_RADIUS_LOCK_BUDGET_S``), drop it, rename ``_next`` in and commit. The exclusive hold
    is the swap only. A failure anywhere rolls the whole transaction back: the live table is
    unchanged and no ``_next`` was ever committed, so a re-run starts clean and ``pg_dump`` never
    sees a half state.
    """
    async with engine.begin() as conn:
        await conn.execute(_SET_MAINTENANCE_TIMEOUT)
        await conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": _RADIUS_REBUILD_LOCK_KEY},
        )
        for sql in iter_sql_statements(build_region_radius_parts_next_sql()):
            await conn.execute(text(sql))
        deadline = time.monotonic() + REGION_RADIUS_LOCK_BUDGET_S
        attempt = 0
        last_lock_error: DBAPIError | None = None
        while True:
            # sleep 재개가 늦어졌다면 새 LOCK 시도 전에 예산을 다시 확인한다.
            if last_lock_error is not None and time.monotonic() >= deadline:
                raise last_lock_error from None
            attempt += 1
            try:
                async with conn.begin_nested():
                    live_exists = await _lock_region_radius_parts(
                        conn, deadline=deadline, last_lock_error=last_lock_error
                    )
                    await _swap_region_radius_parts(conn, live_exists=live_exists)
                break
            except _RegionRadiusLockBusyError as busy:
                if time.monotonic() + REGION_RADIUS_LOCK_RETRY_DELAY_S > deadline:
                    raise busy.cause from None
                LOGGER.warning(
                    "region_radius_parts lock 대기가 %s를 넘었다(시도 %d) — %.0f s 뒤 재시도",
                    REGION_RADIUS_LOCK_TIMEOUT,
                    attempt,
                    REGION_RADIUS_LOCK_RETRY_DELAY_S,
                )
                last_lock_error = busy.cause
                await asyncio.sleep(REGION_RADIUS_LOCK_RETRY_DELAY_S)
        # serving 테이블도 별도 commit을 갖는다. 긴 재생성 뒤 소유권을 다시 검증한다.
        if publication_guard is not None:
            await publication_guard(conn)


async def rebuild_mv(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(_SET_MAINTENANCE_TIMEOUT)
        await conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search"))
        for sql in iter_sql_statements(MV_SQL):
            await conn.execute(text(sql))
        for sql in iter_sql_statements(TEXT_SEARCH_MV_SQL):
            await conn.execute(text(sql))


async def shadow_swap_mv(
    engine: AsyncEngine, *, publication_guard: PublicationGuard | None = None
) -> None:
    async with engine.begin() as conn:
        if publication_guard is not None:
            await publication_guard(conn)
        await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
        current_mv = await conn.scalar(text("SELECT to_regclass('mv_geocode_target')"))
        current_text_search_mv = await conn.scalar(
            text("SELECT to_regclass('mv_geocode_text_search')")
        )
        await conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search_old"))
        if current_mv is not None:
            await conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_target_old"))
        if current_text_search_mv is not None:
            await conn.execute(
                text(
                    "ALTER MATERIALIZED VIEW mv_geocode_text_search "
                    "RENAME TO mv_geocode_text_search_old"
                )
            )
        if current_mv is not None:
            await conn.execute(
                text("ALTER MATERIALIZED VIEW mv_geocode_target RENAME TO mv_geocode_target_old")
            )
        await conn.execute(
            text("ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target")
        )
        await conn.execute(
            text(
                "ALTER MATERIALIZED VIEW mv_geocode_text_search_next "
                "RENAME TO mv_geocode_text_search"
            )
        )
        if current_text_search_mv is not None:
            await conn.execute(text("DROP MATERIALIZED VIEW mv_geocode_text_search_old"))
        if current_mv is not None:
            await conn.execute(text("DROP MATERIALIZED VIEW mv_geocode_target_old"))
        await rename_mv_next_indexes_for_conn(conn)
        if publication_guard is not None:
            await publication_guard(conn)
    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
        await conn.execute(_SET_MAINTENANCE_TIMEOUT)
        await conn.execute(text("ANALYZE mv_geocode_target"))
        await conn.execute(text("ANALYZE mv_geocode_text_search"))


async def rebuild_mv_next(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(_SET_MAINTENANCE_TIMEOUT)
        for sql in iter_sql_statements(build_mv_next_sql()):
            await conn.execute(text(sql))


async def rebuild_text_search_mv_next(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(_SET_MAINTENANCE_TIMEOUT)
        for sql in iter_sql_statements(build_text_search_mv_next_sql()):
            await conn.execute(text(sql))


def build_mv_next_sql() -> str:
    sql = MV_SQL.replace("mv_geocode_target", "mv_geocode_target_next")
    sql = sql.replace("CREATE UNIQUE INDEX idx_mv_", "CREATE UNIQUE INDEX idx_mv_next_")
    sql = sql.replace("CREATE INDEX idx_mv_", "CREATE INDEX idx_mv_next_")
    return sql


def build_text_search_mv_next_sql() -> str:
    sql = TEXT_SEARCH_MV_SQL.replace("mv_geocode_text_search", "mv_geocode_text_search_next")
    sql = sql.replace("mv_geocode_target", "mv_geocode_target_next")
    sql = sql.replace(
        "CREATE UNIQUE INDEX idx_mv_text_search_",
        "CREATE UNIQUE INDEX idx_mv_next_text_search_",
    )
    sql = sql.replace("CREATE INDEX idx_mv_text_search_", "CREATE INDEX idx_mv_next_text_search_")
    return sql


async def normalize_mv_index_names(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await rename_mv_next_indexes_for_conn(conn)


async def rename_mv_next_indexes_for_conn(conn: Any) -> None:
    """Rename shadow MV indexes on an existing SQLAlchemy connection.

    The shadow swap path needs this helper inside the same transaction that
    renames `mv_geocode_target_next` to the live MV. Keep this public so
    benchmark/maintenance scripts do not need to import underscore-prefixed
    internals just to share the production index rename logic.
    """
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


async def _rename_mv_next_indexes(conn: Any) -> None:
    await rename_mv_next_indexes_for_conn(conn)


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
   AND t.relname IN (
       'mv_geocode_target',
       'mv_geocode_target_next',
       'mv_geocode_text_search',
       'mv_geocode_text_search_next'
   )
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
