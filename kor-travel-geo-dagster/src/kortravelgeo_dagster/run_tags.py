"""Run tags that raise the shared Dagster instance's max-runtime cap for long geo jobs.

**Why a job tag, not instance config.** ``run_monitoring.max_runtime_seconds`` is one
instance-wide value. On the shared Dagster plane (Map/geo/PinVi/weather on one daemon) it is
the tenants' common default — 21600 s (6 h) — and geo's own ``docker/dagster.yaml`` no longer
decides it. Dagster lets the run tag ``dagster/max_runtime`` override the instance value per
run, and job-definition tags are copied onto every run of that job (launch-from-API,
schedule, or UI), so carrying the cap on the job keeps it the same on any instance.

**Which jobs** (owner decision 2026-09-30: every other geo job keeps the shared default):

- ``full_load_batch`` — the national full load took 4 h 8 min on the dev workstation
  (T-033, ``docs/t033-full-load-revalidation.md``); n150 is slower, so 6 h is not a safe cap.
- ``load_source`` — one source loader. The SHP loader alone was 3 h 37 min of that 4 h 8 min,
  so a single-source run can cross 6 h on n150 as well.
- ``db_restore`` — a full ``pg_restore`` of the serving DB (n150 max so far 2.18 h, but it
  scales with the dataset and the restore is not resumable: killing it at 6 h wastes the run).
- ``backup_restore_drill`` — the same restore into a throwaway DB, plus reconcile + smoke.

The expected cap of every job is pinned in ``tests/test_definitions.py`` so a new job has to
choose. The value is a string because Dagster tag values are strings.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "LONG_RUN_MAX_RUNTIME_SECONDS",
    "LONG_RUN_TAGS",
    "MAX_RUNTIME_TAG",
]

MAX_RUNTIME_TAG: Final[str] = "dagster/max_runtime"
"""Dagster's per-run override of ``run_monitoring.max_runtime_seconds``."""

LONG_RUN_MAX_RUNTIME_SECONDS: Final[int] = 86400
"""24 h — the cap for geo jobs that can legitimately outlive the shared 6 h default."""

LONG_RUN_TAGS: Final[dict[str, str]] = {
    MAX_RUNTIME_TAG: str(LONG_RUN_MAX_RUNTIME_SECONDS),
}
"""Merged into the job tags of the long-running geo jobs listed in the module docstring."""
