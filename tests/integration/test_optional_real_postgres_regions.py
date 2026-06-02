from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kraddr.geo import AsyncAddressClient
from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.settings import Settings

if TYPE_CHECKING:
    from kraddr.geo.dto.v2 import RegionWithinRadiusItem


@pytest.mark.asyncio
async def test_real_postgres_regions_within_radius_contains_actual_admin_regions() -> None:
    dsn = os.getenv("KRADDR_GEO_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KRADDR_GEO_TEST_PG_DSN to run actual PostgreSQL region radius lookup")

    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.connect() as conn:
            required_tables = (
                await conn.execute(
                    text(
                        """
SELECT to_regclass('tl_scco_ctprvn') AS ctprvn,
       to_regclass('tl_scco_sig') AS sig,
       to_regclass('tl_scco_emd') AS emd
"""
                    )
                )
            ).mappings().one()
            if not all(required_tables.values()):
                pytest.skip("actual administrative region tables are not available")

            sample = (
                await conn.execute(
                    text(
                        """
SELECT left(e.emd_cd, 2) AS sido_code,
       left(e.emd_cd, 5) AS sigungu_code,
       e.emd_cd AS emd_code,
       ST_X(ST_Transform(ST_PointOnSurface(e.geom), 4326)) AS lon,
       ST_Y(ST_Transform(ST_PointOnSurface(e.geom), 4326)) AS lat
  FROM tl_scco_emd e
 WHERE e.geom IS NOT NULL
   AND NOT ST_IsEmpty(e.geom)
 ORDER BY e.emd_cd
 LIMIT 1
"""
                    )
                )
            ).mappings().first()
            if sample is None:
                pytest.skip("actual administrative region geometry rows are not available")

        async with AsyncAddressClient(engine=engine) as client:
            response = await client.regions_within_radius(
                lon=float(sample["lon"]),
                lat=float(sample["lat"]),
                radius_km=0.2,
                levels=("sido", "sigungu", "emd"),
            )

        assert response.center.lon == pytest.approx(float(sample["lon"]))
        assert response.center.lat == pytest.approx(float(sample["lat"]))
        assert response.radius_km == pytest.approx(0.2)
        assert _contains(response.sido, str(sample["sido_code"]))
        assert _contains(response.sigungu, str(sample["sigungu_code"]))
        assert _contains(response.emd, str(sample["emd_code"]))
    finally:
        await engine.dispose()


def _contains(items: tuple[RegionWithinRadiusItem, ...], code: str) -> bool:
    return any(item.code == code and item.relation == "contains" for item in items)
