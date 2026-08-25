"""The guard must not be able to delete coverage silently (issues #523, #525).

A refusal is a `pytest.skip`, and under `pytest -q` a skip looks exactly like "no DSN set". That
is how adding the guard to `build_minimal_serving_schema` turned the T-246 hot-swap e2e from
`3 passed` into `3 skipped` with nobody noticing — and that suite was the only live proof of the
ADR-036 cutover.

So: if a DSN was deliberately configured and the guard refused it, the session fails.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from _pytest.outcomes import Skipped

from tests.integration._pg_guard import (
    ALLOW_SKIPS_ENV,
    DSN_ENV,
    REFUSALS,
    require_disposable_database,
)
from tests.integration.conftest import pytest_sessionfinish


class _FakeEngine:
    """Just enough of AsyncEngine for the guard: one scalar() returning the database name."""

    def __init__(self, database: str) -> None:
        self._database = database

    @asynccontextmanager
    async def _conn(self):
        yield self

    def connect(self):
        return self._conn()

    async def scalar(self, *_args, **_kwargs) -> str:
        return self._database


@pytest.fixture(autouse=True)
def _clean_registry():
    saved = list(REFUSALS)
    REFUSALS.clear()
    yield
    REFUSALS[:] = saved


def test_refusal_with_a_configured_dsn_fails_the_session(monkeypatch) -> None:
    monkeypatch.setenv(DSN_ENV, "postgresql+psycopg://u:p@localhost:5432/kor_travel_geo")
    monkeypatch.delenv(ALLOW_SKIPS_ENV, raising=False)
    REFUSALS.append(("tests/integration/test_x.py::test_y", "kor_travel_geo"))

    session = SimpleNamespace(exitstatus=0)
    pytest_sessionfinish(session, 0)

    assert session.exitstatus == 1


def test_no_refusals_leaves_the_session_alone(monkeypatch) -> None:
    monkeypatch.setenv(DSN_ENV, "postgresql+psycopg://u:p@localhost:5432/kor_travel_geo_test")
    monkeypatch.delenv(ALLOW_SKIPS_ENV, raising=False)

    session = SimpleNamespace(exitstatus=0)
    pytest_sessionfinish(session, 0)

    assert session.exitstatus == 0


def test_no_dsn_is_not_a_failure(monkeypatch) -> None:
    """"DSN not set" is the normal opt-out and must stay a plain skip."""
    monkeypatch.delenv(DSN_ENV, raising=False)
    monkeypatch.delenv(ALLOW_SKIPS_ENV, raising=False)
    REFUSALS.append(("tests/integration/test_x.py::test_y", "kor_travel_geo"))

    session = SimpleNamespace(exitstatus=0)
    pytest_sessionfinish(session, 0)

    assert session.exitstatus == 0


def test_refusals_can_be_accepted_explicitly(monkeypatch) -> None:
    monkeypatch.setenv(DSN_ENV, "postgresql+psycopg://u:p@localhost:5432/kor_travel_geo")
    monkeypatch.setenv(ALLOW_SKIPS_ENV, "1")
    REFUSALS.append(("tests/integration/test_x.py::test_y", "kor_travel_geo"))

    session = SimpleNamespace(exitstatus=0)
    pytest_sessionfinish(session, 0)

    assert session.exitstatus == 0


@pytest.mark.asyncio
async def test_the_guard_actually_records_its_refusal() -> None:
    """The single line wiring the guard to the session hook.

    Deleting `REFUSALS.append(...)` from `require_disposable_database` left the whole suite green
    — every other test in this file appends to the registry by hand and only exercises the hook.
    That made the skip budget, which exists precisely to stop a guard from deleting coverage
    silently, itself silently deletable.
    """
    before = len(REFUSALS)
    with pytest.raises(Skipped):
        await require_disposable_database(_FakeEngine("kor_travel_geo"))
    assert len(REFUSALS) == before + 1
    assert REFUSALS[-1][1] == "kor_travel_geo"


@pytest.mark.asyncio
async def test_an_accepted_database_records_nothing() -> None:
    before = len(REFUSALS)
    name = await require_disposable_database(_FakeEngine("kor_travel_geo_test"))
    assert name == "kor_travel_geo_test"
    assert len(REFUSALS) == before
