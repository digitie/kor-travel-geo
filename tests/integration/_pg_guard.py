"""One definition of "is this database safe to write to" for every opt-in PostgreSQL test.

Three copies of this predicate had drifted (issue #523). The copy in
``test_t210_source_integration.py`` used ``startswith("kor_travel_geo")``, which returns True for
the **production** database ``kor_travel_geo`` itself — and that module goes on to apply the
schema and ``TRUNCATE`` thirteen ``ops`` tables ``CASCADE``. Two other write-heavy modules had no
guard at all.

The predicate here matches whole ``_``/``-`` **segments**, not prefixes or substrings. That is the
only formulation where ``kor_travel_geo`` fails and ``kor_travel_geo_test`` passes for a
structural reason rather than by accident.

This is a name-based, advisory control. It is the primary guard, not the only one: several
loaders open their own psycopg connection and truncate through a raw cursor, so nothing here can
intercept them once a test has been allowed to run.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from sqlalchemy import text

DSN_ENV = "KTG_TEST_PG_DSN"

#: Real databases on the geo cluster. A deny here wins over every allow rule below.
#: ``kor_travel_geo`` is the production database (``Settings.pg_dsn`` default) and
#: ``kor_travel_geo_dagster`` is the live Dagster metadata DB.
PROTECTED_DATABASES = frozenset(
    {
        "kor_travel_geo",
        "kor_travel_geo_dagster",
        "postgres",
        "template0",
        "template1",
    }
)

#: A database is disposable only when a whole segment is a throwaway marker: `test`, `tests`,
#: `scratch`, `tmp`, `temp`, `throwaway`, `probe`, or a task tag like `t177` / `t050`.
#: Deliberately conservative — a name that does not say "throwaway" is treated as real.
_DISPOSABLE_SEGMENT = re.compile(r"tests?|scratch|tmp|temp|throwaway|probe|t\d{2,4}")


def is_disposable_test_database(database_name: str | None) -> bool:
    """True only for names that positively announce themselves as throwaway."""
    if database_name is None:
        return False
    normalized = database_name.strip().lower()
    if not normalized or normalized in PROTECTED_DATABASES:
        return False
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
        pytest.skip(
            f"{DSN_ENV} must point to a disposable scratch database — a name with a "
            f"'test' / 'scratch' / 'tmp' / 't<NNN>' segment, e.g. kor_travel_geo_test; "
            f"got {name!r}"
        )
    return name
