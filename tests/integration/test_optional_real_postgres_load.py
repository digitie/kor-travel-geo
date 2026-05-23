from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.infra.sql import INDEX_SQL, MV_SQL, SCHEMA_SQL, iter_sql_statements
from kraddr.geo.loaders.postload import resolve_text_geometry_links
from kraddr.geo.loaders.text.juso_hangul_loader import load_juso_hangul
from kraddr.geo.loaders.text.locsum_loader import load_locsum
from kraddr.geo.loaders.text.navi_loader import load_navi
from kraddr.geo.settings import Settings


@pytest.mark.asyncio
async def test_real_postgres_can_load_actual_juso_samples_when_dsn_is_set() -> None:
    dsn = os.getenv("KRADDR_GEO_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KRADDR_GEO_TEST_PG_DSN to run actual PostgreSQL COPY load")

    data_root = Path("data/juso")
    if not data_root.exists():
        pytest.skip("actual data/juso directory is not available")

    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.begin() as conn:
            for sql in iter_sql_statements(SCHEMA_SQL):
                await conn.execute(text(sql))
            for sql in iter_sql_statements(INDEX_SQL):
                await conn.execute(text(sql))
        juso_count = await load_juso_hangul(
            engine,
            data_root / "202603_도로명주소 한글_전체분",
            source_yyyymm="202603",
            limit_per_file=2,
        )
        locsum_count = await load_locsum(
            engine,
            data_root / "202604_위치정보요약DB_전체분.zip",
            source_yyyymm="202604",
            limit_per_file=2,
        )
        navi_build_count, navi_ent_count = await load_navi(
            engine,
            data_root / "202604_내비게이션용DB_전체분",
            source_yyyymm="202604",
            limit_per_file=2,
        )
        await resolve_text_geometry_links(engine)
        async with engine.begin() as conn:
            for sql in iter_sql_statements(MV_SQL):
                await conn.execute(text(sql))
            mv_count = await conn.scalar(text("SELECT count(*) FROM mv_geocode_target"))

        assert juso_count >= 2
        assert locsum_count >= 2
        assert navi_build_count >= 2
        assert navi_ent_count >= 1
        assert mv_count is not None and mv_count >= 2
    finally:
        await engine.dispose()

