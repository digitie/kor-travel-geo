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
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
