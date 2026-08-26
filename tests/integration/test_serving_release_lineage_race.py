"""Concurrent-activation lineage race for ``_insert_dataset_snapshot_and_release`` (T-293,
opt-in, real PostgreSQL).

Two distinct race windows, both closed by the same fix:

1. **Zero active rows** (empty table — a fresh database, or a hot-swapped-in database whose
   own history has none yet). The function's ``SELECT ... FOR UPDATE WHERE state = 'active'``
   locks nothing when no row matches, so two concurrent activations both read
   ``previous = None`` and both try to insert with ``state = 'active'``. The T-049 partial
   unique index ``idx_ops_serving_releases_one_active`` (``ops.serving_releases(state) WHERE
   state = 'active'``) stops that from silently producing two active rows — but it does so by
   raising an uncaught ``IntegrityError``/``UniqueViolation`` in whichever transaction commits
   second, crashing that caller instead of correctly serializing it.

2. **A row is already active** (docs/tasks.md's original T-293 report, found in T-291a's
   review, PR #529). The loser's ``SELECT ... FOR UPDATE`` blocks on the *original* active
   row. Once the winner commits (superseding that row and inserting its own), the loser's
   lock unblocks — but PostgreSQL's documented ``FOR UPDATE`` + ``LIMIT`` interaction does
   not re-scan for a fresh matching row when the originally-locked row no longer satisfies
   the ``WHERE`` clause after being updated; it just returns zero rows for that query. The
   "active state" invariant survives (the loser's unconditional
   ``UPDATE ... WHERE state = 'active'`` still supersedes the winner's new row), but the
   loser computes ``previous = None`` and its ``previous_serving_release_id``/
   ``parent_dataset_snapshot_id`` lineage silently drops the winner instead of pointing to
   it — no crash, no error, just a quietly broken lineage chain.

T-293's fix is a transaction-scoped advisory lock (``pg_advisory_xact_lock``,
``AdvisoryLockNamespace.SERVING_RELEASE_ACTIVATION``) acquired before either the ``SELECT``
or the row-existence check, serializing the whole read-decide-write section unconditionally.
This closes window 1 (there's now always something to serialize on) and window 2 (the loser
blocks on the advisory lock itself, not on the row via ``FOR UPDATE`` — so by the time its
``SELECT`` actually runs, it's a fresh query against the winner's already-committed state,
not an ``EvalPlanQual`` re-check of a stale locked row).

Both scenarios are reproduced deterministically with two manually-managed connections and
``asyncio.Event`` synchronization: transaction A starts and completes its insert but is held
open (not yet committed) while transaction B is launched; B must therefore either block on
the advisory lock (fixed) or run ahead unserialized (broken). Only after B has had a chance
to start is A allowed to commit. The ``asyncio.sleep`` below is a real sleep, not merely
decorative — the ``asyncio.Event`` ordering guarantees B *starts* only after A's insert, but
does not by itself guarantee B has reached (and, if fixed, blocked on) the lock before A's
commit is released; the sleep gives B a genuine window to get there so the test proves
contention rather than incidental ordering.

Run with a disposable scratch database (see tests/integration/_pg_guard.py):

    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:12500/kor_travel_geo_test pytest \
        tests/integration/test_serving_release_lineage_race.py
"""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.infra.admin_repo import _insert_dataset_snapshot_and_release
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

_RACE_YYYYMM = {"seed": "202600", "a": "202601", "b": "202602"}


async def _fresh_engine() -> AsyncEngine:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
    except BaseException:
        await engine.dispose()
        raise
    return engine


async def _seed_active_release(engine: AsyncEngine) -> None:
    """Commit an initial active release so the race starts from a non-empty table —
    reproduces docs/tasks.md's originally-reported T-293 scenario (window 2 above), as
    opposed to :func:`test_concurrent_activation_on_empty_table...`'s empty-table window 1.
    """
    async with engine.begin() as conn:
        await _insert_dataset_snapshot_and_release(
            conn,
            snapshot_state="released",
            release_state="active",
            release_kind="full_load",
            source_set={"yyyymm_by_kind": {"juso": _RACE_YYYYMM["seed"]}},
            row_counts={},
        )


async def _run_concurrent_activation_race(
    engine: AsyncEngine,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Race two concurrent activations against ``engine`` and return
    ``((a_snapshot_id, a_release_id), (b_snapshot_id, b_release_id))`` after both commit.

    Connections are opened directly (not via ``engine.begin()``) so each transaction can be
    held open across the ``asyncio.Event`` handshake below; both are guaranteed closed via
    ``AsyncExitStack`` even if either side raises (e.g. the pre-fix ``IntegrityError``) —
    the race this test exists to catch is exactly the case a bare ``close()`` call placed
    only after a successful ``gather()`` would silently skip.
    """
    async with AsyncExitStack() as stack:
        conn_a: AsyncConnection = await stack.enter_async_context(engine.connect())
        trans_a = await conn_a.begin()
        conn_b: AsyncConnection = await stack.enter_async_context(engine.connect())
        trans_b = await conn_b.begin()

        a_done_uncommitted = asyncio.Event()
        release_a = asyncio.Event()

        async def run_a() -> tuple[str, str]:
            snapshot, release = await _insert_dataset_snapshot_and_release(
                conn_a,
                snapshot_state="released",
                release_state="active",
                release_kind="full_load",
                source_set={"yyyymm_by_kind": {"juso": _RACE_YYYYMM["a"]}},
                row_counts={},
            )
            a_done_uncommitted.set()
            await release_a.wait()
            await trans_a.commit()
            return snapshot.dataset_snapshot_id, release.serving_release_id

        async def run_b() -> tuple[str, str]:
            await a_done_uncommitted.wait()
            b_task = asyncio.ensure_future(
                _insert_dataset_snapshot_and_release(
                    conn_b,
                    snapshot_state="released",
                    release_state="active",
                    release_kind="full_load",
                    source_set={"yyyymm_by_kind": {"juso": _RACE_YYYYMM["b"]}},
                    row_counts={},
                )
            )
            # Give B a real chance to reach (and, if fixed, block on) the advisory
            # lock before we let A commit — proves B was actually contending, not
            # just running after A by incidental ordering.
            await asyncio.sleep(0.3)
            release_a.set()
            snapshot, release = await b_task
            await trans_b.commit()
            return snapshot.dataset_snapshot_id, release.serving_release_id

        return await asyncio.gather(run_a(), run_b())


async def _cleanup_race_rows(engine: AsyncEngine) -> None:
    yyyymm_values = tuple(_RACE_YYYYMM.values())
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM ops.serving_releases"
                " WHERE dataset_snapshot_id IN ("
                "   SELECT dataset_snapshot_id FROM ops.dataset_snapshots"
                "    WHERE (source_set #>> '{yyyymm_by_kind,juso}') = ANY(:yyyymm_values)"
                " )"
            ),
            {"yyyymm_values": list(yyyymm_values)},
        )
        await conn.execute(
            text(
                "DELETE FROM ops.dataset_snapshots"
                " WHERE (source_set #>> '{yyyymm_by_kind,juso}') = ANY(:yyyymm_values)"
            ),
            {"yyyymm_values": list(yyyymm_values)},
        )


@pytest.mark.asyncio
async def test_concurrent_activation_on_empty_table_serializes_and_preserves_lineage() -> None:
    """Race window 1: zero active rows (fresh table)."""
    engine = await _fresh_engine()
    try:
        (a_snapshot_id, a_release_id), (b_snapshot_id, b_release_id) = (
            await _run_concurrent_activation_race(engine)
        )

        async with engine.connect() as check_conn:
            active_rows = (
                await check_conn.execute(
                    text(
                        "SELECT serving_release_id, dataset_snapshot_id,"
                        "       previous_serving_release_id"
                        "  FROM ops.serving_releases"
                        " WHERE state = 'active'"
                    )
                )
            ).mappings().all()
            b_snapshot_row = (
                await check_conn.execute(
                    text(
                        "SELECT parent_dataset_snapshot_id"
                        "  FROM ops.dataset_snapshots"
                        " WHERE dataset_snapshot_id = :id"
                    ),
                    {"id": b_snapshot_id},
                )
            ).mappings().one()

        assert len(active_rows) == 1, (
            "exactly one serving_release must be active after both concurrent "
            f"activations commit; found {len(active_rows)}"
        )
        assert str(active_rows[0]["serving_release_id"]) == b_release_id
        assert str(active_rows[0]["previous_serving_release_id"]) == a_release_id
        assert str(b_snapshot_row["parent_dataset_snapshot_id"]) == a_snapshot_id
    finally:
        await _cleanup_race_rows(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_activation_with_pre_existing_active_row_preserves_lineage() -> None:
    """Race window 2 — docs/tasks.md's originally-reported T-293 scenario: a row is already
    active when the race starts. Without the fix, this is the ``FOR UPDATE`` + ``LIMIT``
    EvalPlanQual pitfall — B's lock blocks on the *original* row, which no longer matches
    once A supersedes it, and PostgreSQL does not re-scan for A's new row; B's ``SELECT``
    silently returns zero rows and B computes ``previous = None`` instead of pointing at A.
    """
    engine = await _fresh_engine()
    try:
        await _seed_active_release(engine)
        (a_snapshot_id, a_release_id), (b_snapshot_id, b_release_id) = (
            await _run_concurrent_activation_race(engine)
        )

        async with engine.connect() as check_conn:
            active_rows = (
                await check_conn.execute(
                    text(
                        "SELECT serving_release_id, dataset_snapshot_id,"
                        "       previous_serving_release_id"
                        "  FROM ops.serving_releases"
                        " WHERE state = 'active'"
                    )
                )
            ).mappings().all()
            b_snapshot_row = (
                await check_conn.execute(
                    text(
                        "SELECT parent_dataset_snapshot_id"
                        "  FROM ops.dataset_snapshots"
                        " WHERE dataset_snapshot_id = :id"
                    ),
                    {"id": b_snapshot_id},
                )
            ).mappings().one()

        assert len(active_rows) == 1, (
            "exactly one serving_release must be active after both concurrent "
            f"activations commit; found {len(active_rows)}"
        )
        assert str(active_rows[0]["serving_release_id"]) == b_release_id
        # The bug: without the fix, this comes back None instead of a_release_id — the
        # active-row invariant survives, but B's lineage silently loses A.
        assert str(active_rows[0]["previous_serving_release_id"]) == a_release_id
        assert str(b_snapshot_row["parent_dataset_snapshot_id"]) == a_snapshot_id
    finally:
        await _cleanup_race_rows(engine)
        await engine.dispose()
