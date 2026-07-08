"""Smoke tests for the kor-travel-geo Dagster code location (T-290a).

Structural only: they assert the code location loads and the mv_refresh wiring is
correct without touching a database or requiring credentials. Runtime execution of
the job is validated at the M1 deploy gate (T-290b).
"""

from __future__ import annotations

from kortravelgeo_dagster.backup import (
    notify_run_failure_sensor,
    run_due_scheduled_backup_op,
    scheduled_backup_run_due_job,
    scheduled_backup_schedule,
)
from kortravelgeo_dagster.definitions import (
    DEFAULT_RESOURCE_DEFINITIONS,
    REQUIRED_RESOURCE_KEYS,
    defs,
)
from kortravelgeo_dagster.mv import mv_refresh_job, refresh_geocode_mv_op


def test_code_location_loads_mv_refresh_job() -> None:
    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "mv_refresh" in job_names
    assert defs.get_job_def("mv_refresh").name == "mv_refresh"


def test_code_location_loads_scheduled_backup_onramp() -> None:
    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "scheduled_backup_run_due" in job_names
    assert defs.get_job_def("scheduled_backup_run_due").name == "scheduled_backup_run_due"
    assert scheduled_backup_run_due_job.name == "scheduled_backup_run_due"
    assert scheduled_backup_schedule.name == "scheduled_backup"
    assert notify_run_failure_sensor.name == "run_failure_sensor"


def test_op_name_differs_from_job_name() -> None:
    # Same op/job name makes the code location fail to load (dagster-boundary §10).
    assert refresh_geocode_mv_op.name == "refresh_geocode_mv"
    assert mv_refresh_job.name == "mv_refresh"
    assert refresh_geocode_mv_op.name != mv_refresh_job.name


def test_mv_op_requires_only_client_resource() -> None:
    assert refresh_geocode_mv_op.required_resource_keys == {"client"}


def test_scheduled_backup_op_requires_only_admin_api_resource() -> None:
    assert run_due_scheduled_backup_op.required_resource_keys == {"admin_api"}


def test_default_resources_cover_required_keys() -> None:
    for key in ("admin_api", "client", "rustfs", "settings"):
        assert key in REQUIRED_RESOURCE_KEYS
        assert key in DEFAULT_RESOURCE_DEFINITIONS
