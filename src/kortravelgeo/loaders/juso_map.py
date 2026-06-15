"""Discovery helpers for road-name address electronic map SHP folders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from struct import unpack

# MASTER_LAYER_NAMES is re-exported from kortravelgeo.core.source_layers (single
# source of truth) so core.source_validation can reference it without importing
# this loader. The redundant alias marks it as an explicit re-export for mypy so
# existing ``loaders.juso_map.MASTER_LAYER_NAMES`` references keep working.
from kortravelgeo.core.source_layers import (
    MASTER_LAYER_NAMES as MASTER_LAYER_NAMES,
)
from kortravelgeo.exceptions import LoaderError


@dataclass(frozen=True)
class DbfField:
    name: str
    type: str
    length: int
    decimal_count: int


@dataclass(frozen=True)
class DbfHeader:
    record_count: int
    header_length: int
    record_length: int
    fields: tuple[DbfField, ...]


@dataclass(frozen=True)
class ShpHeader:
    file_code: int
    file_length_bytes: int
    version: int
    shape_type: int
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class JusoLayerFiles:
    name: str
    shp_path: Path
    shx_path: Path
    dbf_path: Path

    def read_shp_header(self) -> ShpHeader:
        return read_shp_header(self.shp_path)

    def read_dbf_header(self) -> DbfHeader:
        return read_dbf_header(self.dbf_path)


@dataclass(frozen=True)
class JusoSidoDataset:
    root: Path
    sido_name: str
    sig_code: str
    layers: tuple[JusoLayerFiles, ...]

    def layer(self, name: str) -> JusoLayerFiles:
        for layer in self.layers:
            if layer.name == name:
                return layer
        msg = f"layer not found: {name}"
        raise LoaderError(msg)


def discover_sido_dataset(path: Path | str) -> JusoSidoDataset:
    root = Path(path)
    if not root.exists():
        msg = f"juso map directory does not exist: {root}"
        raise LoaderError(msg)

    sig_dirs = sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit())
    if not sig_dirs:
        msg = f"no SIG code directory found under: {root}"
        raise LoaderError(msg)
    if len(sig_dirs) > 1:
        msg = f"expected one SIG code directory under {root}, found {len(sig_dirs)}"
        raise LoaderError(msg)

    sig_dir = sig_dirs[0]
    layers = tuple(_layer_files(sig_dir, layer_name) for layer_name in MASTER_LAYER_NAMES)
    return JusoSidoDataset(
        root=root,
        sido_name=root.name,
        sig_code=sig_dir.name,
        layers=layers,
    )


def discover_sido_datasets(path: Path | str) -> tuple[JusoSidoDataset, ...]:
    """Discover one or more 시도 electronic-map datasets under ``path``.

    ``path`` may point directly at one 시도 directory (the legacy behavior) or
    at a parent directory containing several 시도 directories. The latter is the
    shape produced by source-registry rebuild staging for ``electronic_map_full``.
    """

    root = Path(path)
    try:
        return (discover_sido_dataset(root),)
    except LoaderError as exc:
        direct_error = exc

    if not root.exists() or not root.is_dir():
        raise direct_error

    datasets: list[JusoSidoDataset] = []
    failures: list[str] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        has_sig_dir = any(p.is_dir() and p.name.isdigit() for p in child.iterdir())
        if not has_sig_dir:
            continue
        try:
            datasets.append(discover_sido_dataset(child))
        except LoaderError as exc:
            failures.append(f"{child.name}: {exc}")
    if failures:
        joined = "; ".join(failures)
        msg = f"failed to discover one or more sido datasets under {root}: {joined}"
        raise LoaderError(msg)
    if datasets:
        return tuple(datasets)
    raise direct_error


def read_shp_header(path: Path | str) -> ShpHeader:
    shp_path = Path(path)
    data = shp_path.read_bytes()[:100]
    if len(data) != 100:
        msg = f"invalid SHP header length: {shp_path}"
        raise LoaderError(msg)

    file_code = unpack(">i", data[0:4])[0]
    file_length_words = unpack(">i", data[24:28])[0]
    version = unpack("<i", data[28:32])[0]
    shape_type = unpack("<i", data[32:36])[0]
    min_x, min_y, max_x, max_y = unpack("<4d", data[36:68])
    return ShpHeader(
        file_code=file_code,
        file_length_bytes=file_length_words * 2,
        version=version,
        shape_type=shape_type,
        bbox=(min_x, min_y, max_x, max_y),
    )


def read_dbf_header(path: Path | str) -> DbfHeader:
    dbf_path = Path(path)
    with dbf_path.open("rb") as file:
        header = file.read(32)
        if len(header) != 32:
            msg = f"invalid DBF header length: {dbf_path}"
            raise LoaderError(msg)

        record_count = unpack("<I", header[4:8])[0]
        header_length = unpack("<H", header[8:10])[0]
        record_length = unpack("<H", header[10:12])[0]
        field_bytes = file.read(header_length - 33)
        terminator = file.read(1)

    if terminator != b"\r":
        msg = f"invalid DBF field descriptor terminator: {dbf_path}"
        raise LoaderError(msg)

    fields = []
    for offset in range(0, len(field_bytes), 32):
        descriptor = field_bytes[offset : offset + 32]
        if len(descriptor) < 32:
            continue
        raw_name = descriptor[:11].split(b"\x00", 1)[0]
        name = raw_name.decode("ascii")
        fields.append(
            DbfField(
                name=name,
                type=chr(descriptor[11]),
                length=descriptor[16],
                decimal_count=descriptor[17],
            )
        )

    return DbfHeader(
        record_count=record_count,
        header_length=header_length,
        record_length=record_length,
        fields=tuple(fields),
    )


def _layer_files(sig_dir: Path, layer_name: str) -> JusoLayerFiles:
    shp_path = sig_dir / f"{layer_name}.shp"
    shx_path = sig_dir / f"{layer_name}.shx"
    dbf_path = sig_dir / f"{layer_name}.dbf"
    missing = [path for path in (shp_path, shx_path, dbf_path) if not path.is_file()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        msg = f"missing layer files for {layer_name}: {joined}"
        raise LoaderError(msg)
    return JusoLayerFiles(layer_name, shp_path, shx_path, dbf_path)
