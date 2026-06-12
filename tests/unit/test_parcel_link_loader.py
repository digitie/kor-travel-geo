from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.text.parcel_link_loader import (
    discover_daily_lnbr_sources,
    discover_jibun_rnaddrkor_files,
    iter_daily_lnbr_rows,
    iter_jibun_parcel_link_rows,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_jibun_rnaddrkor_rows_build_standard_pnu_and_keep_road_key(tmp_path: Path) -> None:
    source = tmp_path / "jibun_rnaddrkor_seoul.txt"
    source.write_bytes(
        "\n".join(
            [
                _parcel_line(
                    bd_mgt_sn="11110119200500100014900000",
                    bjd_cd="1111012000",
                    mntn_yn="0",
                    lnbr_mnnm="150",
                    lnbr_slno="0",
                    rncode_full="111102005001",
                    buld_mnnm="149",
                    buld_slno="0",
                ),
                _parcel_line(
                    bd_mgt_sn="11110119200500100014900000",
                    bjd_cd="1111012000",
                    mntn_yn="1",
                    lnbr_mnnm="108",
                    lnbr_slno="3",
                    rncode_full="111102005001",
                    buld_mnnm="149",
                    buld_slno="0",
                ),
            ]
        ).encode("cp949")
    )

    sources = discover_jibun_rnaddrkor_files(tmp_path)
    rows = list(iter_jibun_parcel_link_rows(sources[0], source_yyyymm="202603"))

    assert [row.pnu for row in rows] == [
        "1111012000101500000",
        "1111012000201080003",
    ]
    assert rows[0].source_kind == "jibun_full"
    assert rows[0].sig_cd == "11110"
    assert rows[0].rn_cd == "2005001"
    assert rows[0].buld_mnnm == 149
    assert rows[0].source_yyyymm == "202603"


def test_daily_lnbr_rows_parse_movement_code_and_movement_date(tmp_path: Path) -> None:
    archive = tmp_path / "20260401_dailyjusukrdata.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "AlterD.JUSUKR.20260402.TH_SGCO_RNADR_LNBR.TXT",
            _parcel_line(
                bd_mgt_sn="41480253320608900004500023",
                bjd_cd="4148025326",
                mntn_yn="0",
                lnbr_mnnm="31",
                lnbr_slno="7",
                rncode_full="414803206089",
                buld_mnnm="45",
                buld_slno="23",
                mvm_res_cd="31",
            ).encode("cp949"),
        )

    sources = discover_daily_lnbr_sources(archive)
    rows = list(iter_daily_lnbr_rows(sources[0], source_yyyymm=None))

    assert len(rows) == 1
    assert rows[0].source_kind == "daily_lnbr"
    assert rows[0].mvm_res_cd == "31"
    assert rows[0].mvmn_de == "20260402"
    assert rows[0].source_yyyymm == "202604"
    assert rows[0].pnu == "4148025326100310007"


def test_daily_lnbr_no_data_member_is_skipped(tmp_path: Path) -> None:
    archive = tmp_path / "20260404_dailyjusukrdata.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("AlterD.JUSUKR.20260405.TH_SGCO_RNADR_LNBR.TXT", b"No Data")

    sources = discover_daily_lnbr_sources(archive)

    assert list(iter_daily_lnbr_rows(sources[0], source_yyyymm="202604")) == []


def test_parcel_link_loader_rejects_invalid_pnu_fields(tmp_path: Path) -> None:
    source = tmp_path / "jibun_rnaddrkor_seoul.txt"
    source.write_text(
        _parcel_line(
            bd_mgt_sn="11110119200500100014900000",
            bjd_cd="1111012000",
            mntn_yn="9",
            lnbr_mnnm="150",
            lnbr_slno="0",
            rncode_full="111102005001",
            buld_mnnm="149",
            buld_slno="0",
        ),
        encoding="utf-8",
    )
    sources = discover_jibun_rnaddrkor_files(tmp_path)

    with pytest.raises(LoaderError, match="invalid PNU fields"):
        list(iter_jibun_parcel_link_rows(sources[0], source_yyyymm="202603"))


def test_daily_lnbr_loader_rejects_missing_movement_code(tmp_path: Path) -> None:
    archive = tmp_path / "20260401_dailyjusukrdata.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "AlterD.JUSUKR.20260402.TH_SGCO_RNADR_LNBR.TXT",
            _parcel_line(
                bd_mgt_sn="41480253320608900004500023",
                bjd_cd="4148025326",
                mntn_yn="0",
                lnbr_mnnm="31",
                lnbr_slno="7",
                rncode_full="414803206089",
                buld_mnnm="45",
                buld_slno="23",
                mvm_res_cd="",
            ).encode("cp949"),
        )
    sources = discover_daily_lnbr_sources(archive)

    with pytest.raises(LoaderError, match="missing required field mvm_res_cd"):
        list(iter_daily_lnbr_rows(sources[0], source_yyyymm=None))


def _parcel_line(
    *,
    bd_mgt_sn: str,
    bjd_cd: str,
    mntn_yn: str,
    lnbr_mnnm: str,
    lnbr_slno: str,
    rncode_full: str,
    buld_mnnm: str,
    buld_slno: str,
    mvm_res_cd: str = "",
) -> str:
    return "|".join(
        [
            bd_mgt_sn,
            bjd_cd,
            "서울특별시",
            "종로구",
            "청운동",
            "",
            mntn_yn,
            lnbr_mnnm,
            lnbr_slno,
            rncode_full,
            "0",
            buld_mnnm,
            buld_slno,
            mvm_res_cd,
        ]
    )
