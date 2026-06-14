from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.c15_civil_service_poi import (
    compare_c15_civil_service_poi_distance,
    drop_c15_civil_service_poi_staging_tables,
)
from kortravelgeo.settings import Settings

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


@pytest.mark.asyncio
async def test_real_postgres_c15_civil_service_poi_sample_when_enabled() -> None:
    if os.getenv("KTG_SLOW_REAL_DATA") != "1":
        pytest.skip("set KTG_SLOW_REAL_DATA=1 to run C15 real-data PostGIS smoke")
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a PostGIS database with mv_geocode_target")

    civil_zip = _require("민원행정기관전자지도_240124.zip")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.connect() as conn:
            mv_exists = await conn.scalar(text("SELECT to_regclass('public.mv_geocode_target')"))
            if mv_exists is None:
                pytest.skip("mv_geocode_target is not available")
            mv_count = await conn.scalar(text("SELECT count(*)::bigint FROM mv_geocode_target"))
            if not mv_count:
                pytest.skip("mv_geocode_target is empty")

        comparison = await compare_c15_civil_service_poi_distance(
            engine,
            civil_zip,
            source_yyyymm="202401",
            row_limit=100,
            sample_limit=5,
        )

        metrics = comparison.metrics()
        assert comparison.poi_rows == 100
        assert comparison.distance.total_poi_rows == 100
        assert comparison.distance.parsed_address_rows > 0
        assert metrics["serving_promotion"] is False
        assert metrics["geocode_distance_m"]["geocoder_contract"] == "batch_exact_road_lookup"
    finally:
        await drop_c15_civil_service_poi_staging_tables(engine)
        await engine.dispose()


def _require(*relatives: str) -> Path:
    for root in DATA_ROOTS:
        for relative in relatives:
            candidate = root / relative
            if candidate.exists():
                return candidate
    pytest.skip("actual juso data not available for C15 optional smoke")
