from __future__ import annotations

from kraddr.geo.loaders.consistency import CASE_SQL


def test_building_polygon_cases_use_natural_key_not_management_number() -> None:
    c1 = CASE_SQL["C1"].sql
    c4 = CASE_SQL["C4"].sql
    c5 = CASE_SQL["C5"].sql

    assert "p.rncode_full = j.rncode_full" in c1
    assert "p.bjd_cd = j.bjd_cd" in c1
    assert "p.bd_mgt_sn = j.bd_mgt_sn" not in c1
    assert "JOIN tl_juso_text j ON j.bd_mgt_sn = e.bd_mgt_sn" in c4
    assert "postload.resolve_text_geometry_links()" in c4
    assert "JOIN LATERAL" in c4
    assert "ORDER BY e.geom <-> p.geom" in c4
    assert "best_navi" in c5
    assert "JOIN LATERAL" in c5
    assert "ORDER BY n.centroid_5179 <-> p.geom" in c5


def test_road_adjacency_uses_manage_linestring_geometry() -> None:
    c8 = CASE_SQL["C8"].sql

    assert "FROM tl_sprd_manage m" in c8
    assert "m.geom IS NOT NULL" in c8
    assert "ST_DWithin(b.geom, m.geom, 100)" in c8
    assert "JOIN tl_sprd_rw" not in c8
