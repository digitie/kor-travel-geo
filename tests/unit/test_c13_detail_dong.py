from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.augment_harness import CoversMeasurement, KeyOverlapMeasurement
from kortravelgeo.loaders.c13_detail_dong import (
    BUILDING_MANAGEMENT_JOIN_KEYS,
    DETAIL_ADDRESS_COPY_COLUMNS,
    ENTRANCE_BUILDING_REF_JOIN_KEYS,
    ROAD_ADDRESS_JOIN_KEYS,
    C13DetailDongComparison,
    DetailDongEntranceContainmentMeasurement,
    detail_address_member_for_sido,
    detail_dong_entrance_staging_spec,
    detail_dong_polygon_staging_spec,
    detail_entrance_containment_sql,
    discover_c13_detail_dong_source_groups,
    iter_detail_address_rows,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_detail_address_parser_reads_guide_layout(tmp_path: Path) -> None:
    archive = tmp_path / "detail-address.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "adrdc_sejong.txt",
            (
                "36110|10794|48613|193391|0||1|101||0|"
                "3611034038102860001000001|3611034038|361103000098|0|00042|00000\n"
            ).encode("cp949"),
        )

    rows = tuple(iter_detail_address_rows(archive, member_name="adrdc_sejong.txt"))

    assert len(rows) == 1
    row = rows[0]
    assert row.source_member == "adrdc_sejong.txt"
    assert row.sig_cd == "36110"
    assert row.dong_name is None
    assert row.floor_name == "1"
    assert row.unit_name == "101"
    assert row.building_management_no == "3611034038102860001000001"
    assert row.road_name_cd == "361103000098"
    assert row.road_name_no == "3000098"
    assert row.building_main_no == "42"
    assert row.building_sub_no == "0"
    assert len(row.copy_row()) == len(DETAIL_ADDRESS_COPY_COLUMNS)


def test_detail_address_parser_rejects_bad_column_count(tmp_path: Path) -> None:
    archive = tmp_path / "detail-address.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("adrdc_sejong.txt", "36110|too-short\n".encode("cp949"))

    with pytest.raises(LoaderError, match="expected 16 columns"):
        tuple(iter_detail_address_rows(archive, member_name="adrdc_sejong.txt"))


def test_detail_address_parser_rejects_non_numeric_integer_fields(tmp_path: Path) -> None:
    archive = tmp_path / "detail-address.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "adrdc_sejong.txt",
            (
                "36110|not-number|48613|193391|0||1|101||0|"
                "3611034038102860001000001|3611034038|361103000098|0|00042|00000\n"
            ).encode("cp949"),
        )

    with pytest.raises(LoaderError, match=r"adrdc_sejong\.txt:1 dong_serial_no"):
        tuple(iter_detail_address_rows(archive, member_name="adrdc_sejong.txt"))


def test_detail_dong_staging_specs_and_join_keys() -> None:
    polygon = detail_dong_polygon_staging_spec("_ktg_test_polygon")
    entrance = detail_dong_entrance_staging_spec("_ktg_test_entrc")

    assert polygon.geometry_type == "Geometry"
    assert entrance.geometry_type == "Point"
    assert tuple(column.source_field for column in polygon.columns) == (
        "ADR_MNG_NO",
        "BD_MGT_SN",
        "SIG_CD",
        "BUL_MAN_NO",
        "RN_CD",
        "BULD_SE_CD",
        "BULD_MNNM",
        "BULD_SLNO",
        "EQB_MAN_SN",
    )
    assert tuple(column.source_field for column in entrance.columns) == (
        "SIG_CD",
        "ENT_MAN_NO",
        "BUL_MAN_NO",
        "ENTRC_SE",
        "OPERT_DE",
        "ENTRC_DC",
    )
    assert tuple((key.left, key.right) for key in BUILDING_MANAGEMENT_JOIN_KEYS) == (
        ("bd_mgt_sn", "building_management_no"),
    )
    assert tuple((key.left, key.right) for key in ROAD_ADDRESS_JOIN_KEYS) == (
        ("sig_cd", "sig_cd"),
        ("rn_cd", "road_name_no"),
        ("buld_se_cd", "road_underground_yn"),
        ("buld_mnnm", "building_main_no"),
        ("buld_slno", "building_sub_no"),
    )
    assert tuple((key.left, key.right) for key in ENTRANCE_BUILDING_REF_JOIN_KEYS) == (
        ("sig_cd", "sig_cd"),
        ("bul_man_no", "bul_man_no"),
    )


def test_discover_c13_groups_reuses_national_detail_address_zip(tmp_path: Path) -> None:
    detail_root = tmp_path / "detail-dong"
    detail_root.mkdir()
    detail_zip = detail_root / "건물군내동도형_전체분_세종특별자치시.zip"
    detail_zip.write_bytes(b"placeholder")
    address_zip = tmp_path / "202605_상세주소DB_전체분.zip"
    with zipfile.ZipFile(address_zip, "w") as zip_file:
        zip_file.writestr("adrdc_sejong.txt", b"")

    groups = discover_c13_detail_dong_source_groups(
        detail_dong_root=detail_root,
        detail_address_db_zip=address_zip,
        sido_names=("세종특별자치시", "서울특별시"),
    )

    assert groups[0].sido_name == "세종특별자치시"
    assert not groups[0].missing_keys
    assert groups[0].path("detail_dong") == detail_zip
    assert groups[0].path("detail_address_db") == address_zip
    assert groups[1].missing_keys == ("detail_dong", "detail_address_db")
    assert detail_address_member_for_sido("경기도") == "adrdc_gyunggi.txt"


def test_detail_entrance_containment_sql_uses_st_covers_and_address_filter() -> None:
    sql = detail_entrance_containment_sql(
        "_ktg_c13_poly",
        "_ktg_c13_entrc",
        "_ktg_c13_addr",
    )

    assert "ST_Covers(p.geom, e.geom)" in sql
    assert "SELECT DISTINCT building_management_no" in sql
    assert 'FROM "_ktg_c13_poly" p' in sql
    assert 'JOIN "_ktg_c13_entrc" e' in sql


def test_c13_metrics_keep_containment_and_no_serving_promotion() -> None:
    comparison = C13DetailDongComparison(
        sido_name="세종특별자치시",
        detail_dong_zip="detail.zip",
        detail_address_db_zip="address.zip",
        detail_address_member="adrdc_sejong.txt",
        source_yyyymm="202605",
        detail_dong_rows=5,
        detail_entrance_rows=3,
        detail_address_rows=7,
        building_management_overlap=KeyOverlapMeasurement(5, 7, 5, 4, 2, 3, 2),
        road_address_overlap=KeyOverlapMeasurement(5, 7, 3, 2, 1, 2, 1),
        entrance_building_ref_overlap=KeyOverlapMeasurement(3, 5, 3, 5, 3, 0, 2),
        entrance_containment=CoversMeasurement(
            samples=3,
            covered=2,
            outside=1,
            coverage_ratio=2 / 3,
            sample=({"polygon_sig_cd": "36110"},),
        ),
        entrance_containment_with_address=DetailDongEntranceContainmentMeasurement(
            total_pairs=3,
            detail_address_matched_pairs=1,
            covered=2,
            outside=1,
            detail_address_matched_covered=1,
            detail_address_matched_outside=0,
            coverage_ratio=2 / 3,
            detail_address_matched_coverage_ratio=1.0,
            sample=({"detail_address_key_matched": False},),
        ),
    )

    metrics = comparison.metrics()

    assert metrics["serving_promotion"] is False
    assert metrics["staging_rows"] == {
        "detail_dong_tl_sgco_rnadr_dong": 5,
        "detail_dong_tl_spbd_entrc_dong": 3,
        "detail_address_db_adrdc": 7,
    }
    assert metrics["key_overlaps"]["building_management_no_to_bd_mgt_sn"][
        "intersection_count"
    ] == 2
    assert metrics["containment"]["detail_entrance_point_in_detail_dong_polygon"][
        "outside"
    ] == 1
    assert comparison.sample()[0]["sample_kind"] == "entrance_outside_polygon"
    assert comparison.to_payload().source_yyyymm == "202605"
