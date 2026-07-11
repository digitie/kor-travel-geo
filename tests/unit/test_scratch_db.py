"""scratch_database_dsn unit coverage (T-290j staging blue-green).

``ensure_scratch_database`` runs real CREATE DATABASE + schema DDL, so its round-trip lives
in ``tests/integration/test_scratch_db_roundtrip.py`` (opt-in ``KTG_TEST_PG_DSN``); here we
pin the pure DSN-swap + identifier validation the launcher and op both rely on.
"""

from __future__ import annotations

import pytest

from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.scratch_db import scratch_database_dsn


def test_scratch_database_dsn_swaps_database_and_normalizes_driver() -> None:
    dsn = scratch_database_dsn(
        "postgresql://addr:addr@localhost:5432/kor_travel_geo",
        "kor_travel_geo_fullload_e2e",
    )
    # database swapped to the scratch name; serving db name gone
    assert dsn.endswith("/kor_travel_geo_fullload_e2e")
    # the bare postgresql:// input is normalized to the +psycopg driver the app uses
    assert dsn.startswith("postgresql+psycopg://")


def test_scratch_database_dsn_preserves_existing_psycopg_driver() -> None:
    dsn = scratch_database_dsn(
        "postgresql+psycopg://addr:addr@localhost:5432/kor_travel_geo", "scratch_db"
    )
    assert dsn.startswith("postgresql+psycopg://")
    assert dsn.endswith("/scratch_db")


@pytest.mark.parametrize("bad", ["bad name", "db; DROP DATABASE x", "1", "", "a" * 100])
def test_scratch_database_dsn_rejects_invalid_identifier(bad: str) -> None:
    with pytest.raises(InvalidInputError):
        scratch_database_dsn("postgresql+psycopg://addr:addr@localhost:5432/db", bad)
