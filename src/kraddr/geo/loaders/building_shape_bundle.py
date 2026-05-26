"""Analysis helpers for the road-address building shape bundle."""

from __future__ import annotations

import mmap
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

from kraddr.geo.exceptions import LoaderError
from kraddr.geo.loaders.juso_map import discover_sido_dataset, read_dbf_header, read_shp_header

ADDRESS_BUNDLE_LAYER = "TL_SGCO_RNADR_MST"
BUNDLE_ENTRANCE_LAYER = "TL_SPBD_ENTRC"
BUNDLE_CONNECTION_LAYER = "TL_SPOT_CNTC"
ELECTRONIC_BUILDING_LAYER = "TL_SPBD_BULD"
ELECTRONIC_ENTRANCE_LAYER = "TL_SPBD_ENTRC"

ADDRESS_KEY_FIELDS: tuple[str, ...] = (
    "SIG_CD",
    "RN_CD",
    "BULD_SE_CD",
    "BULD_MNNM",
    "BULD_SLNO",
    "BUL_MAN_NO",
    "EQB_MAN_SN",
)
ENTRANCE_KEY_FIELDS: tuple[str, ...] = ("SIG_CD", "BUL_MAN_NO", "ENT_MAN_NO", "EQB_MAN_SN")
CONNECTION_ENTRANCE_REF_FIELDS: tuple[str, ...] = ("SIG_CD", "ENT_MAN_NO")

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
class BuildingShapeBundleComparison:
    sido_name: str
    bundle_zip: str
    electronic_map_dir: str
    bundle_address_layer: LayerSummary
    electronic_building_layer: LayerSummary
    bundle_entrance_layer: LayerSummary
    electronic_entrance_layer: LayerSummary
    bundle_connection_layer: LayerSummary
    address_key_overlap: KeyOverlap
    entrance_key_overlap: KeyOverlap
    connection_entrance_ref_overlap: KeyOverlap


@dataclass(frozen=True, slots=True)
class _KeySet:
    stats: KeySetStats
    keys: frozenset[tuple[bytes, ...]]


def compare_building_shape_bundle(
    bundle_zip: Path | str,
    electronic_map_sido_dir: Path | str,
) -> BuildingShapeBundleComparison:
    """Compare the 202605 address building bundle with the electronic map layers."""

    bundle_path = Path(bundle_zip)
    electronic_root = Path(electronic_map_sido_dir)
    dataset = discover_sido_dataset(electronic_root)
    with zipfile.ZipFile(bundle_path) as zip_file:
        bundle_address_layer = _zip_layer_summary(zip_file, ADDRESS_BUNDLE_LAYER)
        bundle_entrance_layer = _zip_layer_summary(zip_file, BUNDLE_ENTRANCE_LAYER)
        bundle_connection_layer = _zip_layer_summary(zip_file, BUNDLE_CONNECTION_LAYER)
        bundle_address = _zip_key_set(zip_file, ADDRESS_BUNDLE_LAYER, ADDRESS_KEY_FIELDS)
        bundle_entrance = _zip_key_set(zip_file, BUNDLE_ENTRANCE_LAYER, ENTRANCE_KEY_FIELDS)
        bundle_connection_refs = _zip_key_set(
            zip_file,
            BUNDLE_CONNECTION_LAYER,
            CONNECTION_ENTRANCE_REF_FIELDS,
        )

    electronic_building = dataset.layer(ELECTRONIC_BUILDING_LAYER)
    electronic_entrance = dataset.layer(ELECTRONIC_ENTRANCE_LAYER)
    electronic_building_layer = _file_layer_summary(
        electronic_building.shp_path,
        electronic_building.dbf_path,
    )
    electronic_entrance_layer = _file_layer_summary(
        electronic_entrance.shp_path,
        electronic_entrance.dbf_path,
    )
    electronic_building_keys = _file_key_set(electronic_building.dbf_path, ADDRESS_KEY_FIELDS)
    electronic_entrance_keys = _file_key_set(electronic_entrance.dbf_path, ENTRANCE_KEY_FIELDS)
    bundle_entrance_refs = _project_entrance_refs(bundle_entrance)

    return BuildingShapeBundleComparison(
        sido_name=dataset.sido_name,
        bundle_zip=str(bundle_path),
        electronic_map_dir=str(electronic_root),
        bundle_address_layer=bundle_address_layer,
        electronic_building_layer=electronic_building_layer,
        bundle_entrance_layer=bundle_entrance_layer,
        electronic_entrance_layer=electronic_entrance_layer,
        bundle_connection_layer=bundle_connection_layer,
        address_key_overlap=_overlap(bundle_address, electronic_building_keys),
        entrance_key_overlap=_overlap(bundle_entrance, electronic_entrance_keys),
        connection_entrance_ref_overlap=_overlap(bundle_connection_refs, bundle_entrance_refs),
    )


def _overlap(left: _KeySet, right: _KeySet) -> KeyOverlap:
    intersection_count = len(left.keys & right.keys)
    return KeyOverlap(
        left=left.stats,
        right=right.stats,
        intersection_count=intersection_count,
        left_only_count=len(left.keys) - intersection_count,
        right_only_count=len(right.keys) - intersection_count,
    )


def _project_entrance_refs(entrance_keys: _KeySet) -> _KeySet:
    refs = frozenset((key[0], key[2]) for key in entrance_keys.keys)
    return _KeySet(
        stats=KeySetStats(
            row_count=entrance_keys.stats.row_count,
            distinct_count=len(refs),
            duplicate_count=entrance_keys.stats.row_count - len(refs),
        ),
        keys=refs,
    )


def _zip_layer_summary(zip_file: zipfile.ZipFile, layer_name: str) -> LayerSummary:
    shp_data = zip_file.read(_zip_member(zip_file, layer_name, ".shp"))
    dbf_data = zip_file.read(_zip_member(zip_file, layer_name, ".dbf"))
    header = _parse_dbf_header(dbf_data)
    return LayerSummary(
        name=layer_name,
        shape_type=_shape_type_name(struct.unpack("<i", shp_data[:100][32:36])[0]),
        row_count=header.row_count,
        fields=tuple(field.name for field in header.fields),
    )


def _file_layer_summary(shp_path: Path, dbf_path: Path) -> LayerSummary:
    shp_header = read_shp_header(shp_path)
    dbf_header = read_dbf_header(dbf_path)
    return LayerSummary(
        name=Path(shp_path).stem,
        shape_type=_shape_type_name(shp_header.shape_type),
        row_count=dbf_header.record_count,
        fields=tuple(field.name for field in dbf_header.fields),
    )


def _zip_key_set(
    zip_file: zipfile.ZipFile,
    layer_name: str,
    key_fields: tuple[str, ...],
) -> _KeySet:
    return _key_set_from_buffer(
        zip_file.read(_zip_member(zip_file, layer_name, ".dbf")),
        key_fields,
    )


def _file_key_set(path: Path, key_fields: tuple[str, ...]) -> _KeySet:
    with path.open("rb") as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
        return _key_set_from_buffer(data, key_fields)


def _key_set_from_buffer(data: bytes | mmap.mmap, key_fields: tuple[str, ...]) -> _KeySet:
    header = _parse_dbf_header(data)
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

    return _KeySet(
        stats=KeySetStats(
            row_count=row_count,
            distinct_count=len(keys),
            duplicate_count=duplicate_count,
        ),
        keys=frozenset(keys),
    )


@dataclass(frozen=True, slots=True)
class _DbfFieldLayout:
    name: str
    offset: int
    length: int


@dataclass(frozen=True, slots=True)
class _DbfLayout:
    row_count: int
    header_length: int
    record_length: int
    fields: tuple[_DbfFieldLayout, ...]


def _parse_dbf_header(data: bytes | mmap.mmap) -> _DbfLayout:
    if len(data) < 32:
        msg = "invalid DBF header length"
        raise LoaderError(msg)
    row_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]
    if len(data) < header_length:
        msg = "truncated DBF header"
        raise LoaderError(msg)

    fields: list[_DbfFieldLayout] = []
    descriptor_offset = 32
    record_offset = 1
    while descriptor_offset < header_length - 1 and data[descriptor_offset] != 0x0D:
        descriptor = data[descriptor_offset : descriptor_offset + 32]
        if len(descriptor) < 32:
            break
        raw_name = descriptor[:11].split(b"\x00", 1)[0]
        name = raw_name.decode("ascii")
        length = descriptor[16]
        fields.append(_DbfFieldLayout(name=name, offset=record_offset, length=length))
        record_offset += length
        descriptor_offset += 32

    return _DbfLayout(
        row_count=row_count,
        header_length=header_length,
        record_length=record_length,
        fields=tuple(fields),
    )


def _zip_member(zip_file: zipfile.ZipFile, layer_name: str, suffix: str) -> str:
    candidates = [
        name
        for name in zip_file.namelist()
        if f".{layer_name}." in name and name.lower().endswith(suffix)
    ]
    if len(candidates) != 1:
        msg = f"expected one {layer_name}{suffix} member, found {len(candidates)}"
        raise LoaderError(msg)
    return candidates[0]


def _shape_type_name(shape_type: int) -> str:
    return SHAPE_TYPES.get(shape_type, f"Unknown({shape_type})")
