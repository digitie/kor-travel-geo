"""Batch load DAG constants and payload helpers shared by client and api."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from kraddr.geo.exceptions import InvalidInputError

BATCH_SOURCE_KINDS: tuple[str, ...] = (
    "juso_text_load",
    "locsum_load",
    "navi_load",
    "shp_polygons_load",
    "pobox_load",
)

PATH_REQUIRED_KINDS: frozenset[str] = frozenset((*BATCH_SOURCE_KINDS, "bulk_load"))
PATH_KEYS: tuple[str, ...] = ("path", "source_path")


def batch_children(payload: dict[str, Any]) -> Sequence[tuple[str, dict[str, Any]]]:
    """Resolve a ``full_load_batch`` payload to its first-stage child jobs.

    Accepts either an explicit ``children`` / ``child_jobs`` list of
    ``{"kind": str, "payload": dict}`` entries, or a ``payloads`` mapping keyed
    by kind. Falls back to the default ``BATCH_SOURCE_KINDS`` ordering.

    The source loader children are validated before any DB row is created so a
    malformed batch cannot leave an orphaned root + immediately failing child
    jobs in ``load_jobs``.
    """

    raw_children = payload["children"] if "children" in payload else payload.get("child_jobs")
    if raw_children is not None:
        if not isinstance(raw_children, list):
            msg = "full_load_batch children must be a list"
            raise InvalidInputError(msg)
        children = tuple(_parse_child(child, index) for index, child in enumerate(raw_children))
        if not children:
            msg = "full_load_batch children must include at least one child job"
            raise InvalidInputError(msg)
        _validate_child_payloads(children)
        return children

    payloads = payload.get("payloads")
    if payloads is None:
        payloads = {}
    elif not isinstance(payloads, dict):
        msg = "full_load_batch payloads must be a mapping keyed by load kind"
        raise InvalidInputError(msg)
    default_children: list[tuple[str, dict[str, Any]]] = []
    for kind in BATCH_SOURCE_KINDS:
        child_payload = payloads.get(kind)
        default_payload = dict(child_payload) if isinstance(child_payload, dict) else {}
        default_children.append((kind, default_payload))
    children = tuple(default_children)
    _validate_child_payloads(children)
    return children


def _parse_child(child: object, index: int) -> tuple[str, dict[str, Any]]:
    if not isinstance(child, dict):
        msg = f"full_load_batch children[{index}] must be an object"
        raise InvalidInputError(msg)
    kind = child.get("kind")
    if not isinstance(kind, str) or not kind:
        msg = f"full_load_batch children[{index}].kind must be a non-empty string"
        raise InvalidInputError(msg)
    child_payload = child.get("payload")
    if child_payload is None:
        child_payload = {}
    if not isinstance(child_payload, dict):
        msg = f"full_load_batch children[{index}].payload must be an object"
        raise InvalidInputError(msg)
    return kind, dict(child_payload)


def _validate_child_payloads(children: Sequence[tuple[str, dict[str, Any]]]) -> None:
    missing = [
        kind
        for kind, child_payload in children
        if kind in PATH_REQUIRED_KINDS and not _has_path(child_payload)
    ]
    if missing:
        missing_kinds = ", ".join(missing)
        msg = (
            "full_load_batch child payload requires 'path' or 'source_path' "
            f"for: {missing_kinds}"
        )
        raise InvalidInputError(msg)


def _has_path(payload: dict[str, Any]) -> bool:
    return any(isinstance(payload.get(key), str) and bool(payload[key]) for key in PATH_KEYS)
