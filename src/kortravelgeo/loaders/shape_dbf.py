"""Small DBF/SHP analysis helpers for non-serving shape source reviews."""

from __future__ import annotations

import mmap
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

from kortravelgeo.exceptions import LoaderError
from kortravelgeo.loaders.juso_map import read_dbf_header, read_shp_header

SHAPE_TYPES: dict[int, str] = {
    1: "Point",
    3: "PolyLine",
    5: "Polygon",
}


@dataclass(frozen=True, slots=True)
class LayerSummary:
    name: str
    shape_type: str
    row_count: int
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KeySetStats:
    row_count: int
    distinct_count: int
    duplicate_count: int


@dataclass(frozen=True, slots=True)
class KeyOverlap:
    left: KeySetStats
    right: KeySetStats
    intersection_count: int
    left_only_count: int
    right_only_count: int


@dataclass(frozen=True, slots=True)
class DbfKeySet:
    stats: KeySetStats
    keys: frozenset[tuple[bytes, ...]]


@dataclass(frozen=True, slots=True)
class DbfFieldLayout:
    name: str
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class DbfLayout:
    row_count: int
    header_length: int
    record_length: int
    fields: tuple[DbfFieldLayout, ...]


def overlap(left: DbfKeySet, right: DbfKeySet) -> KeyOverlap:
    intersection_count = len(left.keys & right.keys)
    return KeyOverlap(
        left=left.stats,
        right=right.stats,
        intersection_count=intersection_count,
        left_only_count=len(left.keys) - intersection_count,
        right_only_count=len(right.keys) - intersection_count,
    )


def project_key_set(source: DbfKeySet, indexes: tuple[int, ...]) -> DbfKeySet:
    projected = frozenset(tuple(key[index] for index in indexes) for key in source.keys)
    return DbfKeySet(
        stats=KeySetStats(
            row_count=source.stats.row_count,
            distinct_count=len(projected),
            duplicate_count=source.stats.row_count - len(projected),
        ),
        keys=projected,
    )


def zip_layer_summary(zip_file: zipfile.ZipFile, layer_name: str) -> LayerSummary:
    shp_data = zip_file.read(zip_member(zip_file, layer_name, ".shp"))
    dbf_data = zip_file.read(zip_member(zip_file, layer_name, ".dbf"))
    header = parse_dbf_header(dbf_data)
    return LayerSummary(
        name=layer_name,
        shape_type=shape_type_name(struct.unpack("<i", shp_data[:100][32:36])[0]),
        row_count=header.row_count,
        fields=tuple(field.name for field in header.fields),
    )


def file_layer_summary(shp_path: Path, dbf_path: Path) -> LayerSummary:
    shp_header = read_shp_header(shp_path)
    dbf_header = read_dbf_header(dbf_path)
    return LayerSummary(
        name=Path(shp_path).stem,
        shape_type=shape_type_name(shp_header.shape_type),
        row_count=dbf_header.record_count,
        fields=tuple(field.name for field in dbf_header.fields),
    )


def zip_key_set(
    zip_file: zipfile.ZipFile,
    layer_name: str,
    key_fields: tuple[str, ...],
) -> DbfKeySet:
    return key_set_from_buffer(
        zip_file.read(zip_member(zip_file, layer_name, ".dbf")),
        key_fields,
    )


def file_key_set(path: Path, key_fields: tuple[str, ...]) -> DbfKeySet:
    with path.open("rb") as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
        return key_set_from_buffer(data, key_fields)


def key_set_from_buffer(data: bytes | mmap.mmap, key_fields: tuple[str, ...]) -> DbfKeySet:
    header = parse_dbf_header(data)
    offsets = {field.name: (field.offset, field.length) for field in header.fields}
    missing = [field for field in key_fields if field not in offsets]
    if missing:
        msg = f"missing DBF key fields: {', '.join(missing)}"
        raise LoaderError(msg)

    indexes = tuple(offsets[field] for field in key_fields)
    keys: set[tuple[bytes, ...]] = set()
    duplicate_count = 0
    row_count = 0
    for index in range(header.row_count):
        start = header.header_length + index * header.record_length
        record = data[start : start + header.record_length]
        if not record or record[0:1] == b"*":
            continue
        key = tuple(record[offset : offset + length].strip() for offset, length in indexes)
        if key in keys:
            duplicate_count += 1
        keys.add(key)
        row_count += 1

    return DbfKeySet(
        stats=KeySetStats(
            row_count=row_count,
            distinct_count=len(keys),
            duplicate_count=duplicate_count,
        ),
        keys=frozenset(keys),
    )


def parse_dbf_header(data: bytes | mmap.mmap) -> DbfLayout:
    if len(data) < 32:
        msg = "invalid DBF header length"
        raise LoaderError(msg)
    row_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]
    if len(data) < header_length:
        msg = "truncated DBF header"
        raise LoaderError(msg)

    fields: list[DbfFieldLayout] = []
    descriptor_offset = 32
    record_offset = 1
    while descriptor_offset < header_length - 1 and data[descriptor_offset] != 0x0D:
        descriptor = data[descriptor_offset : descriptor_offset + 32]
        if len(descriptor) < 32:
            break
        raw_name = descriptor[:11].split(b"\x00", 1)[0]
        name = raw_name.decode("ascii")
        length = descriptor[16]
        fields.append(DbfFieldLayout(name=name, offset=record_offset, length=length))
        record_offset += length
        descriptor_offset += 32

    return DbfLayout(
        row_count=row_count,
        header_length=header_length,
        record_length=record_length,
        fields=tuple(fields),
    )


def zip_member(zip_file: zipfile.ZipFile, layer_name: str, suffix: str) -> str:
    candidates = [
        name
        for name in zip_file.namelist()
        if _member_layer_name(name) == layer_name and name.lower().endswith(suffix)
    ]
    if len(candidates) != 1:
        msg = f"expected one {layer_name}{suffix} member, found {len(candidates)}"
        raise LoaderError(msg)
    return candidates[0]


def shape_type_name(shape_type: int) -> str:
    return SHAPE_TYPES.get(shape_type, f"Unknown({shape_type})")


def _member_layer_name(path: str) -> str:
    stem = Path(path).stem
    for part in stem.split("."):
        if part.startswith("TL_"):
            return part
    return stem
