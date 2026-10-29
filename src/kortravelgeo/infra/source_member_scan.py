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

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

from kortravelgeo.core.source_layers import (
    ADDRESS_BUNDLE_LAYER,
    BUNDLE_CONNECTION_LAYER,
    BUNDLE_ENTRANCE_LAYER,
    DETAIL_DONG_ENTRANCE_LAYER,
    DETAIL_DONG_POLYGON_LAYER,
    MASTER_LAYER_NAMES,
    ZONE_MAKAREA_LAYER_NAME,
)
from kortravelgeo.core.source_validation import (
    T127_GRID_SHAPE_LAYERS,
    GroupManifest,
    ManifestMember,
    PartManifest,
)
from kortravelgeo.exceptions import InvalidInputError

_SHP_SUFFIXES = {".shp", ".shx", ".dbf", ".prj"}
_YYYYMM_RE = re.compile(r"(20\d{2})(0[1-9]|1[0-2])(?:\d{2})?")
_KNOWN_LAYER_NAMES = tuple(
    sorted(
        {
            *MASTER_LAYER_NAMES,
            ZONE_MAKAREA_LAYER_NAME,
            ADDRESS_BUNDLE_LAYER,
            BUNDLE_ENTRANCE_LAYER,
            BUNDLE_CONNECTION_LAYER,
            DETAIL_DONG_POLYGON_LAYER,
            DETAIL_DONG_ENTRANCE_LAYER,
            # T-127 후속(#307 M1): TL_SPPN_GRID_* (national_point_grid_shape)가
            # 미등록이라 supplier가 파일명을 감싸면(nationwide_TL_SPPN_GRID_1KM)
            # canonical 불일치로 failed 오분류됐다.
            *T127_GRID_SHAPE_LAYERS,
        },
        key=len,
        reverse=True,
    )
)


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
            return [
                _decode_zip_member_name(info.filename, flag_bits=info.flag_bits)
                for info in zf.infolist()
                if not info.filename.endswith("/")
            ]
    # RustFS materialization uses extensionless slot names; inspect the signature.
    with archive.open("rb") as stream:
        is_7z = stream.read(6) == b"7z\xbc\xaf\x27\x1c"
    if is_7z:
        seven_zip = shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
        if seven_zip is None:
            raise InvalidInputError("7z/7zz/7za command not found; 7z 원천을 검증할 수 없습니다")
        try:
            result = subprocess.run(
                [seven_zip, "l", "-slt", "-ba", str(archive)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise InvalidInputError("7z 원천의 파일 목록 조회 시간이 초과되었습니다") from exc
        if result.returncode != 0:
            raise InvalidInputError("7z 원천의 파일 목록을 읽을 수 없습니다")
        names: list[str] = []
        for block in result.stdout.split("\n\n"):
            fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
            if fields.get("Folder") == "+" or fields.get("Attributes", "").startswith("D"):
                continue
            if "Path" in fields:
                names.append(fields["Path"])
        return names
    return [archive.name]


def _decode_zip_member_name(name: str, *, flag_bits: int) -> str:
    """Recover CP949 member names from legacy ZIPs when the UTF-8 flag is absent."""
    if flag_bits & 0x800:
        return name
    try:
        return name.encode("cp437").decode("cp949")
    except UnicodeError:
        return name


def scan_part_manifest(archive: Path, *, part_key: str) -> PartManifest:
    """Build a :class:`PartManifest` from one archive (one upload slot).

    SHP layers are collapsed to one :class:`ManifestMember` per layer name with
    the union of its sidecar suffixes; everything else becomes a plain file
    member. Supplier archives often wrap the canonical layer name in a filename
    prefix/date/sido code, so the scanner extracts known layer tokens from the
    stem before falling back to the full uppercased stem.
    """
    names = _member_names(archive)
    layers: dict[str, set[str]] = {}
    files: list[ManifestMember] = []
    for name in names:
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        stem, _, ext = base.rpartition(".")
        suffix = f".{ext.lower()}" if ext else ""
        if suffix in _SHP_SUFFIXES and stem:
            layer = _canonical_layer_name(stem)
            layers.setdefault(layer, set()).add(suffix)
        else:
            files.append(
                ManifestMember(
                    member_path=name,
                    member_kind="file",
                    detected_yyyymm=_detect_yyyymm(base),
                )
            )
    members = [
        ManifestMember(
            member_path=f"{layer}.shp",
            member_kind="shp_layer",
            layer_name=layer,
            suffixes=frozenset(suffixes),
            detected_yyyymm=_detect_yyyymm(layer),
        )
        for layer, suffixes in sorted(layers.items())
    ]
    members.extend(files)
    return PartManifest(part_key=part_key, members=tuple(members))


def _canonical_layer_name(stem: str) -> str:
    upper = stem.upper()
    if upper in _KNOWN_LAYER_NAMES:
        return upper
    for layer in _KNOWN_LAYER_NAMES:
        start = 0
        while True:
            index = upper.find(layer, start)
            if index < 0:
                break
            end = index + len(layer)
            if _has_layer_token_boundary(upper, index, end):
                return layer
            start = index + 1
    return upper


def _detect_yyyymm(text: str) -> str | None:
    match = _YYYYMM_RE.search(text)
    if match is None:
        return None
    return "".join(match.groups())


def _has_layer_token_boundary(text: str, start: int, end: int) -> bool:
    """Return true when a known layer is separated from vendor affixes.

    Current real archives use dot-delimited names, and this also accepts
    underscore/hyphen/space-style separators. Fully concatenated vendor names
    intentionally fall back to the full stem so structure validation fails
    visibly instead of guessing a false layer match.
    """

    before_ok = start == 0 or not text[start - 1].isalnum()
    after_ok = end == len(text) or not text[end].isalnum()
    return before_ok and after_ok


def scan_group_manifest(
    *,
    category: str,
    group_kind: str,
    parts: dict[str, Path],
    user_yyyymm: str | None = None,
) -> GroupManifest:
    """Build a :class:`GroupManifest` from ``part_key -> archive path``."""
    part_manifests = tuple(
        scan_part_manifest(path, part_key=key) for key, path in sorted(parts.items())
    )
    return GroupManifest(
        category=category,
        group_kind=group_kind,  # type: ignore[arg-type]
        parts=part_manifests,
        user_yyyymm=user_yyyymm,
    )
