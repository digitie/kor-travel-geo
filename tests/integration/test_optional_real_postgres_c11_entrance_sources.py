from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.c11_entrance_sources import (
    C11_ELECTRONIC_ENTRANCE_TABLE,
    compare_c11_entrance_sources,
    drop_c11_entrance_staging_tables,
)
from kortravelgeo.settings import Settings

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


@pytest.mark.asyncio
async def test_real_postgres_c11_entrance_sources_sejong_when_enabled() -> None:
    if os.getenv("KTG_SLOW_REAL_DATA") != "1":
        pytest.skip("set KTG_SLOW_REAL_DATA=1 to run C11 real-data PostGIS smoke")
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

        comparison = await compare_c11_entrance_sources(
            engine,
            bundle_zip,
            electronic_dir,
            source_yyyymm="202605",
            sample_limit=3,
            locsum_table=C11_ELECTRONIC_ENTRANCE_TABLE,
            roadaddr_table=C11_ELECTRONIC_ENTRANCE_TABLE,
        )

        assert comparison.sido_name == "세종특별자치시"
        assert comparison.bundle_rows > 0
        assert comparison.electronic_rows > 0
        assert comparison.dbf_exact_key_overlap.intersection_count > 0
        assert all(pair.distance.samples > 0 for pair in comparison.pairs)
        assert comparison.metrics()["serving_promotion"] is False
    finally:
        await drop_c11_entrance_staging_tables(engine)
        await engine.dispose()


def _require(*relatives: str) -> Path:
    for root in DATA_ROOTS:
        for relative in relatives:
            candidate = root / relative
            if candidate.exists():
                return candidate
    pytest.skip("actual juso data not available for C11 optional smoke")
