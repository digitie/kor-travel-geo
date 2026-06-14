"""T-212 RustFS source archive retention/cleanup: pure decisions + ADR (DB-free).

Covers the highest-value surface the retention policy (ADR-052) adds on top of
T-204/T-203c/T-211, with synthetic facts — no DB, no RustFS:

* bulk hard-delete eligibility: active-정본 is NEVER deletable (reuses the T-204
  guard rule), ``soft_deleted``/``quarantined`` registered files and unregistered
  stored objects (``object_missing_db``/``registration_expired``) ARE eligible,
  and a live ``available``/``validating``/``missing`` archive is NOT (registered
  archives are not bulk/auto-deleted);
* the typed-confirmation token;
* the pre-delete manifest/export safety gate (manifest present OR explicit ack);
* the retention recommendation derived from capacity usage;
* the ADR-052 presence in ``docs/decisions.md``.

The DB/RustFS glue in ``infra.source_reconcile.bulk_hard_delete_sources`` is the
thin wrapper around these decisions.
"""

from __future__ import annotations

from pathlib import Path

from kortravelgeo.core.source_reconcile import (
    HARD_DELETE_CONFIRMATION,
    BulkHardDeletePlan,
    CapacityUsage,
    CategoryCapacity,
    HardDeleteCandidateFact,
    assess_hard_delete_candidate,
    build_retention_recommendation,
    bulk_hard_delete_confirmation,
    check_pre_delete_safety,
    compute_capacity_usage,
    plan_bulk_hard_delete,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


# --- eligibility (the core guard rule) -------------------------------------


def test_active_referenced_object_is_never_eligible() -> None:
    """Reuses the T-204 active-정본 guard: a live-referenced object is blocked."""
    verdict = assess_hard_delete_candidate(
        HardDeleteCandidateFact(
            object_key="k1",
            source_file_id="f1",
            state="soft_deleted",  # otherwise eligible …
            active_referenced=True,  # … but active match set references it.
        )
    )
    assert verdict.eligible is False
    assert "active match set" in verdict.reason


def test_soft_deleted_and_quarantined_are_eligible() -> None:
    for state in ("soft_deleted", "quarantined"):
        verdict = assess_hard_delete_candidate(
            HardDeleteCandidateFact(
                object_key=f"k-{state}", source_file_id="f", state=state
            )
        )
        assert verdict.eligible is True, state


def test_unregistered_stored_objects_are_eligible() -> None:
    for issue in ("object_missing_db", "registration_expired"):
        verdict = assess_hard_delete_candidate(
            HardDeleteCandidateFact(
                object_key=f"k-{issue}", source_file_id=None, state=None, issue_type=issue
            )
        )
        assert verdict.eligible is True, issue


def test_live_registered_archive_is_not_eligible() -> None:
    """available/validating/missing registered archives are never bulk-deleted."""
    for state in ("available", "validating", "missing"):
        verdict = assess_hard_delete_candidate(
            HardDeleteCandidateFact(
                object_key=f"k-{state}", source_file_id="f", state=state
            )
        )
        assert verdict.eligible is False, state
        assert "자동/일괄 삭제하지 않습니다" in verdict.reason


def test_pending_registration_unregistered_is_not_eligible() -> None:
    """A still-pending (not expired) stored object is not yet a cleanup target."""
    verdict = assess_hard_delete_candidate(
        HardDeleteCandidateFact(
            object_key="k", source_file_id=None, state=None, issue_type="pending_registration"
        )
    )
    assert verdict.eligible is False


def test_plan_partitions_and_is_deterministic() -> None:
    facts = (
        HardDeleteCandidateFact(object_key="b", source_file_id="fb", state="quarantined"),
        HardDeleteCandidateFact(
            object_key="a", source_file_id="fa", state="soft_deleted"
        ),
        HardDeleteCandidateFact(
            object_key="c", source_file_id="fc", state="available"
        ),  # skipped
        HardDeleteCandidateFact(
            object_key="d", source_file_id="fd", state="soft_deleted", active_referenced=True
        ),  # skipped (active 정본)
    )
    plan: BulkHardDeletePlan = plan_bulk_hard_delete(facts)
    assert [e.object_key for e in plan.eligible] == ["a", "b"]  # sorted
    assert plan.eligible_count == 2
    assert {s.object_key for s in plan.skipped} == {"c", "d"}
    assert plan.skipped_count == 2


# --- typed confirmation ----------------------------------------------------


def test_confirmation_token() -> None:
    assert bulk_hard_delete_confirmation() == HARD_DELETE_CONFIRMATION
    assert HARD_DELETE_CONFIRMATION == "HARD-DELETE-SOURCES"


# --- pre-delete safety gate ------------------------------------------------


def test_pre_delete_safety_requires_manifest_or_ack() -> None:
    # No manifest, no ack → refused.
    refused = check_pre_delete_safety(backup_manifest_present=False, manifest_ack=False)
    assert refused.allowed is False
    assert "manifest" in refused.reason.lower()
    # Manifest present → allowed (even without ack).
    assert check_pre_delete_safety(
        backup_manifest_present=True, manifest_ack=False
    ).allowed
    # Explicit ack → allowed even without a manifest.
    assert check_pre_delete_safety(
        backup_manifest_present=False, manifest_ack=True
    ).allowed


# --- retention recommendation (capacity surfacing) -------------------------


def _usage(*, limit: int | None, total: int, soft: int, quar: int, unreg: int) -> CapacityUsage:
    return compute_capacity_usage(
        (
            CategoryCapacity(
                category="locsum_full",
                object_count=1,
                total_bytes=total,
                quarantined_bytes=quar,
                soft_deleted_bytes=soft,
            ),
        ),
        unregistered_bytes=unreg,
        capacity_limit_bytes=limit,
    )


def test_retention_reclaimable_excludes_live_archives() -> None:
    usage = _usage(limit=None, total=1000, soft=200, quar=50, unreg=30)
    rec = build_retention_recommendation(usage, eligible_object_count=4)
    assert rec.reclaimable_bytes == 200 + 50 + 30
    assert rec.over_threshold is False
    assert rec.eligible_object_count == 4
    assert "정리" in rec.guidance


def test_retention_over_threshold_is_advisory_only() -> None:
    # total (1000) + unregistered (30) >= limit (1000) → over threshold.
    usage = _usage(limit=1000, total=1000, soft=100, quar=0, unreg=30)
    rec = build_retention_recommendation(usage, eligible_object_count=2)
    assert usage.over_threshold is True
    assert rec.over_threshold is True
    assert "자동 삭제하지 않습니다" in rec.guidance  # never auto-delete


def test_retention_nothing_to_clean() -> None:
    usage = _usage(limit=None, total=1000, soft=0, quar=0, unreg=0)
    rec = build_retention_recommendation(usage)
    assert rec.reclaimable_bytes == 0
    assert "없음" in rec.guidance


# --- ADR presence ----------------------------------------------------------


def test_adr_052_retention_policy_documented() -> None:
    decisions = (_REPO_ROOT / "docs" / "decisions.md").read_text(encoding="utf-8")
    assert "ADR-052" in decisions
    # The core policy statement: registered archives are never auto-deleted.
    assert "등록 완료 원천 archive 자동 삭제 금지" in decisions
    # The typed-confirmation token and the only-auto-cleanup carve-out.
    assert "HARD-DELETE-SOURCES" in decisions
