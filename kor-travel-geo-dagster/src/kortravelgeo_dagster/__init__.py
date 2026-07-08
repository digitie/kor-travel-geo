"""``kortravelgeo_dagster`` — kor-travel-geo standalone Dagster code location.

- This package owns the Dagster jobs / resources / ``Definitions``.
- The main library ``kortravelgeo`` never imports Dagster (one-way dependency,
  enforced by packaging — ADR-066 §6).
- Code-location entrypoint: ``kortravelgeo_dagster.definitions``.
"""

from __future__ import annotations

from .definitions import defs
from .mv import MV_REFRESH_JOBS, mv_refresh_job, refresh_geocode_mv_op
from .resources import client_resource, rustfs_resource, settings_resource

__all__ = [
    "MV_REFRESH_JOBS",
    "client_resource",
    "defs",
    "mv_refresh_job",
    "refresh_geocode_mv_op",
    "rustfs_resource",
    "settings_resource",
]
