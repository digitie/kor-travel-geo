"""T-204 RustFS reconciliation: pure decision-logic tests (DB-free).

Covers the highest-value surface in ``core.source_reconcile`` with synthetic
facts — no DB, no RustFS:

* issue classification across all 12 issue_types incl quick-vs-deep rehash skip
  and the rolling-deep force trigger;
* bucket-wide-loss propagation decision;
* the duplicate / active-정본 deletion guard;
* the read-after-write resolve-still-applies recheck;
* the capacity-preflight aggregation.

The DB/RustFS glue in ``infra.source_reconcile`` is exercised against fakes in
``test_t204_reconcile_service.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kortravelgeo.core.source_reconcile import (
    RECONCILE_ISSUE_TYPES,
    RESOLVE_ACTIONS,
    CategoryCapacity,
    DbFileFact,
    DuplicateObjectFact,
    ObjectHeadFact,
    ReResolveCheck,
    UnregisteredObjectFact,
    assess_bucket_loss,
    classify_db_file,
    classify_unregistered_object,
    compute_capacity_usage,
    decide_rehash,
    find_duplicate_object_groups,
    guard_object_deletion,
    issue_severity,
    mass_loss_issue_type,
    resolve_action_is_destructive,
    resolve_still_applies,
)

_NOW = datetime(2026, 6, 14, tzinfo=UTC)
_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _db(
    *,
    state: str = "available",
    sha256: str = _SHA_A,
    size: int = 1000,
    etag: str | None = "etag-a",
    last_etag: str | None = "etag-a",
    last_size: int | None = 1000,
    last_deep: datetime | None = None,
) -> DbFileFact:
    return DbFileFact(
        source_file_id="f1",
        source_file_group_id="g1",
        object_key="prefix/source-files/locsum_full/202604/g1/sess/archive/archive",
        state=state,
        sha256=sha256,
        size_bytes=size,
        object_etag=etag,
        last_verified_etag=last_etag,
        last_verified_size_bytes=last_size,
        last_verified_at=_NOW - timedelta(days=1),
        last_deep_verified_at=last_deep,
    )


# --- issue_type vocabulary ------------------------------------------------


def test_exactly_twelve_issue_types_match_the_doc() -> None:
    assert {
        "db_missing_object",
        "object_missing_db",
        "pending_registration",
        "registration_expired",
        "source_file_unavailable",
        "source_file_group_incomplete",
        "size_mismatch",
        "hash_mismatch",
        "etag_mismatch",
        "duplicate_object",
        "orphaned_multipart",
        "delete_failed",
    } == RECONCILE_ISSUE_TYPES
    assert len(RECONCILE_ISSUE_TYPES) == 12


def test_eight_resolve_actions_match_the_doc() -> None:
    assert {
        "mark_db_missing",
        "soft_delete_db_row",
        "restore_soft_deleted",
        "import_object",
        "delete_object",
        "extend_registration_deadline",
        "retry_delete_object",
        "update_hash_after_verify",
    } == RESOLVE_ACTIONS
    assert resolve_action_is_destructive("delete_object")
    assert resolve_action_is_destructive("retry_delete_object")
    assert not resolve_action_is_destructive("mark_db_missing")


# --- db_missing_object / delete_failed ------------------------------------


def test_live_db_row_with_absent_object_is_db_missing_object() -> None:
    decision = classify_db_file(
        _db(), ObjectHeadFact(present=False), mode="quick", now=_NOW
    )
    assert decision.issue_type == "db_missing_object"
    assert decision.severity == "error"


def test_soft_deleted_row_does_not_expect_an_object() -> None:
    decision = classify_db_file(
        _db(state="soft_deleted"),
        ObjectHeadFact(present=False),
        mode="quick",
        now=_NOW,
    )
    assert decision.issue_type is None


def test_delete_failed_state_with_object_still_present_is_delete_failed() -> None:
    decision = classify_db_file(
        _db(state="delete_failed"),
        ObjectHeadFact(present=True, size=1000, etag="etag-a"),
        mode="quick",
        now=_NOW,
    )
    assert decision.issue_type == "delete_failed"


# --- size / hash / etag mismatch ------------------------------------------


def test_size_mismatch_takes_precedence() -> None:
    decision = classify_db_file(
        _db(),
        ObjectHeadFact(present=True, size=2000, etag="etag-a", rehash_sha256=_SHA_A),
        mode="deep",
        now=_NOW,
    )
    assert decision.issue_type == "size_mismatch"


def test_hash_mismatch_only_when_a_real_rehash_digest_differs() -> None:
    # deep mode rehashes; digest differs → hash_mismatch.
    decision = classify_db_file(
        _db(),
        ObjectHeadFact(present=True, size=1000, etag="etag-a", rehash_sha256=_SHA_B),
        mode="deep",
        now=_NOW,
    )
    assert decision.issue_type == "hash_mismatch"
    assert decision.rehash_performed is True


def test_etag_only_difference_is_etag_mismatch_not_hash() -> None:
    decision = classify_db_file(
        _db(etag="etag-a"),
        ObjectHeadFact(present=True, size=1000, etag="etag-DIFFERENT", rehash_sha256=_SHA_A),
        mode="deep",
        now=_NOW,
    )
    assert decision.issue_type == "etag_mismatch"
    assert issue_severity("etag_mismatch") == "info"


def test_consistent_object_yields_no_issue() -> None:
    decision = classify_db_file(
        _db(),
        ObjectHeadFact(present=True, size=1000, etag="etag-a"),
        mode="quick",
        now=_NOW,
    )
    assert decision.issue_type is None


# --- quick vs deep rehash + rolling deep ----------------------------------


def test_quick_skips_rehash_when_size_and_etag_unchanged_within_window() -> None:
    db = _db(last_deep=_NOW - timedelta(days=1))
    head = ObjectHeadFact(present=True, size=1000, etag="etag-a")
    decision = decide_rehash(db, head, mode="quick", now=_NOW, rolling_deep_days=30)
    assert decision.rehash is False
    assert decision.reason == "unchanged_within_deep_window"


def test_quick_rehashes_when_size_changed() -> None:
    db = _db(last_size=1000)
    head = ObjectHeadFact(present=True, size=4096, etag="etag-a")
    decision = decide_rehash(db, head, mode="quick", now=_NOW)
    assert decision.rehash is True
    assert decision.reason == "size_or_etag_changed"


def test_quick_rehashes_when_etag_changed() -> None:
    db = _db(last_etag="etag-a")
    head = ObjectHeadFact(present=True, size=1000, etag="etag-z")
    decision = decide_rehash(db, head, mode="quick", now=_NOW)
    assert decision.rehash is True


def test_quick_rehashes_when_no_prior_verification() -> None:
    db = _db(last_etag=None, last_size=None)
    head = ObjectHeadFact(present=True, size=1000, etag="etag-a")
    decision = decide_rehash(db, head, mode="quick", now=_NOW)
    assert decision.rehash is True
    assert decision.reason == "no_prior_verification"


def test_rolling_deep_forces_rehash_when_deep_window_elapsed() -> None:
    db = _db(last_deep=_NOW - timedelta(days=45))
    head = ObjectHeadFact(present=True, size=1000, etag="etag-a")
    decision = decide_rehash(db, head, mode="quick", now=_NOW, rolling_deep_days=30)
    assert decision.rehash is True
    assert decision.reason == "rolling_deep_window_elapsed"


def test_quick_forces_rehash_when_never_deep_verified() -> None:
    db = _db(last_deep=None)
    head = ObjectHeadFact(present=True, size=1000, etag="etag-a")
    decision = decide_rehash(db, head, mode="quick", now=_NOW)
    assert decision.rehash is True
    assert decision.reason == "never_deep_verified"


def test_deep_always_rehashes_a_present_object() -> None:
    db = _db(last_deep=_NOW)
    head = ObjectHeadFact(present=True, size=1000, etag="etag-a")
    decision = decide_rehash(db, head, mode="deep", now=_NOW)
    assert decision.rehash is True
    assert decision.reason == "deep_mode"


def test_quick_skip_means_no_hash_mismatch_even_if_body_corrupt() -> None:
    # Quick skips rehash for an unchanged size/etag within the deep window, so a
    # silently-corrupt-but-same-metadata object is NOT flagged this pass — that is
    # exactly why the rolling-deep window exists. head has no rehash digest.
    db = _db(last_deep=_NOW - timedelta(days=1))
    decision = classify_db_file(
        db,
        ObjectHeadFact(present=True, size=1000, etag="etag-a", rehash_sha256=None),
        mode="quick",
        now=_NOW,
    )
    assert decision.issue_type is None
    assert decision.rehash_performed is False


# --- unregistered object family -------------------------------------------


def test_unregistered_with_live_session_before_deadline_is_pending_registration() -> None:
    decision = classify_unregistered_object(
        UnregisteredObjectFact(
            object_key="k", has_live_session=True, past_registration_deadline=False
        )
    )
    assert decision.issue_type == "pending_registration"
    assert decision.severity == "info"


def test_unregistered_past_deadline_is_registration_expired() -> None:
    decision = classify_unregistered_object(
        UnregisteredObjectFact(
            object_key="k", has_live_session=True, past_registration_deadline=True
        )
    )
    assert decision.issue_type == "registration_expired"


def test_unregistered_with_no_session_is_object_missing_db() -> None:
    decision = classify_unregistered_object(UnregisteredObjectFact(object_key="k"))
    assert decision.issue_type == "object_missing_db"


# --- bucket-wide / prefix mass loss ---------------------------------------


def test_mass_loss_declared_when_ratio_exceeded_above_floor() -> None:
    assessment = assess_bucket_loss(scanned_live_files=10, missing_files=10)
    assert assessment.is_mass_loss is True


def test_mass_loss_not_declared_for_a_single_missing_among_many() -> None:
    assessment = assess_bucket_loss(scanned_live_files=10, missing_files=1)
    assert assessment.is_mass_loss is False


def test_mass_loss_not_declared_below_min_files_floor() -> None:
    # One missing of one file is 100% but below the min-files floor → not mass.
    assessment = assess_bucket_loss(scanned_live_files=1, missing_files=1)
    assert assessment.is_mass_loss is False
    assert assessment.reason == "below_min_files"


def test_mass_loss_issue_type_split_manifest_stub_vs_vanished_object() -> None:
    assert mass_loss_issue_type(present_in_registry_only=True) == "source_file_unavailable"
    assert mass_loss_issue_type(present_in_registry_only=False) == "db_missing_object"


# --- duplicate object detection -------------------------------------------


def test_duplicate_object_groups_same_digest_across_keys() -> None:
    facts = (
        DuplicateObjectFact(source_file_id="a", object_key="k1", sha256=_SHA_A, size_bytes=10),
        DuplicateObjectFact(source_file_id="b", object_key="k2", sha256=_SHA_A, size_bytes=10),
        DuplicateObjectFact(source_file_id="c", object_key="k3", sha256=_SHA_B, size_bytes=10),
    )
    groups = find_duplicate_object_groups(facts)
    assert len(groups) == 1
    assert {m.object_key for m in groups[0]} == {"k1", "k2"}


def test_no_duplicate_for_single_key_or_distinct_digests() -> None:
    facts = (
        DuplicateObjectFact(source_file_id="a", object_key="k1", sha256=_SHA_A, size_bytes=10),
        DuplicateObjectFact(source_file_id="b", object_key="k2", sha256=_SHA_B, size_bytes=10),
    )
    assert find_duplicate_object_groups(facts) == ()


# --- resolve guards -------------------------------------------------------


def test_deletion_guard_blocks_object_an_active_match_set_references() -> None:
    guard = guard_object_deletion(
        object_key="canonical",
        active_match_set_group_object_keys=frozenset({"canonical"}),
        referenced_match_set_ids=("ms-active",),
    )
    assert guard.allowed is False
    assert guard.blocking_match_set_ids == ("ms-active",)


def test_deletion_guard_allows_object_not_referenced_by_any_active_set() -> None:
    guard = guard_object_deletion(
        object_key="dup-2",
        active_match_set_group_object_keys=frozenset({"canonical"}),
    )
    assert guard.allowed is True


def test_resolve_recheck_rejects_import_when_object_vanished() -> None:
    guard = resolve_still_applies(
        action="import_object",
        recheck=ReResolveCheck(db_row_present=False, object_present=False),
    )
    assert guard.allowed is False


def test_resolve_recheck_rejects_import_when_db_row_now_exists() -> None:
    guard = resolve_still_applies(
        action="import_object",
        recheck=ReResolveCheck(db_row_present=True, object_present=True),
    )
    assert guard.allowed is False


def test_resolve_recheck_rejects_mark_missing_when_object_reappeared() -> None:
    guard = resolve_still_applies(
        action="mark_db_missing",
        recheck=ReResolveCheck(db_row_present=True, object_present=True),
    )
    assert guard.allowed is False


def test_resolve_recheck_allows_delete_when_object_present() -> None:
    guard = resolve_still_applies(
        action="delete_object",
        recheck=ReResolveCheck(db_row_present=True, object_present=True),
    )
    assert guard.allowed is True


# --- capacity preflight ---------------------------------------------------


def test_capacity_aggregates_per_category_and_over_threshold() -> None:
    usage = compute_capacity_usage(
        (
            CategoryCapacity(
                category="locsum_full",
                object_count=2,
                total_bytes=600,
                quarantined_bytes=100,
            ),
            CategoryCapacity(
                category="navi_full", object_count=1, total_bytes=300, soft_deleted_bytes=50
            ),
        ),
        unregistered_bytes=100,
        capacity_limit_bytes=1000,
        threshold_ratio=0.9,
    )
    assert usage.total_object_count == 3
    assert usage.total_bytes == 900
    assert usage.unregistered_bytes == 100
    assert usage.quarantined_bytes == 100
    assert usage.soft_deleted_bytes == 50
    # 900 registry + 100 unregistered = 1000 >= 0.9 * 1000 → over threshold.
    assert usage.over_threshold is True
    # categories are sorted by code.
    assert [c.category for c in usage.categories] == ["locsum_full", "navi_full"]


def test_capacity_not_over_threshold_when_no_limit() -> None:
    usage = compute_capacity_usage(
        (CategoryCapacity(category="locsum_full", object_count=1, total_bytes=10),),
    )
    assert usage.over_threshold is False
    assert usage.capacity_limit_bytes is None
