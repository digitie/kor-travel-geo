"""Source-set discovery and planning helpers for full-load jobs."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kraddr.geo.core.redaction import hash_confirmation
from kraddr.geo.dto.admin import SourceCandidate, SourceSetDiscovery, SourceSetPlan
from kraddr.geo.exceptions import InvalidInputError

REQUIRED_SOURCE_KINDS: tuple[str, ...] = ("juso", "parcel_link", "locsum", "navi", "shp")
OPTIONAL_SOURCE_KINDS: tuple[str, ...] = (
    "roadaddr_entrance",
    "sppn_makarea",
    "pobox",
    "bulk",
)
SOURCE_KIND_ORDER: tuple[str, ...] = (*REQUIRED_SOURCE_KINDS, *OPTIONAL_SOURCE_KINDS)

SOURCE_TO_JOB_KIND: dict[str, str] = {
    "juso": "juso_text_load",
    "parcel_link": "juso_parcel_link_load",
    "locsum": "locsum_load",
    "navi": "navi_load",
    "shp": "shp_polygons_load",
    "roadaddr_entrance": "roadaddr_entrance_load",
    "pobox": "pobox_load",
    "bulk": "bulk_load",
}

_YYYYMM_RE = re.compile(r"(20\d{2})(0[1-9]|1[0-2])")
_YYMM_RE = re.compile(r"(?<!\d)(\d{2})(0[1-9]|1[0-2])(?!\d)")


def discover_load_sources(
    root_path: Path,
    *,
    include_optional: bool = True,
) -> SourceSetDiscovery:
    root = root_path.expanduser().resolve()
    if not root.exists():
        msg = f"source root does not exist: {root}"
        raise InvalidInputError(msg)

    candidates = _discover_candidates(root, include_optional=include_optional)
    recommended = _recommended_candidates(candidates, include_optional=include_optional)
    missing_required = tuple(kind for kind in REQUIRED_SOURCE_KINDS if kind not in recommended)
    yyyymm_by_kind = {kind: candidate.inferred_yyyymm for kind, candidate in recommended.items()}
    unique_months = {value for value in yyyymm_by_kind.values() if value is not None}
    warning = None
    if missing_required:
        warning = f"missing required sources: {', '.join(missing_required)}"
    elif len(unique_months) > 1:
        warning = "source set has mixed yyyymm values"

    return SourceSetDiscovery(
        root_path=str(root),
        candidates=tuple(candidates),
        recommended=recommended,
        missing_required=missing_required,
        mixed_yyyymm=len(unique_months) > 1,
        yyyymm_by_kind=yyyymm_by_kind,
        warning=warning,
    )


def build_full_load_source_set_plan(
    *,
    root_path: Path | None = None,
    versions: dict[str, str] | None = None,
    explicit_paths: dict[str, str] | None = None,
    include_optional: bool = True,
    allow_mixed_yyyymm: bool = False,
    confirmation_token: str | None = None,
    acknowledged_by: str = "api",
) -> SourceSetPlan:
    versions = versions or {}
    explicit_paths = explicit_paths or {}
    discovery = (
        discover_load_sources(root_path, include_optional=include_optional)
        if root_path
        else None
    )
    selected = dict(discovery.recommended) if discovery is not None else {}

    for kind, raw_path in explicit_paths.items():
        if kind not in SOURCE_KIND_ORDER:
            msg = f"unknown source kind: {kind}"
            raise InvalidInputError(msg)
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            msg = f"source path does not exist for {kind}: {path}"
            raise InvalidInputError(msg)
        selected[kind] = _candidate_for(kind, path, confidence="high")

    missing_required = tuple(kind for kind in REQUIRED_SOURCE_KINDS if kind not in selected)
    if missing_required:
        msg = f"missing required sources: {', '.join(missing_required)}"
        raise InvalidInputError(msg)

    selected = {
        kind: selected[kind]
        for kind in SOURCE_KIND_ORDER
        if kind in selected and (include_optional or kind in REQUIRED_SOURCE_KINDS)
    }
    yyyymm_by_kind = {
        kind: _version_for(kind, versions, candidate)
        for kind, candidate in selected.items()
    }
    unique_months = {value for value in yyyymm_by_kind.values() if value is not None}
    mixed_yyyymm = len(unique_months) > 1
    expected_confirmation = confirmation_token_for(yyyymm_by_kind) if mixed_yyyymm else None
    if mixed_yyyymm and not allow_mixed_yyyymm:
        msg = f"mixed source yyyymm requires --allow-mixed-yyyymm: {expected_confirmation}"
        raise InvalidInputError(msg)
    if mixed_yyyymm and confirmation_token != expected_confirmation:
        msg = f"mixed source yyyymm requires confirmation token: {expected_confirmation}"
        raise InvalidInputError(msg)

    acknowledged_at = datetime.now(UTC) if mixed_yyyymm else None
    source_set_id = _source_set_id(yyyymm_by_kind, selected)
    candidate_paths = {kind: candidate.path for kind, candidate in selected.items()}
    candidate_sha256 = {kind: candidate.sha256 for kind, candidate in selected.items()}
    source_set = {
        "source_set_id": source_set_id,
        "yyyymm_by_kind": yyyymm_by_kind,
        "mixed_yyyymm": mixed_yyyymm,
        "mixed_yyyymm_acknowledged": mixed_yyyymm,
        "acknowledged_by": acknowledged_by if mixed_yyyymm else None,
        "acknowledged_at": acknowledged_at.isoformat() if acknowledged_at else None,
        "confirmation_token_hash": (
            hash_confirmation(confirmation_token) if confirmation_token else None
        ),
        "candidate_paths": candidate_paths,
        "candidate_sha256": candidate_sha256,
    }
    batch_payload = {
        "source_set": source_set,
        "children": _batch_children(selected, yyyymm_by_kind, source_set),
    }
    warning = "source set has mixed yyyymm values" if mixed_yyyymm else None

    return SourceSetPlan(
        source_set_id=source_set_id,
        root_path=str(root_path.expanduser().resolve()) if root_path else None,
        candidates=discovery.candidates if discovery else tuple(selected.values()),
        selected=selected,
        missing_required=(),
        yyyymm_by_kind=yyyymm_by_kind,
        mixed_yyyymm=mixed_yyyymm,
        mixed_yyyymm_acknowledged=mixed_yyyymm,
        acknowledged_by=acknowledged_by if mixed_yyyymm else None,
        acknowledged_at=acknowledged_at,
        confirmation_token_hash=source_set["confirmation_token_hash"],
        expected_confirmation_token=expected_confirmation,
        candidate_paths=candidate_paths,
        candidate_sha256=candidate_sha256,
        batch_payload=batch_payload,
        warning=warning,
    )


def confirmation_token_for(yyyymm_by_kind: dict[str, str | None]) -> str:
    months = sorted({value for value in yyyymm_by_kind.values() if value is not None})
    return f"{'/'.join(months)} 혼합 적재 확인"


def infer_yyyymm(path: Path) -> str | None:
    recent_parts = path.parts[-4:]
    for part in reversed(recent_parts):
        match = _YYYYMM_RE.search(part)
        if match:
            return "".join(match.groups())
    for part in reversed(recent_parts):
        match = _YYMM_RE.search(part)
        if match:
            year, month = match.groups()
            return f"20{year}{month}"
    return None


def guess_source_kind(path: Path) -> str | None:
    name = path.name.lower()
    if "tl_sppn_makarea" in name:
        return "sppn_makarea"
    if "rnentdata" in name or "출입구" in path.name:
        return "roadaddr_entrance"
    if "위치정보요약" in path.name or "locsum" in name or "entrc" in name:
        return "locsum"
    if "내비게이션" in path.name or "navi" in name:
        return "navi"
    if "전자지도" in path.name or name == "tl_spbd_buld.shp":
        return "shp"
    if "jibun_rnaddrkor" in name:
        return "parcel_link"
    if "도로명주소 한글" in path.name or "rnaddrkor" in name:
        return "juso"
    if "zipcode" in name or "pobox" in name or "사서함" in path.name:
        return "pobox"
    if "bulk" in name or "대량" in path.name:
        return "bulk"
    return None


def _discover_candidates(root: Path, *, include_optional: bool) -> list[SourceCandidate]:
    paths = [root]
    if root.is_dir():
        paths.extend(_walk_limited(root))
    candidates: list[SourceCandidate] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        kind = guess_source_kind(path)
        if kind is None:
            continue
        candidate_path = _candidate_path(kind, path)
        kinds = ("juso", "parcel_link") if kind == "juso" else (kind,)
        for candidate_kind in kinds:
            if not include_optional and candidate_kind in OPTIONAL_SOURCE_KINDS:
                continue
            key = (candidate_kind, str(candidate_path))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_candidate_for(candidate_kind, candidate_path, confidence="high"))
    return candidates


def _candidate_path(kind: str, path: Path) -> Path:
    if kind in {"shp", "sppn_makarea"} and path.is_file():
        return path.parent
    return path


def _candidate_for(kind: str, path: Path, *, confidence: str) -> SourceCandidate:
    file_count, byte_size = _path_stats(path)
    return SourceCandidate(
        kind=kind,
        path=str(path),
        inferred_yyyymm=infer_yyyymm(path),
        file_count=file_count,
        byte_size=byte_size,
        sha256=_path_fingerprint(path),
        confidence=confidence,
        note="directory inventory hash" if path.is_dir() else None,
    )


def _walk_limited(root: Path, *, limit: int = 5_000) -> list[Path]:
    result: list[Path] = []
    for index, path in enumerate(root.rglob("*")):
        if index >= limit:
            break
        result.append(path)
    return result


def _recommended_candidates(
    candidates: list[SourceCandidate],
    *,
    include_optional: bool,
) -> dict[str, SourceCandidate]:
    kinds = SOURCE_KIND_ORDER if include_optional else REQUIRED_SOURCE_KINDS
    result: dict[str, SourceCandidate] = {}
    for kind in kinds:
        matches = [candidate for candidate in candidates if candidate.kind == kind]
        if not matches:
            continue
        result[kind] = sorted(
            matches,
            key=lambda item: (
                item.inferred_yyyymm or "",
                item.file_count or 0,
                item.byte_size or 0,
            ),
            reverse=True,
        )[0]
    return result


def _version_for(
    kind: str,
    versions: dict[str, str],
    candidate: SourceCandidate,
) -> str | None:
    explicit = versions.get(kind)
    if explicit is not None:
        if not re.fullmatch(r"\d{6}", explicit):
            msg = f"{kind} yyyymm must be YYYYMM: {explicit}"
            raise InvalidInputError(msg)
        return explicit
    return candidate.inferred_yyyymm


def _batch_children(
    selected: dict[str, SourceCandidate],
    yyyymm_by_kind: dict[str, str | None],
    source_set: dict[str, Any],
) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    for source_kind in SOURCE_KIND_ORDER:
        candidate = selected.get(source_kind)
        job_kind = SOURCE_TO_JOB_KIND.get(source_kind)
        if candidate is None or job_kind is None:
            continue
        payload: dict[str, Any] = {
            "path": candidate.path,
            "source_yyyymm": yyyymm_by_kind.get(source_kind),
            "source_set": source_set,
        }
        if source_kind == "shp":
            payload["mode"] = "full"
        children.append({"kind": job_kind, "payload": payload})
    return children


def _source_set_id(
    yyyymm_by_kind: dict[str, str | None],
    selected: dict[str, SourceCandidate],
) -> str:
    digest = hashlib.sha256()
    for kind in SOURCE_KIND_ORDER:
        digest.update(kind.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(yyyymm_by_kind.get(kind)).encode("utf-8"))
        digest.update(b"\0")
        if kind in selected:
            digest.update(selected[kind].path.encode("utf-8"))
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{digest.hexdigest()[:12]}"


def _path_stats(path: Path) -> tuple[int, int]:
    if path.is_file():
        return (1, path.stat().st_size)
    file_count = 0
    byte_size = 0
    for child in _walk_limited(path, limit=20_000):
        if child.is_file():
            file_count += 1
            byte_size += child.stat().st_size
    return (file_count, byte_size)


def _path_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    for child in sorted(_walk_limited(path, limit=20_000)):
        if not child.is_file():
            continue
        try:
            relative = child.relative_to(path)
        except ValueError:
            relative = child
        stat = child.stat()
        digest.update(str(relative).encode("utf-8", errors="ignore"))
        digest.update(b"\0")
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()
