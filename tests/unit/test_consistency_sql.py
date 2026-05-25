from __future__ import annotations

from kraddr.geo.loaders.consistency import CASE_SQL


def test_building_polygon_cases_use_natural_key_not_management_number() -> None:
    c1 = CASE_SQL["C1"].sql
    c2 = CASE_SQL["C2"].sql
    c4 = CASE_SQL["C4"].sql
    c5 = CASE_SQL["C5"].sql

    assert "p.rncode_full = j.rncode_full" in c1
    assert "p.bjd_cd = j.bjd_cd" in c1
    assert "p.bd_mgt_sn = j.bd_mgt_sn" not in c1
    assert "missing_resolve_key" in c2
    assert "'error_count', count" in c2
    assert "JOIN tl_juso_text j ON j.bd_mgt_sn = e.bd_mgt_sn" in c4
    assert "postload.resolve_text_geometry_links()" in c4
    assert "JOIN LATERAL" in c4
    assert "ORDER BY e.geom <-> p.geom" in c4
    assert "WITH distances AS MATERIALIZED" in c4
    assert "'error_count', over_500m" in c4
    assert "best_navi" in c5
    assert "JOIN LATERAL" in c5
    assert "ORDER BY n.centroid_5179 <-> p.geom" in c5


def test_polygon_contains_cases_treat_boundary_points_as_inside() -> None:
    c6 = CASE_SQL["C6"].sql
    c7 = CASE_SQL["C7"].sql

    assert "ST_Covers(bas_geom, geom)" in c6
    assert "ST_Covers(emd_geom, geom)" in c7
    assert "WITH base AS MATERIALIZED" in c6
    assert "violations AS MATERIALIZED" in c6
    assert "WITH base AS MATERIALIZED" in c7
    assert "violations AS MATERIALIZED" in c7
    assert "ST_Contains" not in c6
    assert "ST_Contains" not in c7


def test_road_adjacency_uses_manage_linestring_geometry() -> None:
    c8 = CASE_SQL["C8"].sql

    assert "FROM tl_sprd_manage m" in c8
    assert "m.geom IS NOT NULL" in c8
    assert "ST_DWithin(b.geom, m.geom, 100)" in c8
    assert "JOIN tl_sprd_rw" not in c8
