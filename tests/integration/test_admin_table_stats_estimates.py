"""`/admin/tables` row counts against a real PostgreSQL (opt-in, issue #515).

These cases cannot be expressed as unit tests: they depend on how PostgreSQL's *statistics
collector* behaves, which is exactly what the bug was about. `n_live_tup` is a delta the collector
accumulates and a restore / hot-swap resets it, so on a restored database it is not a row count at
all — an untouched table reads 0, and a table that took a handful of writes reads those few
writes. `pg_class.reltuples` is no better on its own: it is -1 until something analyzes the
relation, which is the state a `pg_restore` (or this project's `--no-analyze` restore) leaves
behind. `AdminRepository.table_stats` therefore has to decide whether the stats entry is
*anchored* (a vacuum/analyze has been observed) before deciding which signal to trust.

Each case below kills a specific wrong implementation; see the comments inline.

Run with a disposable scratch database::

    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:12500/kor_travel_geo_test pytest \
        tests/integration/test_admin_table_stats_estimates.py
"""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text

from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings

_TABLE = "ktg_test_table_stats_probe"
_FRESH_TABLE = "ktg_test_table_stats_never_analyzed"

pytestmark = pytest.mark.longrun


def _dsn() -> str:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    return dsn


def _looks_like_disposable_test_database(database_name: str) -> bool:
    normalized = database_name.lower()
    return (
        "test" in normalized
        or normalized.startswith("kor_travel_geo_t")
        or normalized.startswith("tmp_")
    )


async def _require_disposable(engine) -> None:
    """Refuse to run against anything that might be a real database.

    This test creates tables and resets statistics counters. Even though the reset below is
    scoped to a single relation, `KTG_TEST_PG_DSN` is routinely pointed at a working database in
    this repo, so mirror the guard the other opt-in PostgreSQL tests use.
    """
    async with engine.connect() as conn:
        database_name = await conn.scalar(text("SELECT current_database()"))
        version_num = int(await conn.scalar(text("SHOW server_version_num")))
    if database_name is None or not _looks_like_disposable_test_database(str(database_name)):
        pytest.skip(
            "KTG_TEST_PG_DSN must point to a disposable test database whose name includes "
            f"'test' or starts with 'kor_travel_geo_t'; got {database_name!r}"
        )
    if version_num < 150000:
        pytest.skip(f"pg_stat_force_next_flush() requires PostgreSQL 15+; got {version_num}")


async def _flush_stats(engine) -> None:
    """Make the collector's pending deltas visible to `pg_stat_user_tables`.

    Must run AFTER the DML transaction commits: a backend reports its pending table stats at
    commit, so flushing inside the same transaction publishes nothing and the assertions below
    would read stale counters (and quietly pass against a broken query).
    """
    async with engine.begin() as conn:
        await conn.execute(text("SELECT pg_stat_force_next_flush()"))
    # The collector batches within PGSTAT_MIN_INTERVAL; give it room so successive DML in one
    # test is not coalesced into a single (misleading) delta.
    await asyncio.sleep(1.5)


async def _raw_stats(engine, table: str) -> tuple[int, float, bool]:
    """The raw signals, asserted on directly so a broken fixture fails loudly."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
SELECT s.n_live_tup,
       c.reltuples,
       COALESCE(s.last_vacuum, s.last_autovacuum, s.last_analyze, s.last_autoanalyze)
         IS NOT NULL AS anchored
  FROM pg_stat_user_tables s
  JOIN pg_class c ON c.oid = s.relid
 WHERE s.schemaname = 'public' AND s.relname = :t
"""
                ),
                {"t": table},
            )
        ).one()
    return int(row[0]), float(row[1]), bool(row[2])


async def _row_count(engine, table: str = _TABLE) -> tuple[int, bool]:
    stats = await AdminRepository(engine).table_stats(limit=2000)
    for stat in stats:
        if stat.table_name == table:
            return stat.row_count, stat.row_count_estimated
    raise AssertionError(f"{table} missing from table_stats()")


@pytest.mark.asyncio
async def test_table_stats_row_count_survives_a_statistics_reset() -> None:
    engine = make_async_engine(Settings(pg_dsn=_dsn()))
    try:
        await _require_disposable(engine)
        async with engine.begin() as conn:
            for name in (_TABLE, _FRESH_TABLE):
                await conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
            await conn.execute(text(f"CREATE TABLE {_TABLE} (i int)"))
            await conn.execute(text(f"INSERT INTO {_TABLE} SELECT generate_series(1, 1000)"))
            await conn.execute(text(f"ANALYZE {_TABLE}"))
        # Publish the setup deltas BEFORE the reset further down. A backend holds its table stats
        # pending and publishes them at a later flush point; if that lands after the reset the
        # 1000 inserts reappear in `n_live_tup` and the post-reset cases stop discriminating.
        await _flush_stats(engine)

        # --- anchored ------------------------------------------------------------------------
        live, reltuples, anchored = await _raw_stats(engine, _TABLE)
        assert (live, anchored) == (1000, True), f"fixture: {live=} {reltuples=} {anchored=}"
        count, estimated = await _row_count(engine)
        assert count == 1000, f"analyzed table must report its live count, got {count}"
        assert estimated is False

        # Unanalyzed inserts: `reltuples` is stale at 1000, the live counter knows about them.
        # Kills an implementation that always answers `reltuples`.
        async with engine.begin() as conn:
            await conn.execute(text(f"INSERT INTO {_TABLE} SELECT generate_series(1, 500)"))
        await _flush_stats(engine)
        live, reltuples, _ = await _raw_stats(engine, _TABLE)
        assert (live, reltuples) == (1500, 1000), f"fixture: {live=} {reltuples=}"
        count, estimated = await _row_count(engine)
        assert count == 1500, f"anchored live count must beat stale reltuples, got {count}"
        assert estimated is False

        # Unanalyzed deletes: now the live counter is SMALLER than `reltuples`. Kills an
        # implementation that unconditionally takes the larger of the two signals.
        async with engine.begin() as conn:
            await conn.execute(
                text(f"DELETE FROM {_TABLE} WHERE ctid IN "
                     f"(SELECT ctid FROM {_TABLE} LIMIT 1400)")
            )
        await _flush_stats(engine)
        live, reltuples, _ = await _raw_stats(engine, _TABLE)
        assert live < reltuples, f"fixture: expected live < reltuples, got {live=} {reltuples=}"
        count, estimated = await _row_count(engine)
        assert count == live, f"anchored live count must win when it shrinks, got {count}"
        assert estimated is False

        # --- unanchored: the collector was reset (restore / hot-swap) ------------------------
        # Scoped to this relation: `pg_stat_reset()` is database-wide and would wipe the
        # autovacuum scheduling state of every other table.
        async with engine.begin() as conn:
            await conn.execute(
                # Resolved via pg_class rather than `:t::regclass` — SQLAlchemy's `text()` does
                # not bind a parameter that is immediately followed by a `::` cast.
                text(
                    """
SELECT pg_stat_reset_single_table_counters(
         (SELECT c.oid
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE c.relname = :t AND n.nspname = 'public')
       )
"""
                ),
                {"t": _TABLE},
            )
        live, reltuples, anchored = await _raw_stats(engine, _TABLE)
        assert (live, anchored) == (0, False), f"fixture: reset did not take: {live=} {anchored=}"
        count, estimated = await _row_count(engine)
        assert count == pytest.approx(reltuples, rel=0.05), "reset must fall back to reltuples"
        assert estimated is True, "a planner estimate must be reported as an estimate"

        # Churn AFTER the reset must not be mistaken for the row count. This is what the first
        # attempted fix (`COALESCE(NULLIF(n_live_tup,0), NULLIF(reltuples,0), 0)`) got wrong:
        # it answered 6 for a 620k-row table.
        async with engine.begin() as conn:
            await conn.execute(text(f"INSERT INTO {_TABLE} SELECT generate_series(1, 6)"))
        await _flush_stats(engine)
        live, reltuples, _ = await _raw_stats(engine, _TABLE)
        assert live == 6, f"fixture: expected the 6-row post-reset delta, got {live}"
        count, estimated = await _row_count(engine)
        assert count > 900, f"post-reset delta leaked into row_count: {count}"
        assert estimated is True

        # --- unanchored: never analyzed at all ------------------------------------------------
        # A logical restore (`pg_restore`, or this project's restore with `run_analyze=false`)
        # leaves `reltuples` at -1 while the live counter is correct. Kills an implementation
        # that falls back to `reltuples` alone -- that one reports 0 for EVERY table here.
        async with engine.begin() as conn:
            await conn.execute(text(f"CREATE TABLE {_FRESH_TABLE} (i int)"))
            await conn.execute(text(f"INSERT INTO {_FRESH_TABLE} SELECT generate_series(1, 300)"))
        await _flush_stats(engine)
        live, reltuples, anchored = await _raw_stats(engine, _FRESH_TABLE)
        assert (live, reltuples, anchored) == (300, -1.0, False), (
            f"fixture: {live=} {reltuples=} {anchored=}"
        )
        count, estimated = await _row_count(engine, _FRESH_TABLE)
        assert count == 300, f"never-analyzed table must use its live count, got {count}"
        assert estimated is True, "an unanalyzed count is still a guess"
    finally:
        async with engine.begin() as conn:
            for name in (_TABLE, _FRESH_TABLE):
                await conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
        await engine.dispose()
