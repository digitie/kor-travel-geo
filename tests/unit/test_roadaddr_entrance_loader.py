from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

import pytest

from kraddr.geo.exceptions import LoaderError
from kraddr.geo.loaders.text.roadaddr_entrance_loader import (
    discover_roadaddr_entrance_sources,
    iter_roadaddr_entrance_rows,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_roadaddr_entrance_rows_parse_direct_bd_key_and_5179_point(tmp_path: Path) -> None:
    source = tmp_path / "RNENTDATA_2605_36110.txt"
    source.write_bytes(
        _line(
            bd_mgt_sn="36110101200000200181100000",
            bjd_cd="3611010100",
            rncode_full="361102000002",
            rn="한누리대로",
            buld_mnnm="1811",
            buld_slno="0",
            zip_no="30145",
            notice_de="20181204",
            ent_man_no="32169",
            x="983296.172464",
            y="1833330.968984",
        ).encode("cp949")
    )

    rows = list(
        iter_roadaddr_entrance_rows(
            source=discover_roadaddr_entrance_sources(tmp_path)[0],
            source_yyyymm=None,
        )
    )

    assert len(rows) == 1
    assert rows[0].bd_mgt_sn == "36110101200000200181100000"
    assert rows[0].rncode_full == "361102000002"
    assert rows[0].sig_cd == "36110"
    assert rows[0].rn_cd == "2000002"
    assert rows[0].ent_man_no == 32169
    assert rows[0].ent_source_cd == "RM"
    assert rows[0].ent_detail_cd == "01"
    assert rows[0].source_yyyymm == "202605"
    assert rows[0].x_5179 == pytest.approx(983296.172464)


def test_roadaddr_entrance_discovery_opens_zip_members_in_directory(tmp_path: Path) -> None:
    archive = tmp_path / "도로명주소출입구_전체분_세종특별자치시.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            "RNENTDATA_2605_36110.txt",
            _line(
                bd_mgt_sn="36110101200000200181100000",
                bjd_cd="3611010100",
                rncode_full="361102000002",
                rn="한누리대로",
                buld_mnnm="1811",
                buld_slno="0",
                zip_no="30145",
                notice_de="20181204",
                ent_man_no="32169",
                x="983296.172464",
                y="1833330.968984",
            ).encode("cp949"),
        )

    sources = discover_roadaddr_entrance_sources(tmp_path)

    assert len(sources) == 1
    assert sources[0].name == "RNENTDATA_2605_36110.txt"
    assert sources[0].member_name == "RNENTDATA_2605_36110.txt"


def test_roadaddr_entrance_rows_skip_empty_and_zero_coordinates(tmp_path: Path) -> None:
    source = tmp_path / "RNENTDATA_2605_36110.txt"
    source.write_text(
        "\n".join(
            [
                _line(x="", y="1833330.968984"),
                _line(x="0", y="0"),
                _line(x="983296.172464", y="1833330.968984"),
            ]
        ),
        encoding="utf-8",
    )

    rows = list(
        iter_roadaddr_entrance_rows(
            discover_roadaddr_entrance_sources(source)[0],
            source_yyyymm="202605",
        )
    )

    assert len(rows) == 1
    assert rows[0].x_5179 == pytest.approx(983296.172464)


def test_roadaddr_entrance_rows_allow_blank_entrance_number(tmp_path: Path) -> None:
    source = tmp_path / "RNENTDATA_2605_36110.txt"
    source.write_text(_line(ent_man_no=""), encoding="utf-8")

    rows = list(
        iter_roadaddr_entrance_rows(
            discover_roadaddr_entrance_sources(source)[0],
            source_yyyymm="202605",
        )
    )

    assert rows[0].ent_man_no is None


def test_roadaddr_entrance_rows_reject_invalid_road_code(tmp_path: Path) -> None:
    source = tmp_path / "RNENTDATA_2605_36110.txt"
    source.write_text(_line(rncode_full="bad"), encoding="utf-8")

    with pytest.raises(LoaderError, match="rncode_full must be a 12-digit string"):
        list(
            iter_roadaddr_entrance_rows(
                discover_roadaddr_entrance_sources(source)[0],
                source_yyyymm=None,
            )
        )


def _line(
    *,
    bd_mgt_sn: str = "36110101200000200181100000",
    bjd_cd: str = "3611010100",
    rncode_full: str = "361102000002",
    rn: str = "한누리대로",
    buld_mnnm: str = "1811",
    buld_slno: str = "0",
    zip_no: str = "30145",
    notice_de: str = "20181204",
    ent_man_no: str = "32169",
    ent_source_cd: str = "RM",
    ent_detail_cd: str = "01",
    x: str = "983296.172464",
    y: str = "1833330.968984",
) -> str:
    return "|".join(
        [
            bd_mgt_sn,
            bjd_cd,
            "세종특별자치시",
            "",
            "반곡동",
            "",
            rncode_full,
            rn,
            "0",
            buld_mnnm,
            buld_slno,
            zip_no,
            notice_de,
            "",
            ent_man_no,
            ent_source_cd,
            ent_detail_cd,
            x,
            y,
        ]
    )
