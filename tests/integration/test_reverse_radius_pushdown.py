"""실제 PostGIS에서 reverse 반경 조기 적용의 결과·경계·동률을 검증한다."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from kortravelgeo.dto.common import Point
from kortravelgeo.dto.region import RegionHint
from kortravelgeo.infra.reverse_repo import ReverseRepository
from tests.integration.test_full_road_address_search import repository as repository


@pytest_asyncio.fixture
async def reverse_repository(repository):
    """기존 disposable-DB guard와 실행별 독립 schema를 재사용한다."""
    engine = repository.engine
    async with engine.begin() as conn:
        statements = """
ALTER TABLE fixture ADD COLUMN pt_5179 geometry(Point,5179);
UPDATE fixture SET
  pt_5179 = CASE WHEN bd_mgt_sn = 'e' THEN NULL ELSE
    ST_SetSRID(ST_MakePoint(1000000 + CASE bd_mgt_sn
      WHEN 'a' THEN 10 WHEN 'b' THEN 10 WHEN 'c' THEN 200
      WHEN 'd' THEN 200.001 WHEN 'f' THEN 1 ELSE 11 END, 2000000),5179)
    END,
  pt_source = CASE WHEN bd_mgt_sn = 'a' THEN 'centroid' ELSE 'entrance' END,
  bjd_cd = CASE WHEN bd_mgt_sn = 'f' THEN '4717034022' ELSE '4717034021' END;
UPDATE fixture SET pt_4326 = ST_Transform(pt_5179,4326);
DROP MATERIALIZED VIEW mv_geocode_target;
CREATE MATERIALIZED VIEW mv_geocode_target AS SELECT * FROM fixture;
CREATE INDEX reverse_fixture_point ON mv_geocode_target USING gist(pt_5179)
  WHERE pt_5179 IS NOT NULL;
ANALYZE mv_geocode_target;
"""
        for statement in statements.split(";"):
            if statement.strip():
                await conn.execute(text(statement))
    yield ReverseRepository(engine)


async def _lookup(repository, *, radius=200, hint=None, limit=5, point=None):
    return await repository.nearest(
        point or Point(x=1000000, y=2000000), crs="EPSG:5179",
        address_type="road", radius_m=radius, limit=limit, region_hint=hint,
    )


@pytest.mark.asyncio
async def test_reverse_includes_radius_edge_and_preserves_tie_order(reverse_repository):
    rows = await _lookup(reverse_repository)
    assert [r.bd_mgt_sn for r in rows] == ["f", "b", "a", "g", "c"]
    assert [r.distance_m for r in rows] == pytest.approx([1, 10, 10, 11, 200])


@pytest.mark.asyncio
async def test_reverse_filters_region_before_limit_and_keeps_inclusive_radius(reverse_repository):
    hint = RegionHint(bjd_cd="4717034021")
    rows = await _lookup(reverse_repository, radius=10, hint=hint, limit=1)
    assert [r.bd_mgt_sn for r in rows] == ["b"]
    rows = await _lookup(reverse_repository, radius=200, hint=hint)
    assert [r.bd_mgt_sn for r in rows] == ["b", "a", "g", "c"]


@pytest.mark.asyncio
async def test_reverse_empty_radius_does_not_return_null_or_far_points(reverse_repository):
    rows = await _lookup(reverse_repository, point=Point(x=1100000, y=2100000))
    assert rows == []


@pytest.mark.asyncio
async def test_reverse_dense_equal_distance_does_not_drop_preferred_entrance(reverse_repository):
    """후보 상한보다 같은 거리 주소가 많아도 출입구 우선순위를 유지한다."""
    async with reverse_repository.engine.begin() as conn:
        await conn.execute(text("""
INSERT INTO fixture
 (bd_mgt_sn, rncode_full, rn, buld_mnnm, buld_slno, buld_se_cd,
  bjd_cd, adm_cd, adm_kor_nm, mntn_yn, lnbr_mnnm, lnbr_slno,
  zip_no, si_nm, sgg_nm, emd_nm, li_nm, pnu, pt_source, pt_5179, pt_4326)
SELECT CASE WHEN n = 100 THEN 'zz-entrance' ELSE 'tie-' || n::text END,
 b.rncode_full, b.rn, b.buld_mnnm, b.buld_slno, b.buld_se_cd,
 b.bjd_cd, b.adm_cd, b.adm_kor_nm, b.mntn_yn, b.lnbr_mnnm, b.lnbr_slno,
 b.zip_no, b.si_nm, b.sgg_nm, b.emd_nm, b.li_nm, b.pnu,
 CASE WHEN n = 100 THEN 'entrance' ELSE 'centroid' END, b.pt_5179, b.pt_4326
 FROM fixture b CROSS JOIN generate_series(1,100) n
 WHERE b.bd_mgt_sn = 'b'
"""))
        await conn.execute(text("REFRESH MATERIALIZED VIEW mv_geocode_target"))
    rows = await _lookup(
        reverse_repository, radius=10, hint=RegionHint(bjd_cd="4717034021"), limit=2,
    )
    assert [r.bd_mgt_sn for r in rows] == ["b", "zz-entrance"]
