from __future__ import annotations

from typing import TYPE_CHECKING

from kraddr.geo.loaders.text.common import TextSource
from kraddr.geo.loaders.text.navi_loader import iter_navi_build_rows, iter_navi_entrance_rows

if TYPE_CHECKING:
    from pathlib import Path


def _write_pipe_file(path: Path, rows: list[list[str]]) -> TextSource:
    path.write_text("\n".join("|".join(row) for row in rows), encoding="utf-8")
    return TextSource(path=path, name=path.name, size=path.stat().st_size)


def test_iter_navi_build_rows_skips_missing_centroid_coordinates(tmp_path: Path) -> None:
    missing_centroid = [""] * 27
    missing_centroid[0] = "1111010100"
    missing_centroid[4] = "111103100012"
    missing_centroid[10] = "1111010100101440003031291"

    zero_centroid = missing_centroid.copy()
    zero_centroid[10] = "1111010100101440003031290"
    zero_centroid[23] = "0"
    zero_centroid[24] = "0.0"

    valid = missing_centroid.copy()
    valid[10] = "1111010100101440003031292"
    valid[19] = "시군구별칭"
    valid[23] = "953243.01328"
    valid[24] = "1954025.806161"

    source = _write_pipe_file(
        tmp_path / "match_build_sample.txt", [missing_centroid, zero_centroid, valid]
    )

    rows = list(iter_navi_build_rows(source, source_yyyymm="202604"))

    assert len(rows) == 1
    assert rows[0].bd_mgt_sn == "1111010100101440003031292"
    assert rows[0].sigungu_buld_nm == "시군구별칭"
    assert rows[0].centroid_x == 953243.01328
    assert iter_navi_build_rows.__doc__ is not None
    assert "zero-sentinel" in iter_navi_build_rows.__doc__


def test_iter_navi_entrance_rows_skips_missing_coordinates(tmp_path: Path) -> None:
    missing_coordinate = [""] * 10
    missing_coordinate[0] = "11110"
    missing_coordinate[1] = "1331"
    missing_coordinate[2] = "111103100012"
    missing_coordinate[7] = "01"

    zero_coordinate = missing_coordinate.copy()
    zero_coordinate[1] = "1330"
    zero_coordinate[8] = "0.0"
    zero_coordinate[9] = "0"

    valid = missing_coordinate.copy()
    valid[1] = "1332"
    valid[8] = "953135.056899"
    valid[9] = "1954051.245815"

    source = _write_pipe_file(
        tmp_path / "match_rs_entrc.txt", [missing_coordinate, zero_coordinate, valid]
    )

    rows = list(iter_navi_entrance_rows(source, source_yyyymm="202604"))

    assert len(rows) == 1
    assert rows[0].entry_no == 1332
    assert rows[0].x_5179 == 953135.056899
    assert iter_navi_entrance_rows.__doc__ is not None
    assert "zero-sentinel" in iter_navi_entrance_rows.__doc__
