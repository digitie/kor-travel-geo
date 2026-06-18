from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from typing import Any

import pytest

from kortravelgeo.api import _jobs
from kortravelgeo.api import app as api_app
from kortravelgeo.core.consistency_definitions import CASE_DEFINITIONS
from kortravelgeo.core.normalize import AddrParts
from kortravelgeo.dto.admin import ConsistencyCase, ConsistencyReport
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra import (
    admin_repo,
    coordinates,
    geocode_repo,
    geometry_repo,
    pobox_repo,
    reverse_repo,
    search_repo,
    zip_repo,
)
from kortravelgeo.infra import sql as infra_sql
from kortravelgeo.loaders import consistency
from kortravelgeo.loaders.consistency import CASE_SQL, DEFAULT_CASES


def test_reverse_sql_transforms_input_once_and_keeps_indexed_column_raw() -> None:
    sql = str(reverse_repo._NEAREST_SQL)

    assert "WITH target_pt AS" in sql
    assert "knn_candidates AS MATERIALIZED" in sql
    assert "ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179)" in sql
    assert "WHERE distance_m <= :radius_m" in sql
    assert "ST_Transform(t.pt_5179" not in sql
    assert "ORDER BY t.pt_5179 <-> p.geom" in sql
    assert "ST_DWithin(t.pt_5179, p.geom, :radius_m)" not in sql


def test_reverse_radius_sql_keeps_dwithin_prefilter_for_benchmark_path() -> None:
    sql = str(reverse_repo._RADIUS_SQL)

    assert "WITH target_pt AS" in sql
    assert "ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179)" in sql
    assert "ST_DWithin(t.pt_5179, p.geom, :radius_m)" in sql
    assert "ORDER BY t.pt_5179 <-> p.geom" in sql
    assert "knn_candidates AS MATERIALIZED" not in sql


def test_sppn_reverse_sql_uses_covers_and_keeps_polygon_indexed_column_raw() -> None:
    sql = str(reverse_repo._SPPN_AREAS_SQL)

    assert "WITH target_pt AS" in sql
    assert "ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179)" in sql
    assert "ST_Covers(m.geom, p.geom)" in sql
    assert "ST_Transform(m.geom" not in sql
    assert "ORDER BY ST_Area(m.geom) ASC" in sql


def test_zipcode_point_sql_uses_covers_and_keeps_polygon_indexed_column_raw() -> None:
    sql = str(zip_repo._ZIP_BY_POINT)

    assert "WITH target_pt AS" in sql
    assert "ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), 4326), 5179)" in sql
    assert "ST_Covers(k.geom, p.geom)" in sql
    assert "ST_Contains(k.geom, p.geom)" not in sql
    assert "ST_Transform(k.geom" not in sql


def test_sppn_reverse_projection_sql_transforms_input_point_only() -> None:
    sql = str(coordinates._POINT_TO_5179_SQL)

    assert "ST_Transform(ST_SetSRID(ST_MakePoint(:x, :y), :in_srid), 5179)" in sql
    assert "ST_X(geom) AS x5179" in sql
    assert "ST_Transform(m.geom" not in sql
    assert "ST_Transform(t.pt_5179" not in sql


def test_trgm_repos_use_set_local_not_global_threshold() -> None:
    geocode_source = inspect.getsource(geocode_repo.GeocodeRepository.fuzzy_roads)
    search_source = inspect.getsource(search_repo.SearchRepository.search)

    assert "SET LOCAL pg_trgm.similarity_threshold" in geocode_source
    assert "SET LOCAL pg_trgm.similarity_threshold" in search_source
    assert "SET pg_trgm.similarity_threshold" not in geocode_source.replace("SET LOCAL", "")


def test_search_repo_uses_exact_preflight_before_broad_trgm_search() -> None:
    exact_sql = str(search_repo._SEARCH_EXACT_SQL)
    source = inspect.getsource(search_repo.SearchRepository.search)

    assert "WITH exact_keys AS MATERIALIZED" in exact_sql
    assert "UNION ALL" in exact_sql
    assert "SELECT DISTINCT ON (bd_mgt_sn)" in exact_sql
    assert "FROM mv_geocode_target" in exact_sql
    assert "mv_geocode_text_search" not in exact_sql
    assert "rn_nrm = :query_nrm" in exact_sql
    assert "buld_nm_nrm = :query_nrm" in exact_sql
    assert "sigungu_buld_nm_nrm = :query_nrm" in exact_sql
    assert "OR (buld_nm_nrm = :query_nrm" not in exact_sql
    assert "GREATEST(" not in exact_sql
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


def test_regions_within_radius_sql_keeps_region_geometry_indexable() -> None:
    sql = str(geometry_repo._REGIONS_WITHIN_RADIUS_SQL)
    refresh_sql = infra_sql.REGION_RADIUS_PARTS_REFRESH_SQL

    assert sql.count("ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 5179)") == 1
    assert "FROM region_radius_parts p" in sql
    assert "JOIN sido_candidates sido ON sido.code = p.parent_sido_cd" in sql
    assert "JOIN sigungu_candidates sigungu ON sigungu.code = p.parent_sig_cd" in sql
    assert "ST_DWithin(p.geom, target.geom, :radius_m)" in sql
    assert "FROM tl_scco_ctprvn" in sql
    assert "FROM tl_scco_sig" in sql
    assert "FROM tl_scco_emd" in sql
    assert "ST_Covers(c.geom, target.geom)" in sql
    assert "ST_Covers(s.geom, target.geom)" in sql
    assert "ST_Covers(e.geom, target.geom)" in sql
    assert "ST_Subdivide(s.geom, 256)" in refresh_sql
    assert "left(s.sig_cd, 2) AS parent_sido_cd" in refresh_sql
    assert "left(e.emd_cd, 5) AS parent_sig_cd" in refresh_sql
    assert "idx_region_radius_parts_geom" in infra_sql.INDEX_SQL
    assert "ST_DWithin(c.geom, target.geom, :radius_m)" not in sql
    assert "ST_DWithin(s.geom, target.geom, :radius_m)" not in sql
    assert "ST_DWithin(e.geom, target.geom, :radius_m)" not in sql
    assert "ST_Transform(p.geom" not in sql
    assert "ST_Transform(c.geom" not in sql
    assert "ST_Transform(s.geom" not in sql
    assert "ST_Transform(e.geom" not in sql


def test_text_search_queries_use_slim_mv_before_target_join() -> None:
    fuzzy_sql = str(geocode_repo._FUZZY_ROADS)
    search_sql = str(search_repo._SEARCH_SQL)

    assert "WITH candidates AS MATERIALIZED" in fuzzy_sql
    assert "FROM mv_geocode_text_search ts" in fuzzy_sql
    assert "AND ts.buld_mnnm = :mnnm" in fuzzy_sql
    assert "AND ts.buld_slno = :slno" in fuzzy_sql
    assert "AND ts.buld_se_cd = :buld_se_cd" in fuzzy_sql
    assert "JOIN mv_geocode_target t ON t.bd_mgt_sn = c.bd_mgt_sn" in fuzzy_sql
    assert "WITH query_input AS" in search_sql
    assert "SELECT CAST(:query_nrm AS text) AS query_nrm" in search_sql
    assert "regexp_replace(:query" not in search_sql
    assert "FROM mv_geocode_text_search ts" in search_sql
    assert "ts.sigungu_buld_nm_nrm % q.query_nrm" in search_sql
    assert "JOIN mv_geocode_target t ON t.bd_mgt_sn = s.bd_mgt_sn" in search_sql


def test_search_query_normalization_folds_unicode_variants() -> None:
    query = " 서울시  왕산로\uff11\uff18\uff19\uff0d\uff14 "

    assert search_repo._normalize_search_query(query) == "서울시왕산로189-4"


def test_mv_sql_includes_search_indexes_and_slim_text_search_mv() -> None:
    mv_sql = infra_sql.MV_SQL
    text_search_sql = infra_sql.TEXT_SEARCH_MV_SQL

    assert "idx_mv_rn_nrm_exact" in mv_sql
    assert "ON mv_geocode_target (rn_nrm, bd_mgt_sn)" in mv_sql
    assert "idx_mv_buld_nm_nrm_exact" in mv_sql
    assert "WHERE buld_nm_nrm IS NOT NULL" in mv_sql
    assert "sigungu_buld_nm_nrm" in mv_sql
    assert "idx_mv_sigungu_buld_nm_nrm_exact" in mv_sql
    assert "CREATE MATERIALIZED VIEW mv_geocode_text_search AS" in text_search_sql
    assert "FROM mv_geocode_target" in text_search_sql
    assert "left(bjd_cd, 5) AS sig_cd" in text_search_sql
    assert "sigungu_buld_nm_nrm" in text_search_sql
    assert "buld_slno" in text_search_sql
    assert "buld_se_cd" in text_search_sql
    assert "idx_mv_text_search_rn_trgm" in text_search_sql
    assert "idx_mv_text_search_bjd_prefix_buld" in text_search_sql
    assert "sig_cd, buld_mnnm, buld_slno, buld_se_cd, bd_mgt_sn" in text_search_sql
    assert "sido_cd, buld_mnnm, buld_slno, buld_se_cd, bd_mgt_sn" in text_search_sql
    assert "idx_mv_text_search_sigungu_buld_nm_trgm" in text_search_sql
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


def test_region_hint_filters_are_present_on_all_address_lookup_sql_surfaces() -> None:
    statements = {
        "geocode_road": str(geocode_repo._LOOKUP_ROAD),
        "geocode_jibun": str(geocode_repo._LOOKUP_JIBUN),
        "geocode_fuzzy": str(geocode_repo._FUZZY_ROADS),
        "search_exact": str(search_repo._SEARCH_EXACT_SQL),
        "search_fuzzy": str(search_repo._SEARCH_SQL),
        "search_district": str(search_repo._DISTRICT_SEARCH_SQL),
        "reverse_nearest": str(reverse_repo._NEAREST_SQL),
        "reverse_radius": str(reverse_repo._RADIUS_SQL),
        "geometry_road": str(geometry_repo._ROAD_GEOMETRY_SQL),
    }

    for name, sql in statements.items():
        assert "CAST(:sig_cd_filter AS text)" in sql, name
        assert "CAST(:sig_cd_prefix AS text)" in sql, name
        assert "CAST(:bjd_cd_filter AS text)" in sql, name
        assert "CAST(:bjd_cd_prefix AS text)" in sql, name

    assert "ts.sig_cd = CAST(:sig_cd_filter AS text)" in statements["search_fuzzy"]
    assert "ts.sido_cd = left(CAST(:sig_cd_prefix AS text), 2)" in statements["search_fuzzy"]
    assert "bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%'" in statements["geocode_road"]
    assert "t.bjd_cd LIKE CAST(:sig_cd_filter AS text) || '%'" in statements["reverse_nearest"]


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


def test_sppn_geocode_projection_sql_transforms_calculated_point_only() -> None:
    sql = str(coordinates._POINT_5179_TO_4326_SQL)

    assert "ST_SetSRID(ST_MakePoint(:x, :y), 5179)" in sql
    assert "ST_X(ST_Transform(geom, 4326)) AS lon" in sql
    assert "ST_Transform(m.geom" not in sql
    assert "ST_Transform(t.pt_5179" not in sql


def test_coordinate_projection_methods_delegate_to_shared_helpers() -> None:
    geocode_source = inspect.getsource(geocode_repo.GeocodeRepository.project_sppn_point_4326)
    reverse_source = inspect.getsource(reverse_repo.ReverseRepository.project_reverse_point_5179)

    assert "project_point_5179_to_4326" in geocode_source
    assert "project_point_to_5179" in reverse_source
    assert "_SPPN_POINT_4326" not in geocode_source
    assert "_POINT_TO_5179_SQL" not in reverse_source


def test_coordinate_srid_parser_uses_common_crs_normalization() -> None:
    assert coordinates.srid_from_crs("epsg-4326") == 4326
    assert coordinates.srid_from_crs("EPSG5179") == 5179


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


def test_insert_load_batch_preserves_child_queue_order() -> None:
    source = inspect.getsource(admin_repo.AdminRepository.insert_load_batch)

    assert "enumerate(children)" in source
    assert "payload_summary, created_at" in source
    assert (
        "clock_timestamp() + (CAST(:child_order AS integer) * interval '1 microsecond')"
        in source
    )
    assert '"child_order": index' in source


@pytest.mark.asyncio
async def test_batch_consistency_error_reaches_promotion_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class QueueCapture:
        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}

        def register(self, kind: str, handler: Any) -> None:
            self.handlers[kind] = handler

    class NoopLock:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> bool:
            return False

    async def fake_run_all_cases(
        _engine: object,
        *,
        scope: str,
        cases: tuple[str, ...],
        generated_by: str,
        source_set: dict[str, Any],
        on_progress: Any,
    ) -> ConsistencyReport:
        del cases
        if on_progress is not None:
            await on_progress(1.0, "C1")
        now = datetime.now(UTC)
        return ConsistencyReport(
            report_id="consistency_error",
            scope=scope,
            severity_max="ERROR",
            source_set=source_set,
            started_at=now,
            finished_at=now,
            cases=(),
            generated_by=generated_by,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(api_app, "run_all_cases", fake_run_all_cases)
    monkeypatch.setattr(api_app, "cross_process_lock", lambda *_args, **_kwargs: NoopLock())
    queue = QueueCapture()
    api_app._register_default_handlers(queue, object())  # type: ignore[arg-type]
    handler = queue.handlers["consistency_check"]
    progress_events: list[dict[str, Any]] = []

    async def record_progress(**kwargs: Any) -> None:
        progress_events.append(kwargs)

    await handler({"load_batch_id": "batch-1"}, asyncio.Event(), record_progress)

    assert any(
        "batch promotion gate" in str(event.get("message")) for event in progress_events
    )

    with pytest.raises(RuntimeError, match="consistency report failed"):
        await handler({}, asyncio.Event(), record_progress)


@pytest.mark.asyncio
async def test_consistency_cases_disable_statement_timeout_per_case() -> None:
    class Result:
        def mappings(self) -> Result:
            return self

        def one(self) -> dict[str, Any]:
            return {"count": 0, "total": 1, "metric": {}, "sample": []}

    class Conn:
        def __init__(self) -> None:
            self.statements: list[str] = []

        async def execute(self, statement: object, *_args: object, **_kwargs: object) -> Result:
            self.statements.append(str(statement))
            return Result()

    class Begin:
        def __init__(self, conn: Conn) -> None:
            self.conn = conn

        async def __aenter__(self) -> Conn:
            return self.conn

        async def __aexit__(self, *_args: object) -> bool:
            return False

    class Engine:
        def __init__(self) -> None:
            self.conn = Conn()

        def begin(self) -> Begin:
            return Begin(self.conn)

    engine = Engine()
    case = await consistency.run_case(engine, "C1")  # type: ignore[arg-type]

    assert engine.conn.statements[0] == "SET LOCAL statement_timeout = 0"
    assert case.code == "C1"
    assert case.severity == "OK"


@pytest.mark.asyncio
async def test_consistency_sample_point_hydration_tolerates_missing_mv() -> None:
    class Conn:
        def __init__(self, scalar_result: object) -> None:
            self.scalar_result = scalar_result
            self.scalar_statements: list[str] = []
            self.execute_calls: list[tuple[str, dict[str, Any] | None]] = []

        async def scalar(self, statement: object) -> object:
            self.scalar_statements.append(str(statement))
            return self.scalar_result

        async def execute(
            self,
            statement: object,
            params: dict[str, Any] | None = None,
        ) -> None:
            self.execute_calls.append((str(statement), params))

    missing_conn = Conn(None)
    await admin_repo._hydrate_consistency_sample_points(missing_conn, "report-1")

    assert missing_conn.scalar_statements == ["SELECT to_regclass('mv_geocode_target')"]
    assert missing_conn.execute_calls == []

    present_conn = Conn("mv_geocode_target")
    await admin_repo._hydrate_consistency_sample_points(present_conn, "report-1")

    assert len(present_conn.execute_calls) == 1
    assert present_conn.execute_calls[0][1] == {"report_id": "report-1"}


def test_mv_refresh_release_metadata_uses_operational_timeout() -> None:
    source = inspect.getsource(admin_repo.AdminRepository.record_mv_refresh_release)

    assert "SET LOCAL statement_timeout = 0" in source
    assert "_infer_current_source_set" in source
    assert "_collect_row_counts_for_conn" in source


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
    from kortravelgeo.api.routers import admin

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
