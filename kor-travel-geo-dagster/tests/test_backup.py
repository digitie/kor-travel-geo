"""Scheduled-backup Dagster onramp tests (T-290f)."""

from __future__ import annotations

import httpx
import pytest
from kortravelgeo.settings import Settings
from pydantic import SecretStr

from kortravelgeo_dagster.backup import (
    JOB_ID_TAG,
    _failure_notification_payload,
)
from kortravelgeo_dagster.resources import (
    ACTOR_HEADER,
    ADMIN_PROXY_SECRET_HEADER,
    DESTRUCTIVE_ADMIN_ROLE,
    ROLES_HEADER,
    SYSTEM_ACTOR,
    DagsterAdminApiClient,
)


class _FakeError:
    def __init__(self, cls_name: object) -> None:
        self.cls_name = cls_name


class _FakeEventData:
    def __init__(self, error: object) -> None:
        self.error = error


class _FakeFailureEvent:
    def __init__(self, error_cls_name: object, message: str) -> None:
        self.event_specific_data = _FakeEventData(_FakeError(error_cls_name))
        self.message = message


class _FakeDagsterRun:
    def __init__(
        self, run_id: str, job_name: str | None, status: str, tags: dict[str, str]
    ) -> None:
        self.run_id = run_id
        self.job_name = job_name
        self.status = status
        self.tags = tags


class _FakeFailureContext:
    def __init__(self, dagster_run: _FakeDagsterRun, failure_event: object) -> None:
        self.dagster_run = dagster_run
        self.failure_event = failure_event


def test_failure_notification_payload_matches_boundary_contract() -> None:
    context = _FakeFailureContext(
        dagster_run=_FakeDagsterRun(
            run_id="run-9",
            job_name="mv_refresh_job",
            status="DagsterRunStatus.FAILURE",
            tags={JOB_ID_TAG: "job-42"},
        ),
        failure_event=_FakeFailureEvent(
            error_cls_name="Failure",
            message="secret internal traceback detail",
        ),
    )

    payload = _failure_notification_payload(context)  # type: ignore[arg-type]

    assert payload == {
        "job_id": "job-42",
        "run_id": "run-9",
        "job_name": "mv_refresh_job",
        "status": "DagsterRunStatus.FAILURE",
        "error_code": "Failure",
    }
    # The raw Dagster failure message must never reach the notifier.
    assert "message" not in payload
    assert "secret internal traceback detail" not in payload.values()


def test_failure_notification_payload_defaults_when_unavailable() -> None:
    context = _FakeFailureContext(
        dagster_run=_FakeDagsterRun(
            run_id="run-x",
            job_name=None,
            status="DagsterRunStatus.FAILURE",
            tags={},
        ),
        failure_event=None,
    )

    payload = _failure_notification_payload(context)  # type: ignore[arg-type]

    assert payload["run_id"] == "run-x"
    assert payload["job_id"] is None
    assert payload["error_code"] is None
    assert "message" not in payload


def test_admin_api_client_uses_settings_and_proxy_headers() -> None:
    client = DagsterAdminApiClient.from_settings(
        Settings(
            _env_file=None,
            dagster_admin_api_url="http://geo-api.internal:12501/",
            admin_proxy_secret=SecretStr("shared-secret"),
        )
    )

    assert client.base_url == "http://geo-api.internal:12501"
    assert client.url_for("/v1/admin/backups/scheduled/run-due") == (
        "http://geo-api.internal:12501/v1/admin/backups/scheduled/run-due"
    )
    assert client.headers() == {
        ACTOR_HEADER: SYSTEM_ACTOR,
        ROLES_HEADER: DESTRUCTIVE_ADMIN_ROLE,
        ADMIN_PROXY_SECRET_HEADER: "shared-secret",
    }


@pytest.mark.asyncio
async def test_admin_api_client_posts_run_due() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "enqueued": True,
                "job_id": "job-1",
                "status": {"due": True, "reason": "due_initial"},
            },
        )

    client = DagsterAdminApiClient(
        base_url="http://geo-api.internal:12501",
        timeout_seconds=1.0,
        admin_proxy_secret="shared-secret",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        payload = await client.run_due_scheduled_backup(http_client=http_client)

    assert payload["enqueued"] is True
    assert requests[0].url == "http://geo-api.internal:12501/v1/admin/backups/scheduled/run-due"
    assert requests[0].headers[ACTOR_HEADER] == SYSTEM_ACTOR
    assert requests[0].headers[ROLES_HEADER] == DESTRUCTIVE_ADMIN_ROLE
    assert requests[0].headers[ADMIN_PROXY_SECRET_HEADER] == "shared-secret"
