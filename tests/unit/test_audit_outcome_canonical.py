"""record_audit_event normalizes non-canonical outcomes onto the ops.audit_events CHECK set.

Regression (T-290g): handlers historically passed resource states / action names into the
untyped ``record_audit_event(outcome=...)`` (e.g. a source-file state, ``"conflict"``,
``"created"``). Those are outside the CHECK set (started/succeeded/failed/cancelled/denied),
so the audit INSERT raised a constraint violation → 500 (first surfaced by a restore dry-run
that recorded ``outcome="blocked"``). ``canonical_audit_outcome`` collapses each known alias
onto a lifecycle outcome; unknowns fall back to ``"succeeded"``.
"""

from __future__ import annotations

import pytest

from kortravelgeo.infra.admin_repo import (
    _AUDIT_OUTCOME_ALIASES,
    _CANONICAL_AUDIT_OUTCOMES,
    canonical_audit_outcome,
)


@pytest.mark.parametrize("value", ["started", "succeeded", "failed", "cancelled", "denied"])
def test_canonical_outcomes_pass_through(value: str) -> None:
    assert canonical_audit_outcome(value) == value


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("conflict", "denied"),
        ("created", "succeeded"),
        ("registered", "succeeded"),
        # cache invalidation SUCCEEDED — must not be confused with the 'invalid' failure state
        ("invalidated", "succeeded"),
        ("invalid", "failed"),
        ("quarantined", "failed"),
        ("missing", "failed"),
        ("delete_failed", "failed"),
        ("reconstruct_unavailable", "failed"),
        ("integrity_gate_failed", "failed"),
        ("passed", "succeeded"),
        ("active", "succeeded"),
        ("legacy_estimate", "succeeded"),
        ("running", "started"),
    ],
)
def test_aliases_map_to_canonical(alias: str, expected: str) -> None:
    assert canonical_audit_outcome(alias) == expected


def test_unknown_value_falls_back_to_succeeded() -> None:
    assert canonical_audit_outcome("something_brand_new") == "succeeded"


def test_every_alias_target_is_canonical() -> None:
    # guards against a typo in the alias table producing another invalid outcome
    for target in _AUDIT_OUTCOME_ALIASES.values():
        assert target in _CANONICAL_AUDIT_OUTCOMES
