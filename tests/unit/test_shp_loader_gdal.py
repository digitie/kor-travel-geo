from __future__ import annotations

import inspect
import struct
from pathlib import Path

import pytest

from kraddr.geo.exceptions import LoaderError
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
    stage_source = inspect.getsource(polygons_loader._copy_building_polygon_with_stage)

    assert "openOptions" not in source
    assert '"SHAPE_ENCODING": "CP949"' in source
    assert "_gdal_pg_destination(pg_url)" in source
    assert 'accessMode="append"' in source
    assert 'accessMode="overwrite"' not in source
    assert 'accessMode="overwrite"' in stage_source


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


def test_road_interval_layer_uses_direct_dbf_copy_path() -> None:
    source = inspect.getsource(polygons_loader._load_plans_sync)

    assert "ROAD_INTERVAL_LAYER_NAME" in source
    assert "_copy_road_interval_dbf" in source
    assert source.index("_copy_road_interval_dbf") < source.index("gdal.VectorTranslate")


def test_building_polygon_layer_uses_staging_table_copy_path() -> None:
    source = inspect.getsource(polygons_loader._load_plans_sync)
    stage_source = inspect.getsource(polygons_loader._copy_building_polygon_with_stage)
    insert_source = inspect.getsource(polygons_loader._insert_building_polygon_stage)

    assert "BUILDING_POLYGON_LAYER_NAME" in source
    assert "_copy_building_polygon_with_stage" in source
    assert source.index("_copy_building_polygon_with_stage") < source.index(
        "gdal.VectorTranslate"
    )
    assert "BUILDING_POLYGON_STAGE_TABLE" in stage_source
    assert "SQLStatement=plan.sql_statement" in stage_source
    assert '"PG_USE_COPY": "YES"' in stage_source
    assert '"SHAPE_ENCODING": "CP949"' in stage_source
    assert "finally:" in stage_source
    assert "_drop_stage_table(pg_url, BUILDING_POLYGON_STAGE_TABLE)" in stage_source
    assert "_acquire_building_polygon_stage_lock(pg_url)" in stage_source
    assert "_release_building_polygon_stage_lock(lock_engine, lock_conn)" in stage_source
    assert "pg_try_advisory_lock(hashtext(:lock_key))" in inspect.getsource(
        polygons_loader._acquire_building_polygon_stage_lock
    )
    assert "pg_advisory_unlock(hashtext(:lock_key))" in inspect.getsource(
        polygons_loader._release_building_polygon_stage_lock
    )
    assert "staged_count" in insert_source
    assert "skipped invalid rows" in insert_source
    assert "ST_Multi(geom)::geometry(MultiPolygon, 5179)" in insert_source
    assert "SET LOCAL search_path = public, x_extension" in insert_source


def test_road_interval_dbf_rows_project_to_copy_columns(tmp_path: Path) -> None:
    dbf_path = tmp_path / "TL_SPRD_INTRVL.dbf"
    _write_dbf(
        dbf_path,
        fields=(
            ("BSI_INT_SN", "N", 10),
            ("EVE_BSI_MN", "N", 5),
            ("ODD_BSI_MN", "N", 5),
            ("RDS_MAN_NO", "N", 12),
            ("SIG_CD", "C", 5),
        ),
        rows=(
            {
                "BSI_INT_SN": "45438",
                "EVE_BSI_MN": "58",
                "ODD_BSI_MN": "57",
                "RDS_MAN_NO": "1",
                "SIG_CD": "36110",
            },
            {
                "BSI_INT_SN": "42562",
                "EVE_BSI_MN": "",
                "ODD_BSI_MN": "59",
                "RDS_MAN_NO": "2",
                "SIG_CD": "36110",
            },
        ),
    )
    shp_path = tmp_path / "TL_SPRD_INTRVL.shp"
    shp_path.touch()
    plan = polygons_loader.ShpLoadPlan(
        source_layer="TL_SPRD_INTRVL",
        target_table="tl_sprd_intrvl",
        shp_path=shp_path,
        dbf_path=dbf_path,
        source_file="세종특별자치시/36000/TL_SPRD_INTRVL.shp",
        source_yyyymm="202604",
    )

    rows = [row.to_copy_tuple() for row in polygons_loader._iter_road_interval_copy_rows(plan)]

    assert rows == [
        (
            "36110",
            "1",
            "45438",
            "57",
            "58",
            "세종특별자치시/36000/TL_SPRD_INTRVL.shp",
            "202604",
        ),
        (
            "36110",
            "2",
            "42562",
            "59",
            None,
            "세종특별자치시/36000/TL_SPRD_INTRVL.shp",
            "202604",
        ),
    ]


def test_road_interval_dbf_skips_deleted_records(tmp_path: Path) -> None:
    dbf_path = tmp_path / "TL_SPRD_INTRVL.dbf"
    _write_dbf(
        dbf_path,
        fields=(
            ("SIG_CD", "C", 5),
            ("RDS_MAN_NO", "N", 12),
            ("BSI_INT_SN", "N", 10),
            ("ODD_BSI_MN", "N", 5),
            ("EVE_BSI_MN", "N", 5),
        ),
        rows=(
            {"SIG_CD": "36110", "RDS_MAN_NO": "1", "BSI_INT_SN": "1"},
            {"SIG_CD": "36110", "RDS_MAN_NO": "2", "BSI_INT_SN": "2"},
        ),
        deleted_rows={0},
    )
    plan = polygons_loader.ShpLoadPlan(
        source_layer="TL_SPRD_INTRVL",
        target_table="tl_sprd_intrvl",
        shp_path=tmp_path / "TL_SPRD_INTRVL.shp",
        dbf_path=dbf_path,
        source_file="세종특별자치시/36000/TL_SPRD_INTRVL.shp",
    )

    rows = [row.to_copy_tuple() for row in polygons_loader._iter_road_interval_copy_rows(plan)]

    assert len(rows) == 1
    assert rows[0][:3] == ("36110", "2", "2")


def test_road_interval_dbf_decode_error_includes_record_context(tmp_path: Path) -> None:
    dbf_path = tmp_path / "TL_SPRD_INTRVL.dbf"
    _write_dbf(
        dbf_path,
        fields=(
            ("SIG_CD", "C", 5),
            ("RDS_MAN_NO", "N", 12),
            ("BSI_INT_SN", "N", 10),
            ("ODD_BSI_MN", "N", 5),
            ("EVE_BSI_MN", "N", 5),
        ),
        rows=({"SIG_CD": "36110", "RDS_MAN_NO": "1", "BSI_INT_SN": "1"},),
    )
    data = bytearray(dbf_path.read_bytes())
    header = polygons_loader.read_dbf_header(dbf_path)
    data[header.header_length + 1] = 0xFF
    dbf_path.write_bytes(bytes(data))
    plan = polygons_loader.ShpLoadPlan(
        source_layer="TL_SPRD_INTRVL",
        target_table="tl_sprd_intrvl",
        shp_path=tmp_path / "TL_SPRD_INTRVL.shp",
        dbf_path=dbf_path,
        source_file="세종특별자치시/36000/TL_SPRD_INTRVL.shp",
    )

    with pytest.raises(LoaderError, match=r"1 field SIG_CD failed CP949 decode"):
        list(polygons_loader._iter_road_interval_copy_rows(plan))


def test_road_interval_dbf_truncated_record_error_includes_size_context(tmp_path: Path) -> None:
    dbf_path = tmp_path / "TL_SPRD_INTRVL.dbf"
    _write_dbf(
        dbf_path,
        fields=(
            ("SIG_CD", "C", 5),
            ("RDS_MAN_NO", "N", 12),
            ("BSI_INT_SN", "N", 10),
            ("ODD_BSI_MN", "N", 5),
            ("EVE_BSI_MN", "N", 5),
        ),
        rows=({"SIG_CD": "36110", "RDS_MAN_NO": "1", "BSI_INT_SN": "1"},),
    )
    dbf_path.write_bytes(dbf_path.read_bytes()[:-2])
    plan = polygons_loader.ShpLoadPlan(
        source_layer="TL_SPRD_INTRVL",
        target_table="tl_sprd_intrvl",
        shp_path=tmp_path / "TL_SPRD_INTRVL.shp",
        dbf_path=dbf_path,
        source_file="세종특별자치시/36000/TL_SPRD_INTRVL.shp",
    )

    with pytest.raises(LoaderError, match=r"expected \d+ bytes, got \d+"):
        list(polygons_loader._iter_road_interval_copy_rows(plan))


def test_road_interval_dbf_requires_all_projection_fields(tmp_path: Path) -> None:
    dbf_path = tmp_path / "TL_SPRD_INTRVL.dbf"
    _write_dbf(
        dbf_path,
        fields=(
            ("BSI_INT_SN", "N", 10),
            ("EVE_BSI_MN", "N", 5),
            ("ODD_BSI_MN", "N", 5),
            ("SIG_CD", "C", 5),
        ),
        rows=({"BSI_INT_SN": "1", "EVE_BSI_MN": "2", "ODD_BSI_MN": "1", "SIG_CD": "36110"},),
    )
    plan = polygons_loader.ShpLoadPlan(
        source_layer="TL_SPRD_INTRVL",
        target_table="tl_sprd_intrvl",
        shp_path=tmp_path / "TL_SPRD_INTRVL.shp",
        dbf_path=dbf_path,
        source_file="세종특별자치시/36000/TL_SPRD_INTRVL.shp",
    )

    with pytest.raises(LoaderError, match="RDS_MAN_NO"):
        list(polygons_loader._iter_road_interval_copy_rows(plan))


def _write_dbf(
    path: Path,
    *,
    fields: tuple[tuple[str, str, int], ...],
    rows: tuple[dict[str, str], ...],
    deleted_rows: set[int] | None = None,
) -> None:
    deleted_rows = deleted_rows or set()
    header_length = 32 + len(fields) * 32 + 1
    record_length = 1 + sum(length for _, _, length in fields)
    header = bytearray(32)
    header[0] = 0x03
    header[1:4] = b"\x7e\x05\x1a"
    header[4:8] = struct.pack("<I", len(rows))
    header[8:10] = struct.pack("<H", header_length)
    header[10:12] = struct.pack("<H", record_length)
    descriptors = bytearray()
    for name, field_type, length in fields:
        descriptor = bytearray(32)
        descriptor[: len(name)] = name.encode("ascii")
        descriptor[11] = ord(field_type)
        descriptor[16] = length
        descriptors.extend(descriptor)
    body = bytearray()
    for index, row in enumerate(rows):
        body.append(0x2A if index in deleted_rows else 0x20)
        for name, field_type, length in fields:
            raw = row.get(name, "").encode("cp949")
            raw = raw.rjust(length) if field_type == "N" else raw.ljust(length)
            body.extend(raw[:length])
    path.write_bytes(bytes(header + descriptors + b"\r" + body + b"\x1a"))
