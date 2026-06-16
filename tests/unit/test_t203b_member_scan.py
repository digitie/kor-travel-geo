"""T-203b: GDAL-free member-manifest extraction adapter + end-to-end validate.

Builds a real ZIP / directory on disk and checks ``scan_part_manifest`` collapses
SHP sidecars into one layer member, then drives the pure validator through it.
"""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

from kortravelgeo.core.source_validation import validate_group_manifest
from kortravelgeo.infra.source_member_scan import (
    _decode_zip_member_name,
    scan_group_manifest,
    scan_part_manifest,
)
from kortravelgeo.loaders.juso_map import MASTER_LAYER_NAMES

if TYPE_CHECKING:
    from pathlib import Path


def _write_electronic_map_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for layer in MASTER_LAYER_NAMES:
            for ext in (".shp", ".shx", ".dbf", ".prj"):
                zf.writestr(f"11000/{layer}{ext}", b"x")


def test_scan_collapses_shp_sidecars_into_one_layer(tmp_path: Path) -> None:
    archive = tmp_path / "seoul.zip"
    _write_electronic_map_zip(archive)
    part = scan_part_manifest(archive, part_key="11")
    layers = part.layer_names()
    assert layers == set(MASTER_LAYER_NAMES)
    a_layer = next(m for m in part.members if m.layer_name == "TL_SPBD_BULD")
    assert {".shp", ".shx", ".dbf", ".prj"} <= a_layer.suffixes


def test_scan_extracts_layer_name_from_supplier_filename(tmp_path: Path) -> None:
    archive = tmp_path / "shape-bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for layer in (
            "TL_SGCO_RNADR_MST",
            "TL_SPBD_ENTRC",
            "TL_SPBD_ENTRC_DONG",
        ):
            for ext in (".shp", ".shx", ".dbf"):
                zf.writestr(f"Total.JUSURB.20260501.{layer}.11000{ext}", b"x")
        for ext in (".shp", ".shx", ".dbf"):
            zf.writestr(
                f"Total_JUSUED_20260501_TL_SPBD_ENTRC_DONG_11000{ext}",
                b"x",
            )

    part = scan_part_manifest(archive, part_key="11")

    assert {
        "TL_SGCO_RNADR_MST",
        "TL_SPBD_ENTRC",
        "TL_SPBD_ENTRC_DONG",
    } <= part.layer_names()
    assert all(not layer.startswith("TOTAL") for layer in part.layer_names())


def test_scan_recovers_cp949_zip_member_names() -> None:
    original = "민원행정기관_202401.shp"
    mojibake = original.encode("cp949").decode("cp437")

    assert _decode_zip_member_name(mojibake, flag_bits=0) == original
    assert _decode_zip_member_name(original, flag_bits=0x800) == original


def test_scan_detects_member_yyyymm(tmp_path: Path) -> None:
    archive = tmp_path / "grid-center.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("SPPN_20240508.TXT", b"x")

    part = scan_part_manifest(archive, part_key="archive")

    assert part.members[0].detected_yyyymm == "202405"


def test_scan_dir_input_lists_files(tmp_path: Path) -> None:
    root = tmp_path / "extracted"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "rnaddrkor_11.txt").write_text("x", encoding="utf-8")
    part = scan_part_manifest(root, part_key="archive")
    assert any(m.member_path.endswith("rnaddrkor_11.txt") for m in part.members)


def test_scan_group_then_validate_passes(tmp_path: Path) -> None:
    parts: dict[str, Path] = {}
    for code in ("11", "26"):
        archive = tmp_path / f"{code}.zip"
        _write_electronic_map_zip(archive)
        parts[code] = archive
    manifest = scan_group_manifest(
        category="electronic_map_full", group_kind="multi_part", parts=parts
    )
    # only 2 of 17 sido parts present → coverage failure, but the present parts
    # themselves pass their 11-layer structure check.
    result = validate_group_manifest(manifest)
    assert result.coverage["11"] == "present"
    assert result.coverage["41"] == "missing"
    assert result.outcome == "failed"  # missing sido coverage
