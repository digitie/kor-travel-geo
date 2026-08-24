"""The disposable-database predicate that gates every opt-in PostgreSQL test (issue #523).

This runs offline and is the reason the guard can be trusted: the bug it replaces was a
`startswith("kor_travel_geo")` that returned True for the production database itself, and no test
would have noticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration._pg_guard import is_disposable_test_database

_INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "integration"

#: Every write-heavy opt-in PostgreSQL module must route through the shared guard.
_MUST_GUARD = (
    "test_t210_source_integration.py",
    "test_optional_real_postgres_ops_constraints.py",
    "test_admin_table_stats_estimates.py",
    "test_full_load_batch_dagster_roundtrip.py",
    "test_optional_real_postgres_load.py",
)


@pytest.mark.parametrize(
    "name",
    [
        "kor_travel_geo",  # production — the exact name the old predicate let through
        "KOR_TRAVEL_GEO",
        " kor_travel_geo ",
        "kor_travel_geo_dagster",  # live Dagster metadata DB
        "postgres",
        "template1",
        "",
        "geocoder",
        "kor_travel_geo_prod",
        "kor_travel_geo_backup",
    ],
)
def test_real_databases_are_refused(name: str) -> None:
    assert is_disposable_test_database(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "kor_travel_geo_test",
        "kor_travel_geo_t177",
        "kor_travel_geo_t050_ops_constraints",
        "ktg_t246_cur_ab12ef34",
        "ktg_probe_test",
        "tmp_probe",
        "scratch",
        "geo-test-01",
    ],
)
def test_scratch_databases_are_allowed(name: str) -> None:
    assert is_disposable_test_database(name) is True


def test_none_is_refused() -> None:
    assert is_disposable_test_database(None) is False


def test_prefix_matching_would_have_let_production_through() -> None:
    """Pins WHY the predicate is segment-based rather than prefix-based.

    The replaced implementation was `normalized.startswith("kor_travel_geo")`. Asserting the old
    formulation's behaviour here keeps the rationale from being "simplified" back out.
    """
    assert "kor_travel_geo".startswith("kor_travel_geo") is True
    assert is_disposable_test_database("kor_travel_geo") is False


def test_no_local_copies_of_the_predicate_remain() -> None:
    """Three copies had drifted; one matched production. There must be exactly one definition."""
    offenders = [
        path.name
        for path in _INTEGRATION_DIR.glob("*.py")
        if "def _looks_like_disposable_test_database" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"local copies of the guard predicate remain: {offenders}"


@pytest.mark.parametrize("module", _MUST_GUARD)
def test_write_heavy_modules_call_the_shared_guard(module: str) -> None:
    """Assert the CALL, not the name.

    Matching the bare name passes on a module that imports the guard and never calls it — which
    is exactly the state left behind when someone deletes the call and the linter keeps the
    import. Verified: deleting the `await` line while leaving the import made the name-based
    version of this assertion pass.
    """
    source = (_INTEGRATION_DIR / module).read_text(encoding="utf-8")
    assert "await require_disposable_database(" in source, (
        f"{module} writes to KTG_TEST_PG_DSN without awaiting the shared guard"
    )
