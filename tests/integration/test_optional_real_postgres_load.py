from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import text

from kraddr.geo.core.geocoder import geocode
from kraddr.geo.core.sppn import format_national_point_number_from_5179
from kraddr.geo.dto.common import Point
from kraddr.geo.dto.geocode import GeocodeInput
from kraddr.geo.infra.engine import make_async_engine
from kraddr.geo.infra.geocode_repo import GeocodeRepository
from kraddr.geo.infra.reverse_repo import ReverseRepository
from kraddr.geo.infra.sql import INDEX_SQL, MV_SQL, SCHEMA_SQL, iter_sql_statements
from kraddr.geo.loaders.postload import resolve_text_geometry_links
from kraddr.geo.loaders.sppn_makarea_loader import load_sppn_makarea
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
from kraddr.geo.loaders.text.roadaddr_entrance_loader import (
    RoadAddrEntranceRow,
    discover_roadaddr_entrance_sources,
    iter_roadaddr_entrance_rows,
    load_roadaddr_entrances,
)
from kraddr.geo.settings import Settings

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/python-kraddr-geo/data/juso"),
    Path("/home/digitie/kraddr-geo-data/juso"),
)


@pytest.mark.asyncio
async def test_real_postgres_can_load_sppn_makarea_and_lookup_when_dsn_is_set() -> None:
    dsn = os.getenv("KRADDR_GEO_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KRADDR_GEO_TEST_PG_DSN to run actual PostgreSQL SPPN load")

    data_root = _data_root()
    if data_root is None:
        pytest.skip("actual data/juso directory is not available")
    zone_zip = data_root / "구역의 도형" / "구역의도형_전체분_세종특별자치시.zip"
    if not zone_zip.exists():
        pytest.skip(f"actual zone shape data is not available: {zone_zip}")

    pytest.importorskip("osgeo.gdal")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        async with engine.begin() as conn:
            for sql in iter_sql_statements(SCHEMA_SQL):
                await conn.execute(text(sql))
            for sql in iter_sql_statements(INDEX_SQL):
                await conn.execute(text(sql))

        count = await load_sppn_makarea(engine, zone_zip, source_yyyymm="202605")

        async with engine.connect() as conn:
            summary = (
                await conn.execute(
                    text(
                        """
SELECT count(*) AS rows,
       count(DISTINCT sig_cd || ':' || makarea_id) AS keys,
       bool_and(ST_GeometryType(geom) = 'ST_MultiPolygon') AS all_multipolygon,
       bool_and(ST_IsValid(geom)) AS all_valid
  FROM tl_sppn_makarea
"""
                    )
                )
            ).mappings().one()
            sample = (
                await conn.execute(
                    text(
                        """
SELECT sig_cd, makarea_id, makarea_nm,
       ST_X(ST_PointOnSurface(geom)) AS x5179,
       ST_Y(ST_PointOnSurface(geom)) AS y5179,
       ST_X(ST_Transform(ST_PointOnSurface(geom), 4326)) AS lon,
       ST_Y(ST_Transform(ST_PointOnSurface(geom), 4326)) AS lat
  FROM tl_sppn_makarea
 WHERE makarea_nm IS NOT NULL
 ORDER BY ST_Area(geom) DESC
 LIMIT 1
"""
                    )
                )
            ).mappings().one()

        sppn = format_national_point_number_from_5179(
            Point(x=float(sample["x5179"]), y=float(sample["y5179"]))
        )
        assert sppn is not None
        geocode_response = await geocode(GeocodeRepository(engine), GeocodeInput(address=sppn.text))
        reverse_areas = await ReverseRepository(engine).sppn_areas(
            Point(x=float(sample["lon"]), y=float(sample["lat"])),
            crs="EPSG:4326",
            limit=5,
        )

        assert count == 146
        assert summary["rows"] == 146
        assert summary["keys"] == 146
        assert summary["all_multipolygon"] is True
        assert summary["all_valid"] is True
        assert geocode_response.status == "OK"
        assert geocode_response.x_extension is not None
        assert geocode_response.x_extension.national_point_number == sppn.text
        assert geocode_response.x_extension.sppn_makarea is not None
        assert geocode_response.x_extension.sppn_makarea.sig_cd == sample["sig_cd"]
        assert reverse_areas
        assert reverse_areas[0].sig_cd == sample["sig_cd"]
    finally:
        await engine.dispose()


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
        roadaddr_zip = (
            data_root
            / "도로명주소 출입구 정보"
            / "도로명주소출입구_전체분_세종특별자치시.zip"
        )
        if not roadaddr_zip.exists():
            pytest.skip(f"actual roadaddr entrance data is not available: {roadaddr_zip}")
        roadaddr_rows = list(
            iter_roadaddr_entrance_rows(
                discover_roadaddr_entrance_sources(roadaddr_zip)[0],
                source_yyyymm=None,
                limit=3,
            )
        )
        await _insert_roadaddr_text_parents(engine, tuple(roadaddr_rows))
        roadaddr_result = await load_roadaddr_entrances(
            engine,
            roadaddr_zip,
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
            roadaddr_manifest = (
                await conn.execute(
                    text(
                        """
SELECT row_count, source_yyyymm,
       source_set ->> 'kind' AS kind,
       source_set ->> 'upserted_rows' AS upserted_rows
  FROM load_manifest
 WHERE table_name = 'tl_roadaddr_entrc'
"""
                    )
                )
            ).mappings().one()
            roadaddr_mv = (
                await conn.execute(
                    text(
                        """
SELECT pt_source,
       round(ST_X(pt_5179)::numeric, 6)::float8 AS x_5179,
       round(ST_Y(pt_5179)::numeric, 6)::float8 AS y_5179
  FROM mv_geocode_target
 WHERE bd_mgt_sn = :bd_mgt_sn
"""
                    ),
                    {"bd_mgt_sn": roadaddr_rows[0].bd_mgt_sn},
                )
            ).mappings().one()

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
        assert roadaddr_result.processed_rows == 3
        assert roadaddr_result.upserted_rows == 3
        assert roadaddr_result.source_yyyymm == "202605"
        assert roadaddr_manifest["kind"] == "roadaddr_entrance_full"
        assert roadaddr_manifest["row_count"] == 3
        assert roadaddr_manifest["source_yyyymm"] == "202605"
        assert roadaddr_manifest["upserted_rows"] == "3"
        assert roadaddr_mv["pt_source"] == "entrance"
        assert roadaddr_mv["x_5179"] == pytest.approx(round(roadaddr_rows[0].x_5179, 6))
        assert roadaddr_mv["y_5179"] == pytest.approx(round(roadaddr_rows[0].y_5179, 6))
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


async def _insert_roadaddr_text_parents(
    engine,
    rows: tuple[RoadAddrEntranceRow, ...],
) -> None:
    async with engine.begin() as conn:
        for row in rows:
            await conn.execute(
                text(
                    """
INSERT INTO tl_juso_text (
  bd_mgt_sn, sig_cd, rn_cd, bjd_cd, ctp_kor_nm, sig_kor_nm, emd_kor_nm, li_kor_nm,
  rn, buld_se_cd, buld_mnnm, buld_slno, zip_no, source_file, source_yyyymm
) VALUES (
  :bd_mgt_sn, :sig_cd, :rn_cd, :bjd_cd, :ctp_kor_nm, :sig_kor_nm, :emd_kor_nm,
  :li_kor_nm, :rn, :buld_se_cd, :buld_mnnm, :buld_slno, :zip_no, :source_file,
  :source_yyyymm
)
ON CONFLICT (bd_mgt_sn) DO NOTHING
"""
                ),
                {
                    "bd_mgt_sn": row.bd_mgt_sn,
                    "sig_cd": row.sig_cd,
                    "rn_cd": row.rn_cd,
                    "bjd_cd": row.bjd_cd,
                    "ctp_kor_nm": row.ctp_kor_nm,
                    "sig_kor_nm": row.sig_kor_nm,
                    "emd_kor_nm": row.emd_kor_nm,
                    "li_kor_nm": row.li_kor_nm,
                    "rn": row.rn,
                    "buld_se_cd": row.buld_se_cd,
                    "buld_mnnm": row.buld_mnnm,
                    "buld_slno": row.buld_slno,
                    "zip_no": row.zip_no,
                    "source_file": row.source_file,
                    "source_yyyymm": row.source_yyyymm,
                },
            )
