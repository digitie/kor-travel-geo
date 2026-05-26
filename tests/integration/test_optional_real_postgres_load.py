from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.infra.sql import INDEX_SQL, MV_SQL, SCHEMA_SQL, iter_sql_statements
from kraddr.geo.loaders.postload import resolve_text_geometry_links
from kraddr.geo.loaders.text.daily_juso_loader import load_daily_juso_delta
from kraddr.geo.loaders.text.juso_hangul_loader import load_juso_hangul
from kraddr.geo.loaders.text.locsum_loader import load_locsum
from kraddr.geo.loaders.text.navi_loader import load_navi
from kraddr.geo.settings import Settings

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/python-kraddr-geo/data/juso"),
    Path("/home/digitie/kraddr-geo-data/juso"),
)


@pytest.mark.asyncio
async def test_real_postgres_can_load_actual_juso_samples_when_dsn_is_set() -> None:
    dsn = os.getenv("KRADDR_GEO_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KRADDR_GEO_TEST_PG_DSN to run actual PostgreSQL COPY load")

    data_root = _data_root()
    if data_root is None:
        pytest.skip("actual data/juso directory is not available")
    daily_zip = data_root / "daily" / "20260401_dailyjusukrdata.zip"
    if not daily_zip.exists():
        pytest.skip(f"actual daily juso data is not available: {daily_zip}")

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
        daily_result = await load_daily_juso_delta(
            engine,
            daily_zip,
            limit_per_file=3,
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
            manifest = (
                await conn.execute(
                    text(
                        """
SELECT last_mvmn_de, row_count, source_yyyymm,
       source_set ->> 'unsupported_lnbr_rows' AS unsupported_lnbr_rows
  FROM load_manifest
 WHERE table_name = 'tl_juso_text'
"""
                    )
                )
            ).mappings().one()

        assert juso_count >= 2
        assert daily_result.processed_rows == 3
        assert daily_result.last_mvmn_de == "20260402"
        assert manifest["last_mvmn_de"] == "20260402"
        assert manifest["row_count"] == 3
        assert manifest["source_yyyymm"] == "202604"
        assert manifest["unsupported_lnbr_rows"] == "204"
        assert locsum_count >= 2
        assert navi_build_count >= 2
        assert navi_ent_count >= 1
        assert mv_count is not None and mv_count >= 2
    finally:
        await engine.dispose()


def _data_root() -> Path | None:
    for root in DATA_ROOTS:
        if root.exists():
            return root
    return None
