"""Concurrent-activation lineage race for ``_insert_dataset_snapshot_and_release`` (T-293,
opt-in, real PostgreSQL).

T-291a's review flagged that the function's ``SELECT ... FOR UPDATE WHERE state = 'active'``
only serializes concurrent callers when a row currently matches — it locks nothing when
``ops.serving_releases`` has zero active rows (a fresh database, or a hot-swapped-in database
whose own history has none yet). Two concurrent activations racing on an empty table both
read ``previous = None`` and both try to insert with ``state = 'active'``. The T-049 partial
unique index ``idx_ops_serving_releases_one_active`` (``ops.serving_releases(state) WHERE
state = 'active'``) stops that from silently producing two active rows — but it does so by
raising an uncaught ``IntegrityError``/``UniqueViolation`` in whichever transaction commits
second, crashing that caller instead of correctly serializing it, and the caller that *does*
win the race still has wrong lineage relative to whichever one loses. T-293 adds a
transaction-scoped advisory lock (``pg_advisory_xact_lock``,
``AdvisoryLockNamespace.SERVING_RELEASE_ACTIVATION``) that serializes the whole
read-decide-write section independent of whether any row currently matches — the second
caller now waits and correctly supersedes the first instead of crashing.

This test reproduces the race deterministically with two manually-managed connections and
``asyncio.Event`` synchronization — no sleep-and-hope timing. Transaction A starts and
completes its insert but is held open (not yet committed) while transaction B is launched; B
must therefore either block on the advisory lock (fixed) or race ahead and also insert as
active (broken). Only after B has had a chance to run is A allowed to commit.

Run with a disposable scratch database (see tests/integration/_pg_guard.py):

    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@127.0.0.1:12500/kor_travel_geo_test pytest \
        tests/integration/test_serving_release_lineage_race.py
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.admin_repo import _insert_dataset_snapshot_and_release
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database


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


@pytest.mark.asyncio
async def test_concurrent_activation_on_empty_table_serializes_and_preserves_lineage() -> None:
    engine = await _fresh_engine()
    try:
        conn_a = await engine.connect()
        trans_a = await conn_a.begin()
        conn_b = await engine.connect()
        trans_b = await conn_b.begin()

        a_done_uncommitted = asyncio.Event()
        release_a = asyncio.Event()

        async def run_a() -> tuple[str, str]:
            snapshot, release = await _insert_dataset_snapshot_and_release(
                conn_a,
                snapshot_state="released",
                release_state="active",
                release_kind="full_load",
                source_set={"yyyymm_by_kind": {"juso": "202601"}},
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
                    source_set={"yyyymm_by_kind": {"juso": "202602"}},
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

        (a_snapshot_id, a_release_id), (b_snapshot_id, b_release_id) = await asyncio.gather(
            run_a(), run_b()
        )
        await conn_a.close()
        await conn_b.close()

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
        async with engine.begin() as cleanup_conn:
            await cleanup_conn.execute(
                text(
                    "DELETE FROM ops.serving_releases"
                    " WHERE dataset_snapshot_id IN ("
                    "   SELECT dataset_snapshot_id FROM ops.dataset_snapshots"
                    "    WHERE source_set->>'yyyymm_by_kind' IS NOT NULL"
                    "      AND (source_set #>> '{yyyymm_by_kind,juso}') IN ('202601', '202602')"
                    " )"
                )
            )
            await cleanup_conn.execute(
                text(
                    "DELETE FROM ops.dataset_snapshots"
                    " WHERE (source_set #>> '{yyyymm_by_kind,juso}') IN ('202601', '202602')"
                )
            )
        await engine.dispose()
