"""명시 origin 설정만 복구 센서를 등록하고 다른 정의를 보존한다."""

import importlib
import logging

import pytest
from dagster import DefaultSensorStatus

from kortravelgeo_dagster import recovery

_ENV = "KTG_DAGSTER_NATIVE_RECOVERY_REPOSITORY_ORIGIN_ID"
_VALID = "0123456789abcdef" * 2 + "01234567"


@pytest.mark.parametrize("value", [None, "", " ", "\t\n"])
def test_missing_origin_does_not_register(value, monkeypatch, caplog):
    if value is None:
        monkeypatch.delenv(_ENV, raising=False)
    else:
        monkeypatch.setenv(_ENV, value)
    with caplog.at_level(logging.WARNING):
        assert recovery.native_recovery_sensors() == []
    assert not caplog.records


@pytest.mark.parametrize("value", [
    "not-an-origin", "a" * 39, "a" * 41, "A" * 40,
    "g" * 40, " " + _VALID, _VALID + " ", _VALID + "\n",
    "\uff10" * 40, "sensitive-invalid-value",
])
def test_invalid_origin_skips_only_recovery_without_logging_value(value, monkeypatch, caplog):
    monkeypatch.setenv(_ENV, value)
    with caplog.at_level(logging.WARNING):
        assert recovery.native_recovery_sensors() == []
    assert len(caplog.records) == 1
    assert _ENV in caplog.text
    assert value not in caplog.text


def test_valid_origin_registers_common_sensor_stopped(monkeypatch):
    monkeypatch.setenv(_ENV, _VALID)
    from unittest.mock import Mock

    factory = Mock(wraps=recovery.native_incarnation_recovery_sensor)
    monkeypatch.setattr(recovery, "native_incarnation_recovery_sensor", factory)
    sensors = recovery.native_recovery_sensors()
    factory.assert_called_once_with(
        name="geo_native_incarnation_recovery",
        project="geo",
        location_name=recovery.LOCATION_NAME,
        repository_origin_id=_VALID,
    )
    assert len(sensors) == 1
    sensor = sensors[0]
    assert sensor.name == "geo_native_incarnation_recovery"
    assert sensor.default_status is DefaultSensorStatus.STOPPED
    assert sensor.minimum_interval_seconds == 60


@pytest.mark.parametrize("value", [None, "", "private-invalid-origin", _VALID])
def test_optional_registration_preserves_existing_definitions(value, monkeypatch):
    from kortravelgeo_dagster import definitions

    def snapshot():
        repo = definitions.defs.get_repository_def()
        return {
            "jobs": {
                job.name: (dict(job.tags), job.executor_def.name)
                for job in repo.get_all_jobs()
            },
            "schedules": {
                item.name: (item.cron_schedule, item.default_status)
                for item in repo.schedule_defs
            },
            "sensors": {
                item.name: item.default_status for item in repo.sensor_defs
            },
            "resources": set(definitions.defs.resources),
        }

    # reload가 다른 시험의 module-level defs에 새 설정을 남기지 않도록 원복한다.
    try:
        with monkeypatch.context() as env:
            env.delenv(_ENV, raising=False)
            importlib.reload(definitions)
            before = snapshot()
            if value is not None:
                env.setenv(_ENV, value)
            importlib.reload(definitions)
            after = snapshot()
            if value == _VALID:
                assert after["sensors"].pop("geo_native_incarnation_recovery") is (
                    DefaultSensorStatus.STOPPED
                )
            assert after == before
            assert after["sensors"]["geo_infrastructure_retry_backup_verify"] is (
                DefaultSensorStatus.RUNNING
            )
            retry_jobs = {
                name for name, (tags, _) in after["jobs"].items()
                if tags.get("dagster/max_retries") == "1"
            }
            assert retry_jobs == {"backup_verify"}
    finally:
        importlib.reload(definitions)
