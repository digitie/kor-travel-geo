"""T-241 hot-swap execution: pure confirmation gate + swap/rollback SQL planning.

The live ``ALTER DATABASE RENAME`` execution, advisory-lock fail-fast, and auto-rollback
are integration-tested in T-246 (they need a real cluster). These tests cover the pure,
device/DB-independent pieces: the exact-confirmation gate and that the rollback SQL is the
correct inverse of the forward swap.
"""

from __future__ import annotations

import pytest

from kortravelgeo.dto.admin import RestoreHotSwapPlanRequest
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.hotswap import (
    build_hot_swap_rollback_sql,
    build_hot_swap_swap_sql,
    build_restore_hot_swap_plan,
    hot_swap_rollback_blockers,
    rollback_confirmation,
    validate_hot_swap_confirmation,
)
from kortravelgeo.settings import Settings

_SETTINGS = Settings(pg_dsn="postgresql://a:b@localhost:5432/kor_travel_geo")


def _plan(existing: set[str] | None = None):
    return build_restore_hot_swap_plan(
        _SETTINGS,
        RestoreHotSwapPlanRequest(
            restore_database="kor_travel_geo_restore",
            previous_alias="kor_travel_geo_previous",
        ),
        existing_databases=existing,
    )


def test_confirmation_must_match_plan_exactly() -> None:
    plan = _plan()
    assert plan.typed_confirmation == "HOT_SWAP kor_travel_geo FROM kor_travel_geo_restore"
    # exact match passes
    validate_hot_swap_confirmation(plan, plan.typed_confirmation)
    # any deviation hard-fails
    with pytest.raises(InvalidInputError, match="typed_confirmation must be exactly"):
        validate_hot_swap_confirmation(plan, "HOT_SWAP kor_travel_geo")
    with pytest.raises(InvalidInputError, match="typed_confirmation must be exactly"):
        validate_hot_swap_confirmation(plan, plan.typed_confirmation + " ")


def test_swap_sql_order_terminates_then_renames() -> None:
    swap = build_hot_swap_swap_sql(
        "kor_travel_geo", "kor_travel_geo_restore", "kor_travel_geo_previous"
    )
    assert len(swap) == 4
    assert "pg_terminate_backend" in swap[0] and "kor_travel_geo" in swap[0]
    assert "pg_terminate_backend" in swap[1] and "kor_travel_geo_restore" in swap[1]
    # current -> previous, then restore -> current
    assert swap[2] == 'ALTER DATABASE "kor_travel_geo" RENAME TO "kor_travel_geo_previous";'
    assert swap[3] == 'ALTER DATABASE "kor_travel_geo_restore" RENAME TO "kor_travel_geo";'


def test_rollback_sql_is_inverse_of_swap() -> None:
    rollback = build_hot_swap_rollback_sql(
        "kor_travel_geo", "kor_travel_geo_restore", "kor_travel_geo_previous"
    )
    assert len(rollback) == 4
    # current(restored) -> restore, then previous(old) -> current
    assert rollback[2] == 'ALTER DATABASE "kor_travel_geo" RENAME TO "kor_travel_geo_restore";'
    assert rollback[3] == 'ALTER DATABASE "kor_travel_geo_previous" RENAME TO "kor_travel_geo";'


def test_rollback_restores_original_names() -> None:
    # After a forward swap the serving name holds the restored DB and previous_alias holds
    # the old DB; applying rollback must map both names back to their pre-swap databases.
    current, restore, previous = "db", "db_restore", "db_previous"
    rollback = build_hot_swap_rollback_sql(current, restore, previous)
    # restored DB (currently named `current`) goes back to its `restore` name
    assert f'ALTER DATABASE "{current}" RENAME TO "{restore}";' in rollback
    # old serving DB (currently named `previous`) goes back to `current`
    assert f'ALTER DATABASE "{previous}" RENAME TO "{current}";' in rollback


def test_plan_blocks_when_restore_database_missing() -> None:
    plan = _plan(existing={"kor_travel_geo"})  # restore DB absent
    assert plan.can_execute is False
    assert any("restore database does not exist" in b for b in plan.blockers)


# --- T-264 manual rollback ------------------------------------------------


def test_rollback_confirmation_format() -> None:
    assert (
        rollback_confirmation("kor_travel_geo", "kor_travel_geo_previous_x")
        == "ROLLBACK_HOT_SWAP kor_travel_geo FROM kor_travel_geo_previous_x"
    )


def test_rollback_clean_when_previous_exists_and_target_free() -> None:
    blockers = hot_swap_rollback_blockers(
        current_database="kor_travel_geo",
        restore_database="kor_travel_geo_restore",
        previous_alias="kor_travel_geo_previous",
        existing_databases={"kor_travel_geo", "kor_travel_geo_previous"},
    )
    assert blockers == []


def test_rollback_rejected_when_previous_alias_retention_expired() -> None:
    # previous_alias has been dropped (retention passed) → rollback must be rejected
    blockers = hot_swap_rollback_blockers(
        current_database="kor_travel_geo",
        restore_database="kor_travel_geo_restore",
        previous_alias="kor_travel_geo_previous",
        existing_databases={"kor_travel_geo"},
    )
    assert any("previous alias no longer exists" in b for b in blockers)


def test_rollback_rejected_when_restore_target_name_taken() -> None:
    blockers = hot_swap_rollback_blockers(
        current_database="kor_travel_geo",
        restore_database="kor_travel_geo_restore",
        previous_alias="kor_travel_geo_previous",
        existing_databases={"kor_travel_geo", "kor_travel_geo_previous", "kor_travel_geo_restore"},
    )
    assert any("restore target name already exists" in b for b in blockers)


def test_rollback_rejected_when_names_not_distinct() -> None:
    blockers = hot_swap_rollback_blockers(
        current_database="kor_travel_geo",
        restore_database="kor_travel_geo",
        previous_alias="kor_travel_geo_previous",
        existing_databases=None,
    )
    assert any("must all differ" in b for b in blockers)
