"""T-235 restore-target cleanup decision (pure).

On cancel/fail, a partially-filled ``new_database`` target the job owns (verified
empty at start) is dropped/quarantined per policy; ``replace_current`` (the live
serving DB) is **never** auto-cleaned. The actual drop/rename via a maintenance
connection is integration-tested in T-245.
"""

from __future__ import annotations

import pytest

from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.backup import (
    quarantine_restore_database_name,
    quote_database_identifier,
    restore_target_cleanup_action,
    validate_database_identifier,
)


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


def test_restore_database_identifier_rejects_quotes() -> None:
    with pytest.raises(InvalidInputError, match="target_database must match"):
        validate_database_identifier('restore"db', "target_database")


def test_quote_database_identifier_only_quotes_valid_names() -> None:
    assert quote_database_identifier("kor_travel_geo_restore") == '"kor_travel_geo_restore"'


def test_quarantine_name_stays_within_postgres_identifier_limit() -> None:
    name = quarantine_restore_database_name(
        "a" * 63,
        "20260616T123456Z",
    )

    assert len(name) == 63
    assert name.endswith("_quarantine_20260616T123456Z")
