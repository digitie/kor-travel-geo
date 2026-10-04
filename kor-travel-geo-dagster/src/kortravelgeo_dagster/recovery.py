"""geo의 실행 예산을 common 예약·인프라 복구 계약에 연결한다."""

from collections.abc import Mapping
from os import environ
from typing import Any

from dagster import job, multiprocess_executor
from kortravelcommon.dagster import RecoveryPolicy, has_active_run
from kortravelcommon.deadline import call_with_deadline

PROJECT = "geo"
LOCATION_NAME = environ.get(
    "KTG_DAGSTER_REPOSITORY_LOCATION_NAME", "kortravelgeo_dagster.definitions"
)
LONG_JOBS = frozenset({"full_load_batch", "load_source", "db_restore", "backup_restore_drill"})
IDEMPOTENT_RETRY_JOBS = frozenset({"backup_verify"})
GEO_EXECUTOR = multiprocess_executor.configured({"max_concurrent": 1})


def policy_for_job(name: str) -> RecoveryPolicy:
    """24시간이 필요한 작업과 비멱등 작업의 재시도 금지를 보존한다."""
    safe_retry = name in IDEMPOTENT_RETRY_JOBS
    return RecoveryPolicy(
        max_runtime_seconds=86400 if name in LONG_JOBS else 21600,
        idempotent=safe_retry,
        infrastructure_retries=1 if safe_retry else 0,
    )


def geo_job(*, name: str, tags: Mapping[str, str] | None = None, **kwargs: Any) -> Any:
    """각 직접 실행·예약·API 발화에도 같은 실행 상한과 메모리 예산을 적용한다."""
    return job(
        name=name,
        tags={**(tags or {}), **policy_for_job(name).tags(project=PROJECT, job_name=name)},
        executor_def=GEO_EXECUTOR,
        **kwargs,
    )


def schedule_eligible(job_name: str) -> Any:
    """이 location의 같은 작업이나 조회 장애가 있으면 발화를 보류한다."""

    def eligible(context: Any) -> bool:
        try:
            return not call_with_deadline(
                lambda: has_active_run(
                    context.instance,
                    job_name=job_name,
                    project=PROJECT,
                    location_name=LOCATION_NAME,
                ),
                timeout_seconds=10,
            )
        except Exception:
            context.log.warning("실행 저장소를 확인하지 못해 이번 예약 발화를 보류합니다.")
            return False

    return eligible
