from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.c13_detail_dong import (
    compare_c13_detail_dong_containment,
    drop_c13_detail_dong_staging_tables,
)
from kortravelgeo.settings import Settings

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


@pytest.mark.asyncio
async def test_real_postgres_c13_detail_dong_sejong_when_enabled() -> None:
    if os.getenv("KTG_SLOW_REAL_DATA") != "1":
        pytest.skip("set KTG_SLOW_REAL_DATA=1 to run C13 real-data PostGIS smoke")
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostGIS-enabled test database")

    detail_dong_zip = _require(
        "건물군 내 상세주소 동 도형/202604/건물군내동도형_전체분_세종특별자치시.zip",
        "건물군 내 상세주소 동 도형/건물군내동도형_전체분_세종특별자치시.zip",
    )
    detail_address_zip = _require(
        "202605_상세주소DB_전체분.zip",
        "202604_상세주소DB_전체분.zip",
    )
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

        comparison = await compare_c13_detail_dong_containment(
            engine,
            detail_dong_zip,
            detail_address_zip,
            sido_name="세종특별자치시",
            source_yyyymm="202605",
            sample_limit=3,
        )

        assert comparison.sido_name == "세종특별자치시"
        assert comparison.detail_dong_rows > 0
        assert comparison.detail_entrance_rows > 0
        assert comparison.detail_address_rows > 0
        assert comparison.entrance_building_ref_overlap.intersection_count > 0
        assert comparison.entrance_containment.samples > 0
        assert comparison.metrics()["serving_promotion"] is False
    finally:
        await drop_c13_detail_dong_staging_tables(engine)
        await engine.dispose()


def _require(*relatives: str) -> Path:
    for root in DATA_ROOTS:
        for relative in relatives:
            candidate = root / relative
            if candidate.exists():
                return candidate
    pytest.skip("actual juso data not available for C13 optional smoke")
