"""backup_maintenance jobs wiring tests (T-290g ③): op config -> client leaf, no DB.

Each op is a thin wrapper over one AsyncAddressClient leaf, so the tests drive the ops with a
fake client and assert (a) the leaf is called with the resolved config, (b) a bad result
(corruption / sha256 mismatch / FAIL drill) raises a Dagster Failure, and (c) the restore
drill falls back to the latest available backup when no artifact_id is configured.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from dagster import Failure, build_op_context

from kortravelgeo_dagster import backup_maintenance


class _FakeClient:
    def __init__(self, *, verify=None, copy=None, drill=None, backups=None) -> None:
        self._verify = verify
        self._copy = copy
        self._drill = drill
        self._backups = backups or []
        self.calls: dict[str, dict[str, object]] = {}

    async def verify_backup(self, artifact_id, *, mode="quick"):
        self.calls["verify"] = {"artifact_id": artifact_id, "mode": mode}
        return self._verify

    async def copy_backup(self, artifact_id, *, target_dir):
        self.calls["copy"] = {"artifact_id": artifact_id, "target_dir": target_dir}
        return self._copy

    async def run_restore_drill(
        self, *, timestamp, artifact_id=None, archive_path=None, base_database=None, jobs=None
    ):
        self.calls["drill"] = {"timestamp": timestamp, "artifact_id": artifact_id}
        return self._drill

    async def list_artifacts(
        self, *, limit=50, artifact_type=None, state=None, expires_before=None
    ):
        self.calls["list"] = {"artifact_type": artifact_type, "state": state, "limit": limit}
        return self._backups[:limit]


def _verify_result(ok: bool):
    return SimpleNamespace(
        artifact_id="art-1",
        mode="quick",
        ok=ok,
        archive_sha256_matches=ok,
        internal_checksums_ok=ok,
        manifest_ok=ok,
    )


def _copy_result(verified: bool):
    return SimpleNamespace(
        artifact_id="art-1",
        source_path="/data/backups/a.tar.zst",
        destination_path="/off/a.tar.zst",
        sha256="deadbeef",
        verified=verified,
    )


def _drill_result(status: str):
    return SimpleNamespace(
        status=status,
        temp_database="kor_travel_geo_drill_x",
        duration_seconds=1.5,
        restored=True,
        reconcile_ok=True,
        smoke_ok=True,
        cleanup_ok=True,
    )


@pytest.mark.asyncio
async def test_verify_backup_op_ok_returns_metadata() -> None:
    client = _FakeClient(verify=_verify_result(True))
    with build_op_context(
        resources={"client": client}, op_config={"artifact_id": "art-1", "mode": "deep"}
    ) as ctx:
        result = await backup_maintenance.verify_backup_op(ctx)
    assert result["ok"] is True
    assert client.calls["verify"] == {"artifact_id": "art-1", "mode": "deep"}


@pytest.mark.asyncio
async def test_verify_backup_op_corruption_raises() -> None:
    client = _FakeClient(verify=_verify_result(False))
    with (
        build_op_context(resources={"client": client}, op_config={"artifact_id": "art-1"}) as ctx,
        pytest.raises(Failure) as ei,
    ):
        await backup_maintenance.verify_backup_op(ctx)
    assert "verify FAILED" in str(ei.value.description)


@pytest.mark.asyncio
async def test_copy_backup_op_ok_returns_metadata() -> None:
    client = _FakeClient(copy=_copy_result(True))
    with build_op_context(
        resources={"client": client}, op_config={"artifact_id": "art-1", "target_dir": "/off"}
    ) as ctx:
        result = await backup_maintenance.copy_backup_op(ctx)
    assert result["verified"] is True
    assert result["destination_path"] == "/off/a.tar.zst"
    assert client.calls["copy"] == {"artifact_id": "art-1", "target_dir": "/off"}


@pytest.mark.asyncio
async def test_copy_backup_op_mismatch_raises() -> None:
    client = _FakeClient(copy=_copy_result(False))
    with (
        build_op_context(
            resources={"client": client}, op_config={"artifact_id": "art-1", "target_dir": "/off"}
        ) as ctx,
        pytest.raises(Failure) as ei,
    ):
        await backup_maintenance.copy_backup_op(ctx)
    assert "copy sha256" in str(ei.value.description)


@pytest.mark.asyncio
async def test_restore_drill_op_pass_with_explicit_artifact() -> None:
    client = _FakeClient(drill=_drill_result("PASS"))
    with build_op_context(resources={"client": client}, op_config={"artifact_id": "art-1"}) as ctx:
        result = await backup_maintenance.restore_drill_op(ctx)
    assert result["status"] == "PASS"
    assert client.calls["drill"]["artifact_id"] == "art-1"
    assert client.calls["drill"]["timestamp"]  # a per-run timestamp was generated
    assert "list" not in client.calls  # explicit artifact_id -> no latest lookup


@pytest.mark.asyncio
async def test_restore_drill_op_defaults_to_latest_backup() -> None:
    client = _FakeClient(
        drill=_drill_result("PASS"), backups=[SimpleNamespace(artifact_id="latest-1")]
    )
    with build_op_context(resources={"client": client}, op_config={}) as ctx:
        await backup_maintenance.restore_drill_op(ctx)
    assert client.calls["list"] == {"artifact_type": "db_backup", "state": "available", "limit": 1}
    assert client.calls["drill"]["artifact_id"] == "latest-1"


@pytest.mark.asyncio
async def test_restore_drill_op_no_backup_raises() -> None:
    client = _FakeClient(drill=_drill_result("PASS"), backups=[])
    with (
        build_op_context(resources={"client": client}, op_config={}) as ctx,
        pytest.raises(Failure) as ei,
    ):
        await backup_maintenance.restore_drill_op(ctx)
    assert "no available db_backup" in str(ei.value.description)


@pytest.mark.asyncio
async def test_restore_drill_op_fail_raises() -> None:
    client = _FakeClient(drill=_drill_result("FAIL"))
    with (
        build_op_context(resources={"client": client}, op_config={"artifact_id": "art-1"}) as ctx,
        pytest.raises(Failure) as ei,
    ):
        await backup_maintenance.restore_drill_op(ctx)
    assert "restore drill FAILED" in str(ei.value.description)


def test_maintenance_jobs_and_schedule_registered_in_definitions() -> None:
    from kortravelgeo_dagster.definitions import defs

    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert {"backup_verify", "backup_copy", "backup_restore_drill"} <= job_names

    schedule_names = {sched.name for sched in defs.schedules}
    assert "backup_restore_drill_daily" in schedule_names
