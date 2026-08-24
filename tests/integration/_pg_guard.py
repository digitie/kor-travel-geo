"""One definition of "is this database safe to write to" for every opt-in PostgreSQL test.

Four copies of this predicate had drifted (issue #523). The copy in
``test_t210_source_integration.py`` used ``startswith("kor_travel_geo")``, which returns True for
the **production** database ``kor_travel_geo`` itself — and that module goes on to apply the
schema and ``TRUNCATE`` thirteen ``ops`` tables ``CASCADE``. Several other write-heavy modules had
no guard at all.

Why this is not a cleverer name pattern
---------------------------------------
The first attempt at this consolidation allowed any ``t<NNN>`` segment, on the theory that a task
tag means "scratch". It does not — it means "this database belongs to task N", and
``docs/t213-data-preservation.md`` mandates exactly that shape for
``kor_travel_geo_t213_<YYYYMMDD>``, a **preserved baseline** holding an active serving release and
6.4M-row materialized views. The allow rule matched the one database that most needed protecting.
Guessing disposability from a name is wrong in both directions, so:

* ``PROTECTED_DATABASES`` / ``_PROTECTED_PATTERNS`` are absolute. Nothing overrides them.
* A name is otherwise disposable only if a whole ``_``/``-`` segment is an unambiguous throwaway
  marker. Segment matching (not prefix, not substring) is why ``kor_travel_geo`` fails and
  ``kor_travel_geo_test`` passes for a structural reason rather than by accident.
* Anything else requires naming the database explicitly in ``KTG_TEST_PG_ALLOW_WRITES``. That
  covers the ad-hoc review databases this repo actually uses (``kor_travel_geo_codex_pr12_review``
  and friends) without widening the pattern until production fits through it again.

This is an advisory control at the boundary. It is the primary guard, not the only one: several
loaders open their own psycopg connection and truncate through a raw cursor, so nothing here can
intercept them once a test has been allowed to run.
"""

from __future__ import annotations

import os
import re
import warnings
from typing import Any

import pytest
from sqlalchemy import text

DSN_ENV = "KTG_TEST_PG_DSN"

#: Name the database here to allow writes to it when its name does not announce itself as
#: throwaway. Never overrides the protected list below.
ALLOW_ENV = "KTG_TEST_PG_ALLOW_WRITES"

#: Real databases on the geo cluster. A deny here wins over every allow rule.
PROTECTED_DATABASES = frozenset(
    {
        "kor_travel_geo",  # production (Settings.pg_dsn default)
        "kor_travel_geo_dagster",  # live Dagster metadata DB
        "postgres",
        "template0",
        "template1",
    }
)

#: Preserved baselines and the hot-swap restore target. These carry task tags and dates, so no
#: name rule can be allowed to treat them as scratch.
_PROTECTED_PATTERNS = (
    re.compile(r"^kor_travel_geo_t213(?:[_-].*)?$"),  # T-213 preservation baselines
    re.compile(r"^kor_travel_geo_restore(?:[_-].*)?$"),  # ADR-036 hot-swap restore target
    # The rollback alias is a COPY OF PRODUCTION kept for the retention window, and ADR-036 makes
    # it the only rollback path. `hotswap._resolve_previous_alias` mints
    # `kor_travel_geo_previous_<YYYYMMDD>_<HHMMSS>`; the restore *source* was protected but the
    # rollback copy was not.
    re.compile(r"^kor_travel_geo.*_(?:previous|quarantine)(?:[_-].*)?$"),
)

#: Unambiguous throwaway markers, matched against whole segments. Deliberately excludes task tags
#: like `t213` — a task tag says which task owns the database, not that it may be destroyed.
_DISPOSABLE_SEGMENT = re.compile(r"tests?|scratch|tmp|temp|throwaway|probe|rt|e2e|ci")


def is_protected_database(database_name: str | None) -> bool:
    """True for databases that must never be written to by a test, whatever the env says."""
    if database_name is None:
        return False
    normalized = database_name.strip().lower()
    if normalized in PROTECTED_DATABASES:
        return True
    return any(pattern.match(normalized) for pattern in _PROTECTED_PATTERNS)


def is_disposable_test_database(database_name: str | None, env: Any = None) -> bool:
    """True only for databases a test may create, truncate and drop objects in."""
    if database_name is None:
        return False
    environ = os.environ if env is None else env
    normalized = database_name.strip().lower()
    if not normalized or is_protected_database(normalized):
        return False
    allowed = (environ.get(ALLOW_ENV) or "").strip().lower()
    if allowed and allowed == normalized:
        return True
    return any(
        _DISPOSABLE_SEGMENT.fullmatch(segment)
        for segment in re.split(r"[_\-]", normalized)
        if segment
    )


async def require_disposable_database(engine: Any) -> str:
    """Skip the test unless ``engine`` points at a disposable scratch DB. Returns its name.

    Call this BEFORE applying schema or truncating anything — a guard that runs after the first
    write is not a guard.
    """
    async with engine.connect() as conn:
        database_name = await conn.scalar(text("SELECT current_database()"))
    name = "" if database_name is None else str(database_name)
    if not is_disposable_test_database(name):
        reason = (
            f"refusing to write to database {name!r}: {DSN_ENV} must name a disposable scratch "
            f"database (a 'test' / 'scratch' / 'tmp' / 'rt' / 'e2e' segment, e.g. "
            f"kor_travel_geo_test), or set {ALLOW_ENV}={name!r} to allow it explicitly"
        )
        if is_protected_database(name):
            reason = (
                f"refusing to write to protected database {name!r} — "
                f"{ALLOW_ENV} does not override this"
            )
        # Warn as well as skip: under a plain `pytest -q` a skip is indistinguishable from
        # "DSN not set", and reading it that way is how someone concludes they have coverage
        # they do not have.
        warnings.warn(reason, RuntimeWarning, stacklevel=2)
        pytest.skip(reason)
    return name
