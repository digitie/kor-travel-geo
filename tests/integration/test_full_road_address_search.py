"""전체 도로명 검색을 독립된 PostGIS fixture에서 검증한다."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from kortravelgeo.dto.region import RegionHint
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.search_repo import SearchRepository
from kortravelgeo.infra.sql import ROAD_ADDRESS_INDEX_SQL
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database


@pytest_asyncio.fixture
async def repository():
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostGIS database")
    admin = make_async_engine(Settings(pg_dsn=dsn))
    schema = "address_search_" + uuid4().hex
    engine = None
    created = False
    try:
        await require_disposable_database(admin)
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = make_async_engine(
            Settings(pg_dsn=dsn, pg_search_path=f"{schema},x_extension,public")
        )
        async with engine.begin() as conn:
            await conn.execute(text("""
CREATE TABLE fixture (
 bd_mgt_sn text, rncode_full text, rn text, rn_nrm text,
 buld_mnnm integer, buld_slno integer, buld_se_cd text,
 buld_nm text, buld_nm_nrm text, sigungu_buld_nm_nrm text,
 bjd_cd text, adm_cd text, adm_kor_nm text, mntn_yn text,
 lnbr_mnnm integer, lnbr_slno integer, zip_no text,
 si_nm text, sgg_nm text, emd_nm text, li_nm text,
 pnu text, pt_source text, pt_4326 geometry(Point,4326)
)
"""))
            # 같은 도로의 본번·부번·지하, 다른 읍면·시도와 동명 건물을 함께 둔다.
            for key, main, sub, underground, sido, district, town in [
                ("a", 40, 0, "0", "경상북도", "안동시", "풍천면"),
                ("b", 40, 0, "0", "경상북도", "안동시", "풍천면"),
                ("c", 40, 2, "0", "경상북도", "안동시", "풍천면"),
                ("d", 40, 2, "1", "경상북도", "안동시", "풍천면"),
                ("e", 41, 0, "0", "경상북도", "안동시", "풍천면"),
                ("f", 40, 0, "0", "경상북도", "안동시", "다른면"),
                ("g", 40, 0, "0", "경상남도", "안동시", "풍천면"),
            ]:
                await conn.execute(text("""
INSERT INTO fixture
 (bd_mgt_sn, rncode_full, rn, rn_nrm, buld_mnnm, buld_slno, buld_se_cd,
  buld_nm, buld_nm_nrm, sigungu_buld_nm_nrm, bjd_cd, si_nm, sgg_nm,
  emd_nm, li_nm, pt_source, pt_4326)
VALUES (:key, '471703000001', '하회종가길', '하회종가길', :main, :sub,
 :underground, '검색시험건물', '검색시험건물', '안동시검색시험건물',
 '4717034021', :sido, :district, :town, '하회리', 'entrance',
 ST_SetSRID(ST_MakePoint(128.518,36.539),4326))
"""), {"key": key, "main": main, "sub": sub, "underground": underground,
           "sido": sido, "district": district, "town": town})
            await conn.execute(text(
                "CREATE MATERIALIZED VIEW mv_geocode_target AS SELECT * FROM fixture"
            ))
            await conn.execute(text("""
CREATE MATERIALIZED VIEW mv_geocode_text_search AS
SELECT *, left(bjd_cd,5) AS sig_cd, left(bjd_cd,2) AS sido_cd FROM fixture
"""))
        yield SearchRepository(engine)
    finally:
        if engine is not None:
            await engine.dispose()
        if created:
            async with admin.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def ids(repo, query, *, page=1, size=10, region_hint=None):
    rows, total = await repo.search(
        query, search_type="address", page=page, size=size, region_hint=region_hint
    )
    return [row.lookup.bd_mgt_sn for row in rows], total


@pytest.mark.asyncio
@pytest.mark.parametrize("sido", ["경북", "경북도", "경상북도"])
async def test_full_address_alias_returns_exact_buildings(repository, sido):
    rows, total = await ids(repository, f"{sido} 안동시 풍천면 하회종가길 40")
    assert rows == ["a", "b"]
    assert total == 2


@pytest.mark.asyncio
async def test_full_address_pagination_and_region_filter(repository):
    query = "경북 안동시 풍천면 하회종가길 40"
    assert await ids(repository, query, size=1) == (["a"], 2)
    assert await ids(repository, query, page=2, size=1) == (["b"], 2)
    assert await ids(repository, query, page=3, size=1) == ([], 2)
    assert await ids(repository, query, region_hint=RegionHint(sig_cd="11")) == ([], 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(("number", "expected"), [
    ("40-2", ["c"]), ("지하 40-2", ["d"]), ("999", []),
])
async def test_full_address_never_substitutes_another_building(repository, number, expected):
    result = await ids(repository, f"경북 안동시 풍천면 하회종가길 {number}")
    assert result == (expected, len(expected))


@pytest.mark.asyncio
async def test_incomplete_road_and_building_name_search_still_work(repository):
    assert await ids(repository, "하회종가길") == (list("abcdefg"), 7)
    assert await ids(repository, "검색시험건물") == (list("abcdefg"), 7)
    assert await ids(repository, "하회종가") == (list("abcdefg"), 7)


@pytest.mark.asyncio
async def test_numeric_building_name_keeps_exact_name_search(repository):
    async with repository.engine.begin() as conn:
        await conn.execute(text(
            "UPDATE fixture SET buld_nm='서울로7017', buld_nm_nrm='서울로7017' "
            "WHERE bd_mgt_sn='e'"
        ))
        for relation in ("mv_geocode_target", "mv_geocode_text_search"):
            await conn.execute(text(f"REFRESH MATERIALIZED VIEW {relation}"))
    assert await ids(repository, "서울로7017") == (["e"], 1)


@pytest.mark.asyncio
async def test_basement_floor_detail_is_not_underground_building(repository):
    assert await ids(repository, "경북 안동시 풍천면 하회종가길 40 지하1층") == (["a", "b"], 2)


@pytest.mark.asyncio
async def test_numbered_road_keeps_its_identity(repository):
    async with repository.engine.begin() as conn:
        await conn.execute(text(
            "UPDATE fixture SET rn='올림픽로35가길', rn_nrm='올림픽로35가길', "
            "buld_mnnm=10 WHERE bd_mgt_sn='a'"
        ))
        await conn.execute(text(
            "UPDATE fixture SET rn='올림픽로', rn_nrm='올림픽로', "
            "buld_mnnm=35 WHERE bd_mgt_sn='b'"
        ))
        await conn.execute(text(
            "UPDATE fixture SET rn='하회종가길40번길', rn_nrm='하회종가길40번길' "
            "WHERE bd_mgt_sn='e'"
        ))
        for relation in ("mv_geocode_target", "mv_geocode_text_search"):
            await conn.execute(text(f"REFRESH MATERIALIZED VIEW {relation}"))
    assert await ids(repository, "올림픽로35가길 10") == (["a"], 1)
    assert await ids(repository, "하회종가길40번길") == (["e"], 1)


@pytest.mark.asyncio
async def test_compound_road_index_preserves_exact_total_options_and_null_point(repository):
    async with repository.engine.begin() as conn:
        await conn.execute(text("UPDATE fixture SET pt_4326=NULL WHERE bd_mgt_sn='b'"))
        await conn.execute(text("REFRESH MATERIALIZED VIEW mv_geocode_target"))
    cases = [
        ("경북 안동시 풍천면 하회종가길 40", {}),
        ("경북 안동시 풍천면 하회종가길 40", {"page": 2, "size": 1}),
        ("경북 안동시 풍천면 하회종가길 지하 40-2", {}),
        ("경북 안동시 풍천면 하회종가길 40-2", {}),
        ("경북 안동시 풍천면 하회종가길 40", {"region_hint": RegionHint(sig_cd="11")}),
        ("경북 안동시 풍천면 하회종가길 999", {}),
        ("하회종가길", {}),
    ]
    before = [await ids(repository, query, **options) for query, options in cases]
    assert before[:4] == [(["a", "b"], 2), (["b"], 2), (["d"], 1), (["c"], 1)]
    async with repository.engine.begin() as conn:
        await conn.execute(text(ROAD_ADDRESS_INDEX_SQL))
        # 새 DB 생성과 동일한 DDL이며 반복 적용과 일반 MV refresh도 견뎌야 한다.
        await conn.execute(text(ROAD_ADDRESS_INDEX_SQL))
        await conn.execute(text("REFRESH MATERIALIZED VIEW mv_geocode_target"))
        definition = await conn.scalar(text("""
SELECT indexdef FROM pg_indexes
 WHERE schemaname=current_schema() AND indexname='idx_mv_road_address_exact'
"""))
        assert "(rn_nrm text_pattern_ops, buld_mnnm, buld_slno, buld_se_cd)" in definition
    assert [await ids(repository, query, **options) for query, options in cases] == before
