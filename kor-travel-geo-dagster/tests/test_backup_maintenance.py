"""backup_maintenance jobs wiring tests (T-290g ③): op config -> client leaf, no DB.

Each op is a thin wrapper over one AsyncAddressClient leaf, so the tests drive the ops with a
fake client and assert (a) the leaf is called with the resolved config, (b) a bad result
(corruption / sha256 mismatch / FAIL drill / janitor failed_count) raises a Dagster Failure,
and (c) the restore drill falls back to the latest available backup when no artifact_id is
configured. The retention janitor is exercised the same way (dry_run/keep_min pass-through,
skipped_locked = no-op success, failed_count > 0 = Failure).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from dagster import (
    DagsterInstance,
    Failure,
    RunRequest,
    SkipReason,
    build_op_context,
    build_schedule_context,
)
from kortravelgeo.exceptions import UnsupportedOnInstanceError

from kortravelgeo_dagster import backup_maintenance


class _FakeClient:
    def __init__(
        self,
        *,
        verify=None,
        copy=None,
        drill=None,
        backups=None,
        janitor=None,
        lifecycle_error=None,
    ) -> None:
        self._verify = verify
        self._copy = copy
        self._drill = drill
        self._backups = backups or []
        self._janitor = janitor
        self._lifecycle_error = lifecycle_error
        self.calls: dict[str, dict[str, object]] = {}

    async def require_db_lifecycle(self, feature):
        self.calls["lifecycle"] = {"feature": feature}
        if self._lifecycle_error is not None:
            raise self._lifecycle_error

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

    async def run_backup_retention_janitor(
        self, *, dry_run=False, keep_min_count=None, actor_id="system:backup_janitor"
    ):
        self.calls["janitor"] = {"dry_run": dry_run, "keep_min_count": keep_min_count}
        return self._janitor


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


def _janitor_result(*, expired=0, failed=0, skipped_locked=False, dry_run=False, keep_min=3):
    return SimpleNamespace(
        dry_run=dry_run,
        keep_min_count=keep_min,
        skipped_locked=skipped_locked,
        scanned=expired + failed + 1,
        protected_count=1,
        expired_count=expired,
        failed_count=failed,
        expired_artifact_ids=tuple(f"exp-{i}" for i in range(expired)),
        failed_artifact_ids=tuple(f"bad-{i}" for i in range(failed)),
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


@pytest.mark.asyncio
async def test_restore_drill_op_refuses_unsupported_instance_before_any_lookup() -> None:
    """T-312: on the shared instance (no CREATEDB) the (daily) drill stops with the reason
    before resolving a backup or creating the throwaway DB."""
    client = _FakeClient(
        drill=_drill_result("PASS"),
        backups=[SimpleNamespace(artifact_id="latest-1")],
        lifecycle_error=UnsupportedOnInstanceError(
            "restore drill: 공용 DB instance에서는 지원하지 않음 — 운영자가 manager ktdctl로 수행",
            hint="role kor_travel_geo_app: CREATEDB 권한 없음",
        ),
    )
    with (
        build_op_context(resources={"client": client}, op_config={}) as ctx,
        pytest.raises(Failure) as ei,
    ):
        await backup_maintenance.restore_drill_op(ctx)
    description = str(ei.value.description)
    assert "공용 DB instance에서는 지원하지 않음" in description
    assert "CREATEDB" in description
    assert client.calls["lifecycle"] == {"feature": "restore_drill"}
    assert "list" not in client.calls
    assert "drill" not in client.calls


@pytest.mark.asyncio
async def test_restore_drill_op_checks_capability_on_a_supported_instance() -> None:
    client = _FakeClient(drill=_drill_result("PASS"))
    with build_op_context(resources={"client": client}, op_config={"artifact_id": "art-1"}) as ctx:
        await backup_maintenance.restore_drill_op(ctx)
    assert client.calls["lifecycle"] == {"feature": "restore_drill"}
    assert client.calls["drill"]["artifact_id"] == "art-1"


@pytest.mark.asyncio
async def test_retention_janitor_op_defaults_pass_settings_keep_min() -> None:
    client = _FakeClient(janitor=_janitor_result(expired=2))
    with build_op_context(resources={"client": client}, op_config={}) as ctx:
        result = await backup_maintenance.retention_janitor_op(ctx)
    # no config -> not a dry run, keep_min left to Settings (None passed through)
    assert client.calls["janitor"] == {"dry_run": False, "keep_min_count": None}
    assert result["expired_count"] == 2
    assert result["expired_artifact_ids"] == ["exp-0", "exp-1"]
    assert result["failed_count"] == 0


@pytest.mark.asyncio
async def test_retention_janitor_op_passes_dry_run_and_keep_min() -> None:
    client = _FakeClient(janitor=_janitor_result(expired=1, dry_run=True, keep_min=5))
    with build_op_context(
        resources={"client": client}, op_config={"dry_run": True, "keep_min_count": 5}
    ) as ctx:
        result = await backup_maintenance.retention_janitor_op(ctx)
    assert client.calls["janitor"] == {"dry_run": True, "keep_min_count": 5}
    assert result["dry_run"] is True
    assert result["keep_min_count"] == 5


@pytest.mark.asyncio
async def test_retention_janitor_op_keep_min_zero_is_passed_through() -> None:
    client = _FakeClient(janitor=_janitor_result(expired=3, keep_min=0))
    with build_op_context(resources={"client": client}, op_config={"keep_min_count": 0}) as ctx:
        result = await backup_maintenance.retention_janitor_op(ctx)
    # explicit 0 must reach the leaf as 0 (not be coerced to None -> Settings default)
    assert client.calls["janitor"]["keep_min_count"] == 0
    assert result["keep_min_count"] == 0


@pytest.mark.asyncio
async def test_retention_janitor_op_negative_keep_min_raises_before_leaf() -> None:
    client = _FakeClient(janitor=_janitor_result())
    with (
        build_op_context(resources={"client": client}, op_config={"keep_min_count": -1}) as ctx,
        pytest.raises(Failure) as ei,
    ):
        await backup_maintenance.retention_janitor_op(ctx)
    assert "keep_min_count must be >= 0" in str(ei.value.description)
    assert "janitor" not in client.calls  # rejected before the leaf ran


def test_retention_janitor_job_runs_with_empty_run_config() -> None:
    # The real config schema must resolve dry_run's default and the optional keep_min_count.
    client = _FakeClient(janitor=_janitor_result(expired=1))
    result = backup_maintenance.backup_retention_janitor_job.execute_in_process(
        resources={"client": client}, run_config={}
    )
    assert result.success
    assert client.calls["janitor"] == {"dry_run": False, "keep_min_count": None}


@pytest.mark.asyncio
async def test_retention_janitor_op_skipped_locked_is_noop_success() -> None:
    client = _FakeClient(janitor=_janitor_result(skipped_locked=True))
    with build_op_context(resources={"client": client}, op_config={}) as ctx:
        result = await backup_maintenance.retention_janitor_op(ctx)
    assert result["skipped_locked"] is True
    assert result["expired_count"] == 0


@pytest.mark.asyncio
async def test_retention_janitor_op_failed_count_raises() -> None:
    client = _FakeClient(janitor=_janitor_result(expired=1, failed=2))
    with (
        build_op_context(resources={"client": client}, op_config={}) as ctx,
        pytest.raises(Failure) as ei,
    ):
        await backup_maintenance.retention_janitor_op(ctx)
    assert "could not expire 2 archive(s)" in str(ei.value.description)
    assert "bad-0, bad-1" in str(ei.value.description)


_SHARED_INSTANCE_REFUSAL = UnsupportedOnInstanceError(
    "restore drill: 공용 DB instance에서는 지원하지 않음 — 운영자가 manager ktdctl로 수행",
    hint="role kor_travel_geo_app: CREATEDB 권한 없음",
)


def test_restore_drill_schedule_skips_the_tick_on_an_unsupported_instance() -> None:
    """T-321: enabling the daily drill on the shared instance must not pile up Failure runs."""
    client = _FakeClient(lifecycle_error=_SHARED_INSTANCE_REFUSAL)

    result = backup_maintenance.restore_drill_schedule(
        build_schedule_context(resources={"client": client})
    )

    assert isinstance(result, SkipReason)
    assert result.skip_message == (
        "restore drill: 공용 DB instance에서는 지원하지 않음 — 운영자가 manager ktdctl로 수행 "
        "(role kor_travel_geo_app: CREATEDB 권한 없음)"
    )
    assert client.calls == {"lifecycle": {"feature": "restore_drill"}}


def test_restore_drill_schedule_tick_evaluation_yields_no_run_when_unsupported() -> None:
    """Through Dagster's own tick evaluation (the daemon path), not just a direct call."""
    client = _FakeClient(lifecycle_error=_SHARED_INSTANCE_REFUSAL)

    data = backup_maintenance.restore_drill_schedule.evaluate_tick(
        build_schedule_context(resources={"client": client})
    )

    assert data.run_requests == []
    assert data.skip_message is not None
    assert "공용 DB instance에서는 지원하지 않음" in data.skip_message


def test_restore_drill_schedule_requests_a_run_on_a_supported_instance() -> None:
    client = _FakeClient()
    scheduled_at = datetime(2026, 9, 29, 4, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    with DagsterInstance.local_temp() as instance:
        result = backup_maintenance.restore_drill_schedule(
            build_schedule_context(
                instance=instance,
                resources={"client": client},
                scheduled_execution_time=scheduled_at,
            )
        )
    assert isinstance(result, RunRequest)
    assert result.run_key == scheduled_at.isoformat()
    assert result.tags["kor_travel_geo.schedule"] == "backup_restore_drill_daily"
    assert result.tags["kor_travel_geo.job_kind"] == "backup_restore_drill"
    assert client.calls == {"lifecycle": {"feature": "restore_drill"}}


def test_restore_drill_schedule_still_launches_when_the_capability_check_errors() -> None:
    """A failing probe (DB down) must not silently skip: the run's op guard reports it and the
    run-failure sensor alerts — a skipped tick would alert nobody."""
    client = _FakeClient(lifecycle_error=RuntimeError("connection refused"))
    scheduled_at = datetime(2026, 9, 29, 4, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    with DagsterInstance.local_temp() as instance:
        result = backup_maintenance.restore_drill_schedule(
            build_schedule_context(
                instance=instance,
                resources={"client": client},
                scheduled_execution_time=scheduled_at,
            )
        )
    assert isinstance(result, RunRequest)
    assert result.run_key == scheduled_at.isoformat()


def test_restore_drill_schedule_requires_the_client_resource() -> None:
    assert backup_maintenance.restore_drill_schedule.required_resource_keys == {"client"}


def test_retention_janitor_schedule_is_daily_running_by_default() -> None:
    from dagster import DefaultScheduleStatus

    sched = backup_maintenance.retention_janitor_schedule
    assert sched.cron_schedule == "0 6 * * *"
    assert sched.execution_timezone == "Asia/Seoul"
    # D4: prod state declared in code (see test_definitions instigator-state test).
    assert sched.default_status is DefaultScheduleStatus.RUNNING
    assert sched.job.name == "backup_retention_janitor"


def test_maintenance_jobs_and_schedule_registered_in_definitions() -> None:
    from kortravelgeo_dagster.definitions import defs

    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert {
        "backup_verify",
        "backup_copy",
        "backup_restore_drill",
        "backup_retention_janitor",
    } <= job_names

    schedule_names = {sched.name for sched in defs.schedules}
    assert {"backup_restore_drill_daily", "backup_retention_janitor_daily"} <= schedule_names
    # T-321: the drill schedule's `client` resource param must be satisfiable by the code
    # location's resources, or the daemon errors on every tick.
    repo = defs.get_repository_def()
    assert "client" in repo.get_top_level_resources()
    assert repo.get_schedule_def("backup_restore_drill_daily").required_resource_keys == {"client"}
