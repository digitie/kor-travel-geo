from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kortravelgeo.loaders.augment_harness import JoinKey, KeyOverlapMeasurement
from kortravelgeo.loaders.c16_address_building_drift import (
    C16AddressBuildingDriftComparison,
    C16KeyDriftComparison,
    C16StagingRows,
    build_c16_address_building_drift_report,
    c16_staging_index_specs,
    discover_address_db_members,
    discover_building_db_members,
    iter_address_db_address_rows,
    iter_address_db_jibun_rows,
    iter_building_db_build_rows,
    iter_building_db_jibun_rows,
    key_drift_sample_sql,
    parse_address_db_address_row,
    parse_address_db_jibun_row,
    parse_building_db_build_row,
    parse_building_db_jibun_row,
)
from kortravelgeo.loaders.text.common import TextSource


def test_discover_address_db_members_recovers_cp949_zip_names(tmp_path: Path) -> None:
    archive = tmp_path / "address.zip"
    _write_address_db_zip(archive)

    members = discover_address_db_members(archive)

    assert [source.name for source in members.address] == ["주소_서울특별시.txt"]
    assert [source.name for source in members.extra] == ["부가정보_서울특별시.txt"]
    assert [source.name for source in members.jibun] == ["지번_서울특별시.txt"]
    assert members.road_code is not None
    assert members.road_code.name == "개선_도로명코드_전체분.txt"
    assert members.missing_kinds == ()


def test_discover_building_db_members_reads_english_member_names(tmp_path: Path) -> None:
    archive = tmp_path / "building.zip"
    _write_building_db_zip(archive)

    members = discover_building_db_members(archive)

    assert [source.name for source in members.build] == ["build_seoul.txt"]
    assert [source.name for source in members.jibun] == ["jibun_seoul.txt"]
    assert members.road_code is not None
    assert members.road_code.name == "road_code_total.txt"
    assert members.missing_kinds == ()


def test_address_db_parsers_extract_serving_keys() -> None:
    address = parse_address_db_address_row(
        _pipe("1111011900102150000000001|111102005001|01|0|145|2|03186||||0"),
        source_name="주소_서울특별시.txt",
        line_no=1,
    )
    jibun = parse_address_db_jibun_row(
        _pipe("1111010100100010000030843|1|1111010100|서울특별시|종로구|청운동||0|1|0|1"),
        source_name="지번_서울특별시.txt",
        line_no=1,
    )

    assert address.bd_mgt_sn == "1111011900102150000000001"
    assert address.rncode_full == "111102005001"
    assert address.sig_cd == "11110"
    assert address.rn_cd == "2005001"
    assert address.buld_se_cd == "0"
    assert address.buld_mnnm == 145
    assert address.buld_slno == 2
    assert address.zip_no == "03186"
    assert jibun.bd_mgt_sn == "1111010100100010000030843"
    assert jibun.pnu == "1111010100100010000"
    assert jibun.lnbr_mnnm == 1
    assert jibun.lnbr_slno == 0


def test_building_db_parsers_extract_polygon_and_parcel_keys() -> None:
    build = parse_building_db_build_row(
        _BUILDING_BUILD_SAMPLE.split("|"),
        source_name="build_seoul.txt",
        line_no=1,
    )
    jibun = parse_building_db_jibun_row(
        _pipe("1111012000|서울특별시|종로구|신문로1가||0|150|0|111102005001|0|149|0|1114|"),
        source_name="jibun_seoul.txt",
        line_no=1,
    )

    assert build.bd_mgt_sn == "1111010100101440003031291"
    assert build.bjd_cd == "1111010100"
    assert build.rncode_full == "111103100012"
    assert build.buld_se_cd == "0"
    assert build.buld_mnnm == 94
    assert build.buld_slno == 0
    assert build.zip_no == "03047"
    assert jibun.pnu == "1111012000101500000"
    assert jibun.rncode_full == "111102005001"
    assert jibun.buld_mnnm == 149


def test_iterators_read_synthetic_archives(tmp_path: Path) -> None:
    address_zip = tmp_path / "address.zip"
    building_zip = tmp_path / "building.zip"
    _write_address_db_zip(address_zip)
    _write_building_db_zip(building_zip)

    address_rows = tuple(iter_address_db_address_rows(address_zip))
    address_jibun_rows = tuple(iter_address_db_jibun_rows(address_zip))
    building_rows = tuple(iter_building_db_build_rows(building_zip))
    building_jibun_rows = tuple(iter_building_db_jibun_rows(building_zip))

    assert len(address_rows) == 1
    assert address_rows[0].source_file == "주소_서울특별시.txt"
    assert len(address_jibun_rows) == 1
    assert len(building_rows) == 1
    assert len(building_jibun_rows) == 1


def test_key_drift_sample_sql_uses_except_without_serving_writes() -> None:
    sql = key_drift_sample_sql(
        "_ktg_c16_address_db_address",
        "tl_juso_text",
        (JoinKey("bd_mgt_sn", "bd_mgt_sn"),),
    )

    assert 'FROM "_ktg_c16_address_db_address" l' in sql
    assert 'FROM "tl_juso_text" r' in sql
    assert "EXCEPT" in sql
    assert "left_only" in sql
    assert "right_only" in sql
    assert "INSERT INTO" not in sql
    assert "CREATE MATERIALIZED VIEW" not in sql


def test_c16_staging_index_specs_cover_reused_join_keys() -> None:
    specs = c16_staging_index_specs(
        address_table="_address",
        extra_table="_extra",
        address_jibun_table="_address_jibun",
        building_table="_building",
        building_jibun_table="_building_jibun",
    )

    assert [(spec.table_name, spec.columns) for spec in specs] == [
        ("_address", ("bd_mgt_sn",)),
        ("_extra", ("bd_mgt_sn",)),
        ("_address_jibun", ("bd_mgt_sn", "pnu")),
        (
            "_building",
            ("rncode_full", "buld_se_cd", "buld_mnnm", "buld_slno", "bjd_cd"),
        ),
        (
            "_building_jibun",
            ("pnu", "rncode_full", "buld_se_cd", "buld_mnnm", "buld_slno"),
        ),
    ]


def test_c16_metrics_keep_address_and_building_db_validation_only() -> None:
    comparison = C16AddressBuildingDriftComparison(
        address_db_zip="202605_주소DB_전체분.zip",
        building_db_zip="202605_건물DB_전체분.zip",
        source_yyyymm="202605",
        address_members=_address_members(),
        building_members=_building_members(),
        staging_rows=C16StagingRows(1, 1, 1, 1, 1),
        comparisons=(
            C16KeyDriftComparison(
                name="address_db_address_to_tl_juso_text_bd_mgt_sn",
                left_source="address_db_full.주소_*.txt",
                right_source="tl_juso_text",
                key_contract="bd_mgt_sn",
                join_keys=(JoinKey("bd_mgt_sn", "bd_mgt_sn"),),
                overlap=KeyOverlapMeasurement(1, 2, 1, 2, 1, 0, 1),
                sample=({"sample_kind": "right_only", "keys": {"bd_mgt_sn": "B"}},),
            ),
        ),
    )

    metrics = comparison.metrics()

    assert metrics["coordinate_load"] is False
    assert metrics["serving_promotion"] is False
    assert metrics["staging_rows"] == {
        "address_db_address": 1,
        "address_db_extra": 1,
        "address_db_jibun": 1,
        "building_db_build": 1,
        "building_db_jibun": 1,
    }
    assert metrics["comparisons"]["address_db_address_to_tl_juso_text_bd_mgt_sn"][
        "key_overlap"
    ]["right_only_count"] == 1
    assert comparison.sample() == (
        {
            "comparison": "address_db_address_to_tl_juso_text_bd_mgt_sn",
            "sample_kind": "right_only",
            "keys": {"bd_mgt_sn": "B"},
        },
    )


@pytest.mark.asyncio
async def test_build_c16_report_sets_generated_at_on_failure(tmp_path: Path) -> None:
    class DummyEngine:
        pass

    report = await build_c16_address_building_drift_report(
        DummyEngine(),  # type: ignore[arg-type]
        tmp_path / "missing-address.zip",
        tmp_path / "missing-building.zip",
        source_yyyymm="202605",
        generated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert report.task_id == "T-116"
    assert report.generated_at == "2026-06-14T00:00:00+00:00"
    assert report.failed_count == 1
    assert report.groups[0].source_yyyymm == "202605"


_BUILDING_BUILD_SAMPLE = (
    "1111010100|서울특별시|종로구|청운동||0|144|3|111103100012|자하문로|"
    "0|94|0|||1111010100101440003031291|01|1111051500|청운효자동|03047|||||||0|03047|0||"
)


def _write_address_db_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr(
            _mojibake("주소_서울특별시.txt"),
            "1111011900102150000000001|111102005001|01|0|145|2|03186||||0\n".encode(
                "cp949"
            ),
        )
        zip_file.writestr(
            _mojibake("부가정보_서울특별시.txt"),
            "1111010100100010000030843|1111051500|청운효자동|03046|||청운벽산빌리지|청운벽산빌리지|1\n".encode(
                "cp949"
            ),
        )
        zip_file.writestr(
            _mojibake("지번_서울특별시.txt"),
            "1111010100100010000030843|1|1111010100|서울특별시|종로구|청운동||0|1|0|1\n".encode(
                "cp949"
            ),
        )
        zip_file.writestr(
            _mojibake("개선_도로명코드_전체분.txt"),
            "111102005001|세종대로|Sejong-daero|00|서울특별시|Seoul|종로구|Jongno-gu|||2||0||||\n".encode(
                "cp949"
            ),
        )


def _write_building_db_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zip_file:
        zip_file.writestr("build_seoul.txt", (_BUILDING_BUILD_SAMPLE + "\n").encode("cp949"))
        zip_file.writestr(
            "jibun_seoul.txt",
            "1111012000|서울특별시|종로구|신문로1가||0|150|0|111102005001|0|149|0|1114|\n".encode(
                "cp949"
            ),
        )
        zip_file.writestr(
            "road_code_total.txt",
            "11110|2005001|세종대로|Sejong-daero|00|서울특별시|종로구|2|||||0|||Seoul|Jongno-gu||20100520|\n".encode(
                "cp949"
            ),
        )


def _mojibake(value: str) -> str:
    return value.encode("cp949").decode("cp437")


def _address_members() -> object:
    return discover_address_db_members_for_metrics(
        address=("주소_서울특별시.txt",),
        extra=("부가정보_서울특별시.txt",),
        jibun=("지번_서울특별시.txt",),
        road_code="개선_도로명코드_전체분.txt",
    )


def _building_members() -> object:
    return discover_building_db_members_for_metrics(
        build=("build_seoul.txt",),
        jibun=("jibun_seoul.txt",),
        road_code="road_code_total.txt",
    )


def discover_address_db_members_for_metrics(
    *,
    address: tuple[str, ...],
    extra: tuple[str, ...],
    jibun: tuple[str, ...],
    road_code: str,
):
    from kortravelgeo.loaders.c16_address_building_drift import AddressDbMembers

    return AddressDbMembers(
        address=tuple(_source(name) for name in address),
        extra=tuple(_source(name) for name in extra),
        jibun=tuple(_source(name) for name in jibun),
        road_code=_source(road_code),
    )


def discover_building_db_members_for_metrics(
    *,
    build: tuple[str, ...],
    jibun: tuple[str, ...],
    road_code: str,
):
    from kortravelgeo.loaders.c16_address_building_drift import BuildingDbMembers

    return BuildingDbMembers(
        build=tuple(_source(name) for name in build),
        jibun=tuple(_source(name) for name in jibun),
        road_code=_source(road_code),
    )


def _source(name: str) -> TextSource:
    return TextSource(path=Path(name), name=name, size=1)


def _pipe(value: str) -> list[str]:
    return value.split("|")
