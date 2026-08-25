"""The guard must not be able to delete coverage silently (issues #523, #525).

A refusal is a `pytest.skip`, and under `pytest -q` a skip looks exactly like "no DSN set". That
is how adding the guard to `build_minimal_serving_schema` turned the T-246 hot-swap e2e from
`3 passed` into `3 skipped` with nobody noticing — and that suite was the only live proof of the
ADR-036 cutover.

So: if a DSN was deliberately configured and the guard refused it, the session fails.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.integration._pg_guard import ALLOW_SKIPS_ENV, DSN_ENV, REFUSALS
from tests.integration.conftest import pytest_sessionfinish


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
