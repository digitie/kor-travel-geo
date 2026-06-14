from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.c12_connection_lines import (
    compare_c12_connection_lines,
    drop_c12_connection_staging_tables,
)
from kortravelgeo.settings import Settings

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


@pytest.mark.asyncio
async def test_real_postgres_c12_connection_lines_sejong_when_enabled() -> None:
    if os.getenv("KTG_SLOW_REAL_DATA") != "1":
        pytest.skip("set KTG_SLOW_REAL_DATA=1 to run C12 real-data PostGIS smoke")
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostGIS-enabled test database")

    bundle_zip = _require(
        "도로명주소 건물 도형/건물도형_전체분_세종특별자치시.zip",
        "도로명주소 건물 도형/202604/건물도형_전체분_세종특별자치시.zip",
    )
    electronic_dir = _require(
        "도로명주소 전자지도/세종특별자치시",
        "도로명주소 전자지도/202604/세종특별자치시",
    )
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

        comparison = await compare_c12_connection_lines(
            engine,
            bundle_zip,
            electronic_dir,
            source_yyyymm="202605",
            sample_limit=3,
            tolerance_m=1.0,
        )

        assert comparison.sido_name == "세종특별자치시"
        assert comparison.connection_rows > 0
        assert comparison.road_rows > 0
        assert comparison.entrance_ref_overlap.intersection_count > 0
        assert comparison.road_key_overlap.intersection_count > 0
        assert comparison.road_adjacency.total_connections == comparison.connection_rows
        assert comparison.metrics()["serving_promotion"] is False
    finally:
        await drop_c12_connection_staging_tables(engine)
        await engine.dispose()


def _require(*relatives: str) -> Path:
    for root in DATA_ROOTS:
        for relative in relatives:
            candidate = root / relative
            if candidate.exists():
                return candidate
    pytest.skip("actual juso data not available for C12 optional smoke")
