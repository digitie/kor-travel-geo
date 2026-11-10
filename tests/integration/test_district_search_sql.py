"""행정구역 이름 후보 SQL(``_DISTRICT_SEARCH_SQL``)을 실제 PostGIS fixture에서 검증한다.

2026-11-10 geocode 504 수정(대표점을 페이지 뒤로, title 공백 제거 1회, 길이 하한)이 점수·순서·
total·대표점·지역 힌트를 바꾸지 않았는지 본다.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from kortravelgeo.dto.region import RegionHint
from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.infra.search_repo import SearchRepository
from kortravelgeo.settings import Settings
from tests.integration._pg_guard import require_disposable_database

# (table, code column, name column, code, name, envelope origin x or None=EMPTY)
_ROWS = [
    ("tl_scco_ctprvn", "ctprvn_cd", "ctp_kor_nm", "11", "서울특별시", 0),
    ("tl_scco_ctprvn", "ctprvn_cd", "ctp_kor_nm", "41", "경기도", 100),
    ("tl_scco_ctprvn", "ctprvn_cd", "ctp_kor_nm", "51", "강원특별자치도", 200),
    ("tl_scco_sig", "sig_cd", "sig_kor_nm", "11110", "종로구", 300),
    ("tl_scco_sig", "sig_cd", "sig_kor_nm", "41111", "수원시 장안구", 400),
    ("tl_scco_sig", "sig_cd", "sig_kor_nm", "51760", "평창군", 500),
    ("tl_scco_emd", "emd_cd", "emd_kor_nm", "11110101", "청운동", 600),
    ("tl_scco_emd", "emd_cd", "emd_kor_nm", "41111131", "이목동", 700),
    ("tl_scco_emd", "emd_cd", "emd_kor_nm", "51760380", "대관령면", 800),
    ("tl_scco_li", "li_cd", "li_kor_nm", "5176038024", "횡계리", 900),
    ("tl_scco_li", "li_cd", "li_kor_nm", "5176038023", "용산리", None),
]


@pytest_asyncio.fixture
async def repository():
    dsn = os.getenv("KTG_TEST_PG_DSN")
    if not dsn:
        pytest.skip("set KTG_TEST_PG_DSN to a disposable PostGIS database")
    admin = make_async_engine(Settings(pg_dsn=dsn))
    schema = "district_search_" + uuid4().hex
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
            for table, code_col, name_col in {(r[0], r[1], r[2]) for r in _ROWS}:
                await conn.execute(text(
                    f"CREATE TABLE {table} ({code_col} text PRIMARY KEY, {name_col} text, "
                    "geom geometry(Geometry,5179))"
                ))
            for table, code_col, name_col, code, name, origin in _ROWS:
                geom = (
                    "ST_GeomFromText('POLYGON EMPTY', 5179)"
                    if origin is None
                    else "ST_SetSRID(ST_MakeEnvelope(:x0, 2000000, :x0 + 10, 2000010), 5179)"
                )
                await conn.execute(
                    text(f"INSERT INTO {table} VALUES (:code, :name, {geom})"),
                    {"code": code, "name": name, "x0": 1000000 + (origin or 0)},
                )
        yield SearchRepository(engine)
    finally:
        if engine is not None:
            await engine.dispose()
        if created:
            async with admin.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def _search(repo, query, *, page=1, size=10, region_hint=None):
    rows, total = await repo.search(
        query, search_type="district", page=page, size=size, region_hint=region_hint
    )
    return [(row.lookup.bd_mgt_sn.removeprefix("region:"), row.score) for row in rows], total


@pytest.mark.asyncio
async def test_district_scores_order_and_total(repository):
    # 공백 든 시군구 이름(수원시 장안구)도 공백을 빼고 맞춘다 — leaf 일치 0.98, 포함 0.85.
    assert await _search(repository, "수원시 장안구") == (
        [("41111", 0.98), ("41111131", 0.85)],
        2,
    )
    assert await _search(repository, "경기도수원시장안구") == (
        [("41111", 1.0), ("41111131", 0.85)],
        2,
    )
    # 뒤끝 일치(0.95)는 title 끝, 포함(0.85)은 중간이다.
    rows, total = await _search(repository, "평창군대관령면")
    assert total == 3
    assert rows[0] == ("51760380", 0.95)
    assert {code for code, _ in rows[1:]} == {"5176038023", "5176038024"}
    assert {score for _, score in rows[1:]} == {0.85}


@pytest.mark.asyncio
async def test_district_full_address_longer_than_any_title_has_no_candidates(repository):
    assert await _search(repository, "강원특별자치도 평창군 대관령면 올림픽로 123") == ([], 0)


@pytest.mark.asyncio
async def test_district_like_wildcards_are_not_dropped_by_length_floor(repository):
    # '%'가 많아 입력은 어떤 title보다 길지만 LIKE로는 맞는다 — 길이 하한은 '%'를 세지 않는다.
    query = "종로" + "%" * 30 + "운동"
    assert await _search(repository, query) == ([("11110101", 0.85)], 1)
    assert await _search(repository, "서울%구") == ([("11110", 0.85), ("11110101", 0.85)], 2)


@pytest.mark.asyncio
async def test_district_pagination_keeps_total(repository):
    first, total = await _search(repository, "대관령면", size=1)
    assert (first, total) == ([("51760380", 0.98)], 3)
    second, total = await _search(repository, "대관령면", page=2, size=1)
    assert total == 3
    assert len(second) == 1
    assert second[0][0] in {"5176038023", "5176038024"}
    assert await _search(repository, "대관령면", page=4, size=1) == ([], 0)


@pytest.mark.asyncio
async def test_district_point_comes_from_matching_level_and_empty_geometry_is_null(repository):
    rows, _ = await repository.search("횡계리", search_type="district", page=1, size=10)
    assert [row.lookup.bd_mgt_sn for row in rows] == ["region:5176038024"]
    point = rows[0].lookup.point
    assert point is not None
    async with repository.engine.connect() as conn:
        expected = (
            await conn.execute(text(
                "SELECT ST_X(p), ST_Y(p) FROM (SELECT ST_Transform(ST_PointOnSurface(geom), 4326)"
                " AS p FROM tl_scco_li WHERE li_cd = '5176038024') s"
            ))
        ).one()
    assert (point.x, point.y) == pytest.approx(tuple(expected))

    rows, _ = await repository.search("용산리", search_type="district", page=1, size=10)
    assert [row.lookup.bd_mgt_sn for row in rows] == ["region:5176038023"]
    assert rows[0].lookup.point is None


@pytest.mark.asyncio
async def test_district_region_hint_filters_before_ranking(repository):
    assert await _search(repository, "청운동", region_hint=RegionHint(sig_cd="41111")) == ([], 0)
    assert await _search(repository, "청운동", region_hint=RegionHint(sig_cd="11110")) == (
        [("11110101", 0.98)],
        1,
    )
