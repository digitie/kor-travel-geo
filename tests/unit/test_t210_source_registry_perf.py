"""T-210 device-independent memory-ceiling guards.

Fast, deterministic regression guards (no GDAL / 전국 data / RustFS) that lock in
the streaming behaviour of the two memory-sensitive source-registry primitives.
A regression that buffers a whole file (e.g. ``fh.read()`` instead of chunked
reads) blows the tracemalloc ceiling and fails here — independent of machine.
"""

from __future__ import annotations

import hashlib
import tracemalloc
from typing import TYPE_CHECKING

import pytest

from kortravelgeo.infra.rustfs import _read_file_chunks, sha256_file

if TYPE_CHECKING:
    from pathlib import Path

_MIB = 1024 * 1024
_FILE_MIB = 16
#: Streaming reads one 1 MiB chunk at a time; allow generous slack for interpreter
#: overhead but stay far below the 16 MiB file so a whole-file buffer regression trips.
_PEAK_CEILING = 6 * _MIB


def _write_file(path: Path, size_mib: int) -> bytes:
    block = (b"t210-perf\n" * (_MIB // 10 + 1))[:_MIB]
    digest = hashlib.sha256()
    with path.open("wb") as fh:
        for _ in range(size_mib):
            fh.write(block)
            digest.update(block)
    return digest.digest()


@pytest.mark.asyncio
async def test_sha256_file_hashes_correctly_with_bounded_memory(tmp_path: Path) -> None:
    path = tmp_path / "rehash.bin"
    expected = _write_file(path, _FILE_MIB).hex()

    tracemalloc.start()
    try:
        digest = await sha256_file(path)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert digest == expected
    assert peak < _PEAK_CEILING, (
        f"sha256_file peak {peak / _MIB:.1f} MiB exceeded ceiling "
        f"{_PEAK_CEILING / _MIB:.0f} MiB for a {_FILE_MIB} MiB file — "
        "likely buffered the whole file instead of streaming"
    )


@pytest.mark.asyncio
async def test_read_file_chunks_streams_with_bounded_memory(tmp_path: Path) -> None:
    path = tmp_path / "multipart.bin"
    _write_file(path, _FILE_MIB)

    tracemalloc.start()
    try:
        chunks = 0
        total = 0
        max_chunk = 0
        async for chunk in _read_file_chunks(path):
            chunks += 1
            total += len(chunk)
            max_chunk = max(max_chunk, len(chunk))
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert total == _FILE_MIB * _MIB
    assert chunks >= _FILE_MIB  # at least one chunk per MiB
    assert max_chunk <= _MIB
    assert peak < _PEAK_CEILING, (
        f"_read_file_chunks peak {peak / _MIB:.1f} MiB exceeded ceiling for a "
        f"{_FILE_MIB} MiB file — the part iterator must stay streaming"
    )
