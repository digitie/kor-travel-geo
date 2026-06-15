#!/usr/bin/env python3
"""T-210 device-independent source-registry performance harness.

Benchmarks the two memory-sensitive source-registry primitives with synthetic
fixtures (no GDAL / 전국 data / RustFS server needed), so results are comparable
across machines and the memory bound is a real regression guard:

  * **deep rehash** — ``infra.rustfs.sha256_file`` (the hash used by reconcile
    ``deep`` mode), measured over N synthetic objects.
  * **multipart 대용량** — ``infra.rustfs._read_file_chunks`` (the streamed part
    iterator used by ``put_file`` / multipart upload), measured over one large file.

For each, wall time / throughput and **peak RSS delta** are reported. Streaming
keeps peak RSS far below the file size; a regression that buffers a whole file
shows up immediately. Absolute throughput is machine-dependent (informational);
the memory bound is the device-independent assertion (see the opt-in unit guard
``tests/unit/test_t210_source_registry_perf.py``). Real-machine throughput is
T-063; 전국 적재 perf is T-213/T-214.

Run (WSL ext4 mirror)::

    ~/ktgvenv/bin/python scripts/benchmark_source_registry_perf.py \\
        --rehash-count 8 --rehash-size-mib 64 --multipart-size-mib 512 \\
        --output artifacts/perf/t210-device-independent
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from kortravelgeo.infra.rustfs import _read_file_chunks, sha256_file

try:  # Linux-only; absent on native Windows (run this in WSL).
    import resource
except ImportError:  # pragma: no cover - platform guard
    resource = None  # type: ignore[assignment]

_MIB = 1024 * 1024


def _peak_rss_bytes() -> int | None:
    if resource is None:
        return None
    # ru_maxrss is KiB on Linux, bytes on macOS; this harness targets Linux/WSL.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _write_synthetic(path: Path, size_bytes: int, *, chunk: int = _MIB) -> None:
    """Write a deterministic synthetic file without buffering it in memory."""
    block = (b"kor-travel-geo-t210-perf-fixture\n" * (chunk // 32 + 1))[:chunk]
    written = 0
    with path.open("wb") as fh:
        while written < size_bytes:
            take = min(chunk, size_bytes - written)
            fh.write(block[:take])
            written += take


async def _bench_deep_rehash(tmp: Path, *, count: int, size_mib: int) -> dict[str, Any]:
    size = size_mib * _MIB
    paths = []
    for index in range(count):
        path = tmp / f"rehash_{index}.bin"
        _write_synthetic(path, size)
        paths.append(path)
    rss_before = _peak_rss_bytes()
    started = time.monotonic()
    for path in paths:
        await sha256_file(path)
    elapsed = time.monotonic() - started
    total_mib = count * size_mib
    return {
        "objects": count,
        "object_size_mib": size_mib,
        "total_mib": total_mib,
        "elapsed_s": round(elapsed, 3),
        "throughput_mib_s": round(total_mib / elapsed, 1) if elapsed else None,
        "objects_per_s": round(count / elapsed, 2) if elapsed else None,
        "peak_rss_mib": _rss_delta_mib(rss_before),
    }


async def _bench_multipart(tmp: Path, *, size_mib: int, part_mib: int) -> dict[str, Any]:
    size = size_mib * _MIB
    path = tmp / "multipart_large.bin"
    _write_synthetic(path, size)
    rss_before = _peak_rss_bytes()
    started = time.monotonic()
    chunks = 0
    total = 0
    max_chunk = 0
    async for chunk in _read_file_chunks(path):
        chunks += 1
        total += len(chunk)
        max_chunk = max(max_chunk, len(chunk))
    elapsed = time.monotonic() - started
    return {
        "file_size_mib": size_mib,
        "part_size_mib": part_mib,
        "chunks": chunks,
        "bytes_read": total,
        "max_chunk_mib": round(max_chunk / _MIB, 3),
        "elapsed_s": round(elapsed, 3),
        "throughput_mib_s": round(size_mib / elapsed, 1) if elapsed else None,
        "peak_rss_mib": _rss_delta_mib(rss_before),
    }


def _rss_delta_mib(before: int | None) -> float | None:
    after = _peak_rss_bytes()
    if before is None or after is None:
        return None
    return round(max(0, after - before) / _MIB, 1)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    results: dict[str, Any] = {"harness": "t210-device-independent-source-registry-perf"}
    with tempfile.TemporaryDirectory(prefix="ktg-t210-perf-") as raw_tmp:
        tmp = Path(raw_tmp)
        results["deep_rehash"] = await _bench_deep_rehash(
            tmp, count=args.rehash_count, size_mib=args.rehash_size_mib
        )
        results["multipart"] = await _bench_multipart(
            tmp, size_mib=args.multipart_size_mib, part_mib=args.part_size_mib
        )
    return results


def _write_artifact(output: str, results: dict[str, Any]) -> Path:
    out_dir = Path(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / "t210-source-registry-perf.json"
    artifact.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rehash-count", type=int, default=8)
    parser.add_argument("--rehash-size-mib", type=int, default=64)
    parser.add_argument("--multipart-size-mib", type=int, default=512)
    parser.add_argument("--part-size-mib", type=int, default=1)
    parser.add_argument("--output", default=None, help="artifact directory (optional)")
    args = parser.parse_args()
    results = asyncio.run(run(args))
    print(json.dumps(results, indent=2))
    if args.output:
        print(f"\nartifact: {_write_artifact(args.output, results)}")


if __name__ == "__main__":
    main()
