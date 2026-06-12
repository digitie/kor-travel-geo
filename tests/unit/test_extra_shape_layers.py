from __future__ import annotations

import struct
import zipfile
from typing import TYPE_CHECKING

from kortravelgeo.loaders.extra_shape_layers import (
    compare_detail_dong_shape_bundle,
    compare_zone_shape_bundle,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_detail_dong_comparison_tracks_building_subset_and_entrance_refs(
    tmp_path: Path,
) -> None:
    detail_zip = tmp_path / "detail.zip"
    with zipfile.ZipFile(detail_zip, "w") as zip_file:
        _write_zip_layer(
            zip_file,
            "Total.JUSUED.20260501.TL_SGCO_RNADR_DONG.36110",
            5,
            fields=(
                ("BD_MGT_SN", 25),
                ("EQB_MAN_SN", 10),
                ("ADR_MNG_NO", 26),
                ("SIG_CD", 5),
                ("BUL_MAN_NO", 7),
            ),
            records=(
                (False, ("BD1", "1", "ADR1", "36110", "100")),
                (False, ("BD2", "1", "ADR1", "36110", "200")),
                (True, ("BD3", "1", "ADR2", "36110", "300")),
            ),
        )
        _write_zip_layer(
            zip_file,
            "Total.JUSUED.20260501.TL_SPBD_ENTRC_DONG.36110",
            1,
            fields=(("SIG_CD", 5), ("BUL_MAN_NO", 7), ("ENT_MAN_NO", 10)),
            records=(
                (False, ("36110", "100", "1")),
                (False, ("36110", "100", "2")),
                (False, ("36110", "999", "3")),
            ),
        )
    electronic_root = tmp_path / "전자지도" / "세종특별자치시" / "36000"
    _write_file_layer(
        electronic_root,
        "TL_SPBD_BULD",
        5,
        fields=(("BD_MGT_SN", 25), ("EQB_MAN_SN", 10)),
        records=(
            (False, ("BD1", "1")),
            (False, ("BD2", "1")),
            (False, ("BD4", "1")),
        ),
    )

    result = compare_detail_dong_shape_bundle(detail_zip, electronic_root.parent)

    assert result.detail_building_overlap.intersection_count == 2
    assert result.detail_building_overlap.left_only_count == 0
    assert result.detail_building_overlap.right_only_count == 1
    assert result.address_management_stats.row_count == 2
    assert result.address_management_stats.distinct_count == 1
    assert result.address_management_stats.duplicate_count == 1
    assert result.entrance_building_ref_overlap.left.row_count == 3
    assert result.entrance_building_ref_overlap.left.distinct_count == 2
    assert result.entrance_building_ref_overlap.intersection_count == 1
    assert result.entrance_building_ref_overlap.left_only_count == 1
    assert result.entrance_building_ref_overlap.right_only_count == 1


def test_zone_comparison_identifies_exact_duplicates_and_extra_layers(tmp_path: Path) -> None:
    zone_zip = tmp_path / "zone.zip"
    electronic_root = tmp_path / "전자지도" / "세종특별자치시" / "36000"
    layer_specs = {
        "TL_SCCO_CTPRVN": (("CTPRVN_CD", 2), (("36",),)),
        "TL_SCCO_SIG": (("SIG_CD", 5), (("36110",),)),
        "TL_SCCO_EMD": (("EMD_CD", 10), (("3611010100",),)),
        "TL_SCCO_LI": (("LI_CD", 10), (("3611010123",),)),
        "TL_KODIS_BAS": (("BAS_ID", 5), (("30145",),)),
    }
    with zipfile.ZipFile(zone_zip, "w") as zip_file:
        for layer_name, (field, rows) in layer_specs.items():
            records = tuple((False, values) for values in rows)
            _write_zip_layer(zip_file, f"36110/{layer_name}", 5, fields=(field,), records=records)
            _write_file_layer(electronic_root, layer_name, 5, fields=(field,), records=records)
        _write_zip_layer(
            zip_file,
            "36110/TL_SCCO_GEMD",
            5,
            fields=(("EMD_CD", 10),),
            records=((False, ("3611099900",)),),
        )
        _write_zip_layer(
            zip_file,
            "36110/TL_SPPN_MAKAREA",
            5,
            fields=(("SIG_CD", 5), ("MAKAREA_ID", 10)),
            records=(
                (False, ("36110", "1")),
                (False, ("36110", "2")),
            ),
        )

    result = compare_zone_shape_bundle(zone_zip, electronic_root.parent)

    assert all(item.key_overlap.left_only_count == 0 for item in result.duplicate_layer_overlaps)
    assert all(item.key_overlap.right_only_count == 0 for item in result.duplicate_layer_overlaps)
    assert result.gemd_emd_key_overlap.intersection_count == 0
    assert result.gemd_emd_key_overlap.left_only_count == 1
    assert result.gemd_emd_key_overlap.right_only_count == 1
    assert result.makarea_key_stats.row_count == 2
    assert result.makarea_key_stats.distinct_count == 2
    assert result.makarea_key_stats.duplicate_count == 0


def _write_zip_layer(
    zip_file: zipfile.ZipFile,
    stem: str,
    shape_type: int,
    *,
    fields: tuple[tuple[str, int], ...],
    records: tuple[tuple[bool, tuple[str, ...]], ...],
) -> None:
    zip_file.writestr(f"{stem}.shp", _shp_header(shape_type))
    zip_file.writestr(f"{stem}.dbf", _dbf_bytes(fields=fields, records=records))
    zip_file.writestr(f"{stem}.shx", _shp_header(shape_type))


def _write_file_layer(
    root: Path,
    layer_name: str,
    shape_type: int,
    *,
    fields: tuple[tuple[str, int], ...],
    records: tuple[tuple[bool, tuple[str, ...]], ...],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{layer_name}.shp").write_bytes(_shp_header(shape_type))
    (root / f"{layer_name}.dbf").write_bytes(_dbf_bytes(fields=fields, records=records))
    (root / f"{layer_name}.shx").write_bytes(_shp_header(shape_type))


def _shp_header(shape_type: int) -> bytes:
    header = bytearray(100)
    header[0:4] = struct.pack(">i", 9994)
    header[24:28] = struct.pack(">i", 50)
    header[28:32] = struct.pack("<i", 1000)
    header[32:36] = struct.pack("<i", shape_type)
    return bytes(header)


def _dbf_bytes(
    *,
    fields: tuple[tuple[str, int], ...],
    records: tuple[tuple[bool, tuple[str, ...]], ...],
) -> bytes:
    header_length = 32 + 32 * len(fields) + 1
    record_length = 1 + sum(length for _, length in fields)
    header = bytearray(32)
    header[0] = 0x03
    header[4:8] = struct.pack("<I", len(records))
    header[8:10] = struct.pack("<H", header_length)
    header[10:12] = struct.pack("<H", record_length)

    descriptors = bytearray()
    for name, length in fields:
        descriptor = bytearray(32)
        descriptor[: len(name)] = name.encode("ascii")
        descriptor[11] = ord("C")
        descriptor[16] = length
        descriptors.extend(descriptor)

    body = bytearray()
    for deleted, values in records:
        body.extend(b"*" if deleted else b" ")
        for value, (_, length) in zip(values, fields, strict=True):
            body.extend(value.encode("ascii").ljust(length)[:length])

    return bytes(header + descriptors + b"\r" + body + b"\x1a")
