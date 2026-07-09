"""submit_backup Dagster routing (T-290g): _launch_db_backup_dagster_run + the routing setting."""

from __future__ import annotations

from typing import ClassVar

import pytest

from kortravelgeo.api._dagster_client import DagsterLaunchError
from kortravelgeo.api.routers import admin as admin_mod
from kortravelgeo.exceptions import KorTravelGeoError
from kortravelgeo.settings import Settings


def test_dagster_executed_job_kinds_parses_csv_and_defaults_empty() -> None:
    routed = Settings(_env_file=None, dagster_executed_job_kinds="db_backup, db_restore")
    assert "db_backup" in routed.dagster_executed_job_kinds
    assert "db_restore" in routed.dagster_executed_job_kinds
    assert Settings(_env_file=None).dagster_executed_job_kinds == ()


class _FakeRow:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id


class _FakeRepo:
    inserted: ClassVar[dict] = {}

    def __init__(self, _engine: object) -> None:
        pass

    async def insert_load_job(self, *, kind: str, payload: dict, executor: str) -> _FakeRow:
        _FakeRepo.inserted = {"kind": kind, "payload": payload, "executor": executor}
        return _FakeRow("job-dag-1")


class _FakeExecutor:
    failed: ClassVar[tuple] = ()

    def __init__(self, _engine: object) -> None:
        pass

    async def mark_failed(self, job_id: str, message: str) -> None:
        _FakeExecutor.failed = (job_id, message)


class _FakeClient:
    def _engine(self) -> object:
        return object()


@pytest.mark.asyncio
async def test_launch_db_backup_dagster_run_inserts_dagster_row_and_launches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: dict = {}

    async def fake_launch(settings, *, job_name, run_config, tags):
        launched.update(job_name=job_name, run_config=run_config, tags=tags)
        return "run-xyz"

    monkeypatch.setattr(admin_mod, "AdminRepository", _FakeRepo)
    monkeypatch.setattr(admin_mod, "launch_dagster_run", fake_launch)

    job_id = await admin_mod._launch_db_backup_dagster_run(
        _FakeClient(), Settings(_env_file=None), {"jobs": ["addr"]}
    )

    assert job_id == "job-dag-1"
    assert _FakeRepo.inserted["executor"] == "dagster"
    assert _FakeRepo.inserted["kind"] == "db_backup"
    assert launched["job_name"] == "db_backup"
    op_config = launched["run_config"]["ops"]["run_db_backup"]["config"]
    assert op_config["job_id"] == "job-dag-1"
    assert op_config["payload"] == {"jobs": ["addr"]}
    assert launched["tags"] == {"kor_travel_geo.job_id": "job-dag-1"}


@pytest.mark.asyncio
async def test_launch_db_backup_dagster_run_failure_marks_failed_and_raises_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_launch(settings, *, job_name, run_config, tags):
        raise DagsterLaunchError("job not found")

    monkeypatch.setattr(admin_mod, "AdminRepository", _FakeRepo)
    monkeypatch.setattr(admin_mod, "LoadJobExecutor", _FakeExecutor)
    monkeypatch.setattr(admin_mod, "launch_dagster_run", fake_launch)

    with pytest.raises(KorTravelGeoError) as excinfo:
        await admin_mod._launch_db_backup_dagster_run(_FakeClient(), Settings(_env_file=None), {})

    assert excinfo.value.http_status == 502
    # the queued dagster row was failed so no worker leaves it stuck
    assert _FakeExecutor.failed[0] == "job-dag-1"
    assert "job not found" in _FakeExecutor.failed[1]
