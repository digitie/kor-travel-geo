from __future__ import annotations

import inspect

import pytest

from kraddr.geo.api import _jobs
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra import admin_repo, geocode_repo, reverse_repo, search_repo
from kraddr.geo.loaders.consistency import CASE_SQL, DEFAULT_CASES


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


def test_reverse_repo_expands_both_address_type() -> None:
    source = inspect.getsource(reverse_repo.ReverseRepository.nearest)

    assert 'address_type == "both"' in source
    assert 'address_type="road"' in source
    assert 'address_type="parcel"' in source


def test_consistency_cases_cover_c1_through_c10_with_metrics() -> None:
    assert tuple(f"C{index}" for index in range(1, 11)) == DEFAULT_CASES
    assert set(CASE_SQL) == set(DEFAULT_CASES)
    assert "ST_Distance" in CASE_SQL["C4"].sql
    assert "ST_Contains" in CASE_SQL["C6"].sql
    assert "ST_DWithin" in CASE_SQL["C8"].sql
    assert "source_yyyymm" in CASE_SQL["C10"].sql


def test_batch_dag_defers_consistency_and_mv_refresh_until_successors() -> None:
    queue_source = inspect.getsource(_jobs.JobQueue)

    assert "full_load_batch" in queue_source
    assert "consistency_check" in queue_source
    assert '"strategy": "swap"' in queue_source
    assert "consistency report severity ERROR" in queue_source
    assert "log_tail" in queue_source


def test_admin_repo_explain_is_select_only_and_uses_json_format() -> None:
    assert admin_repo._validated_explain_sql(" SELECT 1 ") == "SELECT 1"
    with pytest.raises(InvalidInputError):
        admin_repo._validated_explain_sql("DELETE FROM x")
    with pytest.raises(InvalidInputError):
        admin_repo._validated_explain_sql("SELECT 1; SELECT 2")

    source = inspect.getsource(admin_repo.AdminRepository.explain)
    assert "EXPLAIN (" in source
    assert "FORMAT JSON" in source


def test_admin_repo_exposes_table_cache_log_metric_queries() -> None:
    source = inspect.getsource(admin_repo.AdminRepository)

    assert "pg_stat_user_tables" in source
    assert "geo_cache" in source
    assert "GROUP BY kind, state" in source
    assert "jsonb_array_length(log_tail)" in source
