"""큰 SHP의 헤더 조회가 파일 전체를 읽지 않도록 검증한다."""

import struct
from pathlib import Path

from kortravelgeo.loaders.juso_map import read_shp_header


def test_shp_header_reads_only_fixed_header(tmp_path, monkeypatch):
    path = tmp_path / "large.shp"
    size = 4096
    data = bytearray(size)
    struct.pack_into(">i", data, 0, 9994)
    struct.pack_into(">i", data, 24, size // 2)
    struct.pack_into("<ii", data, 28, 1000, 5)
    struct.pack_into("<4d", data, 36, 1.0, 2.0, 3.0, 4.0)
    path.write_bytes(data)
    original_open = Path.open
    reads = []

    class BoundedReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, size=-1):
            assert 0 <= size <= 100, "SHP 헤더 조회가 전체 파일을 읽었습니다."
            reads.append(size)
            return self.stream.read(size)

    def bounded_open(self, *args, **kwargs):
        stream = original_open(self, *args, **kwargs)
        return BoundedReader(stream) if self == path else stream

    monkeypatch.setattr(Path, "open", bounded_open)
    header = read_shp_header(path)
    assert header.file_length_bytes == size
    assert header.version == 1000 and header.shape_type == 5
    assert header.bbox == (1.0, 2.0, 3.0, 4.0)
    assert reads == [100]
