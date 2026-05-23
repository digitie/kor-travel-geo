"""Shared helpers for pipe-delimited juso text files."""

from __future__ import annotations

import codecs
import csv
import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

from kraddr.geo.exceptions import LoaderError


@dataclass(frozen=True, slots=True)
class TextSource:
    """A filesystem file or ZIP member opened lazily for decoding."""

    path: Path
    name: str
    size: int
    member_name: str | None = None

    def open_binary(self) -> BinaryIO:
        if self.member_name is None:
            return self.path.open("rb")
        archive = zipfile.ZipFile(self.path)
        member = archive.open(self.member_name, "r")
        return _ZipMemberWithArchive(cast("BinaryIO", member), archive)


class _ZipMemberWithArchive(io.BufferedReader):
    def __init__(self, raw: BinaryIO, archive: zipfile.ZipFile) -> None:
        super().__init__(raw)  # type: ignore[arg-type]
        self._archive = archive

    def close(self) -> None:
        try:
            super().close()
        finally:
            self._archive.close()


def discover_text_sources(path: Path | str, *, pattern: str) -> tuple[TextSource, ...]:
    root = Path(path)
    if not root.exists():
        msg = f"text source path does not exist: {root}"
        raise LoaderError(msg)
    if root.is_dir():
        return tuple(
            TextSource(path=file, name=file.name, size=file.stat().st_size)
            for file in sorted(root.glob(pattern))
            if file.is_file()
        )
    if root.suffix.lower() == ".zip":
        with zipfile.ZipFile(root) as archive:
            sources = [
                TextSource(
                    path=root,
                    name=info.filename,
                    member_name=info.filename,
                    size=info.file_size,
                )
                for info in archive.infolist()
                if not info.is_dir() and Path(info.filename).match(pattern)
            ]
        return tuple(sorted(sources, key=lambda source: source.name))
    if root.match(pattern):
        return (TextSource(path=root, name=root.name, size=root.stat().st_size),)
    return ()


def detect_encoding(source: TextSource, *, sample_size: int = 64 * 1024) -> str:
    with source.open_binary() as file:
        sample = file.read(sample_size)
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for encoding in ("cp949", "utf-8"):
        try:
            codecs.getincrementaldecoder(encoding)().decode(sample, final=False)
        except UnicodeDecodeError:
            continue
        return encoding
    msg = f"{source.name} is neither cp949 nor utf-8 text"
    raise LoaderError(msg)


def iter_pipe_rows(
    source: TextSource,
    *,
    min_columns: int,
    encoding: str | None = None,
) -> Iterator[tuple[int, list[str]]]:
    resolved_encoding = encoding or detect_encoding(source)
    with source.open_binary() as raw:
        text_stream = io.TextIOWrapper(
            raw,
            encoding=resolved_encoding,
            errors="strict",
            newline="",
        )
        reader = csv.reader(text_stream, delimiter="|", quoting=csv.QUOTE_NONE)
        for line_no, row in enumerate(reader, start=1):
            if len(row) < min_columns:
                msg = f"{source.name}:{line_no} has {len(row)} columns; expected >= {min_columns}"
                raise LoaderError(msg)
            yield line_no, [value.strip() for value in row]


def as_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def required(value: str | None, *, field: str, source_name: str, line_no: int) -> str:
    if value is None or value == "":
        msg = f"{source_name}:{line_no} missing required field {field}"
        raise LoaderError(msg)
    return value
