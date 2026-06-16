from __future__ import annotations

import os
from time import perf_counter

import pytest
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings


@pytest.mark.asyncio
async def test_pool_checkout_timeout_fast_fails_when_pool_is_saturated() -> None:
    dsn = os.environ.get("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN is required for pool timeout integration test")

    engine = make_async_engine(
        Settings(
            pg_dsn=dsn,
            pg_pool_size=1,
            pg_max_overflow=0,
            pg_pool_timeout_ms=50,
            pg_query_metrics_enabled=False,
        )
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

            started = perf_counter()
            with pytest.raises(SQLAlchemyTimeoutError):
                async with engine.connect():
                    pass
            elapsed_ms = (perf_counter() - started) * 1_000

        assert elapsed_ms < 500
    finally:
        await engine.dispose()
