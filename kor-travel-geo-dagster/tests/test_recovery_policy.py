"""공통 예약 경계와 geo의 멱등성·메모리 예산을 실제 run store로 검증한다."""

from types import SimpleNamespace
from unittest.mock import Mock

from dagster import DagsterInstance, DagsterRunStatus
from kortravelcommon.dagster import PROJECT_TAG

from kortravelgeo_dagster.definitions import defs
from kortravelgeo_dagster.recovery import LONG_JOBS, policy_for_job, schedule_eligible


def test_only_read_only_verify_allows_infrastructure_retry() -> None:
    for job in defs.resolve_all_job_defs():
        policy = policy_for_job(job.name)
        assert policy.idempotent is (job.name == "backup_verify")
        assert job.tags["dagster/max_retries"] == ("1" if policy.idempotent else "0")
        assert job.tags["dagster/retry_on_asset_or_op_failure"] == "false"
        assert int(job.tags["dagster/max_runtime"]) == (86400 if job.name in LONG_JOBS else 21600)
        assert job.executor_def.name == "multiprocess"
        result = job.executor_def.apply_config_mapping({"config": {}})
        assert result.success
        assert result.value["config"]["max_concurrent"] == 1


def test_same_job_other_project_does_not_block_but_geo_does() -> None:
    with DagsterInstance.local_temp() as instance:
        context = SimpleNamespace(instance=instance, log=Mock())
        eligible = schedule_eligible("backup_verify")
        assert eligible(context)
        instance.create_run_for_job(
            defs.get_job_def("backup_verify"),
            run_config={"ops": {"verify_backup": {"config": {"artifact_id": "test"}}}},
            status=DagsterRunStatus.STARTED,
            tags={PROJECT_TAG: "weather"},
        )
        assert eligible(context)
        instance.create_run_for_job(
            defs.get_job_def("backup_verify"),
            run_config={"ops": {"verify_backup": {"config": {"artifact_id": "test"}}}},
            status=DagsterRunStatus.STARTED,
            tags={PROJECT_TAG: "geo"},
        )
        assert not eligible(context)


def test_run_store_failure_defers_and_next_tick_recovers() -> None:
    store = Mock()
    store.get_runs.side_effect = RuntimeError("store unavailable")
    context = SimpleNamespace(instance=store, log=Mock())
    eligible = schedule_eligible("backup_verify")
    assert not eligible(context)
    context.log.warning.assert_called_once()
    store.get_runs.side_effect = None
    store.get_runs.return_value = []
    assert eligible(context)
