from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kraddr.geo.dto.admin import RestoreHotSwapPlanRequest
from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra.hotswap import (
    build_restore_hot_swap_plan,
    hot_swap_confirmation,
    rollback_confirmation,
)
from kraddr.geo.settings import Settings


def test_restore_hot_swap_plan_builds_confirmation_sql_and_steps() -> None:
    settings = Settings(pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/kraddr_geo")
    plan = build_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(restore_database="kraddr_geo_restore_20260529"),
        existing_databases={"kraddr_geo", "kraddr_geo_restore_20260529"},
        generated_at=datetime(2026, 5, 29, 1, 2, 3, tzinfo=UTC),
    )

    assert plan.current_database == "kraddr_geo"
    assert plan.restore_database == "kraddr_geo_restore_20260529"
    assert plan.previous_alias == "kraddr_geo_previous_20260529_010203"
    assert plan.maintenance_database == "postgres"
    assert plan.typed_confirmation == "HOT_SWAP kraddr_geo FROM kraddr_geo_restore_20260529"
    assert plan.rollback_confirmation == (
        "ROLLBACK_HOT_SWAP kraddr_geo FROM kraddr_geo_previous_20260529_010203"
    )
    assert plan.can_execute is True
    assert plan.blockers == ()
    assert plan.sql == (
        "SELECT pg_terminate_backend(pid)\n"
        "  FROM pg_stat_activity\n"
        " WHERE datname = 'kraddr_geo'\n"
        "   AND pid <> pg_backend_pid();",
        "SELECT pg_terminate_backend(pid)\n"
        "  FROM pg_stat_activity\n"
        " WHERE datname = 'kraddr_geo_restore_20260529'\n"
        "   AND pid <> pg_backend_pid();",
        'ALTER DATABASE "kraddr_geo" RENAME TO "kraddr_geo_previous_20260529_010203";',
        'ALTER DATABASE "kraddr_geo_restore_20260529" RENAME TO "kraddr_geo";',
    )
    assert len(plan.steps) == 7


def test_restore_hot_swap_plan_reports_missing_and_conflicting_databases() -> None:
    settings = Settings(pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/kraddr_geo")
    plan = build_restore_hot_swap_plan(
        settings,
        RestoreHotSwapPlanRequest(
            restore_database="kraddr_geo_restore_20260529",
            previous_alias="kraddr_geo_previous_manual",
        ),
        existing_databases={"kraddr_geo", "kraddr_geo_previous_manual"},
    )

    assert plan.can_execute is False
    assert plan.blockers == (
        "restore database does not exist in cluster: kraddr_geo_restore_20260529",
        "previous alias already exists in cluster: kraddr_geo_previous_manual",
    )


def test_restore_hot_swap_plan_rejects_unsafe_database_identifiers() -> None:
    settings = Settings(pg_dsn="postgresql+psycopg://addr:addr@localhost:5432/kraddr_geo")
    with pytest.raises(InvalidInputError, match="restore_database must match"):
        build_restore_hot_swap_plan(
            settings,
            RestoreHotSwapPlanRequest(restore_database="kraddr-geo-restore"),
        )


def test_restore_hot_swap_confirmation_helpers_are_stable() -> None:
    assert hot_swap_confirmation("kraddr_geo", "kraddr_geo_restore") == (
        "HOT_SWAP kraddr_geo FROM kraddr_geo_restore"
    )
    assert rollback_confirmation("kraddr_geo", "kraddr_geo_previous") == (
        "ROLLBACK_HOT_SWAP kraddr_geo FROM kraddr_geo_previous"
    )
