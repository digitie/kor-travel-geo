from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.augment_harness import (
    JoinKey,
    ShapeFeature,
    ShapeGeometry,
    ShapeStagingSpec,
    StagingColumn,
    copy_shape_features_to_staging,
    measure_keyed_covers,
    measure_keyed_distance,
    recreate_shape_staging_table,
)
from kortravelgeo.settings import Settings


@pytest.mark.asyncio
async def test_real_postgres_augment_harness_copy_and_measure_when_enabled() -> None:
    if os.getenv("KTG_SLOW_REAL_DATA") != "1":
        pytest.skip("set KTG_SLOW_REAL_DATA=1 to run PostGIS augment harness smoke")
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostGIS-enabled test database")

    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            await conn.execute(text("DROP TABLE IF EXISTS _ktg_aug_it_left"))
            await conn.execute(text("DROP TABLE IF EXISTS _ktg_aug_it_right"))
            await conn.execute(text("DROP TABLE IF EXISTS _ktg_aug_it_poly"))

        left_spec = ShapeStagingSpec(
            "_ktg_aug_it_left",
            (StagingColumn("id"),),
            geometry_type="Point",
        )
        right_spec = ShapeStagingSpec(
            "_ktg_aug_it_right",
            (StagingColumn("id"),),
            geometry_type="Point",
        )
        poly_spec = ShapeStagingSpec(
            "_ktg_aug_it_poly",
            (StagingColumn("id"),),
            geometry_type="Polygon",
        )
        await recreate_shape_staging_table(engine, left_spec)
        await recreate_shape_staging_table(engine, right_spec)
        await recreate_shape_staging_table(engine, poly_spec)
        await copy_shape_features_to_staging(
            engine,
            left_spec,
            (
                _feature("A", "POINT (0 0)"),
                _feature("B", "POINT (10 0)"),
            ),
        )
        await copy_shape_features_to_staging(
            engine,
            right_spec,
            (
                _feature("A", "POINT (3 4)"),
                _feature("B", "POINT (10 0)"),
            ),
        )
        await copy_shape_features_to_staging(
            engine,
            poly_spec,
            (_feature("A", "POLYGON ((-1 -1, -1 5, 5 5, 5 -1, -1 -1))"),),
        )

        distance = await measure_keyed_distance(
            engine,
            "_ktg_aug_it_left",
            "_ktg_aug_it_right",
            (JoinKey("id", "id"),),
        )
        covers = await measure_keyed_covers(
            engine,
            "_ktg_aug_it_poly",
            "_ktg_aug_it_left",
            (JoinKey("id", "id"),),
        )

        assert distance.samples == 2
        assert distance.max_m == pytest.approx(5.0)
        assert covers.samples == 1
        assert covers.covered == 1
        assert covers.coverage_ratio == pytest.approx(1.0)
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS _ktg_aug_it_left"))
            await conn.execute(text("DROP TABLE IF EXISTS _ktg_aug_it_right"))
            await conn.execute(text("DROP TABLE IF EXISTS _ktg_aug_it_poly"))
        await engine.dispose()


def _feature(identifier: str, wkt: str) -> ShapeFeature:
    return ShapeFeature(
        record_number=1,
        attributes={"id": identifier},
        geometry=ShapeGeometry(
            record_number=1,
            shape_kind="Point",
            wkt=wkt,
            bbox=None,
            part_count=1,
            point_count=1,
        ),
    )
