from __future__ import annotations

from pathlib import Path

import pytest

from kortravelgeo.loaders.text.roadaddr_entrance_loader import (
    discover_roadaddr_entrance_sources,
    iter_roadaddr_entrance_rows,
)

DATA_ROOT = Path("data/juso")
ALT_DATA_ROOTS = (
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


def test_actual_roadaddr_entrance_sejong_zip_loads_direct_rows() -> None:
    root = _roadaddr_entrance_source_dir()
    archive = root / "도로명주소출입구_전체분_세종특별자치시.zip"
    sources = discover_roadaddr_entrance_sources(archive)
    rows = list(iter_roadaddr_entrance_rows(sources[0], source_yyyymm=None))

    assert len(rows) == 27_779
    assert sources[0].name == "RNENTDATA_2605_36110.txt"
    assert rows[0].bd_mgt_sn == "36110101200000200181100000"
    assert rows[0].bjd_cd == "3611010100"
    assert rows[0].rncode_full == "361102000002"
    assert rows[0].zip_no == "30145"
    assert rows[0].notice_de == "20181204"
    assert rows[0].ent_man_no == 32169
    assert rows[0].ent_source_cd == "RM"
    assert rows[0].ent_detail_cd == "01"
    assert rows[0].source_yyyymm == "202605"
    assert rows[0].x_5179 == pytest.approx(983296.172464)
    assert rows[0].y_5179 == pytest.approx(1833330.968984)
    assert len({row.bd_mgt_sn for row in rows}) == len(rows)


def test_actual_roadaddr_entrance_directory_discovers_all_sido_zip_members() -> None:
    root = _roadaddr_entrance_source_dir()
    sources = discover_roadaddr_entrance_sources(root)

    assert len(sources) == 17
    assert {source.name for source in sources} >= {
        "RNENTDATA_2605_11000.txt",
        "RNENTDATA_2605_36110.txt",
        "RNENTDATA_2605_48000.txt",
    }


def _roadaddr_entrance_source_dir() -> Path:
    root = _require(DATA_ROOT / "도로명주소 출입구 정보")
    if tuple(root.glob("도로명주소출입구_전체분_*.zip")):
        return root
    yyyymm_dirs = sorted(path for path in root.iterdir() if path.is_dir() and path.name.isdigit())
    for candidate in reversed(yyyymm_dirs):
        if tuple(candidate.glob("도로명주소출입구_전체분_*.zip")):
            return candidate
    return root


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
    pytest.skip(f"actual data file is not available: {path}")
