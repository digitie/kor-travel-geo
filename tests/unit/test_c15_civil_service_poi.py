from __future__ import annotations

import struct
import zipfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.loaders.c15_civil_service_poi import (
    C15CivilServicePoiComparison,
    CivilServicePoiDistanceMeasurement,
    build_c15_civil_service_poi_report,
    civil_service_poi_geocode_distance_sql,
    civil_service_poi_staging_spec,
    iter_civil_service_poi_features,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_iter_civil_service_poi_features_reads_korean_dbf_fields(tmp_path: Path) -> None:
    archive = tmp_path / "civil.zip"
    _write_civil_zip(
        archive,
        records=(
            (
                (
                    "학교",
                    "중학교",
                    "11110",
                    "3100014",
                    "서울특별시 종로구 창의문로 51",
                    "청운중학교",
                ),
                (953304.964042, 1954550.726243),
                "02-737-0582",
            ),
            (
                (
                    "행정",
                    "주민센터",
                    "11110",
                    "3100001",
                    "서울특별시 종로구 세종대로",
                    "테스트센터",
                ),
                (953000.0, 1954000.0),
                None,
            ),
        ),
    )

    features = tuple(iter_civil_service_poi_features(archive))

    assert len(features) == 2
    assert features[0].geometry.wkt == "POINT (953304.964042 1954550.726243)"
    assert features[0].attributes["institution_type"] == "학교"
    assert features[0].attributes["detail_class"] == "중학교"
    assert features[0].attributes["sigungu_code"] == "11110"
    assert features[0].attributes["road_code"] == "3100014"
    assert features[0].attributes["road_address"] == "서울특별시 종로구 창의문로 51"
    assert features[0].attributes["institution_name"] == "청운중학교"
    assert features[0].attributes["road_nrm"] == "창의문로"
    assert features[0].attributes["buld_mnnm"] == "51"
    assert features[0].attributes["buld_slno"] == "0"
    assert features[0].attributes["buld_se_cd"] == "0"
    assert features[0].attributes["parse_error"] is None
    assert features[1].attributes["parse_error"] == "address number could not be parsed"


def test_civil_service_poi_staging_spec_is_validation_only_point_table() -> None:
    spec = civil_service_poi_staging_spec("_ktg_test_c15")

    assert spec.table_name == "_ktg_test_c15"
    assert spec.geometry_type == "Point"
    assert [column.name for column in spec.columns][:3] == [
        "record_number",
        "institution_type",
        "detail_class",
    ]
    assert {column.name for column in spec.columns} >= {
        "road_address",
        "institution_name",
        "road_nrm",
        "buld_mnnm",
        "parse_error",
    }


def test_civil_service_poi_distance_sql_uses_mv_without_serving_insert() -> None:
    sql = civil_service_poi_geocode_distance_sql(
        "_ktg_c15_civil_service_poi",
        "mv_geocode_target",
    )

    assert 'FROM "_ktg_c15_civil_service_poi"' in sql
    assert 'LEFT JOIN "mv_geocode_target" t' in sql
    assert "ST_Distance(p.geom, t.pt_5179)" in sql
    assert "t.rn_nrm = p.road_nrm" in sql
    assert "right(t.sgg_nm, char_length(p.sgg_nm)) = p.sgg_nm" in sql
    assert "distance_outlier" in sql
    assert "INSERT INTO" not in sql
    assert "CREATE MATERIALIZED VIEW" not in sql


def test_c15_metrics_keep_poi_out_of_serving_candidates() -> None:
    measurement = CivilServicePoiDistanceMeasurement(
        total_poi_rows=10,
        parsed_address_rows=8,
        unparsed_address_rows=2,
        geocode_matched_rows=7,
        geocode_missing_rows=1,
        geocode_point_missing_rows=0,
        measured_rows=7,
        outlier_threshold_m=100.0,
        outlier_rows=2,
        p50_m=12.5,
        p95_m=240.0,
        max_m=400.0,
        sample=({"sample_kind": "distance_outlier", "distance_m": 400.0},),
    )
    comparison = C15CivilServicePoiComparison(
        civil_service_zip="민원행정기관전자지도_240124.zip",
        source_yyyymm="202401",
        poi_rows=10,
        distance=measurement,
        geocode_target_table="mv_geocode_target",
        outlier_threshold_m=100.0,
    )

    metrics = comparison.metrics()

    assert metrics["serving_promotion"] is False
    assert metrics["address_parse"] == {
        "parsed_rows": 8,
        "unparsed_rows": 2,
        "parsed_ratio": 0.8,
    }
    assert metrics["geocode_distance_m"]["geocoder_contract"] == "batch_exact_road_lookup"
    assert metrics["geocode_distance_m"]["outlier_ratio"] == 2 / 7
    assert "does not add institution names" in metrics["notes"]
    assert comparison.sample() == measurement.sample


@pytest.mark.asyncio
async def test_build_c15_report_sets_generated_at_on_failure(tmp_path: Path) -> None:
    class DummyEngine:
        pass

    report = await build_c15_civil_service_poi_report(
        DummyEngine(),  # type: ignore[arg-type]
        tmp_path / "missing.zip",
        source_yyyymm="202401",
        generated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert report.task_id == "T-115"
    assert report.generated_at == "2026-06-14T00:00:00+00:00"
    assert report.failed_count == 1
    assert report.groups[0].source_yyyymm == "202401"


def _write_civil_zip(
    archive: Path,
    *,
    records: tuple[
        tuple[
            tuple[str, str, str, str, str, str],
            tuple[float, float],
            str | None,
        ],
        ...,
    ],
) -> None:
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "민원행정기관_202401.shp",
            _shp_bytes(tuple(_point_record(x, y) for _attrs, (x, y), _phone in records)),
        )
        zip_file.writestr(
            "민원행정기관_202401.dbf",
            _dbf_bytes(
                records=tuple(
                    (
                        *attrs,
                        f"{point[0]:.15f}",
                        f"{point[1]:.15f}",
                        phone or "",
                    )
                    for attrs, point, phone in records
                )
            ),
        )


def _shp_bytes(contents: tuple[bytes, ...]) -> bytes:
    records = bytearray()
    for index, content in enumerate(contents, start=1):
        records.extend(struct.pack(">2i", index, len(content) // 2))
        records.extend(content)
    header = bytearray(100)
    header[0:4] = struct.pack(">i", 9994)
    header[24:28] = struct.pack(">i", (100 + len(records)) // 2)
    header[28:32] = struct.pack("<i", 1000)
    header[32:36] = struct.pack("<i", 1)
    return bytes(header + records)


def _point_record(x: float, y: float) -> bytes:
    return struct.pack("<i2d", 1, x, y)


def _dbf_bytes(
    *,
    records: tuple[tuple[str, str, str, str, str, str, str, str, str], ...],
) -> bytes:
    fields = (
        ("유형", "C", 32, 0),
        ("상세분류", "C", 32, 0),
        ("시군구코드", "N", 10, 0),
        ("도로명코드", "N", 10, 0),
        ("도로명주소", "C", 80, 0),
        ("기관명", "C", 50, 0),
        ("위치X", "N", 24, 15),
        ("위치Y", "N", 24, 15),
        ("전화번호", "C", 30, 0),
    )
    header_length = 32 + 32 * len(fields) + 1
    record_length = 1 + sum(length for _name, _kind, length, _decimal in fields)
    header = bytearray(32)
    header[0] = 0x03
    header[4:8] = struct.pack("<I", len(records))
    header[8:10] = struct.pack("<H", header_length)
    header[10:12] = struct.pack("<H", record_length)

    descriptors = bytearray()
    for name, kind, length, decimal_count in fields:
        name_bytes = name.encode("cp949")
        descriptor = bytearray(32)
        descriptor[: len(name_bytes)] = name_bytes
        descriptor[11] = ord(kind)
        descriptor[16] = length
        descriptor[17] = decimal_count
        descriptors.extend(descriptor)

    body = bytearray()
    for values in records:
        body.extend(b" ")
        for value, (_name, kind, length, _decimal_count) in zip(values, fields, strict=True):
            encoded = value.encode("cp949")
            padded = encoded.rjust(length) if kind == "N" else encoded.ljust(length)
            body.extend(padded[:length])
    return bytes(header + descriptors + b"\r" + body + b"\x1a")
