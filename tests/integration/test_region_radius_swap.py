"""``region_radius_parts`` is rebuilt into ``_next`` and swapped in (opt-in, G-01 follow-up a2).

Bound to effects PostgreSQL reports, without timing guesses: the rebuild is held mid-build by an
ACCESS EXCLUSIVE lock this test takes on a *source* table, and the test waits for the rebuild's
backend to show up as a waiter in ``pg_locks`` before it acts. While the rebuild sits there a
reader with a 1 s ``lock_timeout`` still reads the live table (the old TRUNCATE-in-place rebuild
held ACCESS EXCLUSIVE on it at that point, so the same reader failed with 55P03 — run red once on
purpose, see the PR body). A reader that queues behind the swap itself gets the new table, a
failure or a killed backend at any point leaves the live table as it was with no ``_next``
behind, and the next run succeeds.

Needs a disposable scratch DB (tests/integration/_pg_guard.py naming rule) bootstrapped with
``ktgctl init-db`` + ``alembic stamp head``. Rows use the code prefix ``99`` and are removed::

    KTG_TEST_PG_DSN=postgresql+psycopg://<user>:<pw>@127.0.0.1:<port>/kor_travel_geo_test \
        pytest tests/integration/test_region_radius_swap.py
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders import postload
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

pytestmark = pytest.mark.asyncio

_SQUARE = (
    "ST_GeomFromText('MULTIPOLYGON(((969000 1840000, 969500 1840000, 969500 1840500,"
    " 969000 1840500, 969000 1840000)))', 5179)"
)
_CODE = "99110"
_CANONICAL_INDEXES = {
    "region_radius_parts_pkey",
    "idx_region_radius_parts_geom",
    "idx_region_radius_parts_level_parent_sido",
    "idx_region_radius_parts_level_parent_sig",
}
_CANONICAL_CONSTRAINTS = {"region_radius_parts_pkey", "region_radius_parts_level_check"}
_WAIT_S = 30.0


async def _cleanup(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP VIEW IF EXISTS t_radius_swap_dependent"))
        await conn.execute(text("DROP TABLE IF EXISTS region_radius_parts_next"))
        await conn.execute(text("DELETE FROM tl_scco_sig WHERE sig_cd LIKE '99%'"))
        # A granted live table cannot be reset to the default ACL (REVOKE leaves an explicit
        # one): drop it, the next rebuild recreates it through the first-build path.
        if await conn.scalar(
            text(
                "SELECT count(*) FROM pg_class WHERE oid = to_regclass('region_radius_parts')"
                " AND relacl IS NOT NULL"
            )
        ):
            await conn.execute(text("DROP TABLE region_radius_parts"))


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    eng = make_async_engine(Settings(pg_dsn=dsn, pg_statement_timeout_ms=60_000))
    try:
        await require_disposable_database(eng)
        await _cleanup(eng)
        async with eng.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO tl_scco_sig (sig_cd, sig_kor_nm, geom)"
                    f" VALUES ('{_CODE}', 'old', {_SQUARE})"
                )
            )
        await postload.refresh_region_radius_parts(eng)  # live table holds 'old'
        await _rename_source(eng, "new")
        yield eng
        await _cleanup(eng)
        await postload.refresh_region_radius_parts(eng)  # leave the table, without '99' rows
    finally:
        await eng.dispose()


async def _rename_source(engine: AsyncEngine, name: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE tl_scco_sig SET sig_kor_nm = :n WHERE sig_cd = :c"),
            {"n": name, "c": _CODE},
        )


async def _live_name(conn: AsyncConnection) -> str | None:
    value = await conn.scalar(
        text("SELECT max(name) FROM region_radius_parts WHERE level = 'sigungu' AND code = :c"),
        {"c": _CODE},
    )
    return None if value is None else str(value)


async def _read_live_name(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        return await _live_name(conn)


async def _assert_clean_live_table(engine: AsyncEngine) -> None:
    """The live table looks exactly like one created by the DDL: no `_next` left anywhere."""
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT to_regclass('region_radius_parts_next')")) is None
        indexes = await conn.execute(
            text(
                "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid"
                " WHERE i.indrelid = 'region_radius_parts'::regclass"
            )
        )
        assert {str(r[0]) for r in indexes} == _CANONICAL_INDEXES
        constraints = await conn.execute(
            text(
                "SELECT conname FROM pg_constraint"
                " WHERE conrelid = 'region_radius_parts'::regclass AND contype IN ('p', 'c')"
            )
        )
        assert {str(r[0]) for r in constraints} == _CANONICAL_CONSTRAINTS
        owner_is_me, acl_is_default = (
            await conn.execute(
                text(
                    "SELECT pg_get_userbyid(relowner) = current_user, relacl IS NULL"
                    " FROM pg_class WHERE oid = 'region_radius_parts'::regclass"
                )
            )
        ).one()
        assert owner_is_me and acl_is_default
        leftovers = await conn.scalar(
            text("SELECT count(*) FROM pg_class WHERE relname LIKE '%region_radius_parts_next%'")
        )
        assert leftovers == 0


async def _wait_for_lock_waiter(engine: AsyncEngine, relation: str) -> int:
    """PID of the backend waiting for a lock on ``relation`` — a state, not a timing guess."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _WAIT_S
    async with engine.connect() as conn:
        while True:
            pid = await conn.scalar(
                text(
                    "SELECT pid FROM pg_locks"
                    " WHERE relation = to_regclass(:r) AND NOT granted LIMIT 1"
                ),
                {"r": relation},
            )
            if pid is not None:
                return int(pid)
            await conn.rollback()  # fresh snapshot of pg_locks on the next poll
            if loop.time() > deadline:
                raise AssertionError(f"nothing started waiting for a lock on {relation}")
            await asyncio.sleep(0.05)


async def _hold_source_lock(holder: AsyncConnection) -> None:
    await holder.execute(text("BEGIN"))
    await holder.execute(text("LOCK TABLE tl_scco_emd IN ACCESS EXCLUSIVE MODE"))


async def test_the_swap_publishes_new_rows_and_keeps_the_ddl_names(engine: AsyncEngine) -> None:
    assert await _read_live_name(engine) == "old"
    await postload.refresh_region_radius_parts(engine)
    assert await _read_live_name(engine) == "new"
    await _assert_clean_live_table(engine)


async def test_readers_are_not_blocked_while_the_rebuild_computes(engine: AsyncEngine) -> None:
    async with engine.connect() as holder:
        await _hold_source_lock(holder)
        rebuild = asyncio.create_task(postload.refresh_region_radius_parts(engine))
        try:
            await _wait_for_lock_waiter(engine, "tl_scco_emd")  # rebuild is mid-build
            async with engine.connect() as reader:
                await reader.execute(text("SET lock_timeout = '1s'"))
                # TRUNCATE-in-place held ACCESS EXCLUSIVE here: this read failed with 55P03.
                assert await _live_name(reader) == "old"
            assert not rebuild.done()
        finally:
            await holder.execute(text("ROLLBACK"))
        await asyncio.wait_for(rebuild, _WAIT_S)
    assert await _read_live_name(engine) == "new"
    await _assert_clean_live_table(engine)


async def test_a_reader_queued_behind_the_swap_reads_the_new_table(engine: AsyncEngine) -> None:
    swapped = asyncio.Event()
    release = asyncio.Event()

    async def guard(conn: AsyncConnection) -> None:
        # Runs after the swap, still holding ACCESS EXCLUSIVE on the live table.
        swapped.set()
        await asyncio.wait_for(release.wait(), _WAIT_S)

    rebuild = asyncio.create_task(
        postload.refresh_region_radius_parts(engine, publication_guard=guard)
    )
    try:
        await asyncio.wait_for(swapped.wait(), _WAIT_S)
        reader = asyncio.create_task(_read_live_name(engine))
        await _wait_for_lock_waiter(engine, "region_radius_parts")
    finally:
        release.set()
    await asyncio.wait_for(rebuild, _WAIT_S)
    # The waiter re-resolves the name after the lock: it reads the swapped-in table, no error.
    assert await asyncio.wait_for(reader, _WAIT_S) == "new"


@pytest.mark.parametrize("failure", ["guard_raises_after_swap", "backend_killed_mid_build"])
async def test_a_failure_leaves_the_live_table_and_a_rerun_succeeds(
    engine: AsyncEngine, failure: str
) -> None:
    if failure == "guard_raises_after_swap":

        async def guard(conn: AsyncConnection) -> None:
            raise RuntimeError("simulated lost ownership")

        with pytest.raises(RuntimeError, match="simulated lost ownership"):
            await postload.refresh_region_radius_parts(engine, publication_guard=guard)
    else:
        async with engine.connect() as holder:
            await _hold_source_lock(holder)
            rebuild = asyncio.create_task(postload.refresh_region_radius_parts(engine))
            try:
                pid = await _wait_for_lock_waiter(engine, "tl_scco_emd")
                async with engine.connect() as killer:
                    assert await killer.scalar(
                        text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                    )
                with pytest.raises(DBAPIError):
                    await asyncio.wait_for(rebuild, _WAIT_S)
            finally:
                await holder.execute(text("ROLLBACK"))
    assert await _read_live_name(engine) == "old"
    await _assert_clean_live_table(engine)

    await postload.refresh_region_radius_parts(engine)
    assert await _read_live_name(engine) == "new"
    await _assert_clean_live_table(engine)


async def test_the_first_build_creates_the_live_table(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE region_radius_parts"))
    await postload.refresh_region_radius_parts(engine)
    assert await _read_live_name(engine) == "new"
    await _assert_clean_live_table(engine)


async def test_a_stale_committed_next_table_is_replaced(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE region_radius_parts_next (junk int)"))
    await postload.refresh_region_radius_parts(engine)
    assert await _read_live_name(engine) == "new"
    await _assert_clean_live_table(engine)


@pytest.mark.parametrize(
    ("attachment", "refusal"),
    [
        ("CREATE VIEW t_radius_swap_dependent AS SELECT code FROM region_radius_parts",
         "no_dependents"),
        ("GRANT SELECT ON region_radius_parts TO PUBLIC", "same_grants"),
    ],
)
async def test_the_swap_refuses_to_drop_state_it_does_not_rebuild(
    engine: AsyncEngine, attachment: str, refusal: str
) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(attachment))
    with pytest.raises(RuntimeError, match=refusal):
        await postload.refresh_region_radius_parts(engine)
    assert await _read_live_name(engine) == "old"
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT to_regclass('region_radius_parts_next')")) is None
