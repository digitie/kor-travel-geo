from __future__ import annotations

import inspect

from kraddr.geo.infra import geocode_repo, reverse_repo, search_repo


def test_reverse_sql_transforms_input_once_and_keeps_indexed_column_raw() -> None:
    sql = str(reverse_repo._NEAREST_SQL)

    assert "WITH target_pt AS" in sql
    assert "ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179)" in sql
    assert "ST_DWithin(t.pt_5179, p.geom, :radius_m)" in sql
    assert "ST_Transform(t.pt_5179" not in sql
    assert "ORDER BY t.pt_5179 <-> p.geom" in sql


def test_trgm_repos_use_set_local_not_global_threshold() -> None:
    geocode_source = inspect.getsource(geocode_repo.GeocodeRepository.fuzzy_roads)
    search_source = inspect.getsource(search_repo.SearchRepository.search)

    assert "SET LOCAL pg_trgm.similarity_threshold" in geocode_source
    assert "SET LOCAL pg_trgm.similarity_threshold" in search_source
    assert "SET pg_trgm.similarity_threshold" not in geocode_source.replace("SET LOCAL", "")
