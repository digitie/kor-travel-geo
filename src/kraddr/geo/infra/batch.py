"""Batch load DAG constants and payload helpers shared by client and api."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

BATCH_SOURCE_KINDS: tuple[str, ...] = (
    "juso_text_load",
    "locsum_load",
    "navi_load",
    "shp_polygons_load",
    "pobox_load",
)


def batch_children(payload: dict[str, Any]) -> Sequence[tuple[str, dict[str, Any]]]:
    """Resolve a ``full_load_batch`` payload to its first-stage child jobs.

    Accepts either an explicit ``children`` / ``child_jobs`` list of
    ``{"kind": str, "payload": dict}`` entries, or a ``payloads`` mapping keyed
    by kind. Falls back to the default ``BATCH_SOURCE_KINDS`` ordering.
    """

    raw_children = payload.get("children") or payload.get("child_jobs")
    if isinstance(raw_children, list):
        children: list[tuple[str, dict[str, Any]]] = []
        for child in raw_children:
            if not isinstance(child, dict):
                continue
            kind = child.get("kind")
            child_payload = child.get("payload") or {}
            if isinstance(kind, str) and isinstance(child_payload, dict):
                children.append((kind, child_payload))
        if children:
            return tuple(children)

    payloads = payload.get("payloads")
    if not isinstance(payloads, dict):
        payloads = {}
    default_children: list[tuple[str, dict[str, Any]]] = []
    for kind in BATCH_SOURCE_KINDS:
        child_payload = payloads.get(kind)
        default_payload = dict(child_payload) if isinstance(child_payload, dict) else {}
        default_children.append((kind, default_payload))
    return tuple(default_children)
