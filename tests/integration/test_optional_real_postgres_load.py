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
from kraddr.geo.loaders.text.parcel_link_loader import (
    JusoParcelLinkRow,
    discover_daily_lnbr_sources,
    discover_jibun_rnaddrkor_files,
    iter_daily_lnbr_rows,
    iter_jibun_parcel_link_rows,
    load_daily_parcel_link_delta,
    load_juso_parcel_link_snapshot,
)
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
        jibun_file = data_root / "202603_도로명주소 한글_전체분" / "jibun_rnaddrkor_seoul.txt"
        if not jibun_file.exists():
            pytest.skip(f"actual jibun link data is not available: {jibun_file}")
        jibun_rows = list(
            iter_jibun_parcel_link_rows(
                discover_jibun_rnaddrkor_files(jibun_file)[0],
                source_yyyymm="202603",
                limit=2,
            )
        )
        daily_lnbr_rows = list(
            iter_daily_lnbr_rows(
                discover_daily_lnbr_sources(daily_zip)[0],
                source_yyyymm=None,
                limit=5,
            )
        )
        await _insert_text_parents(engine, (*jibun_rows, *daily_lnbr_rows))
        parcel_snapshot = await load_juso_parcel_link_snapshot(
            engine,
            jibun_file,
            source_yyyymm="202603",
            limit_per_file=2,
        )
        parcel_delta = await load_daily_parcel_link_delta(
            engine,
            daily_zip,
            limit_per_file=5,
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
            parcel_manifest = (
                await conn.execute(
                    text(
                        """
SELECT last_mvmn_de, row_count, source_yyyymm,
       source_set ->> 'kind' AS kind,
       source_set ->> 'upserted_rows' AS upserted_rows
  FROM load_manifest
 WHERE table_name = 'tl_juso_parcel_link'
"""
                    )
                )
            ).mappings().one()
            parcel_count = await conn.scalar(text("SELECT count(*) FROM tl_juso_parcel_link"))

        assert juso_count >= 2
        assert daily_result.processed_rows == 3
        assert daily_result.last_mvmn_de == "20260402"
        assert manifest["last_mvmn_de"] == "20260402"
        assert manifest["row_count"] == 3
        assert manifest["source_yyyymm"] == "202604"
        assert manifest["unsupported_lnbr_rows"] == "204"
        assert parcel_snapshot.processed_rows == 2
        assert parcel_snapshot.upserted_rows == 2
        assert parcel_delta.processed_rows == 5
        assert parcel_delta.upserted_rows == 5
        assert parcel_delta.deleted_rows == 0
        assert parcel_manifest["kind"] == "daily_lnbr"
        assert parcel_manifest["last_mvmn_de"] == "20260402"
        assert parcel_manifest["row_count"] == 5
        assert parcel_manifest["source_yyyymm"] == "202604"
        assert parcel_manifest["upserted_rows"] == "5"
        assert parcel_count is not None and parcel_count >= 5
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


async def _insert_text_parents(
    engine,
    rows: tuple[JusoParcelLinkRow, ...],
) -> None:
    async with engine.begin() as conn:
        for row in rows:
            await conn.execute(
                text(
                    """
INSERT INTO tl_juso_text (
  bd_mgt_sn, sig_cd, rn_cd, bjd_cd, mntn_yn, lnbr_mnnm, lnbr_slno,
  source_file, source_yyyymm
) VALUES (
  :bd_mgt_sn, :sig_cd, :rn_cd, :bjd_cd, :mntn_yn, :lnbr_mnnm, :lnbr_slno,
  :source_file, :source_yyyymm
)
ON CONFLICT (bd_mgt_sn) DO NOTHING
"""
                ),
                {
                    "bd_mgt_sn": row.bd_mgt_sn,
                    "sig_cd": row.sig_cd,
                    "rn_cd": row.rn_cd,
                    "bjd_cd": row.bjd_cd,
                    "mntn_yn": row.mntn_yn,
                    "lnbr_mnnm": row.lnbr_mnnm,
                    "lnbr_slno": row.lnbr_slno,
                    "source_file": row.source_file,
                    "source_yyyymm": row.source_yyyymm,
                },
            )
