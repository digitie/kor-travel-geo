"""Dagster observability endpoints.

The Dagster code location lives outside the main ``kortravelgeo`` package. This
router reads Dagster webserver GraphQL and normalizes it for the admin UI, and
surfaces the app-persisted ``ops.run_failure_alerts`` ledger (written by the
Dagster run-failure sensor, T-290h) via a recent-failures list, a per-run
``failure_alert`` on run detail, and an acknowledge mutation.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from kortravelgeo.api._dagster_client import (
    DagsterUrlConfigurationError,
    _candidate_graphql_url,
    _dagster_urls,
    _DagsterUrls,
    _normalised_allowed_hosts,
    _validated_http_url,
)
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.security import KNOWN_ADMIN_ROLES, require_role
from kortravelgeo.client import AsyncAddressClient
from kortravelgeo.dto.admin import OpsArtifact, RunFailureAlert
from kortravelgeo.dto.dagster import (
    DagsterAssetGroup,
    DagsterBackupArtifact,
    DagsterGraphqlError,
    DagsterInstigationTick,
    DagsterJob,
    DagsterRepository,
    DagsterResponseMeta,
    DagsterRunDetailData,
    DagsterRunDetailResponse,
    DagsterRunEvent,
    DagsterRunFailureAckResponse,
    DagsterRunFailureAlert,
    DagsterRunFailuresData,
    DagsterRunFailuresResponse,
    DagsterRunSummary,
    DagsterSchedule,
    DagsterSensor,
    DagsterSummaryData,
    DagsterSummaryResponse,
)
from kortravelgeo.infra.backup import BACKUP_ARTIFACT_TYPE, backup_download_url
from kortravelgeo.settings import Settings, get_settings

router = APIRouter(
    prefix="/ops/dagster",
    tags=["ops", "dagster"],
    dependencies=[Depends(require_role(*KNOWN_ADMIN_ROLES))],
)

JsonDict = dict[str, Any]

_JOB_ID_TAG = "kor_travel_geo.job_id"

# On the shared Dagster webserver (dagster-shared plan, stage 3) one instance holds several
# projects' code locations and runs. The summary therefore reads only geo's own location:
# ``repositoryOrError`` with the settings' location/repository selector (the same values
# launchRun uses) and ``runsOrError`` filtered by ``.dagster/repository`` — the hidden tag
# Dagster sets on every run at creation (``<repository>@<location>``; GraphQL hides it from
# ``tags`` output, but the filter still matches it). Against today's single-tenant webserver
# the result is identical, so this ships before the cutover.
_DAGSTER_SUMMARY_QUERY = """
query KorTravelGeoDagsterSummary(
  $limit: Int!,
  $repositoryLocationName: String!,
  $repositoryName: String!,
  $repositoryLabel: String!
) {
  version
  repositoryOrError(
    repositorySelector: {
      repositoryLocationName: $repositoryLocationName,
      repositoryName: $repositoryName
    }
  ) {
    __typename
    ... on Repository {
      name
      location { name }
      pipelines { name isJob }
      schedules {
        name
        cronSchedule
        executionTimezone
        scheduleState {
          status
          ticks(limit: 3, statuses: [STARTED, SKIPPED, SUCCESS, FAILURE]) {
            tickId
            status
            timestamp
            endTimestamp
            runIds
            runKeys
            skipReason
            cursor
            error { message stack className }
          }
        }
        futureTicks(limit: 2) {
          results { timestamp }
        }
      }
      sensors {
        name
        sensorState {
          status
          ticks(limit: 3, statuses: [STARTED, SKIPPED, SUCCESS, FAILURE]) {
            tickId
            status
            timestamp
            endTimestamp
            runIds
            runKeys
            skipReason
            cursor
            error { message stack className }
          }
        }
      }
      assetNodes {
        id
        groupName
        assetKey { path }
      }
    }
    ... on RepositoryNotFoundError {
      message
    }
    ... on PythonError {
      message
    }
  }
  runsOrError(
    filter: { tags: [{ key: ".dagster/repository", value: $repositoryLabel }] },
    limit: $limit
  ) {
    __typename
    ... on Runs {
      results {
        runId
        jobName
        status
        startTime
        endTime
        updateTime
        tags { key value }
      }
    }
    ... on PythonError {
      message
    }
  }
  activeRuns: runsOrError(
    filter: {
      tags: [{ key: ".dagster/repository", value: $repositoryLabel }],
      statuses: [NOT_STARTED, QUEUED, STARTING, STARTED, CANCELING]
    },
    limit: 1000
  ) {
    __typename
    ... on Runs {
      results {
        runId
        jobName
        status
        startTime
        endTime
        updateTime
        tags { key value }
      }
    }
    ... on PythonError {
      message
    }
  }
}
"""

_DAGSTER_RUN_DETAIL_QUERY = """
query KorTravelGeoDagsterRunDetail(
  $runId: ID!, $eventLimit: Int!, $afterCursor: String
) {
  runOrError(runId: $runId) {
    __typename
    ... on Run {
      runId
      jobName
      status
      startTime
      endTime
      updateTime
      tags { key value }
      repositoryOrigin { repositoryLocationName repositoryName }
      eventConnection(limit: $eventLimit, afterCursor: $afterCursor) {
        cursor
        hasMore
        events {
          __typename
          ... on MessageEvent {
            message
            timestamp
            level
            stepKey
            eventType
          }
          ... on ErrorEvent {
            error { message stack className }
          }
        }
      }
    }
    ... on RunNotFoundError {
      message
      runId
    }
    ... on PythonError {
      message
      stack
      className
    }
  }
}
"""


# Dagster backend URL resolution + SSRF allowlist live in kortravelgeo.api._dagster_client
# (shared with the T-290g launch adapter). Imported above; _safe_summary_* below use them.


def _safe_summary_dagster_url(settings: Settings) -> str:
    """Return a browser-safe Dagster URL for config-error summaries.

    Config errors can come from the public URL itself. In that path we still return a
    summary DTO, but must not echo a raw invalid value into iframe/link fields.
    """
    if settings.dagster_public_url.strip():
        try:
            return _validated_http_url(
                settings.dagster_public_url,
                setting_name="dagster_public_url",
                allowed_hosts=None,
            ).rstrip("/")
        except DagsterUrlConfigurationError:
            pass
    try:
        return _validated_http_url(
            settings.dagster_url,
            setting_name="dagster_url",
            allowed_hosts=_normalised_allowed_hosts(settings),
        ).rstrip("/")
    except DagsterUrlConfigurationError:
        pass
    return ""


def _safe_summary_graphql_url(settings: Settings) -> str:
    """Return a validated GraphQL URL for config-error summaries/run-details, or "".

    Mirrors :func:`_safe_summary_dagster_url` (#443): the config-error path must not echo
    the raw ``_candidate_graphql_url`` into a summary/run-detail DTO. ``graphql_url`` is the
    internal backend target, so it keeps the SSRF host allowlist and the ``/graphql`` path
    check; an invalid value collapses to ``""`` instead of being surfaced verbatim.
    """
    try:
        return _validated_http_url(
            _candidate_graphql_url(settings),
            setting_name="dagster_graphql_url",
            allowed_hosts=_normalised_allowed_hosts(settings),
            require_graphql_path=True,
        )
    except DagsterUrlConfigurationError:
        return ""


def _dict(value: object) -> JsonDict:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _string(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _string_list(value: object) -> list[str]:
    return [item for item in _list(value) if isinstance(item, str)]


def _asset_name(asset_node: JsonDict) -> str:
    asset_key = _dict(asset_node.get("assetKey"))
    path = [part for part in _list(asset_key.get("path")) if isinstance(part, str)]
    if path:
        return "/".join(path)
    return _string(asset_node.get("id"), "unknown_asset")


def _parse_jobs(raw_jobs: list[object]) -> list[DagsterJob]:
    jobs: list[DagsterJob] = []
    for raw in raw_jobs:
        entry = _dict(raw)
        jobs.append(
            DagsterJob(
                name=_string(entry.get("name"), "unknown_job"),
                is_job=bool(entry.get("isJob")),
            )
        )
    return jobs


def _parse_graphql_error(raw_error: object) -> DagsterGraphqlError | None:
    error = _dict(raw_error)
    if not error:
        return None
    return DagsterGraphqlError(
        message=_optional_string(error.get("message")),
        stack=_string_list(error.get("stack")),
        class_name=_optional_string(error.get("className")),
    )


def _graphql_error_message(raw_error: object) -> str:
    error = _dict(raw_error)
    message = _optional_string(error.get("message"))
    if message:
        return message
    # Do not echo ``str(raw_error)`` — an unshaped GraphQL error can carry internal
    # detail. Surface a fixed generic message instead.
    return "Dagster GraphQL 오류 응답"


def _sanitized_request_error(exc: Exception) -> str:
    """Return a class-tagged generic message with no internal Dagster URL/detail.

    ``str(exc)`` for ``httpx.HTTPStatusError`` embeds the request URL (the internal
    Dagster host), so only the exception class name plus a fixed phrase is exposed.
    """
    return f"Dagster 요청 실패 ({type(exc).__name__})"


def _parse_ticks(raw_ticks: object) -> list[DagsterInstigationTick]:
    ticks: list[DagsterInstigationTick] = []
    for raw in _list(raw_ticks):
        entry = _dict(raw)
        tick_id = _string(entry.get("tickId"))
        if not tick_id:
            continue
        ticks.append(
            DagsterInstigationTick(
                tick_id=tick_id,
                status=_string(entry.get("status"), "UNKNOWN"),
                timestamp=_optional_float(entry.get("timestamp")) or 0.0,
                end_timestamp=_optional_float(entry.get("endTimestamp")),
                run_ids=_string_list(entry.get("runIds")),
                run_keys=_string_list(entry.get("runKeys")),
                skip_reason=_optional_string(entry.get("skipReason")),
                cursor=_optional_string(entry.get("cursor")),
                error=_parse_graphql_error(entry.get("error")),
            )
        )
    return ticks


def _future_tick_timestamps(entry: JsonDict) -> list[float]:
    """Upcoming scheduled fire times (epoch) from the GraphQL ``futureTicks`` block."""
    timestamps: list[float] = []
    for raw in _list(_dict(entry.get("futureTicks")).get("results")):
        ts = _optional_float(_dict(raw).get("timestamp"))
        if ts is not None:
            timestamps.append(ts)
    return timestamps


def _schedule_overdue(
    *,
    status: str | None,
    last_tick_ts: float | None,
    future_ticks: list[float],
    now_ts: float,
    grace_seconds: float,
) -> bool:
    """A RUNNING schedule is overdue when it missed a scheduled fire.

    Uses Dagster's own cron evaluation (``futureTicks``) rather than a cron parser:
    the gap between consecutive future ticks approximates the cron interval, and if
    more than one interval (plus a grace window) has elapsed since the last actual
    tick, a fire was missed — the scheduler daemon is behind. Never flags a stopped
    or never-ticked schedule.
    """
    if status != "RUNNING" or last_tick_ts is None or len(future_ticks) < 2:
        return False
    interval = future_ticks[1] - future_ticks[0]
    if interval <= 0:
        return False
    return (now_ts - last_tick_ts) > (interval + grace_seconds)


def _parse_schedules(
    raw_schedules: list[object], *, now_ts: float, grace_seconds: float
) -> list[DagsterSchedule]:
    schedules: list[DagsterSchedule] = []
    for raw in raw_schedules:
        entry = _dict(raw)
        state = _dict(entry.get("scheduleState"))
        status = _optional_string(state.get("status"))
        recent_ticks = _parse_ticks(state.get("ticks"))
        future_ticks = _future_tick_timestamps(entry)
        last_tick_ts = max((tick.timestamp for tick in recent_ticks), default=None)
        schedules.append(
            DagsterSchedule(
                name=_string(entry.get("name"), "unknown_schedule"),
                cron_schedule=_optional_string(entry.get("cronSchedule")),
                execution_timezone=_optional_string(entry.get("executionTimezone")),
                status=status,
                recent_ticks=recent_ticks,
                next_tick_at=future_ticks[0] if future_ticks else None,
                overdue=_schedule_overdue(
                    status=status,
                    last_tick_ts=last_tick_ts,
                    future_ticks=future_ticks,
                    now_ts=now_ts,
                    grace_seconds=grace_seconds,
                ),
            )
        )
    return schedules


def _parse_sensors(raw_sensors: list[object]) -> list[DagsterSensor]:
    sensors: list[DagsterSensor] = []
    for raw in raw_sensors:
        entry = _dict(raw)
        state = _dict(entry.get("sensorState"))
        sensors.append(
            DagsterSensor(
                name=_string(entry.get("name"), "unknown_sensor"),
                status=_optional_string(state.get("status")),
                recent_ticks=_parse_ticks(state.get("ticks")),
            )
        )
    return sensors


def _parse_asset_groups(raw_assets: list[object]) -> list[DagsterAssetGroup]:
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for raw in raw_assets:
        entry = _dict(raw)
        group_name = _string(entry.get("groupName"), "default")
        groups[group_name].append(_asset_name(entry))

    return [
        DagsterAssetGroup(
            group_name=group_name,
            asset_count=len(assets),
            assets=sorted(assets),
        )
        for group_name, assets in sorted(groups.items())
    ]


def _parse_repository(
    raw_repository: JsonDict, *, now_ts: float, grace_seconds: float
) -> tuple[list[DagsterRepository], list[str]]:
    """Parse the location-scoped ``repositoryOrError`` result into 0 or 1 repositories."""
    if raw_repository.get("__typename") != "Repository":
        # RepositoryNotFoundError (geo's location is not loaded in this workspace) or
        # PythonError. Either way nothing of another project's is shown instead.
        message = _optional_string(raw_repository.get("message")) or "Dagster repository 조회 실패"
        return [], [message]

    location = _dict(raw_repository.get("location"))
    assets = _list(raw_repository.get("assetNodes"))
    repository = DagsterRepository(
        name=_string(raw_repository.get("name"), "__repository__"),
        location_name=_string(location.get("name"), "unknown_location"),
        jobs=_parse_jobs(_list(raw_repository.get("pipelines"))),
        schedules=_parse_schedules(
            _list(raw_repository.get("schedules")),
            now_ts=now_ts,
            grace_seconds=grace_seconds,
        ),
        sensors=_parse_sensors(_list(raw_repository.get("sensors"))),
        asset_count=len(assets),
        asset_groups=_parse_asset_groups(assets),
    )
    return [repository], []


def _repository_label(settings: Settings) -> str:
    """Value of Dagster's ``.dagster/repository`` run tag for geo's code location."""
    return f"{settings.dagster_repository_name}@{settings.dagster_repository_location_name}"


def _summary_variables(settings: Settings, *, limit: int) -> dict[str, object]:
    return {
        "limit": limit,
        "repositoryLocationName": settings.dagster_repository_location_name,
        "repositoryName": settings.dagster_repository_name,
        "repositoryLabel": _repository_label(settings),
    }


def _run_belongs_to_location(raw_run: JsonDict, settings: Settings) -> bool:
    """True when the run was launched from geo's own code location.

    Run ids are global on a shared instance, so a run id alone could name another
    project's run. The origin is set on every run launched from a code location.
    """
    origin = _dict(raw_run.get("repositoryOrigin"))
    return (
        origin.get("repositoryLocationName") == settings.dagster_repository_location_name
        and origin.get("repositoryName") == settings.dagster_repository_name
    )


def _run_tags(entry: JsonDict) -> dict[str, str]:
    return {
        _string(_dict(tag).get("key")): _string(_dict(tag).get("value"))
        for tag in _list(entry.get("tags"))
        if _string(_dict(tag).get("key"))
    }


def _parse_runs(raw_runs: JsonDict) -> tuple[list[DagsterRunSummary], dict[str, int], list[str]]:
    if raw_runs.get("__typename") != "Runs":
        message = _optional_string(raw_runs.get("message")) or "Dagster run 조회 실패"
        return [], {}, [message]

    runs: list[DagsterRunSummary] = []
    counts: Counter[str] = Counter()
    for raw in _list(raw_runs.get("results")):
        entry = _dict(raw)
        status = _string(entry.get("status"), "UNKNOWN")
        counts[status] += 1
        runs.append(_parse_run_summary(entry))
    return runs, dict(counts), []


def _parse_run_summary(entry: JsonDict) -> DagsterRunSummary:
    return DagsterRunSummary(
        run_id=_string(entry.get("runId"), "unknown_run"),
        job_name=_optional_string(entry.get("jobName")),
        status=_string(entry.get("status"), "UNKNOWN"),
        start_time=_optional_float(entry.get("startTime")),
        end_time=_optional_float(entry.get("endTime")),
        update_time=_optional_float(entry.get("updateTime")),
        tags=_run_tags(entry),
    )


def _parse_run_event(raw_event: object) -> DagsterRunEvent:
    event = _dict(raw_event)
    return DagsterRunEvent(
        event_type=_string(event.get("__typename"), "DagsterEvent"),
        message=_optional_string(event.get("message")),
        timestamp=_optional_string(event.get("timestamp")),
        level=_optional_string(event.get("level")),
        step_id=_optional_string(event.get("stepKey")),
        dagster_event_type=_optional_string(event.get("eventType")),
        error=_parse_graphql_error(event.get("error")),
    )


def _parse_run_detail(
    raw_run: JsonDict,
    *,
    dagster_urls: _DagsterUrls,
    checked_at: datetime,
    settings: Settings,
) -> DagsterRunDetailData:
    typename = _string(raw_run.get("__typename"))
    if typename == "Run" and not _run_belongs_to_location(raw_run, settings):
        # Another project's run on a shared instance: answer exactly like an unknown id,
        # so neither its events nor its existence leak through geo's admin API.
        return DagsterRunDetailData(
            status="not_found",
            dagster_url=dagster_urls.dagster_url,
            graphql_url=dagster_urls.graphql_url,
            checked_at=checked_at,
            errors=["Dagster run을 찾을 수 없습니다."],
        )
    if typename == "Run":
        event_connection = _dict(raw_run.get("eventConnection"))
        return DagsterRunDetailData(
            status="ok",
            dagster_url=dagster_urls.dagster_url,
            graphql_url=dagster_urls.graphql_url,
            checked_at=checked_at,
            run=_parse_run_summary(raw_run),
            events=[
                _parse_run_event(raw_event) for raw_event in _list(event_connection.get("events"))
            ],
            event_cursor=_optional_string(event_connection.get("cursor")),
            event_has_more=bool(event_connection.get("hasMore")),
        )
    if typename == "RunNotFoundError":
        return DagsterRunDetailData(
            status="not_found",
            dagster_url=dagster_urls.dagster_url,
            graphql_url=dagster_urls.graphql_url,
            checked_at=checked_at,
            errors=[_string(raw_run.get("message"), "Dagster run을 찾을 수 없습니다.")],
        )
    if typename == "PythonError":
        message = _optional_string(raw_run.get("message")) or "Dagster run 상세 조회 실패"
        return DagsterRunDetailData(
            status="error",
            dagster_url=dagster_urls.dagster_url,
            graphql_url=dagster_urls.graphql_url,
            checked_at=checked_at,
            errors=[message],
        )
    return DagsterRunDetailData(
        status="error",
        dagster_url=dagster_urls.dagster_url,
        graphql_url=dagster_urls.graphql_url,
        checked_at=checked_at,
        errors=[f"알 수 없는 Dagster run 응답 타입: {typename or 'unknown'}"],
    )


async def _post_graphql(
    client: httpx.AsyncClient,
    graphql_url: str,
    variables: dict[str, object],
    query: str = _DAGSTER_SUMMARY_QUERY,
) -> JsonDict:
    # 응답을 전부 버퍼링하기 전에 상한을 적용한다. 오류 stack도 무한히 적재하지 않는다.
    try:
        async with asyncio.timeout(client.timeout.read or 30.0):
            async with client.stream(
                "POST", graphql_url, json={"query": query, "variables": variables}
            ) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 4 * 1024 * 1024:
                        raise ValueError("Dagster 응답이 4 MiB 상한을 넘었습니다.")
                    content.extend(chunk)
                return _dict(json.loads(content))
    except TimeoutError as exc:
        raise httpx.ReadTimeout("Dagster 전체 응답 시간 상한 초과") from exc


def _response_meta(*, started_at: float) -> DagsterResponseMeta:
    return DagsterResponseMeta(duration_ms=round((perf_counter() - started_at) * 1000, 3))


def _summary_response(data: DagsterSummaryData, *, started_at: float) -> DagsterSummaryResponse:
    return DagsterSummaryResponse(data=data, meta=_response_meta(started_at=started_at))


def _run_detail_response(
    data: DagsterRunDetailData, *, started_at: float
) -> DagsterRunDetailResponse:
    return DagsterRunDetailResponse(data=data, meta=_response_meta(started_at=started_at))


def _backup_artifact_dto(
    artifact: OpsArtifact,
    *,
    settings: Settings,
) -> DagsterBackupArtifact:
    download_url = None
    if artifact.state == "available" and artifact.sha256:
        download_url = backup_download_url(artifact, settings)
    return DagsterBackupArtifact(
        artifact_id=artifact.artifact_id,
        state=artifact.state,
        display_name=artifact.display_name,
        size_bytes=artifact.size_bytes,
        download_url=download_url,
    )


async def _with_backup_artifact(
    detail: DagsterRunDetailData,
    *,
    client: AsyncAddressClient,
    settings: Settings,
) -> DagsterRunDetailData:
    job_id = detail.run.tags.get(_JOB_ID_TAG) if detail.run is not None else None
    if not job_id:
        return detail
    try:
        artifact = await client.get_artifact_by_job_id(
            job_id,
            artifact_type=BACKUP_ARTIFACT_TYPE,
        )
    except Exception as exc:  # pragma: no cover - exact DB errors are driver-dependent.
        return detail.model_copy(
            update={
                "errors": [
                    *detail.errors,
                    f"backup artifact 조회 실패 ({type(exc).__name__})",
                ]
            }
        )
    if artifact is None:
        return detail
    return detail.model_copy(
        update={"backup_artifact": _backup_artifact_dto(artifact, settings=settings)}
    )


def _run_failure_alert_dto(alert: RunFailureAlert) -> DagsterRunFailureAlert:
    return DagsterRunFailureAlert(
        run_id=alert.run_id,
        job_id=alert.job_id,
        job_name=alert.job_name,
        job_kind=alert.job_kind,
        status=alert.status,
        error_code=alert.error_code,
        run_failed_at=alert.run_failed_at,
        recorded_at=alert.recorded_at,
        acknowledged_at=alert.acknowledged_at,
    )


async def _with_failure_alert(
    detail: DagsterRunDetailData,
    *,
    client: AsyncAddressClient,
) -> DagsterRunDetailData:
    """Attach the persisted ``ops.run_failure_alerts`` row for this run, if any."""
    if detail.run is None:
        return detail
    try:
        alert = await client.get_run_failure_alert(detail.run.run_id)
    except Exception as exc:  # pragma: no cover - exact DB errors are driver-dependent.
        return detail.model_copy(
            update={
                "errors": [
                    *detail.errors,
                    f"failure alert 조회 실패 ({type(exc).__name__})",
                ]
            }
        )
    if alert is None:
        return detail
    return detail.model_copy(update={"failure_alert": _run_failure_alert_dto(alert)})


def _empty_summary_data(
    *,
    status: Literal["unavailable", "error"],
    dagster_url: str,
    graphql_url: str,
    checked_at: datetime,
    errors: list[str],
) -> DagsterSummaryData:
    return DagsterSummaryData(
        status=status,
        # Browser-facing URL even on the outage/error path so the admin iframe keeps
        # the public domain; graphql_url stays the internal backend target.
        dagster_url=dagster_url,
        graphql_url=graphql_url,
        checked_at=checked_at,
        repository_count=0,
        job_count=0,
        asset_count=0,
        schedule_count=0,
        sensor_count=0,
        run_counts={},
        repositories=[],
        recent_runs=[],
        errors=errors,
    )


@router.get(
    "/summary",
    response_model=DagsterSummaryResponse,
    summary="Dagster 운영 요약",
    description=(
        "Dagster GraphQL에서 repository, asset, schedule/sensor, recent run 정보를 읽어 "
        "admin UI 요약 DTO로 반환한다. Dagster webserver가 내려가도 200 응답"
        "(status=unavailable)으로 UI가 장애 상태를 표시할 수 있게 한다."
    ),
)
async def get_dagster_summary(
    page_size: int = Query(default=10, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> DagsterSummaryResponse:
    started_at = perf_counter()
    checked_at = datetime.now(UTC)

    try:
        dagster_urls = _dagster_urls(settings)
    except DagsterUrlConfigurationError as exc:
        return _summary_response(
            _empty_summary_data(
                status="error",
                dagster_url=_safe_summary_dagster_url(settings),
                graphql_url=_safe_summary_graphql_url(settings),
                checked_at=checked_at,
                errors=[str(exc)],
            ),
            started_at=started_at,
        )

    try:
        async with httpx.AsyncClient(
            timeout=settings.dagster_observability_timeout_seconds
        ) as client:
            payload = await _post_graphql(
                client=client,
                graphql_url=dagster_urls.graphql_url,
                variables=_summary_variables(settings, limit=page_size),
            )
    except (httpx.HTTPError, ValueError) as exc:
        return _summary_response(
            _empty_summary_data(
                status="unavailable",
                dagster_url=dagster_urls.public_url,
                graphql_url=dagster_urls.graphql_url,
                checked_at=checked_at,
                errors=[_sanitized_request_error(exc)],
            ),
            started_at=started_at,
        )

    graphql_errors = payload.get("errors")
    if isinstance(graphql_errors, list) and graphql_errors:
        return _summary_response(
            _empty_summary_data(
                status="error",
                dagster_url=dagster_urls.public_url,
                graphql_url=dagster_urls.graphql_url,
                checked_at=checked_at,
                errors=[_graphql_error_message(error) for error in graphql_errors],
            ),
            started_at=started_at,
        )

    data = _dict(payload.get("data"))
    repositories, repository_errors = _parse_repository(
        _dict(data.get("repositoryOrError")),
        now_ts=checked_at.timestamp(),
        grace_seconds=float(settings.dagster_schedule_overdue_grace_seconds),
    )
    recent_runs, _, run_errors = _parse_runs(_dict(data.get("runsOrError")))
    active_runs, _, active_errors = _parse_runs(_dict(data.get("activeRuns")))
    # 최근 종료 실행에 밀린 오래된 활성 실행도 남기며 중복 집계하지 않는다.
    recent_runs = list({run.run_id: run for run in [*active_runs, *recent_runs]}.values())
    run_counts = dict(Counter(run.status for run in recent_runs))
    errors = [*repository_errors, *run_errors, *active_errors]
    if len(active_runs) >= 1000:
        errors.append(
            "활성 실행 조회가 1000건 상한에 도달했습니다. Dagster에서 전체 실행을 확인하세요."
        )

    return _summary_response(
        DagsterSummaryData(
            status="error" if errors else "ok",
            # Browser-facing URL (public domain in prod) for the admin iframe/links;
            # the backend GraphQL target stays internal via graphql_url.
            dagster_url=dagster_urls.public_url,
            graphql_url=dagster_urls.graphql_url,
            version=_optional_string(data.get("version")),
            checked_at=checked_at,
            repository_count=len(repositories),
            job_count=sum(len(repository.jobs) for repository in repositories),
            asset_count=sum(repository.asset_count for repository in repositories),
            schedule_count=sum(len(repository.schedules) for repository in repositories),
            sensor_count=sum(len(repository.sensors) for repository in repositories),
            run_counts=run_counts,
            repositories=repositories,
            recent_runs=recent_runs,
            errors=errors,
        ),
        started_at=started_at,
    )


@router.get(
    "/runs/{run_id}",
    response_model=DagsterRunDetailResponse,
    summary="Dagster run 상세",
    description=(
        "Dagster GraphQL runOrError를 조회해 최근 event log와 실패 error payload를 "
        "admin UI용 DTO로 반환한다. 조회 전용이며 Dagster run을 재실행하거나 "
        "상태를 변경하지 않는다."
    ),
)
async def get_dagster_run_detail(
    run_id: str,
    page_size: int = Query(default=50, ge=1, le=200),
    after: str | None = Query(
        default=None,
        description="event log cursor. 미지정이면 처음부터 조회한다.",
    ),
    settings: Settings = Depends(get_settings),
    address_client: AsyncAddressClient = Depends(get_client),
) -> DagsterRunDetailResponse:
    started_at = perf_counter()
    checked_at = datetime.now(UTC)

    try:
        dagster_urls = _dagster_urls(settings)
    except DagsterUrlConfigurationError as exc:
        return _run_detail_response(
            DagsterRunDetailData(
                status="error",
                dagster_url=_safe_summary_dagster_url(settings),
                graphql_url=_safe_summary_graphql_url(settings),
                checked_at=checked_at,
                errors=[str(exc)],
            ),
            started_at=started_at,
        )

    try:
        async with httpx.AsyncClient(
            timeout=settings.dagster_observability_timeout_seconds
        ) as client:
            payload = await _post_graphql(
                client=client,
                graphql_url=dagster_urls.graphql_url,
                variables={
                    "runId": run_id,
                    "eventLimit": page_size,
                    "afterCursor": after,
                },
                query=_DAGSTER_RUN_DETAIL_QUERY,
            )
    except (httpx.HTTPError, ValueError) as exc:
        return _run_detail_response(
            DagsterRunDetailData(
                status="unavailable",
                dagster_url=dagster_urls.dagster_url,
                graphql_url=dagster_urls.graphql_url,
                checked_at=checked_at,
                errors=[_sanitized_request_error(exc)],
            ),
            started_at=started_at,
        )

    graphql_errors = payload.get("errors")
    if isinstance(graphql_errors, list) and graphql_errors:
        return _run_detail_response(
            DagsterRunDetailData(
                status="error",
                dagster_url=dagster_urls.dagster_url,
                graphql_url=dagster_urls.graphql_url,
                checked_at=checked_at,
                errors=[_graphql_error_message(error) for error in graphql_errors],
            ),
            started_at=started_at,
        )

    data = _dict(payload.get("data"))
    detail = _parse_run_detail(
        _dict(data.get("runOrError")),
        dagster_urls=dagster_urls,
        checked_at=checked_at,
        settings=settings,
    )
    if detail.status == "ok":
        detail = await _with_backup_artifact(
            detail,
            client=address_client,
            settings=settings,
        )
        detail = await _with_failure_alert(detail, client=address_client)
    return _run_detail_response(
        detail,
        started_at=started_at,
    )


@router.get(
    "/run-failures",
    response_model=DagsterRunFailuresResponse,
    summary="Dagster run 실패 알림 목록",
    description=(
        "Dagster run-failure 센서가 ``ops.run_failure_alerts``에 영속한 실패 알림을 "
        "최근순으로 반환한다. 기본은 미확인(unacknowledged) 알림만이며, "
        "``include_acknowledged=true``이면 확인된 알림도 포함한다. app DB를 읽으며 "
        "Dagster webserver에 의존하지 않는다."
    ),
)
async def get_dagster_run_failures(
    limit: int = Query(default=50, ge=1, le=200),
    include_acknowledged: bool = Query(
        default=False,
        description="true이면 이미 확인(ack)된 알림도 포함한다.",
    ),
    address_client: AsyncAddressClient = Depends(get_client),
) -> DagsterRunFailuresResponse:
    started_at = perf_counter()
    checked_at = datetime.now(UTC)
    alerts = await address_client.list_run_failure_alerts(
        limit=limit,
        unacknowledged_only=not include_acknowledged,
    )
    return DagsterRunFailuresResponse(
        data=DagsterRunFailuresData(
            checked_at=checked_at,
            alerts=[_run_failure_alert_dto(alert) for alert in alerts],
        ),
        meta=_response_meta(started_at=started_at),
    )


@router.post(
    "/runs/{run_id}/ack",
    response_model=DagsterRunFailureAckResponse,
    summary="Dagster run 실패 알림 확인(ack)",
    description=(
        "``ops.run_failure_alerts``의 해당 run 알림을 확인 처리한다(``acknowledged_at`` "
        "설정). 멱등이며, 이미 확인된 알림은 그대로 반환한다. 알림이 없으면 404."
    ),
)
async def acknowledge_dagster_run_failure(
    run_id: str,
    address_client: AsyncAddressClient = Depends(get_client),
) -> DagsterRunFailureAckResponse:
    started_at = perf_counter()
    alert = await address_client.acknowledge_run_failure_alert(run_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="run-failure 알림을 찾을 수 없습니다.")
    return DagsterRunFailureAckResponse(
        data=_run_failure_alert_dto(alert),
        meta=_response_meta(started_at=started_at),
    )
