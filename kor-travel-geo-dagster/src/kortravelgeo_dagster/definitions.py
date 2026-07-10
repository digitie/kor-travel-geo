"""Dagster code location entrypoint.

Aggregates the per-domain job/schedule/sensor/asset lists into a single
module-level ``defs`` and assembles resources with a 3-way fallback:

    value  ->  real @resource  ->  missing-guard

The guard raises a key-specific ``RuntimeError`` at *resource init* (not import),
so ``dagster dev -m kortravelgeo_dagster.definitions`` always loads the code
location even when a credential is missing.
"""

from __future__ import annotations

from typing import Any, Final, cast

from dagster import Definitions, ResourceDefinition, resource

from .backup import BACKUP_JOBS, BACKUP_SCHEDULES, BACKUP_SENSORS
from .backup_execute import DB_BACKUP_JOBS
from .backup_maintenance import BACKUP_MAINTENANCE_JOBS, BACKUP_MAINTENANCE_SCHEDULES
from .mv import MV_REFRESH_JOBS
from .resources import admin_api_resource, client_resource, rustfs_resource, settings_resource

REQUIRED_RESOURCE_KEYS: Final[tuple[str, ...]] = (
    "admin_api",
    "client",
    "rustfs",
    "settings",
)
"""Resource keys the geo Dagster jobs/ops require."""

DEFAULT_RESOURCE_VALUES: Final[dict[str, object]] = {
    # Optional @run_failure_sensor wiring point (dagster-boundary §3). ``None`` is a
    # safe default a production Definitions can override with a webhook notifier.
    "failure_notifier": None,
}
"""Resource values safe to register even if a deployment does not override them."""

DEFAULT_RESOURCE_DEFINITIONS: Final[dict[str, ResourceDefinition]] = {
    "admin_api": admin_api_resource,
    "client": client_resource,
    "rustfs": rustfs_resource,
    "settings": settings_resource,
}
"""Default Dagster resources backed by real env-driven implementations."""


def _missing_resource(key: str) -> ResourceDefinition:
    @resource(description=f"{key} resource must be replaced with a real one in a deployment.")
    def _resource() -> object:
        raise RuntimeError(
            f"Dagster resource {key!r} is not configured. "
            "Inject a real resource in the kor-travel-geo Dagster deployment settings."
        )

    return _resource


def _value_resource(key: str, value: object) -> ResourceDefinition:
    @resource(description=f"{key} default resource value.")
    def _resource() -> object:
        return value

    return _resource


defs = Definitions(
    jobs=cast("Any", [*MV_REFRESH_JOBS, *BACKUP_JOBS, *DB_BACKUP_JOBS, *BACKUP_MAINTENANCE_JOBS]),
    schedules=cast("Any", [*BACKUP_SCHEDULES, *BACKUP_MAINTENANCE_SCHEDULES]),
    sensors=cast("Any", [*BACKUP_SENSORS]),
    resources={
        key: (
            _value_resource(key, DEFAULT_RESOURCE_VALUES[key])
            if key in DEFAULT_RESOURCE_VALUES
            else DEFAULT_RESOURCE_DEFINITIONS[key]
            if key in DEFAULT_RESOURCE_DEFINITIONS
            else _missing_resource(key)
        )
        for key in REQUIRED_RESOURCE_KEYS
        + tuple(DEFAULT_RESOURCE_VALUES)
        + tuple(DEFAULT_RESOURCE_DEFINITIONS)
    },
)
"""``dagster dev -m kortravelgeo_dagster.definitions`` entrypoint."""
