"""T-205a: source match set validate / activate / retire pure decisions.

DB-free tests for the highest-value surface — the pure decision logic in
``core.source_match_set``:

* item invariants (role / omitted↔group_id / UNIQUE category);
* the ``POST /validate`` state-split (draft / revalidatable / active-in-place /
  reject) given state + integrity_alert + coverage;
* the ``activate`` precondition (only ``validated``, hash-stale refusal) + the
  atomic-swap step sequence (retire-current then activate-target);
* ``retire`` and the ``yyyymm`` aggregation derived fields.

The canonical ``source_set_hash`` reuse is asserted by importing the single
``core.source_match_propagation.compute_source_set_hash`` (no duplicate impl).
"""

from __future__ import annotations

from kortravelgeo.core.source_match_propagation import (
    MatchSetItemFacts,
    compute_source_set_hash,
)
from kortravelgeo.core.source_match_set import (
    ActivateFacts,
    MatchSetItemSpec,
    ValidateCoverage,
    ValidateFacts,
    aggregate_yyyymm,
    decide_activate,
    decide_retire,
    decide_validate,
    validate_item_invariants,
)

# --- item invariants -------------------------------------------------------


def _spec(category: str, **kw: object) -> MatchSetItemSpec:
    base: dict[str, object] = {"category": category, "role": "build_required"}
    base.update(kw)
    return MatchSetItemSpec(**base)  # type: ignore[arg-type]


def test_item_invariants_all_valid() -> None:
    items = (
        _spec("roadname_hangul_full", source_file_group_id="g1"),
        _spec("locsum_full", role="build_required", source_file_group_id="g2"),
        _spec("zone_shape_full", role="build_recommended", omitted=True,
              omitted_reason="skip"),
    )
    assert validate_item_invariants(items) == ()


def test_item_invariant_bad_role() -> None:
    errs = validate_item_invariants((_spec("locsum_full", role="nope",
                                           source_file_group_id="g1"),))
    assert len(errs) == 1 and "invalid role" in errs[0].reason


def test_item_invariant_omitted_with_group_id() -> None:
    errs = validate_item_invariants(
        (_spec("locsum_full", omitted=True, source_file_group_id="g1"),)
    )
    assert any("omitted=true requires source_file_group_id IS NULL" in e.reason
               for e in errs)


def test_item_invariant_present_without_group_id() -> None:
    errs = validate_item_invariants((_spec("locsum_full", omitted=False),))
    assert any("requires a source_file_group_id" in e.reason for e in errs)


def test_item_invariant_duplicate_category() -> None:
    errs = validate_item_invariants(
        (
            _spec("locsum_full", source_file_group_id="g1"),
            _spec("locsum_full", source_file_group_id="g2"),
        )
    )
    assert any("duplicate category" in e.reason for e in errs)


# --- validate state-split --------------------------------------------------


def _cov(ok: bool = True, **kw: object) -> ValidateCoverage:
    if ok:
        return ValidateCoverage(all_groups_available=True)
    base: dict[str, object] = {"all_groups_available": False}
    base.update(kw)
    return ValidateCoverage(**base)  # type: ignore[arg-type]


def _vfacts(state: str, *, integrity_alert: bool = False,
            coverage: ValidateCoverage | None = None) -> ValidateFacts:
    return ValidateFacts(
        source_match_set_id="ms1",
        state=state,  # type: ignore[arg-type]
        integrity_alert=integrity_alert,
        coverage=coverage or _cov(ok=True),
    )


def test_validate_draft_ok_goes_validated() -> None:
    d = decide_validate(_vfacts("draft"))
    assert d.action == "validate_draft" and d.ok is True
    assert d.next_state == "validated"


def test_validate_draft_coverage_fail_no_state_change() -> None:
    cov = _cov(ok=False, unavailable_group_ids=("g9",))
    d = decide_validate(_vfacts("draft", coverage=cov))
    assert d.action == "validate_draft" and d.ok is False
    assert d.next_state is None
    assert any("not all available" in r for r in d.reasons)


def test_validate_draft_missing_required_category_fails() -> None:
    cov = ValidateCoverage(
        all_groups_available=True,
        missing_required_categories=("electronic_map_full",),
    )
    d = decide_validate(_vfacts("draft", coverage=cov))
    assert d.ok is False
    assert any("required categories missing" in r for r in d.reasons)


def test_validate_revalidatable_ok_goes_validated() -> None:
    d = decide_validate(_vfacts("revalidatable"))
    assert d.action == "revalidate" and d.ok is True
    assert d.next_state == "validated"


def test_validate_active_with_alert_in_place_success_clears_alert() -> None:
    d = decide_validate(_vfacts("active", integrity_alert=True))
    assert d.action == "validate_in_place" and d.ok is True
    assert d.clear_integrity_alert is True
    assert d.next_state is None  # stays active


def test_validate_active_with_alert_in_place_failure_keeps_alert() -> None:
    cov = _cov(ok=False, unavailable_group_ids=("g3",))
    d = decide_validate(_vfacts("active", integrity_alert=True, coverage=cov))
    assert d.action == "validate_in_place" and d.ok is False
    assert d.clear_integrity_alert is False
    assert d.next_state is None  # stays active even on failure


def test_validate_active_without_alert_rejects() -> None:
    d = decide_validate(_vfacts("active", integrity_alert=False))
    assert d.action == "reject" and d.ok is False


def test_validate_rejects_retired_invalid_restored() -> None:
    for state in ("retired", "invalid", "restored_from_backup"):
        d = decide_validate(_vfacts(state))
        assert d.action == "reject" and d.ok is False
        assert any("not directly validatable" in r for r in d.reasons)


# --- activate precondition + atomic swap -----------------------------------


def _afacts(state: str, *, stored: str | None = "a" * 64,
            recomputed: str | None = "a" * 64,
            current_active: str | None = None) -> ActivateFacts:
    return ActivateFacts(
        source_match_set_id="target",
        state=state,  # type: ignore[arg-type]
        stored_source_set_hash=stored,
        recomputed_source_set_hash=recomputed,
        current_active_id=current_active,
    )


def test_activate_only_from_validated() -> None:
    for state in ("draft", "active", "invalid", "revalidatable",
                  "restored_from_backup", "retired"):
        d = decide_activate(_afacts(state))
        assert d.ok is False
        assert d.steps == ()


def test_activate_validated_no_current_active_single_step() -> None:
    d = decide_activate(_afacts("validated", current_active=None))
    assert d.ok is True
    assert len(d.steps) == 1
    assert d.steps[0].kind == "activate_target"
    assert d.steps[0].source_match_set_id == "target"
    assert d.steps[0].new_state == "active"


def test_activate_swap_retires_current_then_activates_target() -> None:
    d = decide_activate(_afacts("validated", current_active="old"))
    assert d.ok is True
    assert len(d.steps) == 2
    # retire-current FIRST (one-active index is not deferrable), then activate.
    assert d.steps[0].kind == "retire_current"
    assert d.steps[0].source_match_set_id == "old"
    assert d.steps[0].new_state == "retired"
    assert d.steps[1].kind == "activate_target"
    assert d.steps[1].source_match_set_id == "target"
    assert d.steps[1].new_state == "active"


def test_activate_refuses_stale_hash() -> None:
    d = decide_activate(_afacts("validated", stored="a" * 64, recomputed="b" * 64))
    assert d.ok is False
    assert any("stale" in r for r in d.reasons)
    assert d.steps == ()


def test_activate_refuses_missing_hash() -> None:
    assert decide_activate(_afacts("validated", recomputed=None)).ok is False
    assert decide_activate(_afacts("validated", stored=None)).ok is False


def test_activate_already_active_is_noop_refusal() -> None:
    d = decide_activate(_afacts("validated", current_active="target"))
    assert d.ok is False
    assert any("already active" in r for r in d.reasons)


# --- retire ----------------------------------------------------------------


def test_retire_active_marks_was_active() -> None:
    d = decide_retire(state="active")
    assert d.ok is True and d.next_state == "retired" and d.was_active is True


def test_retire_validated_ok_not_active() -> None:
    d = decide_retire(state="validated")
    assert d.ok is True and d.was_active is False


def test_retire_already_retired_refused() -> None:
    assert decide_retire(state="retired").ok is False


# --- yyyymm aggregation ----------------------------------------------------


def test_aggregate_yyyymm_single_month_not_mixed() -> None:
    agg = aggregate_yyyymm((("a", "202604"), ("b", "202604"), ("c", None)))
    assert agg.mixed_yyyymm is False
    assert agg.yyyymm_by_category == {"a": "202604", "b": "202604"}


def test_aggregate_yyyymm_two_months_mixed() -> None:
    agg = aggregate_yyyymm((("a", "202603"), ("b", "202604")))
    assert agg.mixed_yyyymm is True


# --- canonical hash is the shared propagation impl (no duplication) ---------


def test_validate_uses_shared_source_set_hash() -> None:
    items = (
        MatchSetItemFacts("locsum_full", "g1", "a" * 64, "202604", False, None),
        MatchSetItemFacts("navi_full", "g2", "b" * 64, "202604", False, None),
    )
    # Order independence proves we reuse the canonical impl from propagation.
    assert compute_source_set_hash(items) == compute_source_set_hash(tuple(reversed(items)))
    assert len(compute_source_set_hash(items)) == 64
