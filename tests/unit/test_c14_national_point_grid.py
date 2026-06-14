from __future__ import annotations

import struct
import zipfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.dto.common import Point
from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.augment_harness import ShapeFeature, ShapeGeometry
from kortravelgeo.loaders.c14_national_point_grid import (
    GRID_LAYER_SPECS,
    C14NationalPointGridComparison,
    CenterFileValidation,
    CenterRow,
    GridCoverageItem,
    GridCoverageValidation,
    GridLayerValidation,
    build_c14_national_point_grid_report,
    iter_center_rows,
    iter_grid_zip_shape_features,
    measure_count_coverage,
    parent_grid_code_from_point,
    parse_grid_code,
    validate_center_rows,
    validate_grid_layer_features,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_grid_code_computes_bbox_and_formatter_parent() -> None:
    ten_km = parse_grid_code("나바45", expected_digits_per_axis=1)
    hundred_m = parse_grid_code("가다789668", expected_digits_per_axis=3)

    assert ten_km is not None
    assert ten_km.bbox_5179 == (840000.0, 1850000.0, 850000.0, 1860000.0)
    assert ten_km.center_5179.x == pytest.approx(845000.0)
    assert ten_km.center_5179.y == pytest.approx(1855000.0)
    assert parent_grid_code_from_point(ten_km.center_5179, 1) == "나바45"

    assert hundred_m is not None
    assert hundred_m.bbox_5179 == (778900.0, 1566800.0, 779000.0, 1566900.0)
    assert hundred_m.center_5179.x == pytest.approx(778950.0)
    assert hundred_m.center_5179.y == pytest.approx(1566850.0)
    assert parent_grid_code_from_point(hundred_m.center_5179, 3) == "가다789668"

    assert parse_grid_code("세종 가다789668") is None
    assert parse_grid_code("가다789668", expected_digits_per_axis=2) is None
    assert parent_grid_code_from_point(Point(x=1.0, y=1.0), 3) is None


def test_validate_grid_layer_features_tracks_bbox_and_formatter_samples() -> None:
    spec = GRID_LAYER_SPECS[3]
    features = (
        _feature("가다789668", (778900.0, 1566800.0, 779000.0, 1566900.0), field="SPO_100M"),
        _feature("가다789669", (0.0, 0.0, 1.0, 1.0), field="SPO_100M"),
        _feature("bad-code", (0.0, 0.0, 1.0, 1.0), field="SPO_100M"),
    )

    validation = validate_grid_layer_features(
        spec,
        features,
        total_rows=3,
        sample_limit=3,
    )

    assert validation.row_count == 3
    assert validation.checked_count == 3
    assert validation.invalid_code_count == 1
    assert validation.bbox_mismatch_count == 1
    assert validation.formatter_parent_mismatch_count == 0
    assert {row["issue"] for row in validation.sample} == {"bbox_mismatch", "invalid_code"}


def test_iter_grid_zip_shape_features_streams_bbox_and_key(tmp_path: Path) -> None:
    archive = tmp_path / "grid.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "TL_SPPN_GRID_100M.shp",
            _shp_bytes(
                5,
                (
                    _polygon_record(_box_points(778900.0, 1566800.0, 779000.0, 1566900.0)),
                    _polygon_record(_box_points(779000.0, 1566800.0, 779100.0, 1566900.0)),
                ),
            ),
        )
        zip_file.writestr(
            "TL_SPPN_GRID_100M.dbf",
            _dbf_bytes(
                fields=(("SPO_100M", 10),),
                records=(
                    (False, ("가다789668",)),
                    (False, ("가다790668",)),
                ),
            ),
        )

    features = tuple(
        iter_grid_zip_shape_features(
            archive,
            "TL_SPPN_GRID_100M",
            fields=("SPO_100M",),
        )
    )
    validation = validate_grid_layer_features(
        GRID_LAYER_SPECS[3],
        features,
        total_rows=2,
    )

    assert [feature.attributes["SPO_100M"] for feature in features] == [
        "가다789668",
        "가다790668",
    ]
    assert features[0].geometry.bbox == (778900.0, 1566800.0, 779000.0, 1566900.0)
    assert validation.invalid_code_count == 0
    assert validation.bbox_mismatch_count == 0


def test_center_rows_parser_and_validation_reads_zip(tmp_path: Path) -> None:
    archive = tmp_path / "center.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "SPPN_TEST.TXT",
            "나바45|845000.0|1855000.0\n가다789668|778950.0|1566850.0\n".encode(
                "cp949"
            ),
        )

    rows = tuple(iter_center_rows(archive))
    validation = validate_center_rows(rows, member_name="SPPN_TEST.TXT")

    assert [row.code_text for row in rows] == ["나바45", "가다789668"]
    assert validation.row_count == 2
    assert validation.count_by_resolution_m[10_000] == 1
    assert validation.count_by_resolution_m[100] == 1
    assert validation.center_mismatch_count == 0
    assert validation.formatter_parent_mismatch_count == 0


def test_center_validation_tracks_mismatch_samples() -> None:
    validation = validate_center_rows(
        (
            CenterRow("<stream>", 1, "나바45", Point(x=855001.0, y=1855000.0)),
            CenterRow("<stream>", 2, "bad", Point(x=1.0, y=1.0)),
        ),
        sample_limit=3,
    )

    assert validation.invalid_row_count == 1
    assert validation.center_mismatch_count == 1
    assert validation.formatter_parent_mismatch_count == 1
    assert {row["issue"] for row in validation.sample} == {
        "center_mismatch",
        "formatter_parent_mismatch",
        "invalid_code",
    }


def test_center_rows_parser_rejects_bad_column_count(tmp_path: Path) -> None:
    archive = tmp_path / "center.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("SPPN_TEST.TXT", "나바45|845000.0\n".encode("cp949"))

    with pytest.raises(LoaderError, match="expected 3 columns"):
        tuple(iter_center_rows(archive))


def test_count_coverage_compares_shape_and_center_resolution_counts() -> None:
    layers = (
        _layer_validation(100_000, 30),
        _layer_validation(10_000, 1341),
        _layer_validation(1_000, 106596),
        _layer_validation(100, 10076774),
    )
    center = CenterFileValidation(
        member_name="SPPN_20240508.TXT",
        row_count=10184741,
        checked_count=10184741,
        limited=False,
        count_by_resolution_m={
            100_000: 30,
            10_000: 1341,
            1_000: 106596,
            100: 10076774,
        },
        invalid_row_count=0,
        center_mismatch_count=0,
        formatter_parent_mismatch_count=0,
    )

    coverage = measure_count_coverage(layers, center)

    assert coverage.total_shape_rows == 10184741
    assert coverage.total_center_rows == 10184741
    assert coverage.all_row_counts_match is True


def test_c14_metrics_keep_validation_only_contract() -> None:
    coverage = GridCoverageValidation((GridCoverageItem(100_000, 30, 30),))
    comparison_layers = (_layer_validation(100_000, 30),)
    center = CenterFileValidation(
        member_name="SPPN_TEST.TXT",
        row_count=30,
        checked_count=30,
        limited=False,
        count_by_resolution_m={100_000: 30},
        invalid_row_count=0,
        center_mismatch_count=0,
        formatter_parent_mismatch_count=0,
    )
    comparison = C14NationalPointGridComparison(
        grid_shape_zip="grid.zip",
        grid_center_zip="center.zip",
        source_yyyymm="202405",
        layer_validations=comparison_layers,
        center_validation=center,
        coverage=coverage,
    )

    metrics = comparison.metrics()

    assert metrics["serving_promotion"] is False
    assert metrics["coverage_count_basis"] == "full_stream"
    assert metrics["coverage"] == {
        "total_shape_rows": 30,
        "total_center_rows": 30,
        "all_row_counts_match": True,
        "by_resolution_m": {
            100_000: {
                "shape_rows": 30,
                "center_rows": 30,
                "row_count_delta": 0,
                "row_count_matches": True,
            }
        },
    }


def test_build_c14_report_sets_generated_at_on_failure(tmp_path: Path) -> None:
    report = build_c14_national_point_grid_report(
        tmp_path / "missing-grid.zip",
        tmp_path / "missing-center.zip",
        source_yyyymm="202405",
        generated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert report.task_id == "T-114"
    assert report.generated_at == "2026-06-14T00:00:00+00:00"
    assert report.failed_count == 1
    assert report.groups[0].source_yyyymm == "202405"


def _feature(
    code: str,
    bbox: tuple[float, float, float, float],
    *,
    field: str,
) -> ShapeFeature:
    return ShapeFeature(
        record_number=1,
        attributes={field: code},
        geometry=ShapeGeometry(
            record_number=1,
            shape_kind="Polygon",
            wkt=None,
            bbox=bbox,
            part_count=1,
            point_count=5,
        ),
    )


def _layer_validation(resolution_m: int, row_count: int) -> GridLayerValidation:
    return GridLayerValidation(
        layer_name=f"layer_{resolution_m}",
        key_field="code",
        resolution_m=resolution_m,
        digits_per_axis=0,
        row_count=row_count,
        checked_count=row_count,
        limited=False,
        invalid_code_count=0,
        bbox_mismatch_count=0,
        formatter_parent_mismatch_count=0,
    )


def _box_points(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> tuple[tuple[float, float], ...]:
    return (
        (min_x, min_y),
        (max_x, min_y),
        (max_x, max_y),
        (min_x, max_y),
        (min_x, min_y),
    )


def _shp_bytes(shape_type: int, contents: tuple[bytes, ...]) -> bytes:
    records = bytearray()
    for index, content in enumerate(contents, start=1):
        records.extend(struct.pack(">2i", index, len(content) // 2))
        records.extend(content)
    header = bytearray(100)
    header[0:4] = struct.pack(">i", 9994)
    header[24:28] = struct.pack(">i", (100 + len(records)) // 2)
    header[28:32] = struct.pack("<i", 1000)
    header[32:36] = struct.pack("<i", shape_type)
    return bytes(header + records)


def _polygon_record(points: tuple[tuple[float, float], ...]) -> bytes:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    content = bytearray()
    content.extend(struct.pack("<i", 5))
    content.extend(struct.pack("<4d", min(xs), min(ys), max(xs), max(ys)))
    content.extend(struct.pack("<2i", 1, len(points)))
    content.extend(struct.pack("<i", 0))
    for x, y in points:
        content.extend(struct.pack("<2d", x, y))
    return bytes(content)


def _dbf_bytes(
    *,
    fields: tuple[tuple[str, int], ...],
    records: tuple[tuple[bool, tuple[str, ...]], ...],
) -> bytes:
    header_length = 32 + 32 * len(fields) + 1
    record_length = 1 + sum(length for _, length in fields)
    header = bytearray(32)
    header[0] = 0x03
    header[4:8] = struct.pack("<I", len(records))
    header[8:10] = struct.pack("<H", header_length)
    header[10:12] = struct.pack("<H", record_length)

    descriptors = bytearray()
    for name, length in fields:
        descriptor = bytearray(32)
        descriptor[: len(name)] = name.encode("ascii")
        descriptor[11] = ord("C")
        descriptor[16] = length
        descriptors.extend(descriptor)

    body = bytearray()
    for deleted, values in records:
        body.extend(b"*" if deleted else b" ")
        for value, (_, length) in zip(values, fields, strict=True):
            body.extend(value.encode("cp949").ljust(length)[:length])

    return bytes(header + descriptors + b"\r" + body + b"\x1a")
