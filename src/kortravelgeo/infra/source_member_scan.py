"""Archive member-manifest extraction adapter (T-203b).

Thin, lazily-used adapter that turns an uploaded archive (ZIP / extracted dir)
on disk into the :class:`~kortravelgeo.core.source_validation.PartManifest` the
*pure* validator decides on. Structure validation (member presence + SHP/DBF
sidecar completeness) needs only ``zipfile`` member listing, NOT GDAL — so this
adapter reads the central directory / dir entries only and never opens geometry.

Keeping extraction here (and the decision logic GDAL-free in
``core.source_validation``) is the doc's "SHP/DBF partial read" split (L7 /
lines ~970-977): no GB-scale reads to validate structure.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from kortravelgeo.core.source_validation import (
    GroupManifest,
    ManifestMember,
    PartManifest,
)

_SHP_SUFFIXES = {".shp", ".shx", ".dbf", ".prj"}


def _member_names(archive: Path) -> list[str]:
    """List member names of a ZIP, or files under an extracted directory."""
    if archive.is_dir():
        return [
            str(p.relative_to(archive)).replace("\\", "/")
            for p in archive.rglob("*")
            if p.is_file()
        ]
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            return [name for name in zf.namelist() if not name.endswith("/")]
    # 7z / other: caller supplies a pre-extracted dir; treat as the lone member.
    return [archive.name]


def scan_part_manifest(archive: Path, *, part_key: str) -> PartManifest:
    """Build a :class:`PartManifest` from one archive (one upload slot).

    SHP layers are collapsed to one :class:`ManifestMember` per layer name with
    the union of its sidecar suffixes; everything else becomes a plain file
    member. Layer name = the stem of a ``.shp/.shx/.dbf/.prj`` member, uppercased
    to match the loader layer constants.
    """
    names = _member_names(archive)
    layers: dict[str, set[str]] = {}
    files: list[ManifestMember] = []
    for name in names:
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        stem, _, ext = base.rpartition(".")
        suffix = f".{ext.lower()}" if ext else ""
        if suffix in _SHP_SUFFIXES and stem:
            layers.setdefault(stem.upper(), set()).add(suffix)
        else:
            files.append(ManifestMember(member_path=name, member_kind="file"))
    members = [
        ManifestMember(
            member_path=f"{layer}.shp",
            member_kind="shp_layer",
            layer_name=layer,
            suffixes=frozenset(suffixes),
        )
        for layer, suffixes in sorted(layers.items())
    ]
    members.extend(files)
    return PartManifest(part_key=part_key, members=tuple(members))


def scan_group_manifest(
    *,
    category: str,
    group_kind: str,
    parts: dict[str, Path],
) -> GroupManifest:
    """Build a :class:`GroupManifest` from ``part_key -> archive path``."""
    part_manifests = tuple(
        scan_part_manifest(path, part_key=key) for key, path in sorted(parts.items())
    )
    return GroupManifest(
        category=category,
        group_kind=group_kind,  # type: ignore[arg-type]
        parts=part_manifests,
    )
