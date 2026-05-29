from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from kraddr.geo.api import _jobs
from kraddr.geo.core.consistency_definitions import CASE_DEFINITIONS
from kraddr.geo.core.normalize import AddrParts
from kraddr.geo.dto.admin import ConsistencyCase, ConsistencyReport
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra import (
    admin_repo,
    geocode_repo,
    pobox_repo,
    reverse_repo,
    search_repo,
    zip_repo,
)
from kraddr.geo.infra import sql as infra_sql
from kraddr.geo.loaders.consistency import CASE_SQL, DEFAULT_CASES


def test_reverse_sql_transforms_input_once_and_keeps_indexed_column_raw() -> None:
    sql = str(reverse_repo._NEAREST_SQL)

    assert "WITH target_pt AS" in sql
    assert "ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179)" in sql
    assert "ST_DWithin(t.pt_5179, p.geom, :radius_m)" in sql
    assert "ST_Transform(t.pt_5179" not in sql
    assert "ORDER BY t.pt_5179 <-> p.geom" in sql


def test_sppn_reverse_sql_uses_covers_and_keeps_polygon_indexed_column_raw() -> None:
    sql = str(reverse_repo._SPPN_AREAS_SQL)

    assert "WITH target_pt AS" in sql
    assert "ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179)" in sql
    assert "ST_Covers(m.geom, p.geom)" in sql
    assert "ST_Transform(m.geom" not in sql
    assert "ORDER BY ST_Area(m.geom) ASC" in sql


def test_trgm_repos_use_set_local_not_global_threshold() -> None:
    geocode_source = inspect.getsource(geocode_repo.GeocodeRepository.fuzzy_roads)
    search_source = inspect.getsource(search_repo.SearchRepository.search)

    assert "SET LOCAL pg_trgm.similarity_threshold" in geocode_source
    assert "SET LOCAL pg_trgm.similarity_threshold" in search_source
    assert "SET pg_trgm.similarity_threshold" not in geocode_source.replace("SET LOCAL", "")


def test_search_repo_uses_exact_preflight_before_broad_trgm_search() -> None:
    exact_sql = str(search_repo._SEARCH_EXACT_SQL)
    source = inspect.getsource(search_repo.SearchRepository.search)

    assert "FROM mv_geocode_target" in exact_sql
    assert "mv_geocode_text_search" not in exact_sql
    assert "rn_nrm = :query_nrm" in exact_sql
    assert "buld_nm_nrm = :query_nrm" in exact_sql
    assert "_SEARCH_EXACT_SQL" in source
    assert "exact_total > 0" in source
    assert source.index("_SEARCH_EXACT_SQL") < source.rindex("_SEARCH_SQL")


def test_search_repo_supports_district_candidates_from_admin_polygons() -> None:
    sql = str(search_repo._DISTRICT_SEARCH_SQL)
    source = inspect.getsource(search_repo.SearchRepository.search)

    assert "tl_scco_sig" in sql
    assert "tl_scco_emd" in sql
    assert "ST_PointOnSurface" in sql
    assert "map_region_search" in source
    assert 'search_type == "district"' in source


def test_text_search_queries_use_slim_mv_before_target_join() -> None:
    fuzzy_sql = str(geocode_repo._FUZZY_ROADS)
    search_sql = str(search_repo._SEARCH_SQL)

    assert "WITH candidates AS MATERIALIZED" in fuzzy_sql
    assert "FROM mv_geocode_text_search ts" in fuzzy_sql
    assert "JOIN mv_geocode_target t ON t.bd_mgt_sn = c.bd_mgt_sn" in fuzzy_sql
    assert "WITH query_input AS" in search_sql
    assert "FROM mv_geocode_text_search ts" in search_sql
    assert "JOIN mv_geocode_target t ON t.bd_mgt_sn = s.bd_mgt_sn" in search_sql


def test_mv_sql_includes_search_indexes_and_slim_text_search_mv() -> None:
    mv_sql = infra_sql.MV_SQL
    text_search_sql = infra_sql.TEXT_SEARCH_MV_SQL

    assert "idx_mv_rn_nrm_exact" in mv_sql
    assert "ON mv_geocode_target (rn_nrm, bd_mgt_sn)" in mv_sql
    assert "idx_mv_buld_nm_nrm_exact" in mv_sql
    assert "WHERE buld_nm_nrm IS NOT NULL" in mv_sql
    assert "CREATE MATERIALIZED VIEW mv_geocode_text_search AS" in text_search_sql
    assert "FROM mv_geocode_target" in text_search_sql
    assert "left(bjd_cd, 5) AS sig_cd" in text_search_sql
    assert "idx_mv_text_search_rn_trgm" in text_search_sql
    assert "idx_mv_text_search_bjd_prefix_buld" in text_search_sql
    assert "idx_mv_text_search_rn_exact" not in text_search_sql


def test_optional_filters_cast_parameters_for_psycopg_type_inference() -> None:
    geocode_sql = str(geocode_repo._LOOKUP_ROAD)
    reverse_sql = str(reverse_repo._NEAREST_SQL)
    search_sql = str(search_repo._SEARCH_SQL)
    zip_sql = str(zip_repo._ZIP_BY_ADDRESS)
    pobox_sql = str(pobox_repo._POBOX_SQL)

    assert "CAST(:si AS text) IS NULL" in geocode_sql
    assert "CAST(:buld_se_cd AS text) IS NULL" in geocode_sql
    assert "CAST(:sig_cd_filter AS text) IS NULL" in geocode_sql
    assert "CAST(:bjd_cd_prefix AS text) IS NULL" in reverse_sql
    assert "CAST(:sig_cd_prefix AS text) IS NULL" in search_sql
    assert "CAST(:mnnm AS integer) IS NULL" in zip_sql
    assert "CAST(:include_bulk AS boolean)" in str(zip_repo._ZIP_BY_BD)
    assert "CAST(:query AS text) IS NULL" in pobox_sql


def test_geocode_uses_separate_suffix_retry_for_district_only_compound_sigungu_names() -> None:
    lookup_sql = str(geocode_repo._LOOKUP_ROAD)
    suffix_sql = str(geocode_repo._LOOKUP_ROAD_SGG_SUFFIX)
    source = inspect.getsource(geocode_repo.GeocodeRepository.lookup_by_road)

    assert "sgg_nm LIKE '% ' || CAST(:sgg AS text)" not in lookup_sql
    assert "right(sgg_nm, char_length(CAST(:sgg_suffix AS text)))" in suffix_sql
    assert "_LOOKUP_ROAD_SGG_SUFFIX" in source
    assert source.index("_LOOKUP_ROAD") < source.index("_LOOKUP_ROAD_SGG_SUFFIX")
    assert geocode_repo._sgg_suffix(AddrParts(raw="", normalized="", sgg="수지구")) == "수지구"
    assert geocode_repo._sgg_suffix(AddrParts(raw="", normalized="", sgg="용인시 수지구")) is None
    assert geocode_repo._sgg_suffix(AddrParts(raw="", normalized="", sgg="용인시")) is None


def test_reverse_repo_expands_both_address_type() -> None:
    source = inspect.getsource(reverse_repo.ReverseRepository.nearest)

    assert 'address_type == "both"' in source
    assert 'address_type="road"' in source
    assert 'address_type="parcel"' in source


def test_sppn_geocode_sql_verifies_point_inside_makarea_polygon() -> None:
    sql = str(geocode_repo._SPPN_AREA_BY_POINT)

    assert "ST_SetSRID(ST_MakePoint(:x, :y), 5179)" in sql
    assert "ST_Covers(m.geom, p.geom)" in sql
    assert "ST_Transform(m.geom" not in sql


def test_consistency_cases_cover_c1_through_c10_with_metrics() -> None:
    assert tuple(f"C{index}" for index in range(1, 11)) == DEFAULT_CASES
    assert set(CASE_SQL) == set(DEFAULT_CASES)
    assert tuple(case.code for case in CASE_DEFINITIONS) == DEFAULT_CASES
    assert "ST_Distance" in CASE_SQL["C4"].sql
    assert "ST_Covers" in CASE_SQL["C6"].sql
    assert "ST_DWithin" in CASE_SQL["C8"].sql
    assert "source_yyyymm" in CASE_SQL["C10"].sql


def test_consistency_sample_rows_are_stable_and_decision_ready() -> None:
    now = datetime.now(UTC)
    report = ConsistencyReport(
        report_id="consistency_test",
        scope="full",
        severity_max="ERROR",
        source_set={},
        started_at=now,
        finished_at=now,
        generated_by="api",
        cases=(
            ConsistencyCase(
                code="C4",
                name="출입구 좌표와 건물 polygon 거리 이상치",
                severity="ERROR",
                count=1,
                threshold="50m 초과 WARN, 500m 초과 ERROR",
                metric={"over_500m": 1.0},
                sample=(
                    {
                        "bd_mgt_sn": "1111010100100010000000001",
                        "ent_man_no": "1",
                        "source_kind": "locsum",
                        "dist_m": 650.25,
                    },
                ),
            ),
        ),
    )

    first = admin_repo._consistency_sample_rows(report)
    second = admin_repo._consistency_sample_rows(report)

    assert first[0]["sample_id"] == second[0]["sample_id"]
    assert first[0]["severity"] == "ERROR"
    assert first[0]["sig_cd"] == "11110"
    assert first[0]["distance_m"] == 650.25
    assert first[0]["has_polygon"] is True
    assert first[0]["source_snapshot"]["bd_mgt_sn"] == "1111010100100010000000001"


def test_batch_dag_defers_consistency_and_mv_refresh_until_successors() -> None:
    queue_source = inspect.getsource(_jobs.JobQueue)

    assert "full_load_batch" in queue_source
    assert "consistency_check" in queue_source
    assert '"strategy": "swap"' in queue_source
    assert "consistency report severity ERROR" in queue_source
    assert "log_tail" in queue_source
    assert "kind NOT IN" in queue_source


def test_admin_repo_explain_is_select_only_and_uses_json_format() -> None:
    assert admin_repo._validated_explain_sql(" SELECT 1 ") == "SELECT 1"
    with pytest.raises(InvalidInputError):
        admin_repo._validated_explain_sql("DELETE FROM x")
    with pytest.raises(InvalidInputError):
        admin_repo._validated_explain_sql("SELECT 1; SELECT 2")

    source = inspect.getsource(admin_repo.AdminRepository.explain)
    assert "EXPLAIN (" in source
    assert "FORMAT JSON" in source
    assert "set_config('statement_timeout'" in source


def test_admin_repo_exposes_table_cache_log_metric_queries() -> None:
    source = inspect.getsource(admin_repo.AdminRepository)

    assert "pg_stat_user_tables" in source
    assert "geo_cache" in source
    assert "GROUP BY kind, state" in source
    assert "jsonb_array_length(log_tail)" in source


def test_admin_upload_helpers_prevent_path_escape(tmp_path) -> None:
    from kraddr.geo.api.routers import admin

    assert admin._safe_filename("../../서울.zip") == "서울.zip"
    assert "/" not in admin._safe_path_token("../../../etc/cron.d")
    upload_dir = admin._safe_upload_dir(tmp_path, admin._safe_path_token("../../../etc/cron.d"))
    assert upload_dir.relative_to((tmp_path / "uploads").resolve())


def test_admin_repo_active_upload_refs_scan_queued_and_running_payloads() -> None:
    source = inspect.getsource(admin_repo.AdminRepository.active_upload_set_ids)

    assert "state IN ('queued','running')" in source
    assert "payload::text LIKE '%upload_%'" in source
    assert "extract_upload_set_ids" in source


def test_consistency_severity_filter_is_pushed_to_sql() -> None:
    source = inspect.getsource(admin_repo.AdminRepository.list_consistency_reports)

    assert "min_severity_rank" in source
    assert "WHERE" in source
    assert "severity_rank.get(report.severity_max" not in source
