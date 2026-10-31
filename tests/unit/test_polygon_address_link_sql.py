from kortravelgeo.infra.geometry_repo import _BUILDING_GEOMETRY_SQL
from kortravelgeo.loaders.consistency import CASE_SQL


def test_polygon_matching_accepts_address_sigungu_without_changing_raw_road_code():
    for code in ('C1', 'C2', 'C4', 'C5'):
        sql = CASE_SQL[code].sql
        assert '(p.sig_cd || p.rn_cd)' in sql, code
        assert 'p.rncode_full' in sql, code
    assert '(p.sig_cd || p.rn_cd)' in str(_BUILDING_GEOMETRY_SQL)
    assert 'p.rncode_full = CAST(:rncode_full AS text)' in str(_BUILDING_GEOMETRY_SQL)
