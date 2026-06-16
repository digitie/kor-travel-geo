"""T-174 EPSG:5179 ↔ EPSG:4326 projection round-trip precision (opt-in)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kortravelgeo.dto.common import Point
from kortravelgeo.infra.coordinates import (
    ROUNDTRIP_MAX_ERROR_M,
    project_point_5179_to_4326,
    project_point_to_5179,
)
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings

_SAMPLES_5179 = (
    Point(x=953_901.165, y=1_952_030.693),  # 서울
    Point(x=1_143_730.854, y=1_686_047.501),  # 부산
    Point(x=906_150.602, y=1_501_727.102),  # 제주
    Point(x=969_255.0, y=1_940_455.0),  # 국가지점번호 T-166 회귀 샘플
)


@pytest.mark.asyncio
async def test_epsg_5179_4326_roundtrip_precision_stays_sub_millimeter() -> None:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to run actual PostGIS projection round-trip test")

    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.connect() as conn:
            postgis_version = await conn.scalar(text("SELECT postgis_version()"))
        if postgis_version is None:
            pytest.skip("PostGIS is not available")

        for point_5179 in _SAMPLES_5179:
            point_4326 = await project_point_5179_to_4326(engine, point_5179)
            assert point_4326 is not None
            roundtrip_5179 = await project_point_to_5179(engine, point_4326, crs="EPSG:4326")
            assert roundtrip_5179 is not None
            assert abs(roundtrip_5179.x - point_5179.x) <= ROUNDTRIP_MAX_ERROR_M
            assert abs(roundtrip_5179.y - point_5179.y) <= ROUNDTRIP_MAX_ERROR_M
    finally:
        await engine.dispose()
