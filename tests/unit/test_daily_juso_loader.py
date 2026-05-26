from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

import pytest

from kraddr.geo.exceptions import LoaderError
from kraddr.geo.loaders.text.daily_juso_loader import (
    discover_daily_juso_sources,
    infer_daily_mvmn_de,
    is_no_data_source,
    iter_daily_juso_rows,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_daily_zip_discovers_mst_lnbr_and_parses_movement_code(tmp_path: Path) -> None:
    archive = _write_daily_zip(
        tmp_path,
        mst_lines=[_mst_line("11110101310001200009400000", "31")],
        lnbr_lines=[_lnbr_line()],
        mvmn_de="20260402",
    )

    sources = discover_daily_juso_sources(archive)
    rows = list(iter_daily_juso_rows(sources.mst[0], source_yyyymm=None))

    assert len(sources.mst) == 1
    assert len(sources.lnbr) == 1
    assert infer_daily_mvmn_de(sources.mst[0]) == "20260402"
    assert rows[0].mvm_res_cd == "31"
    assert rows[0].mvmn_de == "20260402"
    assert rows[0].juso.source_yyyymm == "202604"
    assert rows[0].juso.pnu == "1111010100101440003"


def test_daily_no_data_member_is_skipped(tmp_path: Path) -> None:
    archive = _write_daily_zip(tmp_path, mst_lines=["No Data"], lnbr_lines=["No Data"])

    sources = discover_daily_juso_sources(archive)

    assert is_no_data_source(sources.mst[0])
    assert is_no_data_source(sources.lnbr[0])
    assert list(iter_daily_juso_rows(sources.mst[0], source_yyyymm="202604")) == []


def test_daily_loader_rejects_missing_movement_code(tmp_path: Path) -> None:
    archive = _write_daily_zip(
        tmp_path,
        mst_lines=[_mst_line("11110101310001200009400000", "")],
        lnbr_lines=["No Data"],
    )
    sources = discover_daily_juso_sources(archive)

    with pytest.raises(LoaderError, match="missing required field mvm_res_cd"):
        list(iter_daily_juso_rows(sources.mst[0], source_yyyymm="202604"))


def test_daily_loader_rejects_paths_without_daily_members(tmp_path: Path) -> None:
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("rnaddrkor_seoul.txt", _mst_line("11110101310001200009400000", "31"))

    with pytest.raises(LoaderError, match="contains no MST/LNBR"):
        discover_daily_juso_sources(archive)


def _write_daily_zip(
    tmp_path: Path,
    *,
    mst_lines: list[str],
    lnbr_lines: list[str],
    mvmn_de: str = "20260402",
) -> Path:
    archive = tmp_path / "20260401_dailyjusukrdata.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(
            f"AlterD.JUSUKR.{mvmn_de}.TH_SGCO_RNADR_MST.TXT",
            "\n".join(mst_lines).encode("cp949"),
        )
        zip_file.writestr(
            f"AlterD.JUSUKR.{mvmn_de}.TH_SGCO_RNADR_LNBR.TXT",
            "\n".join(lnbr_lines).encode("cp949"),
        )
    return archive


def _mst_line(bd_mgt_sn: str, mvm_res_cd: str) -> str:
    return "|".join(
        [
            bd_mgt_sn,
            "1111010100",
            "서울특별시",
            "종로구",
            "청운동",
            "",
            "0",
            "144",
            "3",
            "111103100012",
            "자하문로",
            "0",
            "94",
            "0",
            "1111051500",
            "청운효자동",
            "03047",
            "",
            "20110729",
            "0",
            mvm_res_cd,
            "",
            "",
            "",
        ]
    )


def _lnbr_line() -> str:
    return "|".join(
        [
            "11110101310001200009400000",
            "1111010100",
            "서울특별시",
            "종로구",
            "청운동",
            "",
            "0",
            "144",
            "3",
            "111103100012",
            "0",
            "94",
            "0",
            "31",
        ]
    )
