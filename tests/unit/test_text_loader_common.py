from __future__ import annotations

from kortravelgeo.loaders.text.common import TextSource, detect_encoding, iter_pipe_rows


def test_detect_encoding_prefers_cp949_but_falls_back_to_utf8(tmp_path) -> None:
    cp949_path = tmp_path / "rnaddrkor_cp949.txt"
    cp949_path.write_bytes("서울|강남\n".encode("cp949"))
    utf8_path = tmp_path / "rnaddrkor_utf8.txt"
    utf8_path.write_text("서울|강남\n", encoding="utf-8")

    cp949_source = TextSource(path=cp949_path, name=cp949_path.name, size=cp949_path.stat().st_size)
    utf8_source = TextSource(path=utf8_path, name=utf8_path.name, size=utf8_path.stat().st_size)

    assert detect_encoding(cp949_source) == "cp949"
    assert detect_encoding(utf8_source) == "utf-8"
    assert list(iter_pipe_rows(utf8_source, min_columns=2)) == [(1, ["서울", "강남"])]
