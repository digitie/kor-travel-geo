from kraddr.geo.infra.reverse_sql import KODIS_BAS_ZIP_AT_SQL, NEAREST_ENTRANCE_SQL


def _squashed_sql(sql: object) -> str:
    return " ".join(str(sql).split())


def test_nearest_entrance_sql_transforms_input_once_and_uses_5179_index_column() -> None:
    sql = _squashed_sql(NEAREST_ENTRANCE_SQL)

    assert sql.count("ST_Transform(") == 1
    assert "WITH target_pt AS" in sql
    assert "ST_SetSRID(ST_MakePoint(:lon, :lat), :in_srid)" in sql
    assert "ST_DWithin(t.ent_pt_5179, p.geom, :radius_m)" in sql
    assert "ORDER BY t.ent_pt_5179 <-> p.geom" in sql
    assert "ST_DWithin(ST_Transform" not in sql
    assert "ent_pt_4326, p.geom, :radius_m" not in sql


def test_nearest_entrance_sql_keeps_4326_only_for_response_coordinates() -> None:
    sql = _squashed_sql(NEAREST_ENTRANCE_SQL)

    assert "ST_X(t.ent_pt_4326) AS lon" in sql
    assert "ST_Y(t.ent_pt_4326) AS lat" in sql
    assert "ST_Distance(t.ent_pt_5179, p.geom) AS dist_m" in sql


def test_kodis_bas_zip_sql_uses_same_single_input_transform_pattern() -> None:
    sql = _squashed_sql(KODIS_BAS_ZIP_AT_SQL)

    assert sql.count("ST_Transform(") == 1
    assert "ST_Contains(b.geom, p.geom)" in sql
    assert "ST_Transform(b.geom" not in sql
    assert "ST_SetSRID(ST_MakePoint(:lon, :lat), :in_srid)" in sql
