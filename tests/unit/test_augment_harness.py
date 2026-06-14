from __future__ import annotations

import struct
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.augment_harness import (
    AugmentGroupPayload,
    JoinKey,
    ShapeStagingSpec,
    SidoPathPattern,
    SidoSourceGroup,
    StagingColumn,
    build_augment_report,
    discover_sido_source_groups,
    iter_shape_features_from_buffers,
    iter_shp_geometries_from_bytes,
    key_overlap_sql,
    keyed_covers_sql,
    keyed_distance_sql,
    staging_copy_sql,
    staging_create_sql,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_shp_geometry_reader_parses_point_polyline_and_polygon() -> None:
    data = _shp_bytes(
        5,
        (
            _point_record(1.5, 2.5),
            _polyline_record((((0.0, 0.0), (1.0, 1.0), (2.0, 1.0)),)),
            _polygon_record((((0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)),)),
        ),
    )

    point, line, polygon = tuple(iter_shp_geometries_from_bytes(data))

    assert point.shape_kind == "Point"
    assert point.wkt == "POINT (1.5 2.5)"
    assert point.ewkt_5179 == "SRID=5179;POINT (1.5 2.5)"
    assert line.shape_kind == "PolyLine"
    assert line.wkt == "LINESTRING (0 0, 1 1, 2 1)"
    assert polygon.shape_kind == "Polygon"
    assert polygon.wkt == "POLYGON ((0 0, 0 10, 10 10, 10 0, 0 0))"


def test_shape_feature_reader_aligns_dbf_rows_and_skips_deleted_records() -> None:
    shp = _shp_bytes(
        1,
        (
            _point_record(1.0, 2.0),
            _point_record(3.0, 4.0),
            _point_record(5.0, 6.0),
        ),
    )
    dbf = _dbf_bytes(
        fields=(("SIG_CD", 5), ("NAME", 10)),
        records=(
            (False, ("36110", "세종")),
            (True, ("36110", "삭제")),
            (False, ("11680", "")),
        ),
    )

    features = tuple(
        iter_shape_features_from_buffers(
            shp,
            dbf,
            fields=("SIG_CD", "NAME"),
            source_name="synthetic",
        )
    )

    assert [feature.record_number for feature in features] == [1, 3]
    assert features[0].attributes == {"SIG_CD": "36110", "NAME": "세종"}
    assert features[1].attributes == {"SIG_CD": "11680", "NAME": None}


def test_discover_sido_source_groups_tracks_missing_required_inputs(tmp_path: Path) -> None:
    electronic_root = tmp_path / "전자지도"
    bundle_root = tmp_path / "건물도형"
    (electronic_root / "세종특별자치시").mkdir(parents=True)
    bundle_root.mkdir()
    (bundle_root / "건물도형_전체분_세종특별자치시.zip").write_text("", encoding="utf-8")

    groups = discover_sido_source_groups(
        (
            SidoPathPattern("electronic", electronic_root, "{sido}"),
            SidoPathPattern("bundle", bundle_root, "*{sido}*.zip"),
        ),
        sido_names=("세종특별자치시", "서울특별시"),
    )

    assert groups[0].path("electronic") == electronic_root / "세종특별자치시"
    assert groups[0].path("bundle") == bundle_root / "건물도형_전체분_세종특별자치시.zip"
    assert groups[0].missing_keys == ()
    assert groups[1].missing_keys == ("electronic", "bundle")


def test_discover_sido_source_groups_rejects_ambiguous_matches(tmp_path: Path) -> None:
    root = tmp_path / "건물도형"
    root.mkdir()
    (root / "a_세종특별자치시.zip").write_text("", encoding="utf-8")
    (root / "b_세종특별자치시.zip").write_text("", encoding="utf-8")

    with pytest.raises(LoaderError, match="matched 2 paths"):
        discover_sido_source_groups(
            (SidoPathPattern("bundle", root, "*{sido}*.zip"),),
            sido_names=("세종특별자치시",),
        )


def test_build_augment_report_counts_used_skipped_and_failed_groups() -> None:
    groups = discover_sido_source_groups((), sido_names=("세종특별자치시", "서울특별시", "경기도"))

    def analyze(group: SidoSourceGroup) -> AugmentGroupPayload | None:
        if group.sido_name == "서울특별시":
            return None
        if group.sido_name == "경기도":
            raise RuntimeError("boom")
        return AugmentGroupPayload(metrics={"rows": 3}, sample=({"id": "A"},))

    report = build_augment_report(
        task_id="T-110",
        title="test",
        groups=groups,
        analyze_group=analyze,
        source_yyyymm="202605",
        generated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert report.used_count == 1
    assert report.skipped_count == 1
    assert report.failed_count == 1
    assert report.summary()["used"] == 1
    assert report.groups[0].metrics == {"rows": 3}
    assert report.groups[1].error == "analyzer skipped group"
    assert report.groups[2].error == "RuntimeError: boom"


def test_staging_sql_and_measurement_sql_contracts() -> None:
    spec = ShapeStagingSpec(
        table_name="_ktg_aug_points",
        columns=(
            StagingColumn("sig_cd"),
            StagingColumn("ent_man_no", source_field="ENT_MAN_NO"),
        ),
        geometry_type="Point",
    )

    assert staging_create_sql(spec) == (
        'CREATE TABLE "_ktg_aug_points" '
        '("sig_cd" text, "ent_man_no" text, "geom" geometry(Point, 5179))'
    )
    assert staging_copy_sql(spec) == (
        'COPY "_ktg_aug_points" ("sig_cd", "ent_man_no", "geom") FROM STDIN'
    )

    distance_sql = keyed_distance_sql(
        "_left",
        "_right",
        (JoinKey("sig_cd", "sig_cd"), JoinKey("ent_man_no", "ent_man_no")),
    )
    covers_sql = keyed_covers_sql(
        "_poly",
        "_point",
        (JoinKey("sig_cd", "sig_cd"),),
    )

    assert "ST_Distance" in distance_sql
    assert "percentile_cont(0.95)" in distance_sql
    assert '"left_sig_cd"' in distance_sql
    assert "ST_Covers" in covers_sql
    assert "coverage_ratio" in covers_sql
    assert "ST_Contains" not in covers_sql

    overlap_sql = key_overlap_sql(
        "_left",
        "_right",
        (JoinKey("sig_cd", "sig_cd"), JoinKey("ent_man_no", "ent_man_no")),
    )

    assert "left_source" in overlap_sql
    assert "right_source" in overlap_sql
    assert 'USING ("k0", "k1")' in overlap_sql
    assert '"ent_man_no" IS NOT NULL' in overlap_sql
    assert "left_only_count" in overlap_sql


def test_staging_sql_rejects_unsafe_identifiers() -> None:
    spec = ShapeStagingSpec(
        table_name="_ktg_aug_points;DROP TABLE x",
        columns=(StagingColumn("sig_cd"),),
    )

    with pytest.raises(LoaderError, match="invalid SQL identifier"):
        staging_create_sql(spec)


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


def _point_record(x: float, y: float) -> bytes:
    return struct.pack("<i2d", 1, x, y)


def _polyline_record(parts: tuple[tuple[tuple[float, float], ...], ...]) -> bytes:
    return _parted_record(3, parts)


def _polygon_record(parts: tuple[tuple[tuple[float, float], ...], ...]) -> bytes:
    return _parted_record(5, parts)


def _parted_record(shape_type: int, parts: tuple[tuple[tuple[float, float], ...], ...]) -> bytes:
    points = tuple(point for part in parts for point in part)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    content = bytearray()
    content.extend(struct.pack("<i", shape_type))
    content.extend(struct.pack("<4d", min(xs), min(ys), max(xs), max(ys)))
    content.extend(struct.pack("<2i", len(parts), len(points)))
    offset = 0
    for part in parts:
        content.extend(struct.pack("<i", offset))
        offset += len(part)
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
