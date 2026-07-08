"""Scheduled-backup Dagster onramp tests (T-290f)."""

from __future__ import annotations

import httpx
import pytest
from kortravelgeo.settings import Settings
from pydantic import SecretStr

from kortravelgeo_dagster.resources import (
    ACTOR_HEADER,
    ADMIN_PROXY_SECRET_HEADER,
    DESTRUCTIVE_ADMIN_ROLE,
    ROLES_HEADER,
    SYSTEM_ACTOR,
    DagsterAdminApiClient,
)


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
