"""대표 좌표 선택을 생성 입력으로 검증하고 불필요한 NAVI 읽기를 차단한다."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.serving_quality import RAW_POINT_CTES
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database


def _inputs(varied: bool) -> str:
    mode = "true" if varied else "false"
    return f"""
fixture AS MATERIALIZED (
 SELECT g, '주소-'||g::text AS bd_mgt_sn,
        CASE WHEN {mode} AND g%19=0 THEN NULL ELSE '311104307224' END::text AS rncode_full,
        CASE WHEN {mode} AND g%7=0 THEN NULL ELSE '0' END::text AS buld_se_cd,
        CASE WHEN {mode} AND g%11=0 THEN NULL ELSE g END AS buld_mnnm,
        CASE WHEN {mode} AND g%13=0 THEN NULL ELSE 0 END AS buld_slno,
        '3111011400'::text AS bjd_cd,'202609'::text AS source_yyyymm
   FROM generate_series(1,500) g
),
tl_juso_text AS MATERIALIZED (SELECT * FROM fixture),
tl_locsum_entrc AS MATERIALIZED (
 SELECT bd_mgt_sn,g AS ent_man_no,'31110'::text AS sig_cd,
        CASE WHEN {mode} AND g%5=1 THEN NULL::geometry
             WHEN {mode} AND g%23=0 THEN ST_GeomFromText('POINT EMPTY',5179)
             ELSE ST_SetSRID(ST_MakePoint(1000000+g,1700000),5179) END AS geom,
        '위치정보 입력'::text AS source_file,source_yyyymm,'0'::text AS ent_se_cd
   FROM fixture WHERE NOT ({mode} AND g%5=0)
),
tl_roadaddr_entrc AS MATERIALIZED (
 SELECT bd_mgt_sn,g+10000 AS ent_man_no,ST_SetSRID(ST_MakePoint(1200000+g,1700000),5179) AS geom,
        '출입구 입력'::text AS source_file,
        CASE WHEN g%10=0 THEN '202610' ELSE '202609' END::text AS source_yyyymm
   FROM fixture
),
tl_navi_buld_centroid AS MATERIALIZED (
 SELECT 'N-'||lpad(g::text,6,'0')||v::text AS bd_mgt_sn,rncode_full,buld_se_cd,buld_mnnm,buld_slno,
        CASE WHEN v=2 THEN left(bjd_cd,8)||'01' ELSE bjd_cd END AS bjd_cd,
        CASE WHEN {mode} AND g%17=0 AND v=1 THEN NULL::geometry
             ELSE ST_SetSRID(ST_MakePoint(1100000+g+v,1700000),5179) END AS centroid_5179,
        'NAVI 입력'::text AS source_file,
        CASE WHEN g%29=0 THEN '202610' ELSE source_yyyymm END::text AS source_yyyymm
   FROM fixture CROSS JOIN generate_series(1,2) v
)
"""


def _selection(varied: bool) -> str:
    return (
        "WITH "
        + _inputs(varied)
        + ","
        + RAW_POINT_CTES
        + """
SELECT bd_mgt_sn,ST_AsText(geom) AS geom,ent_man_no,source_kind,source_key,
       source_file,source_yyyymm
  FROM raw_serving_points ORDER BY bd_mgt_sn
"""
    )


@asynccontextmanager
async def _connection():
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("KTG_TEST_PG_DSN이 지정된 폐기 가능한 DB가 필요하다")
    engine = make_async_engine(Settings(pg_dsn=dsn))
    try:
        await require_disposable_database(engine)
        async with engine.begin() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            yield conn
    finally:
        await engine.dispose()


def _key(g: int, varied: bool) -> tuple:
    return (
        None if varied and g % 19 == 0 else "311104307224",
        None if varied and g % 7 == 0 else "0",
        None if varied and g % 11 == 0 else g,
        None if varied and g % 13 == 0 else 0,
    )


def _expected(g: int, varied: bool) -> dict:
    row = {"bd_mgt_sn": f"주소-{g}", "ent_man_no": None}
    has_loc = not (varied and g % 5 == 0)
    has_road = g % 10 != 0
    if has_loc:
        row["ent_man_no"] = g
        if not (varied and g % 5 == 1):
            geom = "POINT EMPTY" if varied and g % 23 == 0 else f"POINT({1000000 + g} 1700000)"
            return dict(
                row,
                geom=geom,
                source_kind="locsum",
                source_key=f"31110:{g}",
                source_file="위치정보 입력",
                source_yyyymm="202609",
            )
    elif has_road:
        return dict(
            row,
            geom=f"POINT({1200000 + g} 1700000)",
            ent_man_no=g + 10000,
            source_kind="roadaddr",
            source_key=f"주소-{g}",
            source_file="출입구 입력",
            source_yyyymm="202609",
        )
    # 같은 주소키에서는 리 코드 끝 두 자리와 관계없이 가장 작은 원천 ID를 선택한다.
    matches = [
        n
        for n in range(1, 501)
        if _key(g, varied)[0] is not None and _key(n, varied) == _key(g, varied)
    ]
    if not matches:
        return dict(
            row,
            geom=None,
            source_kind="navi",
            source_key=None,
            source_file=None,
            source_yyyymm=None,
        )
    first = matches[0]
    geom = None if varied and first % 17 == 0 else f"POINT({1100001 + first} 1700000)"
    return dict(
        row,
        geom=geom,
        source_kind="navi",
        source_key=f"N-{first:06d}1",
        source_file="NAVI 입력",
        source_yyyymm="202610" if first % 29 == 0 else "202609",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("varied", [False, True])
async def test_source_priority_null_keys_and_first_navi_row_are_preserved(varied):
    async with _connection() as conn:
        actual = [dict(row) for row in (await conn.execute(text(_selection(varied)))).mappings()]
    expected = sorted(
        (_expected(g, varied) for g in range(1, 501)), key=lambda row: row["bd_mgt_sn"]
    )
    assert actual == expected


@pytest.mark.asyncio
async def test_available_entrances_do_not_read_navi_rows():
    async with _connection() as conn:
        plan = (
            await conn.execute(text("EXPLAIN (ANALYZE,FORMAT JSON) " + _selection(False)))
        ).scalar_one()

    def scans(node):
        found = [node] if node.get("CTE Name") == "tl_navi_buld_centroid" else []
        for child in node.get("Plans", []):
            found.extend(scans(child))
        return found

    navi_scans = scans(plan[0]["Plan"])
    assert navi_scans  # 실행되지 않은 NAVI 분기도 계획에는 남아 있어야 한다.
    assert all(node["Actual Loops"] == 0 for node in navi_scans)
