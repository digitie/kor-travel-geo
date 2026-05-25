from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kraddr.geo.loaders.data_quality import (
    CASE_PREPARE_SQL,
    DATA_QUALITY_CASES,
    EXPORT_SPECS,
    _csv_value,
    _iter_sql_statements,
    _write_csv,
    export_data_quality_samples,
)

if TYPE_CHECKING:
    from pathlib import Path


def _spec(filename: str) -> str:
    for spec in EXPORT_SPECS:
        if spec.filename == filename:
            return spec.sql
    raise AssertionError(f"missing export spec: {filename}")


def test_export_specs_cover_t031_followup_cases_and_files() -> None:
    assert DATA_QUALITY_CASES == ("C2", "C4", "C6", "C7")
    assert [spec.filename for spec in EXPORT_SPECS] == [
        "c2_samples.csv",
        "c2_missing_key_summary.csv",
        "c4_distance_samples.csv",
        "c4_distance_buckets.csv",
        "c6_samples.csv",
        "c6_region_summary.csv",
        "c7_samples.csv",
        "c7_region_summary.csv",
    ]
    assert {spec.case_code for spec in EXPORT_SPECS} == set(DATA_QUALITY_CASES)


def test_c2_samples_split_missing_key_and_missing_text_with_trace_columns() -> None:
    sql = _spec("c2_samples.csv")

    assert "missing_resolve_key" in sql
    assert "missing_text" in sql
    assert "NOT EXISTS" in sql
    assert "j.rncode_full = p.rncode_full" in sql
    assert "j.bjd_cd = p.bjd_cd" in sql
    assert "missing_rncode_full" in sql
    assert "missing_bjd_cd" in sql
    assert "source_file" in sql
    assert "source_yyyymm" in sql
    assert "ST_PointOnSurface(p.geom)" in sql
    assert "LIMIT :limit" in sql


def test_c2_missing_key_summary_counts_each_nullable_key_and_source_file() -> None:
    sql = _spec("c2_missing_key_summary.csv")

    assert "NULLIF(rds_sig_cd, '') IS NULL" in sql
    assert "NULLIF(rn_cd, '') IS NULL" in sql
    assert "NULLIF(sig_cd, '') IS NULL" in sql
    assert "NULLIF(emd_cd, '') IS NULL" in sql
    assert "buld_mnnm IS NULL" in sql
    assert "buld_slno IS NULL" in sql
    assert "source_file IS NULL" in sql


def test_c4_exports_use_nearest_polygon_and_distance_buckets() -> None:
    prepare_sql = CASE_PREPARE_SQL["C4"]
    samples_sql = _spec("c4_distance_samples.csv")
    buckets_sql = _spec("c4_distance_buckets.csv")

    assert "CREATE TEMP TABLE _kraddr_dq_c4_distances" in prepare_sql
    assert "JOIN LATERAL" in prepare_sql
    assert "ORDER BY e.geom <-> p.geom" in prepare_sql
    assert "ST_Distance(e.geom, nearest.geom)" in prepare_sql
    assert "CREATE INDEX _kraddr_dq_c4_distances_dist_idx" in prepare_sql
    assert "ST_Transform" not in prepare_sql
    assert "polygon_source_file" in samples_sql
    assert "entrance_source_file" in samples_sql
    assert "WITH samples AS" in samples_sql
    assert "ST_Transform(entrance_geom, 4326)" in samples_sql
    assert "delta_lon" in samples_sql
    assert "delta_lat" in samples_sql
    assert "FROM _kraddr_dq_c4_distances" in samples_sql
    assert "FROM _kraddr_dq_c4_distances" in buckets_sql
    assert "JOIN LATERAL" not in samples_sql + buckets_sql
    assert "WHEN dist_m > 500 THEN '500+'" in samples_sql
    assert "WHEN dist_m > 100 THEN '100-500'" in samples_sql
    assert "ELSE '50-100'" in samples_sql
    assert "WHEN dist_m > 50 THEN '50-100'" in buckets_sql
    assert "ELSE '0-50'" in buckets_sql


def test_c6_c7_exports_keep_st_covers_and_region_summaries() -> None:
    c6_prepare = CASE_PREPARE_SQL["C6"]
    c7_prepare = CASE_PREPARE_SQL["C7"]
    c6_samples = _spec("c6_samples.csv")
    c6_summary = _spec("c6_region_summary.csv")
    c7_samples = _spec("c7_samples.csv")
    c7_summary = _spec("c7_region_summary.csv")

    assert "CREATE TEMP TABLE _kraddr_dq_c6_violations" in c6_prepare
    assert "CREATE TEMP TABLE _kraddr_dq_c7_violations" in c7_prepare
    assert "NOT ST_Covers(bas_geom, geom)" in c6_prepare
    assert "NOT ST_Covers(emd_geom, geom)" in c7_prepare
    assert "missing_zip_polygon" in c6_prepare
    assert "outside_zip_polygon" in c6_prepare
    assert "FROM _kraddr_dq_c6_violations" in c6_samples
    assert "FROM _kraddr_dq_c6_violations" in c6_summary
    assert "zip_no AS region_key" in c6_prepare
    assert "missing_emd_polygon" in c7_prepare
    assert "outside_emd_polygon" in c7_prepare
    assert "FROM _kraddr_dq_c7_violations" in c7_samples
    assert "FROM _kraddr_dq_c7_violations" in c7_summary
    assert "emd_cd AS region_key" in c7_prepare
    combined_sql = c6_prepare + c7_prepare + c6_samples + c6_summary + c7_samples + c7_summary
    assert "ST_Contains" not in combined_sql


def test_write_csv_writes_header_for_empty_rows(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"

    _write_csv(path, ("a", "b"), ())

    assert path.read_text(encoding="utf-8") == "a,b\n"


def test_write_csv_serializes_nulls_booleans_and_ignores_extra_keys(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"

    _write_csv(
        path,
        ("missing", "ok", "value"),
        ({"missing": None, "ok": True, "value": 3, "extra": "ignored"},),
    )

    assert path.read_text(encoding="utf-8") == "missing,ok,value\n,true,3\n"
    assert _csv_value(False) == "false"
    assert _csv_value(None) == ""


def test_iter_sql_statements_splits_prepare_batches() -> None:
    statements = _iter_sql_statements(CASE_PREPARE_SQL["C4"])

    assert statements[0] == "DROP TABLE IF EXISTS _kraddr_dq_c4_distances"
    assert statements[-1] == "ANALYZE _kraddr_dq_c4_distances"
    assert len(statements) == 4


@pytest.mark.asyncio
async def test_export_rejects_unknown_case_before_touching_engine(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported data quality case"):
        await export_data_quality_samples(
            object(),  # type: ignore[arg-type]
            tmp_path,
            cases=("C99",),
        )
