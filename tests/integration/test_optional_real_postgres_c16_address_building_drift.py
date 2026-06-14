from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.c16_address_building_drift import (
    compare_c16_address_building_drift,
    drop_c16_address_building_staging_tables,
)
from kortravelgeo.settings import Settings

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


@pytest.mark.asyncio
async def test_real_postgres_c16_address_building_drift_sample_when_enabled() -> None:
    if os.getenv("KTG_SLOW_REAL_DATA") != "1":
        pytest.skip("set KTG_SLOW_REAL_DATA=1 to run C16 real-data PostGIS smoke")
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a database with serving tables")

    address_zip = _require("202605_주소DB_전체분.zip")
    building_zip = _require("202605_건물DB_전체분.zip")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.connect() as conn:
            for table in ("tl_juso_text", "tl_juso_parcel_link", "tl_spbd_buld_polygon"):
                exists = await conn.scalar(text(f"SELECT to_regclass('public.{table}')"))
                if exists is None:
                    pytest.skip(f"{table} is not available")

        comparison = await compare_c16_address_building_drift(
            engine,
            address_zip,
            building_zip,
            source_yyyymm="202605",
            limit_per_member=2,
            sample_limit=2,
        )

        metrics = comparison.metrics()
        assert comparison.staging_rows.address_db_address == 34
        assert comparison.staging_rows.address_db_jibun == 34
        assert comparison.staging_rows.building_db_build == 34
        assert metrics["coordinate_load"] is False
        assert metrics["serving_promotion"] is False
        assert len(comparison.comparisons) == 6
    finally:
        await drop_c16_address_building_staging_tables(engine)
        await engine.dispose()


def _require(*relatives: str) -> Path:
    for root in DATA_ROOTS:
        for relative in relatives:
            candidate = root / relative
            if candidate.exists():
                return candidate
    pytest.skip("actual juso data not available for C16 optional smoke")
