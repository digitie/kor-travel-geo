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
from kortravelgeo_dagster.mv import mv_refresh_job, run_mv_refresh_op
from kortravelgeo_dagster.run_tags import LONG_RUN_TAGS, MAX_RUNTIME_TAG


def test_code_location_loads_mv_refresh_job() -> None:
    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "mv_refresh" in job_names
    assert defs.get_job_def("mv_refresh").name == "mv_refresh"


def test_code_location_loads_t290k_additive_jobs() -> None:
    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "consistency_check" in job_names
    assert "source_rebuild_db" in job_names
    assert defs.get_job_def("consistency_check").name == "consistency_check"
    assert defs.get_job_def("source_rebuild_db").name == "source_rebuild_db"


def test_code_location_loads_scheduled_backup_onramp() -> None:
    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "scheduled_backup_run_due" in job_names
    assert defs.get_job_def("scheduled_backup_run_due").name == "scheduled_backup_run_due"
    assert scheduled_backup_run_due_job.name == "scheduled_backup_run_due"
    assert scheduled_backup_schedule.name == "scheduled_backup"
    assert notify_run_failure_sensor.name == "run_failure_sensor"


# D4 (dagster-shared plan): every instigator's on/off state is declared in code. The shared
# Dagster instance starts with an empty DB, so a state that lived only in the old DB (prod
# had these three toggled on by hand) would silently come up STOPPED. This table is the
# prod state read from n150 on 2026-09-29; a new schedule/sensor must be added here, which
# forces a deliberate choice instead of inheriting STOPPED.
_DECLARED_INSTIGATOR_STATUS = {
    "scheduled_backup": "RUNNING",
    "backup_retention_janitor_daily": "RUNNING",
    "backup_restore_drill_daily": "STOPPED",
    "run_failure_sensor": "RUNNING",
    "geo_infrastructure_retry_backup_verify": "RUNNING",
}


def test_every_instigator_declares_its_prod_status_in_code() -> None:
    repo = defs.get_repository_def()
    declared = {
        instigator.name: instigator.default_status.value
        for instigator in [*repo.schedule_defs, *repo.sensor_defs]
    }
    assert declared == _DECLARED_INSTIGATOR_STATUS


# Shared-plane max runtime (owner decision 2026-09-30): the shared instance's 6 h
# run_monitoring default applies to every geo job except the ones that can legitimately run
# longer, which carry ``dagster/max_runtime`` = 86400 (``kortravelgeo_dagster/run_tags.py``
# explains each). ``None`` means "no tag — the instance default applies". Every job is listed,
# so a new job fails this test until someone decides which side it belongs on.
_EXPECTED_MAX_RUNTIME_TAG: dict[str, str | None] = {
    "backup_copy": "21600",
    "backup_restore_drill": "86400",
    "backup_retention_janitor": "21600",
    "backup_verify": "21600",
    "consistency_check": "21600",
    "db_backup": "21600",
    "db_restore": "86400",
    "full_load_batch": "86400",
    "load_source": "86400",
    "mv_refresh": "21600",
    "scheduled_backup_run_due": "21600",
    "source_rebuild_db": "21600",
}


def test_every_job_declares_its_max_runtime() -> None:
    declared = {
        job.name: job.tags.get(MAX_RUNTIME_TAG)
        for job in defs.resolve_all_job_defs()
        if not job.name.startswith("__")
    }
    assert declared == _EXPECTED_MAX_RUNTIME_TAG


def test_long_run_tag_is_twenty_four_hours() -> None:
    assert LONG_RUN_TAGS == {"dagster/max_runtime": "86400"}


def test_run_failure_sensor_monitors_only_this_code_location() -> None:
    # On the shared instance monitor_all_code_locations=True would persist other projects'
    # run failures into geo's ops.run_failure_alerts. Omitting monitored_jobs already means
    # "every job in this code location" (Dagster matches the run's location+repository).
    assert notify_run_failure_sensor._monitor_all_code_locations is False


def test_op_name_differs_from_job_name() -> None:
    # Same op/job name makes the code location fail to load (dagster-boundary §10).
    assert run_mv_refresh_op.name == "run_mv_refresh"
    assert mv_refresh_job.name == "mv_refresh"
    assert run_mv_refresh_op.name != mv_refresh_job.name


def test_mv_op_requires_client_and_settings_resources() -> None:
    # T-290k: the release-gated mv_refresh bridges to load_jobs, so it needs settings
    # (lease TTL) alongside client, unlike the T-290a wiring proof.
    assert run_mv_refresh_op.required_resource_keys == {"client", "settings"}


def test_scheduled_backup_op_requires_only_admin_api_resource() -> None:
    assert run_due_scheduled_backup_op.required_resource_keys == {"admin_api"}


def test_default_resources_cover_required_keys() -> None:
    for key in ("admin_api", "client", "rustfs", "settings"):
        assert key in REQUIRED_RESOURCE_KEYS
        assert key in DEFAULT_RESOURCE_DEFINITIONS
