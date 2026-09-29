"""T-319 원천 기준월 manifest를 실제 PostgreSQL에서 옛 ``max(source_yyyymm)``과 대조 (opt-in).

manifest 조회(`admin_repo.source_yyyymm_by_kind`)가 옛 전수 scan 조회와 같은 값을 내는지를
옛 쿼리 자체를 oracle로 삼아 확인한다.

- legacy DB(적재 row는 있고 manifest 행은 없음) → 조회는 scan하지 않고 None → Alembic 0028
  backfill 뒤에는 oracle과 같다. manifest가 이미 있는 테이블은 scan 노드가 아예 실행되지 않는다.
- 실제 적재기(도로명주소 한글·위치정보요약·내비게이션 건물·SHP 건물 polygon)가 남긴 manifest가
  적재 뒤 oracle과 같다. SHP full 적재의 TRUNCATE는 manifest 행도 지운다.

원천 테이블 7개가 비어 있는 scratch DB가 필요하다(``ktgctl init-db`` + ``alembic stamp head``,
tests/integration/_pg_guard.py 이름 규칙). 비어 있지 않으면 skip — 끝에서 그 7개를 비우기
때문이다::

    KTG_TEST_PG_DSN=postgresql+psycopg://<user>:<password>@127.0.0.1:<port>/kor_travel_geo_test \
        pytest tests/integration/test_t319_source_month_manifest_live.py
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from kortravelgeo.infra.admin_repo import source_yyyymm_by_kind
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.loaders.shp import polygons_loader
from kortravelgeo.loaders.text.juso_hangul_loader import JusoTextRow, copy_juso_rows
from kortravelgeo.loaders.text.locsum_loader import LocsumEntranceRow, copy_locsum_rows
from kortravelgeo.loaders.text.navi_loader import NaviBuildingRow, copy_navi_rows
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

_TABLE_BY_KIND = {
    "juso": "tl_juso_text",
    "parcel_link": "tl_juso_parcel_link",
    "locsum": "tl_locsum_entrc",
    "navi": "tl_navi_buld_centroid",
    "shp": "tl_spbd_buld_polygon",
    "roadaddr_entrance": "tl_roadaddr_entrc",
    "sppn_makarea": "tl_sppn_makarea",
}
_TABLES = tuple(_TABLE_BY_KIND.values())
_MIGRATION_PATH = Path("alembic/versions/0028_t319_source_month_manifest.py")


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("_t319_migration_live", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _fresh_engine() -> AsyncEngine:
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostgreSQL scratch DB")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.connect() as conn:
            for table in _TABLES:
                if await conn.scalar(text(f"SELECT EXISTS (SELECT 1 FROM public.{table})")):
                    pytest.skip(f"{table} has rows; T-319 test needs empty source tables")
    except BaseException:
        await engine.dispose()
        raise
    return engine


async def _reset(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} CASCADE"))
        await conn.execute(
            text("DELETE FROM load_manifest WHERE table_name = ANY(:names)"),
            {"names": list(_TABLES)},
        )


async def _oracle(conn: AsyncConnection) -> dict[str, str | None]:
    """옛 조회 그대로 — 테이블마다 전수 scan."""
    result: dict[str, str | None] = {}
    for kind, table in _TABLE_BY_KIND.items():
        value = await conn.scalar(text(f"SELECT max(source_yyyymm) FROM public.{table}"))
        result[kind] = str(value) if value is not None else None
    return result


async def _insert_legacy_juso(conn: AsyncConnection, months: list[str | None]) -> None:
    """T-319 이전 적재기처럼 row만 쓰고 manifest는 남기지 않는다."""
    for index, month in enumerate(months):
        await conn.execute(
            text(
                "INSERT INTO tl_juso_text (bd_mgt_sn, sig_cd, bjd_cd, rn_cd, source_yyyymm)"
                " VALUES (:sn, '11110', '1111010100', '3100001', :month)"
            ),
            {"sn": f"111101010010001{index:010d}", "month": month},
        )


@pytest.mark.asyncio
async def test_backfill_turns_legacy_db_into_manifest_equal_to_max_scan() -> None:
    engine = await _fresh_engine()
    migration = _load_migration()
    try:
        async with engine.connect() as conn:
            tx = await conn.begin()
            try:
                await _insert_legacy_juso(conn, ["202603", "202605", None])
                # 적재기가 쓴 manifest가 이미 있는 테이블 — backfill은 건드리지도 scan하지도
                # 않는다(값을 일부러 테이블과 다르게 둬 덮어쓰면 드러나게 한다).
                await conn.execute(
                    text(
                        "INSERT INTO load_manifest (table_name, source_yyyymm)"
                        " VALUES ('tl_juso_parcel_link', '202602')"
                    )
                )

                before = await source_yyyymm_by_kind(conn, _TABLE_BY_KIND)
                assert before["juso"] is None  # legacy: scan으로 메우지 않는다
                assert before["parcel_link"] == "202602"

                plan = (
                    await conn.execute(
                        text(
                            "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) "
                            + migration.backfill_sql("tl_juso_parcel_link")
                        )
                    )
                ).scalars().all()
                scan_lines = [
                    line for line in plan if "Scan" in line and "tl_juso_parcel_link" in line
                ]
                assert scan_lines, plan
                assert all("never executed" in line for line in scan_lines), plan

                for table in migration.SOURCE_MONTH_TABLES:
                    await conn.execute(text(migration.backfill_sql(table)))

                after = await source_yyyymm_by_kind(conn, _TABLE_BY_KIND)
                oracle = await _oracle(conn)
                assert after["juso"] == oracle["juso"] == "202605"
                assert after["parcel_link"] == "202602"  # 기존 행 그대로
                for kind in ("locsum", "navi", "shp", "roadaddr_entrance", "sppn_makarea"):
                    assert after[kind] is None
                    assert oracle[kind] is None
                row = (
                    await conn.execute(
                        text(
                            "SELECT row_count, source_set ->> 'kind' AS kind"
                            "  FROM load_manifest WHERE table_name = 'tl_juso_text'"
                        )
                    )
                ).mappings().one()
                assert row["row_count"] == 3
                assert row["kind"] == migration.BACKFILL_KIND
                empty_rows = await conn.scalar(
                    text(
                        "SELECT count(*) FROM load_manifest"
                        " WHERE table_name IN ('tl_locsum_entrc', 'tl_navi_buld_centroid',"
                        " 'tl_spbd_buld_polygon', 'tl_roadaddr_entrc', 'tl_sppn_makarea')"
                    )
                )
                assert empty_rows == 0  # 빈 테이블에는 행을 만들지 않는다
            finally:
                await tx.rollback()
    finally:
        await engine.dispose()


def _juso_row(sn_suffix: int, month: str | None) -> JusoTextRow:
    return JusoTextRow(
        bd_mgt_sn=f"111101010010002{sn_suffix:010d}",
        sig_cd="11110",
        rn_cd="3100001",
        ctp_kor_nm=None,
        sig_kor_nm=None,
        emd_kor_nm=None,
        li_kor_nm=None,
        bjd_cd="1111010100",
        adm_cd=None,
        adm_kor_nm=None,
        rn=None,
        buld_se_cd=None,
        buld_mnnm=None,
        buld_slno=None,
        buld_nm=None,
        mntn_yn=None,
        lnbr_mnnm=None,
        lnbr_slno=None,
        zip_no=None,
        source_file="t319",
        source_yyyymm=month,
    )


def _locsum_row(ent_man_no: int, month: str | None) -> LocsumEntranceRow:
    return LocsumEntranceRow(
        sig_cd="11110",
        ent_man_no=ent_man_no,
        bjd_cd="1111010100",
        ctp_kor_nm=None,
        sig_kor_nm=None,
        emd_kor_nm=None,
        rn_cd="3100001",
        rn=None,
        buld_se_cd=None,
        buld_mnnm=None,
        buld_slno=None,
        zip_no=None,
        buld_use=None,
        ent_se_cd=None,
        adm_kor_nm=None,
        x_5179=953000.0,
        y_5179=1952000.0,
        source_file="t319",
        source_yyyymm=month,
    )


def _navi_row(sn_suffix: int, month: str | None) -> NaviBuildingRow:
    return NaviBuildingRow(
        bjd_cd="1111010100",
        ctp_kor_nm=None,
        sig_kor_nm=None,
        emd_kor_nm=None,
        sig_cd="11110",
        rn_cd="3100001",
        rn=None,
        buld_se_cd=None,
        buld_mnnm=None,
        buld_slno=None,
        zip_no=None,
        bd_mgt_sn=f"111101010010003{sn_suffix:010d}",
        buld_nm=None,
        sigungu_buld_nm=None,
        buld_use=None,
        adm_cd=None,
        adm_kor_nm=None,
        centroid_x=953000.0,
        centroid_y=1952000.0,
        entrance_x=None,
        entrance_y=None,
        source_file="t319",
        source_yyyymm=month,
    )


def _stage_buildings(pg_url: str, first_suffix: int, count: int) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(pg_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL search_path = public, x_extension"))
            conn.execute(
                text(f"DROP TABLE IF EXISTS {polygons_loader.BUILDING_POLYGON_STAGE_TABLE}")
            )
            conn.execute(
                text(
                    f"CREATE TABLE {polygons_loader.BUILDING_POLYGON_STAGE_TABLE} ("
                    "  bd_mgt_sn text, sig_cd text, emd_cd text, li_cd text, rds_sig_cd text,"
                    "  rn_cd text, buld_se_cd text, buld_mnnm text, buld_slno text,"
                    "  geom geometry(MultiPolygon, 5179))"
                )
            )
            for suffix in range(first_suffix, first_suffix + count):
                conn.execute(
                    text(
                        f"INSERT INTO {polygons_loader.BUILDING_POLYGON_STAGE_TABLE}"
                        " (bd_mgt_sn, geom) VALUES (:sn, ST_GeomFromText("
                        "'MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))', 5179))"
                    ),
                    {"sn": f"111101010010004{suffix:010d}"},
                )
    finally:
        engine.dispose()


def _building_plan(month: str) -> polygons_loader.ShpLoadPlan:
    return polygons_loader.ShpLoadPlan(
        source_layer=polygons_loader.BUILDING_POLYGON_LAYER_NAME,
        target_table="tl_spbd_buld_polygon",
        shp_path=Path("TL_SPBD_BULD.shp"),
        dbf_path=Path("TL_SPBD_BULD.dbf"),
        source_file="t319/TL_SPBD_BULD.shp",
        source_yyyymm=month,
    )


@pytest.mark.asyncio
async def test_real_loaders_keep_manifest_equal_to_max_scan() -> None:
    engine = await _fresh_engine()
    pg_url = engine.url.render_as_string(hide_password=False)
    try:
        # 도로명주소 한글: 적재 row 최댓값(NULL 무시)
        await copy_juso_rows(engine, [_juso_row(1, "202606"), _juso_row(2, None)])
        await copy_juso_rows(engine, [_juso_row(3, "202607"), _juso_row(4, "202605")])
        await copy_locsum_rows(engine, [_locsum_row(1, "202604"), _locsum_row(2, "202604")])
        await copy_navi_rows(engine, [_navi_row(1, "202604")], [])

        # SHP 건물: full(TRUNCATE) → 시도 두 번 append. row_count는 누적해 테이블 행 수와 같다.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO load_manifest (table_name, source_yyyymm, row_count)"
                    " VALUES ('tl_spbd_buld_polygon', '209912', 99)"
                )
            )
        polygons_loader._truncate_target_tables(pg_url, ("tl_spbd_buld_polygon",))
        async with engine.connect() as conn:
            assert (await source_yyyymm_by_kind(conn, _TABLE_BY_KIND))["shp"] is None
        for first_suffix, count in ((1, 2), (3, 3)):
            _stage_buildings(pg_url, first_suffix, count)
            polygons_loader._insert_building_polygon_stage(pg_url, _building_plan("202604"))
        polygons_loader._drop_stage_table(pg_url, polygons_loader.BUILDING_POLYGON_STAGE_TABLE)

        async with engine.connect() as conn:
            looked_up = await source_yyyymm_by_kind(conn, _TABLE_BY_KIND)
            oracle = await _oracle(conn)
            shp_rows = await conn.scalar(text("SELECT count(*) FROM tl_spbd_buld_polygon"))
            shp_manifest_rows = await conn.scalar(
                text(
                    "SELECT row_count FROM load_manifest"
                    " WHERE table_name = 'tl_spbd_buld_polygon'"
                )
            )
        assert looked_up == oracle
        assert looked_up["juso"] == "202607"
        assert looked_up["locsum"] == "202604"
        assert looked_up["navi"] == "202604"
        assert looked_up["shp"] == "202604"
        assert shp_rows == shp_manifest_rows == 5
    finally:
        try:
            await _reset(engine)
        finally:
            await engine.dispose()
