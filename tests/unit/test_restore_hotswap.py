from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kortravelgeo.dto.admin import RestoreHotSwapPlanRequest
from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.hotswap import (
    build_restore_hot_swap_plan,
    hot_swap_confirmation,
    rollback_confirmation,
)
from kortravelgeo.settings import Settings


def test_restore_hot_swap_plan_builds_confirmation_sql_and_steps() -> None:
    settings = Settings(pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo")
    plan = build_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(restore_database="kor_travel_geo_restore_20260529"),
        existing_databases={"kor_travel_geo", "kor_travel_geo_restore_20260529"},
        generated_at=datetime(2026, 5, 29, 1, 2, 3, tzinfo=UTC),
    )

    assert plan.current_database == "kor_travel_geo"
    assert plan.restore_database == "kor_travel_geo_restore_20260529"
    assert plan.previous_alias == "kor_travel_geo_previous_20260529_010203"
    assert plan.maintenance_database == "postgres"
    assert plan.typed_confirmation == "HOT_SWAP kor_travel_geo FROM kor_travel_geo_restore_20260529"
    assert plan.rollback_confirmation == (
        "ROLLBACK_HOT_SWAP kor_travel_geo FROM kor_travel_geo_previous_20260529_010203"
    )
    assert plan.can_execute is True
    assert plan.blockers == ()
    assert plan.sql == (
        "SELECT pg_terminate_backend(pid)\n"
        "  FROM pg_stat_activity\n"
        " WHERE datname = 'kor_travel_geo'\n"
        "   AND pid <> pg_backend_pid();",
        "SELECT pg_terminate_backend(pid)\n"
        "  FROM pg_stat_activity\n"
        " WHERE datname = 'kor_travel_geo_restore_20260529'\n"
        "   AND pid <> pg_backend_pid();",
        'ALTER DATABASE "kor_travel_geo" RENAME TO "kor_travel_geo_previous_20260529_010203";',
        'ALTER DATABASE "kor_travel_geo_restore_20260529" RENAME TO "kor_travel_geo";',
    )
    assert len(plan.steps) == 7


def test_restore_hot_swap_plan_reports_missing_and_conflicting_databases() -> None:
    settings = Settings(pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo")
    plan = build_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(
            restore_database="kor_travel_geo_restore_20260529",
            previous_alias="kor_travel_geo_previous_manual",
        ),
        existing_databases={"kor_travel_geo", "kor_travel_geo_previous_manual"},
    )

    assert plan.can_execute is False
    assert plan.blockers == (
        "restore database does not exist in cluster: kor_travel_geo_restore_20260529",
        "previous alias already exists in cluster: kor_travel_geo_previous_manual",
    )


def test_restore_hot_swap_plan_distinguishes_unchecked_from_empty_database_inventory() -> None:
    settings = Settings(pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo")
    unchecked = build_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(restore_database="kor_travel_geo_restore_20260529"),
    )
    checked_empty = build_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(restore_database="kor_travel_geo_restore_20260529"),
        existing_databases=set(),
    )

    assert unchecked.can_execute is True
    assert checked_empty.can_execute is False
    assert checked_empty.blockers[:2] == (
        "current database does not exist in cluster: kor_travel_geo",
        "restore database does not exist in cluster: kor_travel_geo_restore_20260529",
    )


def test_restore_hot_swap_plan_truncates_long_generated_previous_alias() -> None:
    settings = Settings(
        pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/"
        "kor_travel_geo_serving_database_name_that_is_long_but_valid",
    )
    plan = build_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(restore_database="kor_travel_geo_restore_20260529"),
        generated_at=datetime(2026, 5, 29, 1, 2, 3, tzinfo=UTC),
    )

    assert len(plan.previous_alias) == 63
    assert plan.previous_alias.endswith("_previous_20260529_010203")


def test_restore_hot_swap_plan_allows_custom_maintenance_database() -> None:
    settings = Settings(pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo")
    plan = build_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(
            restore_database="kor_travel_geo_restore_20260529",
            maintenance_database="kor_travel_geo_admin",
        ),
    )

    assert plan.maintenance_database == "kor_travel_geo_admin"


def test_restore_hot_swap_plan_rejects_unsafe_database_identifiers() -> None:
    settings = Settings(pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo")
    with pytest.raises(InvalidInputError, match="restore_database must match"):
        build_restore_hot_swap_plan(
            settings,
            RestoreHotSwapPlanRequest(restore_database="kor-travel-geo-restore"),
        )


def test_restore_hot_swap_confirmation_helpers_are_stable() -> None:
    assert hot_swap_confirmation("kor_travel_geo", "kor_travel_geo_restore") == (
        "HOT_SWAP kor_travel_geo FROM kor_travel_geo_restore"
    )
    assert rollback_confirmation("kor_travel_geo", "kor_travel_geo_previous") == (
        "ROLLBACK_HOT_SWAP kor_travel_geo FROM kor_travel_geo_previous"
    )
