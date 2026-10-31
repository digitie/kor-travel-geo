"""Maintenance ``statement_timeout`` ceiling against a real PostgreSQL (opt-in, G-01).

The post-load maintenance transactions (link resolution, MV refresh/swap, release record) used a
literal ``SET LOCAL statement_timeout = '30min'``. On the Dagster maintenance engine (session
timeout ``0``) that cut an odroid ``mv_refresh`` link-resolution UPDATE at exactly 30 min under
host contention (2026-10-15, ``job_fb535a34…``). They now use one named ceiling,
``MAINTENANCE_STATEMENT_TIMEOUT`` (= the ``mv_refresh`` run cap, ADR-070 D4).

Bound to what PostgreSQL itself reports *inside* the real transaction: the wired statement raises
unless ``current_setting('statement_timeout')`` is the expected value. With the old ``'30min'``
literal the first case raises.

Needs a disposable scratch DB (tests/integration/_pg_guard.py naming rule) bootstrapped with
``ktgctl init-db`` + ``alembic stamp head``::

    KTG_TEST_PG_DSN=postgresql+psycopg://<user>:<pw>@127.0.0.1:<port>/kor_travel_geo_test \
        pytest tests/integration/test_maintenance_statement_timeout.py
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.infra.engine import (
    MAINTENANCE_STATEMENT_TIMEOUT,
    MAINTENANCE_STATEMENT_TIMEOUT_MS,
    make_async_engine,
)
from kortravelgeo.loaders import postload
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

pytestmark = pytest.mark.asyncio


def _assert_timeout_sql(expected: str) -> str:
    return (
        "DO $$ BEGIN IF current_setting('statement_timeout') <> '"
        + expected
        + "' THEN RAISE EXCEPTION 'statement_timeout is %', current_setting('statement_timeout');"
        " END IF; END $$;"
    )


async def _engine(session_timeout_ms: int) -> AsyncEngine:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    # model_copy skips the ge=1 bound on purpose: 0 is the Dagster maintenance engine's session
    # value (kortravelgeo_dagster.resources._maintenance_engine_settings does the same).
    settings = Settings(pg_dsn=dsn).model_copy(
        update={"pg_statement_timeout_ms": session_timeout_ms}
    )
    engine = make_async_engine(settings)
    try:
        await require_disposable_database(engine)
    except BaseException:
        await engine.dispose()
        raise
    return engine


async def test_the_ceiling_text_and_milliseconds_agree() -> None:
    engine = await _engine(5_000)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"SET LOCAL statement_timeout = '{MAINTENANCE_STATEMENT_TIMEOUT}'")
            )
            setting = await conn.scalar(
                text("SELECT setting::bigint FROM pg_settings WHERE name = 'statement_timeout'")
            )
        assert setting == MAINTENANCE_STATEMENT_TIMEOUT_MS
    finally:
        await engine.dispose()


async def test_link_resolution_runs_under_the_maintenance_ceiling_on_the_dagster_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check = _assert_timeout_sql(MAINTENANCE_STATEMENT_TIMEOUT)
    monkeypatch.setattr(postload, "POSTLOAD_SQL", check)
    engine = await _engine(0)
    try:
        await postload.resolve_text_geometry_links(engine)
    finally:
        await engine.dispose()


async def test_link_resolution_zero_still_means_unlimited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # tests/integration/_t177_full_load_harness.py passes 0 on a 5 s serving engine.
    monkeypatch.setattr(postload, "POSTLOAD_SQL", _assert_timeout_sql("0"))
    engine = await _engine(5_000)
    try:
        await postload.resolve_text_geometry_links(engine, statement_timeout_ms=0)
    finally:
        await engine.dispose()


async def test_link_resolution_uses_emd_and_preserves_postcode_and_null_rules() -> None:
    from kortravelgeo.infra.sql import POSTLOAD_SQL, iter_sql_statements

    engine = await _engine(5_000)
    try:
        async with engine.begin() as conn:
            # 임시 테이블만 사용하며 기존 서빙 테이블은 갱신하지 않는다.
            for name in (
                "tl_juso_text", "tl_locsum_entrc", "tl_navi_entrc", "tl_navi_buld_centroid"
            ):
                await conn.execute(text(
                    f"CREATE TEMP TABLE {name} (id integer, bd_mgt_sn text, "
                    "rncode_full text, bjd_cd text, buld_se_cd text, buld_mnnm integer, "
                    "buld_slno integer, zip_no text) ON COMMIT DROP"
                ))
            await conn.execute(text(
                "INSERT INTO tl_juso_text VALUES "
                "(1,'43111340457177500004100009','431114571775','4311134022','0',41,9,'28187'),"
                "(2,'nullable-fields','431114571776','4311134022',NULL,NULL,NULL,NULL)"
            ))
            await conn.execute(text(
                "INSERT INTO tl_locsum_entrc VALUES "
                "(1,NULL,'431114571775','4311134000','0',41,9,'28187'),"
                "(2,NULL,'431114571775','4311135000','0',41,9,'28187'),"
                "(3,NULL,'431114571775','4311134000','0',41,9,'28188'),"
                "(4,NULL,'431114571775','4311134000','0',41,9,NULL),"
                "(5,NULL,'431114571775','4311134000',NULL,41,9,'28187'),"
                "(6,NULL,'431114571776','4311134000',NULL,NULL,NULL,NULL)"
            ))
            await conn.execute(text(
                "INSERT INTO tl_navi_entrc VALUES "
                "(1,NULL,'431114571775','4311134000','0',41,9,NULL),"
                "(2,NULL,'431114571775','4311135000','0',41,9,NULL)"
            ))
            for sql in iter_sql_statements(POSTLOAD_SQL):
                await conn.execute(text(sql))
            locsum = dict((await conn.execute(text(
                "SELECT id, bd_mgt_sn FROM tl_locsum_entrc ORDER BY id"
            ))).all())
            navi = dict((await conn.execute(text(
                "SELECT id, bd_mgt_sn FROM tl_navi_entrc ORDER BY id"
            ))).all())
            expected = "43111340457177500004100009"
            assert locsum == {1: expected, 2: None, 3: None, 4: expected, 5: None,
                              6: "nullable-fields"}
            assert navi == {1: expected, 2: None}
    finally:
        await engine.dispose()
