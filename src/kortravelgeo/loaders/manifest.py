"""Load manifest models and checksums."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LoadManifest:
    table_name: str
    source_path: Path
    source_yyyymm: str | None
    source_checksum: str
    row_count: int = 0


def infer_yyyymm(path: Path | str) -> str | None:
    match = re.search(r"(20\d{2})(0[1-9]|1[0-2])", str(path))
    return "".join(match.groups()) if match else None


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

