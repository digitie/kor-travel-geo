"""geo의 실행 예산을 common 예약·인프라 복구 계약에 연결한다."""

import logging
import re
from collections.abc import Mapping
from os import environ
from typing import Any

from dagster import SensorDefinition, job, multiprocess_executor
from kortravelcommon.dagster import RecoveryPolicy, has_active_run
from kortravelcommon.dagster_recovery import native_incarnation_recovery_sensor
from kortravelcommon.deadline import call_with_deadline

PROJECT = "geo"
LOCATION_NAME = environ.get(
    "KTG_DAGSTER_REPOSITORY_LOCATION_NAME", "kortravelgeo_dagster.definitions"
)
LONG_JOBS = frozenset({"full_load_batch", "load_source", "db_restore", "backup_restore_drill"})
IDEMPOTENT_RETRY_JOBS = frozenset({"backup_verify"})
#: ADR-070 D4 (ii): measured job-specific run caps = round(standalone wall s x 1.5). mv_refresh:
#: odroid standalone run 2026-10-18 (Dagster run 2bd07f07, quiet window) 2156.9 s -> 3235 s.
MAX_RUNTIME_OVERRIDES: dict[str, int] = {"mv_refresh": 3235}
GEO_EXECUTOR = multiprocess_executor.configured({"max_concurrent": 1})


def native_recovery_sensors() -> list[SensorDefinition]:
    """운영에서 확인한 origin을 명시한 경우에만 STOPPED 복구 센서를 추가한다."""
    key = "KTG_DAGSTER_NATIVE_RECOVERY_REPOSITORY_ORIGIN_ID"
    origin_id = environ.get(key)
    if origin_id is None or not origin_id.strip():
        return []
    if re.fullmatch(r"[0-9a-f]{40}", origin_id) is None:
        logging.getLogger(__name__).warning(
            "%s 형식이 잘못되어 native 복구 센서를 등록하지 않습니다.", key
        )
        return []
    return [
        native_incarnation_recovery_sensor(
            name="geo_native_incarnation_recovery",
            project=PROJECT,
            location_name=LOCATION_NAME,
            repository_origin_id=origin_id,
        )
    ]


def policy_for_job(name: str) -> RecoveryPolicy:
    """24시간이 필요한 작업과 비멱등 작업의 재시도 금지를 보존한다."""
    safe_retry = name in IDEMPOTENT_RETRY_JOBS
    default_runtime = 86400 if name in LONG_JOBS else 21600
    return RecoveryPolicy(
        max_runtime_seconds=MAX_RUNTIME_OVERRIDES.get(name, default_runtime),
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
