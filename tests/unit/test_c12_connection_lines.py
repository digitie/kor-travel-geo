from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from kortravelgeo.loaders.augment_harness import (
    DistanceMeasurement,
    KeyOverlapMeasurement,
)
from kortravelgeo.loaders.building_shape_bundle import CONNECTION_ENTRANCE_REF_FIELDS
from kortravelgeo.loaders.c12_connection_lines import (
    CONNECTION_ROAD_JOIN_KEYS,
    CONNECTION_SOURCE_FIELDS,
    ROAD_MANAGE_SOURCE_FIELDS,
    C12ConnectionComparison,
    RoadAdjacencyMeasurement,
    build_c12_connection_report,
    c12_staging_index_specs,
    connection_staging_spec,
    discover_c12_connection_source_groups,
    road_adjacency_sql,
    road_manage_staging_spec,
)
from kortravelgeo.loaders.shape_dbf import KeyOverlap, KeySetStats

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncEngine


def test_c12_staging_specs_keep_connection_and_road_key_contracts() -> None:
    connection = connection_staging_spec("_ktg_c12_connection")
    road = road_manage_staging_spec("_ktg_c12_road")

    assert connection.geometry_type == "Geometry"
    assert tuple(column.source_field for column in connection.columns) == CONNECTION_SOURCE_FIELDS
    assert tuple(column.name for column in connection.columns) == (
        "sig_cd",
        "ent_man_no",
        "rds_sig_cd",
        "rds_man_no",
        "bsi_int_sn",
        "cnt_drc_ln",
        "cnt_dst_ln",
    )
    assert road.geometry_type == "Geometry"
    assert tuple(column.source_field for column in road.columns) == ROAD_MANAGE_SOURCE_FIELDS
    assert tuple((key.left, key.right) for key in CONNECTION_ROAD_JOIN_KEYS) == (
        ("rds_sig_cd", "sig_cd"),
        ("rds_man_no", "rds_man_no"),
    )
    indexes = c12_staging_index_specs(
        connection_table="_connection",
        road_table="_road",
    )
    assert [(idx.table_name, idx.columns) for idx in indexes] == [
        ("_connection", ("rds_sig_cd", "rds_man_no")),
        ("_road", ("sig_cd", "rds_man_no")),
    ]
    assert CONNECTION_ENTRANCE_REF_FIELDS == ("SIG_CD", "ENT_MAN_NO")


def test_road_adjacency_sql_counts_key_missing_and_distance_dangling() -> None:
    sql = road_adjacency_sql("_connection", "_road")

    assert "LEFT JOIN" in sql
    assert "c.rds_sig_cd = r.sig_cd" in sql
    assert "c.rds_man_no = r.rds_man_no" in sql
    assert "ST_Distance(c.geom, r.geom)" in sql
    assert "road_key_missing" in sql
    assert "dangling_ratio" in sql
    assert ":tolerance_m" in sql


def test_c12_connection_metrics_include_no_serving_promotion_and_samples() -> None:
    comparison = C12ConnectionComparison(
        sido_name="세종특별자치시",
        bundle_zip="bundle.zip",
        electronic_map_dir="electronic/세종특별자치시",
        source_yyyymm="202605",
        tolerance_m=1.0,
        connection_rows=3,
        road_rows=2,
        entrance_ref_overlap=KeyOverlap(
            left=KeySetStats(row_count=3, distinct_count=3, duplicate_count=0),
            right=KeySetStats(row_count=4, distinct_count=4, duplicate_count=0),
            intersection_count=2,
            left_only_count=1,
            right_only_count=2,
        ),
        road_key_overlap=KeyOverlapMeasurement(
            left_rows=3,
            right_rows=2,
            left_distinct=3,
            right_distinct=2,
            intersection_count=2,
            left_only_count=1,
            right_only_count=0,
        ),
        road_distance=DistanceMeasurement(
            samples=2,
            p50_m=0.0,
            p95_m=0.5,
            max_m=1.0,
            sample=(),
        ),
        road_adjacency=RoadAdjacencyMeasurement(
            total_connections=3,
            road_key_matched=2,
            road_key_missing=1,
            within_tolerance=1,
            over_tolerance=1,
            dangling=2,
            dangling_ratio=2 / 3,
            p50_m=0.0,
            p95_m=0.5,
            max_m=1.0,
            sample=({"connection_sig_cd": "36110", "road_key_matched": False},),
        ),
    )

    metrics = comparison.metrics()

    assert metrics["serving_promotion"] is False
    assert metrics["staging_rows"] == {
        "bundle_tl_spot_cntc": 3,
        "electronic_tl_sprd_manage": 2,
    }
    assert metrics["road_adjacency"] == {
        "total_connections": 3,
        "road_key_matched": 2,
        "road_key_missing": 1,
        "within_tolerance": 1,
        "over_tolerance": 1,
        "dangling": 2,
        "dangling_ratio": 2 / 3,
        "p50_m": 0.0,
        "p95_m": 0.5,
        "max_m": 1.0,
    }
    assert comparison.sample()[0]["sample_kind"] == "road_dangling"
    assert comparison.to_payload().source_yyyymm == "202605"


def test_discover_c12_connection_source_groups_tracks_required_inputs(tmp_path: Path) -> None:
    bundle_root = tmp_path / "도로명주소 건물 도형"
    electronic_root = tmp_path / "도로명주소 전자지도"
    bundle_root.mkdir()
    (bundle_root / "건물도형_전체분_세종특별자치시.zip").write_text("", encoding="utf-8")
    (electronic_root / "세종특별자치시").mkdir(parents=True)

    groups = discover_c12_connection_source_groups(
        bundle_root=bundle_root,
        electronic_map_root=electronic_root,
        sido_names=("세종특별자치시", "서울특별시"),
    )

    assert groups[0].path("bundle") == bundle_root / "건물도형_전체분_세종특별자치시.zip"
    assert groups[0].path("electronic") == electronic_root / "세종특별자치시"
    assert groups[0].missing_keys == ()
    assert groups[1].missing_keys == ("bundle", "electronic")


@pytest.mark.asyncio
async def test_build_c12_connection_report_marks_missing_groups_skipped() -> None:
    groups = discover_c12_connection_source_groups(
        bundle_root="missing-bundle",
        electronic_map_root="missing-electronic",
        sido_names=("세종특별자치시",),
    )

    report = await build_c12_connection_report(
        cast("AsyncEngine", object()),
        groups,
        source_yyyymm="202605",
        generated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert report.task_id == "T-112"
    assert report.skipped_count == 1
    assert report.groups[0].error == "missing required source(s): bundle, electronic"
