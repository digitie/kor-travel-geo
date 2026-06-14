"""Pure decision logic for ``recompute_group_aggregates`` (T-203b).

Implements the ``recompute_group_aggregates()`` contract table and the match-set
state-transition rules from ``docs/t109-backup-source-upload-management.md``
(lines ~345-356 and ~804-818), as **pure functions** so the down/up propagation
can be unit-tested without a database. The DB-backed service in
``infra/source_group_service.py`` reads the rows, calls these functions, and
writes the results back inside the caller's transaction.

The canonical ``group_sha256`` / ``source_set_hash`` computations live here too:
both are deterministic SHA-256 over a canonically-ordered JSON serialization of
child metadata (never the archive body).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

# --- group derived state ---------------------------------------------------

GroupState = Literal[
    "validating",
    "available",
    "quarantined",
    "missing",
    "soft_deleted",
    "hard_deleted",
    "delete_failed",
]
ValidationState = Literal[
    "unknown", "not_started", "running", "passed", "warning", "failed", "skipped"
]
MatchSetState = Literal[
    "draft", "validated", "active", "retired", "invalid", "revalidatable", "restored_from_backup"
]

#: A group is "bad" (down-propagation trigger) when an active match set can no
#: longer be rebuilt from it. doc line 343: missing/quarantined/delete_failed.
_BAD_GROUP_STATES: frozenset[str] = frozenset({"missing", "quarantined", "delete_failed"})


@dataclass(frozen=True)
class ChildFileFacts:
    """The subset of a child ``ops.source_files`` row recompute needs."""

    part_kind: str
    part_key: str
    state: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class GroupDerived:
    """Recomputed group aggregates (doc contract row 1)."""

    state: GroupState
    validation_state: ValidationState
    actual_file_count: int
    coverage: dict[str, str]
    group_sha256: str | None


def compute_group_sha256(children: tuple[ChildFileFacts, ...]) -> str | None:
    """Deterministic group hash over child ``(part_kind, part_key, sha256, size)``.

    Canonical ordering (chosen + documented per the task): children are sorted by
    ``(part_kind, part_key)`` ascending, then serialized as a JSON array of
    ``[part_kind, part_key, sha256, size_bytes]`` with ``sort_keys`` and no
    whitespace, and SHA-256 hex'd. The archive body is never re-read (doc M3 /
    line 326/392). Returns ``None`` when there are no non-deleted children.
    """
    usable = [c for c in children if c.state not in {"hard_deleted", "soft_deleted"}]
    if not usable:
        return None
    ordered = sorted(usable, key=lambda c: (c.part_kind, c.part_key))
    payload = [
        [c.part_kind, c.part_key, c.sha256, c.size_bytes] for c in ordered
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MatchSetItemFacts:
    """Subset of an ``ops.source_match_set_items`` row for hash computation."""

    category: str
    source_file_group_id: str | None
    group_sha256: str | None
    effective_yyyymm: str | None
    omitted: bool
    omitted_reason: str | None


def compute_source_set_hash(items: tuple[MatchSetItemFacts, ...]) -> str:
    """Canonical ``source_set_hash`` over match-set items (doc line 764).

    Items are sorted by ``category`` ascending, then serialized as a JSON array
    of ``[category, source_file_group_id, group_sha256, effective_yyyymm,
    omitted, omitted_reason]`` (no whitespace, ``sort_keys``) and SHA-256 hex'd.
    Used to pre-compute the hash for ``restored_from_backup`` recovery *before*
    the ``revalidatable`` transition (M-A option 2).
    """
    ordered = sorted(items, key=lambda i: i.category)
    payload = [
        [
            i.category,
            i.source_file_group_id,
            i.group_sha256,
            i.effective_yyyymm,
            i.omitted,
            i.omitted_reason,
        ]
        for i in ordered
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def recompute_group_derived(
    *,
    group_kind: str,
    expected_part_keys: tuple[str, ...],
    children: tuple[ChildFileFacts, ...],
    structure_validation_state: ValidationState,
    structure_coverage: dict[str, str] | None = None,
) -> GroupDerived:
    """Recompute ``state``/``validation_state``/coverage/hash from child files.

    ``state`` is an aggregate of child states (doc line 342-343):

    * any child bad (missing/quarantined/delete_failed) → group takes the worst
      of those (missing < quarantined < delete_failed by severity here);
    * else if a required part is absent → ``missing``;
    * else ``available`` only when structure validation passed/warning;
    * a child still ``validating`` keeps the group ``validating``.
    """
    present_keys = {c.part_key for c in children if c.state not in {"hard_deleted"}}
    coverage: dict[str, str] = dict(structure_coverage or {})
    for key in expected_part_keys:
        coverage.setdefault(key, "present" if key in present_keys else "missing")

    actual = sum(1 for c in children if c.state not in {"hard_deleted", "soft_deleted"})
    group_sha256 = compute_group_sha256(children)

    # Worst child state wins for the down-propagation trigger.
    child_states = {c.state for c in children}
    state: GroupState
    if "delete_failed" in child_states:
        state = "delete_failed"
    elif "quarantined" in child_states:
        state = "quarantined"
    elif "missing" in child_states or any(k not in present_keys for k in expected_part_keys):
        state = "missing"
    elif "validating" in child_states or structure_validation_state == "running":
        state = "validating"
    elif structure_validation_state in {"passed", "warning"} and actual >= len(expected_part_keys):
        state = "available"
    else:
        state = "validating"

    return GroupDerived(
        state=state,
        validation_state=structure_validation_state,
        actual_file_count=actual,
        coverage=coverage,
        group_sha256=group_sha256,
    )


def group_is_bad(state: str) -> bool:
    return state in _BAD_GROUP_STATES


def group_is_available(state: str) -> bool:
    return state == "available"


# --- match-set propagation -------------------------------------------------


@dataclass(frozen=True)
class MatchSetFacts:
    """The subset of a referencing ``ops.source_match_sets`` row recompute needs."""

    source_match_set_id: str
    state: MatchSetState
    integrity_alert: bool = False
    #: True when *every* group this match set references is now ``available``
    #: (the up-propagation precondition for restored/invalid recovery).
    all_groups_available: bool = False
    #: Canonical hash precomputed by the service when recovering a
    #: ``restored_from_backup`` set (M-A option 2, doc line 816).
    recomputed_source_set_hash: str | None = None


@dataclass(frozen=True)
class MatchSetTransition:
    """A decided change to apply to one referencing match set.

    ``new_state`` of ``None`` means "keep state" (only flags/details change).
    The service is responsible for *not* doing the things the contract forbids:
    finalizing ``integrity_alert=false``, activating, or enqueuing rebuild
    (those belong to ``POST /validate`` / T-205).
    """

    source_match_set_id: str
    new_state: MatchSetState | None = None
    set_integrity_alert: bool | None = None
    set_source_set_hash: str | None = None
    integrity_alert_detail: dict[str, object] = field(default_factory=dict)
    reason: str = ""


def propagate_group_bad(
    match_set: MatchSetFacts,
    *,
    detail: dict[str, object] | None = None,
) -> MatchSetTransition | None:
    """DOWN propagation when a referenced group became bad (doc lines 343/809-812).

    * active            → keep ``active`` + ``integrity_alert=true`` (+detail)
    * non-active validated → ``invalid``
    * draft / restored_from_backup (pre-hash) → unchanged (return ``None``)
    * already invalid / revalidatable / retired → unchanged
    """
    detail = detail or {}
    if match_set.state == "active":
        return MatchSetTransition(
            source_match_set_id=match_set.source_match_set_id,
            set_integrity_alert=True,
            integrity_alert_detail=detail,
            reason="active match set source integrity loss",
        )
    if match_set.state == "validated":
        return MatchSetTransition(
            source_match_set_id=match_set.source_match_set_id,
            new_state="invalid",
            reason="validated match set referenced a bad group",
        )
    # draft / restored_from_backup / invalid / revalidatable / retired stay.
    return None


def propagate_group_recovered(
    match_set: MatchSetFacts,
) -> MatchSetTransition | None:
    """UP propagation when referenced groups returned to ``available``.

    * non-active ``invalid`` → ``revalidatable``
    * ``restored_from_backup`` (when all groups available) → compute canonical
      hash FIRST, then ``revalidatable`` (M-A option 2). The caller supplies the
      hash via ``recomputed_source_set_hash``.
    * active with ``integrity_alert`` → only mark a recovery *candidate*
      (``integrity_alert_detail.recovered=true``); do NOT clear the alert here.
    * everything else → unchanged.
    """
    if match_set.state == "invalid":
        return MatchSetTransition(
            source_match_set_id=match_set.source_match_set_id,
            new_state="revalidatable",
            reason="all referenced groups recovered",
        )
    if match_set.state == "restored_from_backup" and match_set.all_groups_available:
        if match_set.recomputed_source_set_hash is None:
            # Service must pre-compute the hash before this transition is legal
            # (CHECK requires NOT NULL once state leaves restored_from_backup).
            return None
        return MatchSetTransition(
            source_match_set_id=match_set.source_match_set_id,
            new_state="revalidatable",
            set_source_set_hash=match_set.recomputed_source_set_hash,
            reason="restored_from_backup objects reattached",
        )
    if match_set.state == "active" and match_set.integrity_alert and match_set.all_groups_available:
        return MatchSetTransition(
            source_match_set_id=match_set.source_match_set_id,
            integrity_alert_detail={"recovered": True},
            reason="active recovery candidate (clearing belongs to POST /validate)",
        )
    return None


def decide_match_set_transition(
    match_set: MatchSetFacts,
    *,
    group_state: str,
    detail: dict[str, object] | None = None,
) -> MatchSetTransition | None:
    """Single entry point: pick down vs up propagation from the group state."""
    if group_is_bad(group_state):
        return propagate_group_bad(match_set, detail=detail)
    if group_is_available(group_state):
        return propagate_group_recovered(match_set)
    return None
