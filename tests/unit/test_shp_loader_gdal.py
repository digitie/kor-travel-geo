from __future__ import annotations

import inspect
from pathlib import Path

from kraddr.geo.loaders.juso_map import MASTER_LAYER_NAMES
from kraddr.geo.loaders.shp import polygons_loader


def test_gdal_pg_destination_converts_sqlalchemy_url_to_pg_conninfo() -> None:
    destination = polygons_loader._gdal_pg_destination(
        "postgresql+psycopg://addr:p%27w@localhost:15432/kraddr_geo"
    )

    assert destination == (
        "PG:dbname='kraddr_geo' host='localhost' port='15432' "
        "user='addr' password='p\\'w' connect_timeout='10'"
    )


def test_gdal_pg_destination_uses_query_connect_timeout() -> None:
    destination = polygons_loader._gdal_pg_destination(
        "postgresql+psycopg://addr:addr@localhost:15432/kraddr_geo?connect_timeout=30"
    )

    assert "connect_timeout='30'" in destination


def test_vector_translate_uses_gdal_38_compatible_encoding_options() -> None:
    source = inspect.getsource(polygons_loader._load_plans_sync)

    assert "openOptions" not in source
    assert '"SHAPE_ENCODING": "CP949"' in source
    assert "_gdal_pg_destination(pg_url)" in source
    assert 'accessMode="append"' in source
    assert 'accessMode="overwrite"' not in source


def test_full_mode_logs_row_count_snapshot_before_truncate() -> None:
    source = inspect.getsource(polygons_loader._truncate_target_tables)

    assert "_table_count_snapshot" in source
    assert "approximate row counts before TRUNCATE" in source
    assert source.index("_table_count_snapshot") < source.index("TRUNCATE TABLE")


def test_shp_loader_analyzes_target_tables_after_requested_batch() -> None:
    source = inspect.getsource(polygons_loader._load_plans_sync)
    analyze_source = inspect.getsource(polygons_loader._analyze_target_tables)

    assert "if analyze:" in source
    assert "_analyze_target_tables" in source
    assert "_unique_target_tables(plans)" in source
    assert "ANALYZE {table_name}" in analyze_source
    assert analyze_source.index("for table_name in table_names") < analyze_source.index(
        "with engine.begin()"
    )


def test_unique_target_tables_preserves_order() -> None:
    plans = (
        polygons_loader.ShpLoadPlan("A", "table_a", Path("a.shp"), Path("a.dbf"), "a.shp"),
        polygons_loader.ShpLoadPlan("B", "table_b", Path("b.shp"), Path("b.dbf"), "b.shp"),
        polygons_loader.ShpLoadPlan("C", "table_a", Path("c.shp"), Path("c.dbf"), "c.shp"),
    )

    assert polygons_loader._unique_target_tables(plans) == ("table_a", "table_b")


def test_shp_load_plan_projects_source_columns_to_target_schema() -> None:
    source = inspect.getsource(polygons_loader._sql_statement)

    assert "CTPRVN_CD AS ctprvn_cd" in source
    assert "BAS_MGT_SN AS bas_mgt_sn" in source
    assert "BD_MGT_SN AS bd_mgt_sn" in source
    assert "RDS_SIG_CD AS rds_sig_cd" in source
    assert "BULD_MNNM AS buld_mnnm" in source
    assert "RW_SN AS rw_sn" in source
    assert "source_file" in source
    assert "source_yyyymm" in source
    assert "GEOMETRY AS geom" not in source


def test_shp_load_plan_embeds_source_trace_metadata(tmp_path: Path) -> None:
    sig_dir = tmp_path / "Seoul" / "11000"
    sig_dir.mkdir(parents=True)
    for layer_name in MASTER_LAYER_NAMES:
        for suffix in (".shp", ".shx", ".dbf"):
            (sig_dir / f"{layer_name}{suffix}").touch()

    plans = polygons_loader.build_shp_load_plan(
        tmp_path / "Seoul",
        source_yyyymm="202604",
    )
    building = next(plan for plan in plans if plan.source_layer == "TL_SPBD_BULD")

    assert building.source_file == "Seoul/11000/TL_SPBD_BULD.shp"
    assert building.source_yyyymm == "202604"
    assert building.sql_statement is not None
    assert "'Seoul/11000/TL_SPBD_BULD.shp' AS source_file" in building.sql_statement
    assert "'202604' AS source_yyyymm" in building.sql_statement


def test_shp_sql_literal_escapes_quotes_and_allows_null_month() -> None:
    assert polygons_loader._sql_literal("a'b") == "'a''b'"
    assert polygons_loader._metadata_projection(
        source_file="a'b.shp",
        source_yyyymm=None,
    ) == ", 'a''b.shp' AS source_file, NULL AS source_yyyymm"


def test_only_road_interval_layer_drops_geometry() -> None:
    source = inspect.getsource(polygons_loader._geometry_type)

    assert 'layer.name == "TL_SPRD_INTRVL"' in source
    assert 'layer.name == "TL_SPRD_MANAGE"' in source
    assert '"NONE"' in source
    assert '"PROMOTE_TO_MULTI"' in source
