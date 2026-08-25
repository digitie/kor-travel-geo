"""Integration-test fixtures (T-210).

The only cross-cutting concern here is the Windows asyncio event-loop policy.
``psycopg``'s async driver (used by SQLAlchemy ``make_async_engine``) cannot run
on the Windows default ``ProactorEventLoop`` — it needs a selector loop. On
Windows we install the selector policy at import time so every async DB test in
this directory (and pytest-asyncio's per-test loops) uses it. This is a no-op on
Linux/CI, so the same suite stays green in both places.
"""

from __future__ import annotations

import asyncio
import os
import sys

from tests.integration._pg_guard import ALLOW_SKIPS_ENV, DSN_ENV, REFUSALS

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_sessionfinish(session, exitstatus) -> None:
    """Fail the session if the database guard refused a DSN that was deliberately configured.

    ``exitstatus`` is unused; it is part of the pytest hook signature.

    Skipping is the right behaviour for "no DSN set". It is the WRONG behaviour for "you set a
    DSN and every write-heavy suite quietly declined it" — that reads as a green run with
    coverage, which is how the T-246 hot-swap e2e silently disappeared (issue #523/#525).
    """
    if not os.getenv(DSN_ENV) or not REFUSALS:
        return
    if os.getenv(ALLOW_SKIPS_ENV) == "1":
        return
    for nodeid, database in REFUSALS:
        print(f"GUARD REFUSED {nodeid} -> database {database!r}")
    print(
        f"{len(REFUSALS)} test(s) skipped because the guard refused the configured {DSN_ENV}. "
        f"Point it at a disposable database, or set {ALLOW_SKIPS_ENV}=1 if that is intended."
    )
    session.exitstatus = 1
