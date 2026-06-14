"""T-205b: rebuild-db + rollback pure decisions (DB-free).

DB-free tests for the highest-value surface — the pure decision logic in
``core.source_rebuild`` that the rebuild-db loader bridge + rollback swap glue
in ``infra.source_rebuild_service`` consumes:

* the forced_promotion / consistency-ERROR gate (ADR-049 #13): which gate blocks
  and whether ``forced_promotion`` is allowed — covering ERROR+forced→allow only
  when source ok, ERROR+forced+source-mismatch→still blocked, integrity_alert
  +forced→blocked, normal OK→promote;
* the pre-load source-archive integrity gate (mismatch → quarantine+fail, ok →
  proceed);
* the rollback target resolution (FK → swap; legacy → estimate-only) and the
  pre-rollback ``integrity_alert`` recompute;
* stale running-job detection (heartbeat timeout → force-fail, live → block).
"""

from __future__ import annotations

from kortravelgeo.core.source_rebuild import (
    GroupArchiveCheck,
    PromotionFacts,
    RebuildStartFacts,
    RollbackIntegrityFacts,
    RollbackTargetFacts,
    RunningJobFacts,
    decide_integrity_gate,
    decide_promotion,
    decide_rebuild_start,
    decide_rollback_target,
    decide_stale_jobs,
    recompute_rollback_integrity_alert,
)

# --- pre-load integrity gate ----------------------------------------------


def _ok_check(gid: str = "g1", category: str = "locsum_full") -> GroupArchiveCheck:
    return GroupArchiveCheck(
        source_file_group_id=gid,
        category=category,
        group_state="available",
        all_objects_present=True,
        sha256_ok=True,
        size_ok=True,
        group_sha256_ok=True,
    )


def test_integrity_gate_all_ok_proceeds() -> None:
    decision = decide_integrity_gate((_ok_check("g1"), _ok_check("g2", "navi_full")))
    assert decision.ok is True
    assert decision.failed_group_ids == ()


def test_integrity_gate_sha_mismatch_quarantines_and_fails() -> None:
    bad = GroupArchiveCheck(
        source_file_group_id="g2",
        category="navi_full",
        group_state="available",
        all_objects_present=True,
        sha256_ok=False,
        size_ok=True,
        group_sha256_ok=False,
    )
    decision = decide_integrity_gate((_ok_check("g1"), bad))
    assert decision.ok is False
    assert decision.failed_group_ids == ("g2",)
    assert any("sha256 mismatch" in r for r in decision.reasons)


def test_integrity_gate_missing_object_fails() -> None:
    bad = GroupArchiveCheck(
        source_file_group_id="g3",
        category="roadname_hangul_full",
        group_state="available",
        all_objects_present=False,
        sha256_ok=True,
        size_ok=True,
        group_sha256_ok=True,
    )
    decision = decide_integrity_gate((bad,))
    assert decision.ok is False
    assert decision.failed_group_ids == ("g3",)


def test_integrity_gate_group_not_available_fails() -> None:
    bad = GroupArchiveCheck(
        source_file_group_id="g4",
        category="locsum_full",
        group_state="quarantined",
        all_objects_present=True,
        sha256_ok=True,
        size_ok=True,
        group_sha256_ok=True,
    )
    decision = decide_integrity_gate((bad,))
    assert decision.ok is False and decision.failed_group_ids == ("g4",)


# --- forced_promotion / consistency ERROR gate -----------------------------


def _facts(**kw: object) -> PromotionFacts:
    base: dict[str, object] = {
        "consistency_severity": "OK",
        "source_integrity_ok": True,
        "all_groups_available": True,
        "match_set_integrity_alert": False,
    }
    base.update(kw)
    return PromotionFacts(**base)  # type: ignore[arg-type]


def test_promotion_normal_ok_auto_promotes() -> None:
    d = decide_promotion(_facts(consistency_severity="OK"))
    assert d.allow is True and d.forced_promotion is False and d.blocker is None


def test_promotion_warn_auto_promotes() -> None:
    assert decide_promotion(_facts(consistency_severity="WARN")).allow is True


def test_promotion_error_without_force_blocked() -> None:
    d = decide_promotion(_facts(consistency_severity="ERROR"))
    assert d.allow is False and d.blocker == "consistency_error"


def test_promotion_error_forced_authorized_allows() -> None:
    d = decide_promotion(
        _facts(
            consistency_severity="ERROR",
            forced=True,
            has_destructive_admin=True,
            typed_confirmation_ok=True,
        )
    )
    assert d.allow is True and d.forced_promotion is True and d.blocker is None


def test_promotion_error_forced_without_role_blocked() -> None:
    d = decide_promotion(
        _facts(
            consistency_severity="ERROR",
            forced=True,
            has_destructive_admin=False,
            typed_confirmation_ok=True,
        )
    )
    assert d.allow is False and d.blocker == "forced_promotion_unauthorized"


def test_promotion_error_forced_without_confirmation_blocked() -> None:
    d = decide_promotion(
        _facts(
            consistency_severity="ERROR",
            forced=True,
            has_destructive_admin=True,
            typed_confirmation_ok=False,
        )
    )
    assert d.allow is False and d.blocker == "forced_promotion_unauthorized"


def test_promotion_source_mismatch_never_bypassed_by_force() -> None:
    # ERROR + forced + authorized BUT source integrity failed → still blocked.
    d = decide_promotion(
        _facts(
            consistency_severity="ERROR",
            source_integrity_ok=False,
            forced=True,
            has_destructive_admin=True,
            typed_confirmation_ok=True,
        )
    )
    assert d.allow is False and d.blocker == "source_integrity"
    assert d.forced_promotion is False


def test_promotion_integrity_alert_never_bypassed_by_force() -> None:
    d = decide_promotion(
        _facts(
            consistency_severity="ERROR",
            match_set_integrity_alert=True,
            forced=True,
            has_destructive_admin=True,
            typed_confirmation_ok=True,
        )
    )
    assert d.allow is False and d.blocker == "match_set_integrity_alert"


def test_promotion_group_unavailable_never_bypassed_by_force() -> None:
    d = decide_promotion(
        _facts(
            consistency_severity="ERROR",
            all_groups_available=False,
            forced=True,
            has_destructive_admin=True,
            typed_confirmation_ok=True,
        )
    )
    assert d.allow is False and d.blocker == "group_unavailable"


def test_promotion_source_integrity_precedes_consistency_when_clean_consistency() -> None:
    # Even with OK consistency, a source mismatch blocks (defensive ordering).
    d = decide_promotion(_facts(consistency_severity="OK", source_integrity_ok=False))
    assert d.allow is False and d.blocker == "source_integrity"


# --- rebuild start precondition --------------------------------------------


def test_rebuild_start_validated_ok() -> None:
    d = decide_rebuild_start(
        RebuildStartFacts(
            state="validated",
            integrity_alert=False,
            source_set_hash="a" * 64,
            all_groups_available=True,
        )
    )
    assert d.ok is True


def test_rebuild_start_integrity_alert_blocks() -> None:
    d = decide_rebuild_start(
        RebuildStartFacts(
            state="active",
            integrity_alert=True,
            source_set_hash="a" * 64,
            all_groups_available=True,
        )
    )
    assert d.ok is False and any("integrity_alert" in r for r in d.reasons)


def test_rebuild_start_draft_blocks() -> None:
    d = decide_rebuild_start(
        RebuildStartFacts(
            state="draft",
            integrity_alert=False,
            source_set_hash=None,
            all_groups_available=False,
        )
    )
    assert d.ok is False


# --- stale running-job detection -------------------------------------------


def test_stale_job_past_heartbeat_is_failed() -> None:
    d = decide_stale_jobs(
        (
            RunningJobFacts(job_id="j1", state="running", seconds_since_heartbeat=2000.0),
        ),
        heartbeat_timeout_s=900.0,
    )
    assert d.stale_job_ids == ("j1",) and d.live_blocking_job_id is None


def test_stale_job_never_heartbeated_is_failed() -> None:
    d = decide_stale_jobs(
        (RunningJobFacts(job_id="j1", state="running", seconds_since_heartbeat=None),),
        heartbeat_timeout_s=900.0,
    )
    assert d.stale_job_ids == ("j1",)


def test_live_job_blocks_new_rebuild() -> None:
    d = decide_stale_jobs(
        (RunningJobFacts(job_id="j2", state="running", seconds_since_heartbeat=10.0),),
        heartbeat_timeout_s=900.0,
    )
    assert d.stale_job_ids == () and d.live_blocking_job_id == "j2"


def test_non_running_jobs_ignored() -> None:
    d = decide_stale_jobs(
        (RunningJobFacts(job_id="j3", state="done", seconds_since_heartbeat=5.0),),
        heartbeat_timeout_s=900.0,
    )
    assert d.stale_job_ids == () and d.live_blocking_job_id is None


# --- rollback target resolution --------------------------------------------


def test_rollback_with_fk_swaps_match_set() -> None:
    d = decide_rollback_target(
        RollbackTargetFacts(
            release_id="r1",
            snapshot_id="s1",
            release_state="superseded",
            target_source_match_set_id="ms_target",
            current_active_match_set_id="ms_current",
        )
    )
    assert d.ok is True and d.mode == "match_set_swap"
    assert d.activate_match_set_id == "ms_target"
    assert d.retire_match_set_id == "ms_current"


def test_rollback_with_fk_same_active_no_retire() -> None:
    d = decide_rollback_target(
        RollbackTargetFacts(
            release_id="r1",
            snapshot_id="s1",
            release_state="active",
            target_source_match_set_id="ms_target",
            current_active_match_set_id="ms_target",
        )
    )
    assert d.mode == "match_set_swap" and d.retire_match_set_id is None


def test_rollback_legacy_no_fk_is_estimate_only() -> None:
    d = decide_rollback_target(
        RollbackTargetFacts(
            release_id="r1",
            snapshot_id="s1",
            release_state="superseded",
            target_source_match_set_id=None,
            current_active_match_set_id="ms_current",
        )
    )
    assert d.ok is True and d.mode == "legacy_estimate"
    assert d.activate_match_set_id is None and d.retire_match_set_id is None


def test_rollback_failed_release_refused() -> None:
    d = decide_rollback_target(
        RollbackTargetFacts(
            release_id="r1",
            snapshot_id="s1",
            release_state="failed",
            target_source_match_set_id="ms_target",
            current_active_match_set_id=None,
        )
    )
    assert d.ok is False


# --- rollback integrity_alert recompute ------------------------------------


def test_rollback_integrity_alert_set_when_group_unavailable() -> None:
    assert (
        recompute_rollback_integrity_alert(
            RollbackIntegrityFacts(
                all_groups_available=False, unavailable_group_ids=("g9",)
            )
        )
        is True
    )


def test_rollback_integrity_alert_cleared_when_all_available() -> None:
    assert (
        recompute_rollback_integrity_alert(
            RollbackIntegrityFacts(all_groups_available=True)
        )
        is False
    )
