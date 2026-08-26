"""Dataset version token derivation + reference-month normalization (T-291b, ADR-067 D1/D2).

Pure functions only — no DB access. The async orchestration that walks
``parent_dataset_snapshot_id`` lineage when a snapshot's own ``source_set`` doesn't normalize
lives in :mod:`kortravelgeo.infra.admin_repo` (core must not depend on infra).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

VERSION_TOKEN_PREFIX = "dv1-"
_TOKEN_NAMESPACE = "ktg.dataset.version:"
VERSION_TOKEN_RE = re.compile(r"^dv1-[0-9a-f]{32}$")

#: External reference_months key vocabulary (ADR-067 D2) — fixed regardless of which
#: internal source_set shape produced it. ``pobox`` is reserved: no current writer emits it.
EXTERNAL_REFERENCE_MONTH_KEYS: frozenset[str] = frozenset(
    {
        "juso",
        "parcel_link",
        "locsum",
        "navi",
        "shp",
        "roadaddr_entrance",
        "sppn_makarea",
        "pobox",
    }
)

#: Rebuild-path (source_rebuild_service, "form A") category code -> external key(s).
#: Mirrors ``source_rebuild_service._CATEGORY_TO_LOAD_KINDS`` exactly (that dict is the
#: 정본 for which categories the rebuild path actually bridges into a load) —
#: ``roadname_hangul_full`` maps to both ``juso`` and ``parcel_link`` since the 한글
#: 전체분 archive is the source of both. Categories not in ``_CATEGORY_TO_LOAD_KINDS``
#: (e.g. ``epost_pobox_full``, ``roadaddr_building_shape_bundle``) are intentionally
#: absent — unmapped keys are skipped, not guessed.
_CATEGORY_TO_REFERENCE_MONTH_KEYS: dict[str, tuple[str, ...]] = {
    "roadname_hangul_full": ("juso", "parcel_link"),
    "locsum_full": ("locsum",),
    "navi_full": ("navi",),
    "electronic_map_full": ("shp",),
    "roadaddr_entrance_full": ("roadaddr_entrance",),
    "zone_shape_full": ("sppn_makarea",),
}

#: Top-level keys that are provenance/metadata, never a source category or kind — skipped
#: while normalizing regardless of which of the 4 source_set shapes is being read.
_NON_CATEGORY_KEYS: frozenset[str] = frozenset(
    {
        "load_batch_id",
        "rebuild_metadata",
        "source",
        "yyyymm_by_kind",
        "mixed_yyyymm",
        "hot_swap",
        "hot_swap_rollback",
    }
)

_YYYYMM_RE = re.compile(r"^\d{6}$")

#: internal release_kind -> external change_type (ADR-067 D2). Only daily_delta reads as
#: "delta"; everything else (including rollback) reads as "full" — a consumer's action
#: space is only "resync everything" vs "apply an increment."
ChangeType = Literal["full", "delta"]
_DELTA_RELEASE_KIND = "daily_delta"


def derive_version_token(serving_release_id: str | UUID) -> str:
    """``dv1-`` + first 32 hex chars of sha256("ktg.dataset.version:" + canonical uuid).

    The canonical form is always the lowercase-hyphenated 36-char UUID text
    representation, regardless of whether the caller passed a ``uuid.UUID`` object (the
    repository projection) or a plain string (a backup manifest's ``::text`` copy) — both
    must derive the same token for the same release.
    """
    canonical = str(UUID(str(serving_release_id)))
    digest = hashlib.sha256((_TOKEN_NAMESPACE + canonical).encode("utf-8")).hexdigest()
    return VERSION_TOKEN_PREFIX + digest[:32]


def derive_change_type(release_kind: str) -> ChangeType:
    return "delta" if release_kind == _DELTA_RELEASE_KIND else "full"


def normalize_reference_months_from_source_set(
    source_set: Mapping[str, Any],
) -> dict[str, str] | None:
    """Normalize one snapshot's raw ``source_set`` JSONB into the external key vocabulary.

    Handles the 4 shapes real writers produce (design doc §2):

    - **Form A** (rebuild path): top-level category codes -> ``{source_file_group_id,
      group_sha256, user_yyyymm, effective_yyyymm}``. Reads ``effective_yyyymm`` with
      ``user_yyyymm`` fallback (loader itself falls back the same way), maps the category
      code to 1-2 external keys via :data:`_CATEGORY_TO_REFERENCE_MONTH_KEYS`.
    - **Form B** (inference writers): ``{yyyymm_by_kind: {...}, mixed_yyyymm, source?}`` —
      reads the nested ``yyyymm_by_kind`` map, whose keys are already external-vocabulary
      kind names.
    - **Form C** (hot-swap/rollback recording): ``{"hot_swap": {...}}`` /
      ``{"hot_swap_rollback": {...}}`` — no category/kind keys survive the denylist, so
      this always normalizes to nothing (``None``), signaling the caller to fall back to
      snapshot lineage.
    - **Form D** (flat map — batch_dag._source_set / operator-submitted payload):
      ``{key: "YYYYMM"}`` — accepted only when the value matches ``^\\d{6}$``; a
      ``str()``-flattened degraded value (a Python repr string) fails the pattern and is
      silently skipped rather than guessed.

    Returns ``None`` (not an empty dict) when nothing normalized, so callers can
    distinguish "this snapshot's source_set had nothing to offer, try the parent" from "the
    normalized result was legitimately empty" — the two are the same thing here, but the
    ``None`` sentinel makes the lineage-fallback trigger condition explicit at call sites.
    """
    candidate: Mapping[str, Any] = source_set
    nested = source_set.get("yyyymm_by_kind")
    if isinstance(nested, Mapping):
        candidate = nested

    result: dict[str, str] = {}
    for key, value in candidate.items():
        if key in _NON_CATEGORY_KEYS:
            continue
        if key in _CATEGORY_TO_REFERENCE_MONTH_KEYS:
            if not isinstance(value, Mapping):
                continue
            yyyymm = value.get("effective_yyyymm") or value.get("user_yyyymm")
            if not (isinstance(yyyymm, str) and _YYYYMM_RE.match(yyyymm)):
                continue
            for external_key in _CATEGORY_TO_REFERENCE_MONTH_KEYS[key]:
                result[external_key] = yyyymm
            continue
        if key in EXTERNAL_REFERENCE_MONTH_KEYS:
            if isinstance(value, str) and _YYYYMM_RE.match(value):
                result[key] = value
            continue
        # Unknown key (unmapped rebuild category, arbitrary operator payload key): skip.
    return result or None


def reference_months_mixed(reference_months: Mapping[str, str] | None) -> bool:
    if not reference_months:
        return False
    return len(set(reference_months.values())) > 1


def encode_history_cursor(ordered_at: datetime, version_token: str) -> str:
    """Opaque keyset cursor over ``(ordered_at DESC, version_token DESC)``.

    Never carries an internal UUID — only the already-external ``version_token`` and the
    ordering timestamp, both already part of the public response shape.
    """
    payload = {"before_at": ordered_at.isoformat(), "before_token": version_token}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_history_cursor(cursor: str) -> tuple[datetime, str] | None:
    """Inverse of :func:`encode_history_cursor`. Returns ``None`` on any malformed input —
    callers turn that into a structured 400, never a 500."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw)
        before_at = datetime.fromisoformat(payload["before_at"])
        before_token = payload["before_token"]
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError):
        return None
    if not isinstance(before_token, str) or not VERSION_TOKEN_RE.match(before_token):
        return None
    return before_at, before_token
