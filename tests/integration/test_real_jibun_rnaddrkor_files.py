from __future__ import annotations

from pathlib import Path

import pytest

from kraddr.geo.infra.pnu import build_pnu
from kraddr.geo.loaders.text.parcel_link_loader import (
    discover_daily_lnbr_sources,
    discover_jibun_rnaddrkor_files,
    iter_daily_lnbr_rows,
    iter_jibun_parcel_link_rows,
)

DATA_ROOT = Path("data/juso")
ALT_DATA_ROOTS = (
    Path("/mnt/f/dev/python-kraddr-geo/data/juso"),
    Path("/home/digitie/kraddr-geo-data/juso"),
)


def test_actual_jibun_rnaddrkor_file_exposes_one_to_many_parcel_links() -> None:
    root = _require(DATA_ROOT / "202603_도로명주소 한글_전체분")
    rows = _read_pipe_rows(root / "jibun_rnaddrkor_seoul.txt", limit=3)
    sources = {source.name: source for source in discover_jibun_rnaddrkor_files(root)}
    parsed = list(
        iter_jibun_parcel_link_rows(
            sources["jibun_rnaddrkor_seoul.txt"],
            source_yyyymm="202603",
            limit=3,
        )
    )

    assert [len(row) for row in rows] == [14, 14, 14]
    assert rows[0][0] == "11110119200500100014900000"
    assert rows[1][0] == rows[0][0]
    assert rows[0][1] == "1111012000"
    assert rows[1][1] == "1114010300"
    assert rows[0][9] == "111102005001"
    assert rows[0][10:13] == ["0", "149", "0"]
    assert rows[0][13] == ""
    assert _pnu(rows[0]) == "1111012000101500000"
    assert _pnu(rows[1]) == "1114010300100680000"
    assert [row.pnu for row in parsed[:2]] == [
        "1111012000101500000",
        "1114010300100680000",
    ]
    assert parsed[0].source_kind == "jibun_full"
    assert parsed[0].source_yyyymm == "202603"


def test_actual_daily_lnbr_member_matches_jibun_shape_with_movement_code() -> None:
    import zipfile

    archive = _require(DATA_ROOT / "daily" / "20260401_dailyjusukrdata.zip")
    parsed = list(iter_daily_lnbr_rows(discover_daily_lnbr_sources(archive)[0], source_yyyymm=None))
    with zipfile.ZipFile(archive) as zip_file:
        member = next(name for name in zip_file.namelist() if name.endswith("RNADR_LNBR.TXT"))
        lines = zip_file.read(member).decode("cp949").splitlines()[:5]

    rows = [line.split("|") for line in lines]

    assert [len(row) for row in rows] == [14, 14, 14, 14, 14]
    assert rows[0][0] == "41480253320608900004500023"
    assert rows[0][13] == "31"
    assert rows[3][0] == rows[0][0]
    assert rows[3][7:9] == ["176", "14"]
    assert _pnu(rows[0]) == "4148025326100310007"
    assert _pnu(rows[3]) == "4148025326101760014"
    assert len(parsed) == 204
    assert parsed[0].source_kind == "daily_lnbr"
    assert parsed[0].mvm_res_cd == "31"
    assert parsed[0].mvmn_de == "20260402"
    assert parsed[0].pnu == "4148025326100310007"


def _require(path: Path) -> Path:
    if path.exists():
        return path
    try:
        relative = path.relative_to(DATA_ROOT)
    except ValueError:
        relative = None
    if relative is not None:
        for root in ALT_DATA_ROOTS:
            candidate = root / relative
            if candidate.exists():
                return candidate
    pytest.skip(f"actual juso data not available: {path}")


def _read_pipe_rows(path: Path, *, limit: int) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open("rb") as file:
        for _index in range(limit):
            line = file.readline()
            if not line:
                break
            rows.append(line.decode("cp949").rstrip("\r\n").split("|"))
    return rows


def _pnu(row: list[str]) -> str | None:
    return build_pnu(
        bjd_cd=row[1],
        mntn_yn=row[6],
        lnbr_mnnm=int(row[7]),
        lnbr_slno=int(row[8] or "0"),
    )
