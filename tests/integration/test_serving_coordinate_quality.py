"""실제 PostGIS에서 원본 보존·대체 검증·미격리 오류 차단을 검증한다."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.geometry_repo import _BUILDING_GEOMETRY_SQL
from kortravelgeo.infra.serving_quality import (
    ACTIVE_RUN_SQL,
    _prepare_serving_quality,
    require_serving_quality,
)
from kortravelgeo.infra.sql import MV_SQL
from kortravelgeo.loaders.consistency import CASE_SQL, _severity, run_case
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

ADDRESS = "31110114430722400000100000"
PHYSICAL = "3111011400103710000000001"


async def _fixture(conn):
    for name in (
        "tl_juso_text",
        "tl_locsum_entrc",
        "tl_roadaddr_entrc",
        "tl_navi_buld_centroid",
        "tl_spbd_buld_polygon",
        "tl_kodis_bas",
        "tl_scco_emd",
        "load_manifest",
        "serving_quality_runs",
        "serving_coordinate_quarantine",
    ):
        await conn.execute(
            text(
                f"CREATE TEMP TABLE {name} (LIKE public.{name} "
                "INCLUDING DEFAULTS INCLUDING GENERATED) ON COMMIT DROP"
            )
        )
    await conn.execute(
        text("""
INSERT INTO tl_juso_text
 (bd_mgt_sn,sig_cd,bjd_cd,rn_cd,buld_se_cd,buld_mnnm,buld_slno,zip_no,source_yyyymm)
VALUES (:address,'31110','3111011400','4307224','0',1,0,'44485','202609')
"""),
        {"address": ADDRESS},
    )
    await conn.execute(
        text("""
INSERT INTO tl_locsum_entrc
 (sig_cd,ent_man_no,bd_mgt_sn,bjd_cd,rn_cd,buld_se_cd,buld_mnnm,buld_slno,
  zip_no,geom,source_file,source_yyyymm)
VALUES ('31110',33524,:address,'3111011400','4307224','0',1,0,'44485',
 ST_SetSRID(ST_MakePoint(1348303.981119,1737872.851913),5179),'원본.txt','202609')
"""),
        {"address": ADDRESS},
    )
    await conn.execute(
        text("""
INSERT INTO tl_spbd_buld_polygon
 (bd_mgt_sn,sig_cd,emd_cd,li_cd,rds_sig_cd,rn_cd,buld_se_cd,buld_mnnm,buld_slno,
  geom,source_yyyymm)
VALUES (:physical,'31110','114','00','31140','4307224','0',1,0,
 ST_Multi(ST_MakeEnvelope(1167000,1732600,1167100,1732700,5179)),'202610')
"""),
        {"physical": PHYSICAL},
    )
    await conn.execute(
        text("""
INSERT INTO tl_kodis_bas (bas_mgt_sn,bas_id,geom) VALUES
 ('검증용구역','44485',ST_Multi(ST_MakeEnvelope(1166000,1732000,1168000,1733000,5179))),
 ('같은우편번호의별도도형','44485',
  ST_Multi(ST_MakeEnvelope(1450000,1749000,1451000,1750000,5179)));
""")
    )
    await conn.execute(
        text("""
INSERT INTO tl_scco_emd (emd_cd,geom) VALUES
 ('31110114',ST_Multi(ST_MakeEnvelope(1166000,1732000,1168000,1733000,5179)))
""")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alternative",
    [
        "verified",
        "none",
        "wrong_month",
        "wrong_address",
        "wrong_bjd",
        "outside_building",
        "outside_zip",
        "outside_emd",
        "boundary",
    ],
)
async def test_invalid_original_never_leaks_and_only_verified_alternative_is_served(alternative):
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN이 지정된 폐기 가능한 DB가 필요하다")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.begin() as conn:
            await _fixture(conn)
            if alternative != "none":
                await conn.execute(
                    text("""
INSERT INTO tl_navi_buld_centroid
 (bd_mgt_sn,sig_cd,bjd_cd,rn_cd,buld_se_cd,buld_mnnm,buld_slno,centroid_5179,
  source_yyyymm,source_file)
VALUES (:physical,'31110',:bjd,'4307224','0',:main,0,ST_SetSRID(ST_MakePoint(:x,:y),5179),
 :month,'검증후보.txt')
"""),
                    {
                        "physical": PHYSICAL,
                        "month": "202610" if alternative == "wrong_month" else "202609",
                        "main": 999 if alternative == "wrong_address" else 1,
                        "bjd": "3111011401" if alternative == "wrong_bjd" else "3111011400",
                        "x": 1167200 if alternative == "outside_building" else 1167030.422728,
                        "y": 1732639.602453,
                    },
                )
            if alternative == "wrong_bjd":
                await conn.execute(text("UPDATE tl_spbd_buld_polygon SET li_cd='01'"))
            if alternative in ("outside_zip", "boundary"):
                x_edge = 1167030.422728 if alternative == "boundary" else 1167020
                await conn.execute(
                    text(
                        "UPDATE tl_kodis_bas SET geom="
                        "ST_Multi(ST_MakeEnvelope(1166000,1732000,:edge,1733000,5179))"
                    ),
                    {"edge": x_edge},
                )
            if alternative == "outside_emd":
                await conn.execute(
                    text(
                        "UPDATE tl_scco_emd SET geom="
                        "ST_Multi(ST_MakeEnvelope(1166000,1732000,1167020,1733000,5179))"
                    )
                )
            original = await conn.scalar(text("SELECT ST_AsEWKB(geom) FROM tl_locsum_entrc"))
            # 수정 전 선택 규칙에서 실제 약 181km 밖 원본이 우선됨을 재현한다.
            before = (await conn.execute(text(CASE_SQL["C4"].sql))).mappings().one()
            if alternative != "wrong_bjd":
                assert before["metric"]["over_500m"] == 1
            await _prepare_serving_quality(conn)
            assert await conn.scalar(text(ACTIVE_RUN_SQL)) is not None
            q = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM serving_coordinate_quarantine WHERE entity_kind='point'"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert q["source_file"] == "원본.txt"
            assert q["source_yyyymm"] == "202609"
            assert q["reasons"]
            assert (
                await conn.scalar(text("SELECT ST_AsEWKB(geom) FROM tl_locsum_entrc")) == original
            )
            select_sql = MV_SQL.split("CREATE MATERIALIZED VIEW mv_geocode_target AS", 1)[1]
            select_sql = select_sql.split("WITH DATA", 1)[0]
            row = (await conn.execute(text(select_sql))).mappings().one()
            replaced = alternative in ("verified", "boundary")
            assert (row["pt_5179"] is not None) is replaced
            assert row["pt_source"] == ("centroid" if replaced else None)
            assert (q["replacement_geom"] is not None) is replaced
            for code in ("C4", "C6", "C7"):
                after = (await conn.execute(text(CASE_SQL[code].sql))).mappings().one()
                assert after["metric"]["error_count"] == 0, (code, dict(after))

            @asynccontextmanager
            async def shared_connection():
                yield conn

            case = await run_case(SimpleNamespace(begin=shared_connection), "C4")
            assert case.count == 1
            assert case.severity == "WARN"
            assert case.metric["quarantined_count"] == 1
            assert case.metric["replaced_count"] == int(replaced)
            assert case.sample[0]["quarantined"] is True
            if replaced:
                assert await conn.scalar(
                    text(
                        "SELECT ST_Equals(replacement_geom,"
                        "ST_SetSRID(ST_MakePoint(1167030.422728,1732639.602453),5179)) "
                        "FROM serving_coordinate_quarantine WHERE entity_kind='point'"
                    )
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("input_change", ["manifest", "direct"])
async def test_new_source_invalidates_quality_without_discarding_previous_audit(input_change):
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN이 지정된 폐기 가능한 DB가 필요하다")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.begin() as conn:
            await _fixture(conn)
            old_run = await _prepare_serving_quality(conn)
            original = await conn.scalar(
                text(
                    "SELECT ST_AsEWKB(original_geom) "
                    "FROM serving_coordinate_quarantine WHERE entity_kind='point'"
                )
            )
            await conn.execute(
                text(
                    "UPDATE tl_locsum_entrc SET geom="
                    "ST_SetSRID(ST_MakePoint(1167030.422728,1732639.602453),5179)"
                )
            )
            if input_change == "manifest":
                await conn.execute(
                    text(
                        "INSERT INTO load_manifest(table_name,source_checksum) "
                        "VALUES ('tl_locsum_entrc','정정된 테스트 원천')"
                    )
                )
                assert await conn.scalar(text(ACTIVE_RUN_SQL)) is None
                with pytest.raises(RuntimeError, match="원천이 변경"):
                    await require_serving_quality(conn, run_id=old_run)
            new_run = await _prepare_serving_quality(conn)
            assert new_run != old_run
            assert str(await conn.scalar(text(ACTIVE_RUN_SQL))) == new_run
            await conn.execute(text("SET LOCAL TIME ZONE 'Asia/Seoul'"))
            await require_serving_quality(conn, run_id=new_run)
            assert (
                await conn.scalar(
                    text(
                        "SELECT ST_AsEWKB(original_geom) "
                        "FROM serving_coordinate_quarantine WHERE run_id=CAST(:run AS uuid) "
                        "AND entity_kind='point'"
                    ),
                    {"run": old_run},
                )
                == original
            )
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM serving_coordinate_quarantine "
                        "WHERE run_id=CAST(:run AS uuid)"
                    ),
                    {"run": new_run},
                )
                == 0
            )
            select_sql = MV_SQL.split("CREATE MATERIALIZED VIEW mv_geocode_target AS", 1)[1]
            row = (await conn.execute(text(select_sql.split("WITH DATA", 1)[0]))).mappings().one()
            assert row["pt_source"] == "entrance"
            assert row["pt_5179"] is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_invalid_primary_navi_can_only_fall_back_to_a_verified_other_building():
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN이 지정된 폐기 가능한 DB가 필요하다")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.begin() as conn:
            await _fixture(conn)
            await conn.execute(text("DELETE FROM tl_locsum_entrc"))
            second = "3111011400103710000000002"
            await conn.execute(
                text("""
INSERT INTO tl_spbd_buld_polygon
 (bd_mgt_sn,sig_cd,emd_cd,li_cd,rds_sig_cd,rn_cd,buld_se_cd,buld_mnnm,buld_slno,geom)
SELECT :second,sig_cd,emd_cd,li_cd,rds_sig_cd,rn_cd,buld_se_cd,buld_mnnm,buld_slno,geom
 FROM tl_spbd_buld_polygon
"""),
                {"second": second},
            )
            for key, x in ((PHYSICAL, 1348303.981119), (second, 1167030.422728)):
                await conn.execute(
                    text("""
INSERT INTO tl_navi_buld_centroid
 (bd_mgt_sn,sig_cd,bjd_cd,rn_cd,buld_se_cd,buld_mnnm,buld_slno,centroid_5179,source_yyyymm)
VALUES (:key,'31110','3111011400','4307224','0',1,0,
 ST_SetSRID(ST_MakePoint(:x,1732639.602453),5179),'202609')
"""),
                    {"key": key, "x": x},
                )
            await _prepare_serving_quality(conn)
            q = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM serving_coordinate_quarantine WHERE entity_kind='point'"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert q["source_kind"] == "navi"
            assert q["source_key"] == PHYSICAL
            assert q["replacement_source_key"] == second
            assert q["replacement_geom"] is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unlinked_polygon_is_preserved_but_unserved_and_unquarantined_error_still_blocks():
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN이 지정된 폐기 가능한 DB가 필요하다")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.begin() as conn:
            await _fixture(conn)
            await conn.execute(text("UPDATE tl_spbd_buld_polygon SET buld_mnnm=999"))
            before = (await conn.execute(text(CASE_SQL["C2"].sql))).mappings().one()
            assert before["metric"]["error_count"] == 1
            await _prepare_serving_quality(conn)
            after = (await conn.execute(text(CASE_SQL["C2"].sql))).mappings().one()
            assert after["count"] == 1  # 원본 위반은 보고서에서 지우지 않는다.
            assert after["metric"]["quarantined_count"] == 1
            assert after["metric"]["error_count"] == 0
            assert _severity("C2", count=1, ratio=1.0, metric=after["metric"]) == "WARN"
            await conn.execute(
                text(
                    "CREATE TEMP TABLE mv_geocode_target ON COMMIT DROP AS "
                    "SELECT * FROM tl_juso_text"
                )
            )
            assert not (
                await conn.execute(
                    _BUILDING_GEOMETRY_SQL,
                    {
                        "bd_mgt_sn": PHYSICAL,
                        "rncode_full": None,
                        "bjd_cd": None,
                        "buld_mnnm": None,
                        "buld_slno": None,
                        "buld_se_cd": None,
                    },
                )
            ).first()
            await conn.execute(
                text(
                    "DELETE FROM serving_coordinate_quarantine WHERE entity_kind='building_polygon'"
                )
            )
            unquarantined = (await conn.execute(text(CASE_SQL["C2"].sql))).mappings().one()
            assert unquarantined["metric"]["error_count"] == 1
            assert _severity("C2", count=1, ratio=1.0, metric=unquarantined["metric"]) == "ERROR"
            assert await conn.scalar(text("SELECT count(*) FROM tl_spbd_buld_polygon")) == 1
    finally:
        await engine.dispose()
