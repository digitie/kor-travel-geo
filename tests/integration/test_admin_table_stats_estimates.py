"""`/admin/tables` row counts against a real PostgreSQL (opt-in, issue #515).

These three cases cannot be expressed as unit tests: they depend on how PostgreSQL's *statistics
collector* behaves, which is exactly what the bug was about. `n_live_tup` is a delta the
collector accumulates and a restore / hot-swap resets it, so on a restored database it is not a
row count at all — an untouched table reads 0, and a table that took a handful of writes reads
those few writes. `AdminRepository.table_stats` therefore has to decide whether the stats entry
is *anchored* (a vacuum/analyze has been observed) before trusting it.

Run with a disposable scratch database::

    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:12500/scratch pytest \
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


def _dsn() -> str:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    return dsn


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


async def _live_tup(engine, table: str = _TABLE) -> int:
    """The collector's raw delta — asserted on directly so a broken fixture fails loudly."""
    async with engine.connect() as conn:
        return await conn.scalar(
            text(
                "SELECT n_live_tup FROM pg_stat_user_tables "
                "WHERE schemaname = 'public' AND relname = :t"
            ),
            {"t": table},
        )


async def _row_count(engine, table: str = _TABLE) -> tuple[int, bool]:
    stats = await AdminRepository(engine).table_stats(limit=500)
    for stat in stats:
        if stat.table_name == table:
            return stat.row_count, stat.row_count_estimated
    raise AssertionError(f"{table} missing from table_stats()")


@pytest.mark.asyncio
async def test_table_stats_row_count_survives_a_statistics_reset() -> None:
    engine = make_async_engine(Settings(pg_dsn=_dsn()))
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
            await conn.execute(text(f"CREATE TABLE {_TABLE} (i int)"))
            await conn.execute(
                text(f"INSERT INTO {_TABLE} SELECT generate_series(1, 1000)")
            )
            await conn.execute(text(f"ANALYZE {_TABLE}"))
        # Publish the setup deltas BEFORE resetting. A backend holds its table stats pending and
        # publishes them at a later flush point; if that happens after `pg_stat_reset()` the 1000
        # inserts reappear in `n_live_tup` and case 2 below silently stops discriminating.
        await _flush_stats(engine)

        # Case 1 — a restore / hot-swap clears the collector. Before the fix every table
        # reported 0 here, which is the whole of issue #515.
        async with engine.begin() as conn:
            await conn.execute(text("SELECT pg_stat_reset()"))
        reset_live = await _live_tup(engine)
        assert reset_live == 0, f"fixture broken: pg_stat_reset() left n_live_tup at {reset_live}"
        count, estimated = await _row_count(engine)
        assert count == pytest.approx(1000, rel=0.05), "stats reset must fall back to reltuples"
        assert estimated is True, "a planner estimate must be reported as an estimate"

        # Case 2 — churn AFTER the reset must not be mistaken for the row count. This is the
        # case a naive `n_live_tup or reltuples` fallback gets wrong: it would answer 6.
        async with engine.begin() as conn:
            await conn.execute(text(f"INSERT INTO {_TABLE} SELECT generate_series(1, 6)"))
        await _flush_stats(engine)
        # Sanity-check the fixture itself: unless the collector really is sitting on a small
        # post-reset delta, this case cannot tell a correct query from the naive
        # `n_live_tup or reltuples` one — it would pass either way.
        live = await _live_tup(engine)
        assert live == 6, f"fixture broken: expected the 6-row delta to be visible, got {live}"
        count, _ = await _row_count(engine)
        assert count > 900, f"post-reset delta leaked into row_count: {count}"

        # Case 3 — once the relation is analyzed again the live counter is authoritative, and it
        # must win even though `reltuples` still holds the old estimate. A DELETE-emptied table
        # has to read 0, not its pre-delete count.
        async with engine.begin() as conn:
            await conn.execute(text(f"DELETE FROM {_TABLE}"))
            await conn.execute(text(f"ANALYZE {_TABLE}"))
        await _flush_stats(engine)
        count, estimated = await _row_count(engine)
        assert count == 0, f"DELETE-emptied table must report 0, got {count}"
        assert estimated is False, "an anchored live count is exact, not an estimate"
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {_TABLE}"))
        await engine.dispose()
