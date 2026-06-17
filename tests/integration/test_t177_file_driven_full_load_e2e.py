from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from kortravelgeo.infra.engine import make_async_engine
from kortravelgeo.settings import Settings
from tests.integration._t177_full_load_harness import (
    ENV_ALLOW_NONEMPTY,
    ENV_CONFIRM,
    T177D_REQUIRED_NONEMPTY_TABLES,
    T177D_TARGET_TABLES,
    T177E_MANIFEST_TABLES,
    T177E_TARGET_TABLES,
    T177PreflightError,
    T177SkipError,
    apply_schema_index_smoke,
    assert_no_existing_rows_without_confirmation,
    build_discovery_plan,
    collect_existing_row_counts,
    collect_t177c_table_counts,
    collect_t177d_table_counts,
    collect_t177e_table_counts,
    reset_t177c_target_tables,
    reset_t177e_target_tables,
    run_t177c_text_delta_fast_sample_load,
    run_t177d_shp_geometry_fast_sample_load,
    run_t177e_supplemental_fast_sample_load,
    runtime_from_env,
    sample_limit_from_env,
    schema_smoke_report,
    source_yyyymm,
    t177c_text_delta_source_paths,
    t177d_shp_geometry_source,
    t177e_supplemental_source_paths,
    validate_database_preflight,
    write_json_artifact,
)


@pytest.mark.asyncio
async def test_t177_file_driven_full_load_preflight_and_schema_smoke() -> None:
    started_at = datetime.now(UTC)
    try:
        runtime = runtime_from_env()
    except T177SkipError as exc:
        pytest.skip(str(exc))

    engine = make_async_engine(Settings(pg_dsn=runtime.dsn))
    try:
        preflight = await validate_database_preflight(
            engine,
            confirmation=os.getenv(ENV_CONFIRM),
        )
        discovery_plan = build_discovery_plan(runtime.data_root)

        await apply_schema_index_smoke(engine)
        schema_report = await schema_smoke_report(engine)
        existing_rows = await collect_existing_row_counts(engine)
        allow_nonempty = os.getenv(ENV_ALLOW_NONEMPTY) == "1"
        assert_no_existing_rows_without_confirmation(
            existing_rows,
            destructive_confirmed=preflight.destructive_confirmed,
            allow_nonempty=allow_nonempty,
        )

        artifact = {
            "schema_version": 1,
            "task": "T-177B",
            "run_id": runtime.run_id,
            "mode": "preflight_schema_smoke",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "gates": {
                "full_load_e2e": True,
                "pg_dsn": True,
                "confirmation_ok": preflight.destructive_confirmed,
                "allow_nonempty": allow_nonempty,
                "longrun": False,
            },
            "database": {
                "name": preflight.database_name,
                "expected_confirmation": preflight.expected_confirmation,
                "destructive_confirmed": preflight.destructive_confirmed,
                "available_extensions": preflight.available_extensions,
            },
            "data": discovery_plan,
            "schema": schema_report,
            "existing_rows": existing_rows,
        }
        artifact_path = write_json_artifact(
            runtime.artifact_dir,
            "t177b-preflight-schema-smoke.json",
            artifact,
        )

        assert artifact_path.is_file()
        assert schema_report["missing_objects"] == []
        assert discovery_plan["data_root"] == str(runtime.data_root)
    except T177PreflightError as exc:
        pytest.fail(str(exc))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_t177d_file_driven_shp_geometry_fast_sample_load() -> None:
    started_at = datetime.now(UTC)
    try:
        runtime = runtime_from_env()
    except T177SkipError as exc:
        pytest.skip(str(exc))

    pytest.importorskip("osgeo.gdal")

    engine = make_async_engine(Settings(pg_dsn=runtime.dsn))
    try:
        preflight = await validate_database_preflight(
            engine,
            confirmation=os.getenv(ENV_CONFIRM),
        )
        discovery_plan = build_discovery_plan(runtime.data_root)
        source = t177d_shp_geometry_source(
            discovery_plan,
            materialize_dir=runtime.artifact_dir / "t177d-electronic-map",
        )

        await apply_schema_index_smoke(engine)
        schema_report = await schema_smoke_report(engine)
        existing_rows = await collect_existing_row_counts(engine)
        existing_shp_rows = await collect_t177d_table_counts(engine)
        allow_nonempty = os.getenv(ENV_ALLOW_NONEMPTY) == "1"
        assert_no_existing_rows_without_confirmation(
            {**existing_rows, **existing_shp_rows},
            destructive_confirmed=preflight.destructive_confirmed,
            allow_nonempty=allow_nonempty,
        )

        before_counts = await collect_t177d_table_counts(engine)
        result = await run_t177d_shp_geometry_fast_sample_load(engine, source=source)

        artifact = {
            "schema_version": 1,
            "task": "T-177D",
            "run_id": runtime.run_id,
            "mode": "shp_geometry_fast_sample_load",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "gates": {
                "full_load_e2e": True,
                "pg_dsn": True,
                "confirmation_ok": preflight.destructive_confirmed,
                "allow_nonempty": allow_nonempty,
                "longrun": False,
            },
            "database": {
                "name": preflight.database_name,
                "expected_confirmation": preflight.expected_confirmation,
            },
            "data": discovery_plan,
            "schema": schema_report,
            "before_counts": before_counts,
            "result": result,
        }
        artifact_path = write_json_artifact(
            runtime.artifact_dir,
            "t177d-shp-geometry-fast-sample-load.json",
            artifact,
        )

        assert artifact_path.is_file()
        assert schema_report["missing_objects"] == []
        assert result["loaded_layers"] == len(result["plans"]) == 9
        assert result["source"]["sido_path"] == str(source.sido_path)

        table_counts = result["table_counts"]
        assert set(T177D_TARGET_TABLES).issubset(table_counts)
        for table_name in T177D_REQUIRED_NONEMPTY_TABLES:
            assert table_counts[table_name] > 0

        for table_name, report in result["geometry_report"].items():
            row_count = report["row_count"]
            geom_rows = report["geom_rows"]
            if row_count == 0:
                continue
            if table_name != "public.tl_sprd_manage":
                assert geom_rows == row_count
            assert report["srid_5179_rows"] == geom_rows
            assert report["empty_geom_rows"] == 0
            assert report["invalid_geom_rows"] == 0
            assert report["source_file_rows"] == row_count
            assert report["source_yyyymm_rows"] == row_count
            assert set(report["geometry_types"]) <= {report["expected_geometry_type"]}

        interval_report = result["non_geometry_report"]["public.tl_sprd_intrvl"]
        assert interval_report["row_count"] > 0
        assert interval_report["source_file_rows"] == interval_report["row_count"]
        assert interval_report["source_yyyymm_rows"] == interval_report["row_count"]

        region_report = result["region_radius_parts"]
        for level in ("sido", "sigungu", "emd"):
            assert region_report[level]["row_count"] > 0
            assert region_report[level]["srid_5179_rows"] == region_report[level]["geom_rows"]
            assert region_report[level]["empty_geom_rows"] == 0
            assert region_report[level]["invalid_geom_rows"] == 0
    except T177SkipError as exc:
        pytest.skip(str(exc))
    except T177PreflightError as exc:
        pytest.fail(str(exc))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_t177e_file_driven_supplemental_fast_sample_load() -> None:
    started_at = datetime.now(UTC)
    try:
        runtime = runtime_from_env()
        limit_per_file = sample_limit_from_env()
    except T177SkipError as exc:
        pytest.skip(str(exc))
    except T177PreflightError as exc:
        pytest.fail(str(exc))

    pytest.importorskip("osgeo.gdal")

    engine = make_async_engine(Settings(pg_dsn=runtime.dsn))
    try:
        preflight = await validate_database_preflight(
            engine,
            confirmation=os.getenv(ENV_CONFIRM),
        )
        discovery_plan = build_discovery_plan(runtime.data_root)
        source_paths = t177e_supplemental_source_paths(discovery_plan)

        await apply_schema_index_smoke(engine)
        schema_report = await schema_smoke_report(engine)
        existing_rows = await collect_existing_row_counts(engine)
        existing_supplemental_rows = await collect_t177e_table_counts(engine)
        allow_nonempty = os.getenv(ENV_ALLOW_NONEMPTY) == "1"
        assert_no_existing_rows_without_confirmation(
            {**existing_rows, **existing_supplemental_rows},
            destructive_confirmed=preflight.destructive_confirmed,
            allow_nonempty=allow_nonempty,
        )

        await reset_t177e_target_tables(engine)
        before_counts = await collect_t177e_table_counts(engine)
        result = await run_t177e_supplemental_fast_sample_load(
            engine,
            source_paths=source_paths,
            limit_per_file=limit_per_file,
        )

        artifact = {
            "schema_version": 1,
            "task": "T-177E",
            "run_id": runtime.run_id,
            "mode": "supplemental_fast_sample_load",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "gates": {
                "full_load_e2e": True,
                "pg_dsn": True,
                "confirmation_ok": preflight.destructive_confirmed,
                "allow_nonempty": allow_nonempty,
                "longrun": False,
                "limit_per_file": limit_per_file,
            },
            "database": {
                "name": preflight.database_name,
                "expected_confirmation": preflight.expected_confirmation,
            },
            "data": discovery_plan,
            "schema": schema_report,
            "before_counts": before_counts,
            "result": result,
        }
        artifact_path = write_json_artifact(
            runtime.artifact_dir,
            "t177e-supplemental-fast-sample-load.json",
            artifact,
        )

        loader_results = result["loader_results"]
        table_counts = result["table_counts"]
        manifests = result["manifests"]
        roadaddr_report = result["roadaddr_report"]
        sppn_report = result["sppn_report"]
        sppn_smoke = result["sppn_smoke"]
        source_months = result["source_months"]

        assert artifact_path.is_file()
        assert schema_report["missing_objects"] == []
        assert set(T177E_TARGET_TABLES).issubset(table_counts)
        assert set(T177E_MANIFEST_TABLES) == set(manifests)
        assert source_months["roadaddr_entrance_plan"] is not None
        assert source_months["roadaddr_entrance_loaded"] is not None
        assert source_months["sppn_makarea"] is not None

        roadaddr_result = loader_results["roadaddr_entrance"]
        assert roadaddr_result["source_count"] == 1
        assert 1 <= roadaddr_result["processed_rows"] <= limit_per_file
        assert roadaddr_result["upserted_rows"] >= 1
        assert roadaddr_result["source_yyyymm"] == source_months[
            "roadaddr_entrance_loaded"
        ]
        assert table_counts["public.tl_roadaddr_entrc"] >= 1
        assert roadaddr_report["row_count"] == table_counts["public.tl_roadaddr_entrc"]
        assert roadaddr_report["geom_rows"] == roadaddr_report["row_count"]
        assert roadaddr_report["srid_5179_rows"] == roadaddr_report["geom_rows"]
        assert roadaddr_report["empty_geom_rows"] == 0
        assert roadaddr_report["invalid_geom_rows"] == 0
        assert roadaddr_report["source_file_rows"] == roadaddr_report["row_count"]
        assert roadaddr_report["source_yyyymm_rows"] == roadaddr_report["row_count"]
        assert set(roadaddr_report["geometry_types"]) <= {"ST_Point"}

        assert loader_results["sppn_makarea_rows"] > 0
        assert table_counts["public.tl_sppn_makarea"] > 0
        assert sppn_report["row_count"] == table_counts["public.tl_sppn_makarea"]
        assert sppn_report["geom_rows"] == sppn_report["row_count"]
        assert sppn_report["srid_5179_rows"] == sppn_report["geom_rows"]
        assert sppn_report["empty_geom_rows"] == 0
        assert sppn_report["invalid_geom_rows"] == 0
        assert sppn_report["source_file_rows"] == sppn_report["row_count"]
        assert sppn_report["source_yyyymm_rows"] == sppn_report["row_count"]
        assert set(sppn_report["geometry_types"]) <= {"ST_MultiPolygon"}

        assert manifests["tl_roadaddr_entrc"]["source_yyyymm"] == (
            source_months["roadaddr_entrance_loaded"]
        )
        assert manifests["tl_roadaddr_entrc"]["source_set"]["kind"] == (
            "roadaddr_entrance_full"
        )
        assert manifests["tl_sppn_makarea"]["source_yyyymm"] == source_months[
            "sppn_makarea"
        ]
        assert manifests["tl_sppn_makarea"]["source_set"]["kind"] == "sppn_makarea"

        assert sppn_smoke["direct_lookup"]["makarea_id"] == sppn_smoke["sample"][
            "makarea_id"
        ]
        assert sppn_smoke["geocode_status"] == "OK"
        assert sppn_smoke["geocode_sppn_found"] is True
        assert sppn_smoke["reverse_area_count"] > 0
        assert sppn_smoke["reverse_sppn_found"] is True

        loaded_months = {
            source_months["roadaddr_entrance_loaded"],
            source_months["sppn_makarea"],
        } - {None}
        if len(loaded_months) > 1:
            assert result["c10"]["severity"] == "WARN"
            assert result["c10"]["metric"]["distinct_months"] >= 2
    except T177SkipError as exc:
        pytest.skip(str(exc))
    except T177PreflightError as exc:
        pytest.fail(str(exc))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_t177c_file_driven_text_delta_fast_sample_load() -> None:
    started_at = datetime.now(UTC)
    try:
        runtime = runtime_from_env()
        limit_per_file = sample_limit_from_env()
    except T177SkipError as exc:
        pytest.skip(str(exc))
    except T177PreflightError as exc:
        pytest.fail(str(exc))

    engine = make_async_engine(Settings(pg_dsn=runtime.dsn))
    try:
        preflight = await validate_database_preflight(
            engine,
            confirmation=os.getenv(ENV_CONFIRM),
        )
        discovery_plan = build_discovery_plan(runtime.data_root)
        source_paths = t177c_text_delta_source_paths(discovery_plan)
        source_months = {
            "juso_hangul": source_yyyymm(discovery_plan, "juso_hangul"),
            "jibun_rnaddrkor": source_yyyymm(discovery_plan, "jibun_rnaddrkor"),
            "daily_juso": source_yyyymm(discovery_plan, "daily_juso"),
            "daily_lnbr": source_yyyymm(discovery_plan, "daily_lnbr"),
            "locsum": source_yyyymm(discovery_plan, "locsum"),
            "navi": source_yyyymm(discovery_plan, "navi"),
        }

        await apply_schema_index_smoke(engine)
        schema_report = await schema_smoke_report(engine)
        existing_rows = await collect_existing_row_counts(engine)
        allow_nonempty = os.getenv(ENV_ALLOW_NONEMPTY) == "1"
        assert_no_existing_rows_without_confirmation(
            existing_rows,
            destructive_confirmed=preflight.destructive_confirmed,
            allow_nonempty=allow_nonempty,
        )

        await reset_t177c_target_tables(engine)
        before_counts = await collect_t177c_table_counts(engine)
        result = await run_t177c_text_delta_fast_sample_load(
            engine,
            source_paths=source_paths,
            source_months=source_months,
            limit_per_file=limit_per_file,
        )

        artifact = {
            "schema_version": 1,
            "task": "T-177C",
            "run_id": runtime.run_id,
            "mode": "text_delta_fast_sample_load",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "gates": {
                "full_load_e2e": True,
                "pg_dsn": True,
                "confirmation_ok": preflight.destructive_confirmed,
                "allow_nonempty": allow_nonempty,
                "longrun": False,
                "limit_per_file": limit_per_file,
            },
            "database": {
                "name": preflight.database_name,
                "expected_confirmation": preflight.expected_confirmation,
            },
            "data": discovery_plan,
            "schema": schema_report,
            "before_counts": before_counts,
            "result": result,
        }
        artifact_path = write_json_artifact(
            runtime.artifact_dir,
            "t177c-text-delta-fast-sample-load.json",
            artifact,
        )

        loader_results = result["loader_results"]
        table_counts = result["table_counts"]
        manifests = result["manifests"]
        links = result["links"]

        assert artifact_path.is_file()
        assert schema_report["missing_objects"] == []
        assert loader_results["juso_hangul_rows"] >= limit_per_file
        assert loader_results["daily_juso"]["processed_rows"] == limit_per_file
        assert loader_results["juso_parcel_link_snapshot"]["processed_rows"] >= limit_per_file
        assert loader_results["daily_parcel_link"]["processed_rows"] == limit_per_file
        assert loader_results["locsum_rows"] >= limit_per_file
        assert loader_results["navi_build_rows"] >= limit_per_file
        assert loader_results["navi_entrance_rows"] >= 1
        assert table_counts["public.tl_juso_text"] >= limit_per_file
        assert table_counts["public.tl_juso_parcel_link"] >= limit_per_file
        assert table_counts["public.tl_locsum_entrc"] >= limit_per_file
        assert table_counts["public.tl_navi_buld_centroid"] >= limit_per_file
        assert table_counts["public.tl_navi_entrc"] >= 1
        assert manifests["tl_juso_text"]["source_set"]["kind"] == "daily_juso_delta"
        assert manifests["tl_juso_text"]["row_count"] == limit_per_file
        assert manifests["tl_juso_parcel_link"]["source_set"]["kind"] == "daily_lnbr"
        assert manifests["tl_juso_parcel_link"]["row_count"] == limit_per_file
        assert (
            links["after_resolve"]["locsum_resolved_rows"]
            >= links["before_resolve"]["locsum_resolved_rows"]
        )
        assert (
            links["after_resolve"]["navi_entrance_resolved_rows"]
            >= links["before_resolve"]["navi_entrance_resolved_rows"]
        )
    except T177SkipError as exc:
        pytest.skip(str(exc))
    except T177PreflightError as exc:
        pytest.fail(str(exc))
    finally:
        await engine.dispose()
