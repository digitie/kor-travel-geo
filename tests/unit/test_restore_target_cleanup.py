"""T-235 restore-target cleanup decision (pure).

On cancel/fail, a partially-filled ``new_database`` target the job owns (verified
empty at start) is dropped/quarantined per policy; ``replace_current`` (the live
serving DB) is **never** auto-cleaned. The actual drop/rename via a maintenance
connection is integration-tested in T-245.
"""

from __future__ import annotations

from kortravelgeo.infra.backup import restore_target_cleanup_action


def test_replace_current_is_never_cleaned() -> None:
    # even with an aggressive policy and an owned target.
    assert (
        restore_target_cleanup_action(
            mode="replace_current", policy="drop", job_owns_target=True
        )
        is None
    )


def test_unowned_target_is_not_cleaned() -> None:
    # the target was not verified empty (not new_database flow) → leave it.
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="drop", job_owns_target=False
        )
        is None
    )


def test_quarantine_policy_returns_quarantine() -> None:
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="quarantine", job_owns_target=True
        )
        == "quarantine"
    )


def test_drop_policy_returns_drop() -> None:
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="drop", job_owns_target=True
        )
        == "drop"
    )


def test_keep_and_unknown_policy_do_nothing() -> None:
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="keep", job_owns_target=True
        )
        is None
    )
    assert (
        restore_target_cleanup_action(
            mode="new_database", policy="bogus", job_owns_target=True
        )
        is None
    )
