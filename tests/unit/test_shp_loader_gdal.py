from __future__ import annotations

import inspect

from kraddr.geo.loaders.shp import polygons_loader


def test_gdal_pg_destination_converts_sqlalchemy_url_to_pg_conninfo() -> None:
    destination = polygons_loader._gdal_pg_destination(
        "postgresql+psycopg://addr:p%27w@localhost:15432/kraddr_geo"
    )

    assert destination == (
        "PG:dbname='kraddr_geo' host='localhost' port='15432' "
        "user='addr' password='p\\'w'"
    )


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


def test_shp_load_plan_projects_source_columns_to_target_schema() -> None:
    source = inspect.getsource(polygons_loader._sql_statement)

    assert "CTPRVN_CD AS ctprvn_cd" in source
    assert "BAS_MGT_SN AS bas_mgt_sn" in source
    assert "BD_MGT_SN AS bd_mgt_sn" in source
    assert "RDS_SIG_CD AS rds_sig_cd" in source
    assert "BULD_MNNM AS buld_mnnm" in source
    assert "RW_SN AS rw_sn" in source
    assert "GEOMETRY AS geom" not in source


def test_only_road_interval_layer_drops_geometry() -> None:
    source = inspect.getsource(polygons_loader._geometry_type)

    assert 'layer.name == "TL_SPRD_INTRVL"' in source
    assert 'layer.name == "TL_SPRD_MANAGE"' in source
    assert '"NONE"' in source
    assert '"PROMOTE_TO_MULTI"' in source
