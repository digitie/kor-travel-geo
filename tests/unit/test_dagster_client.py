"""_dagster_client tests (T-290g): launch_dagster_run + backend URL/SSRF resolution."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from kortravelgeo.api._dagster_client import (
    DagsterLaunchError,
    DagsterUrlConfigurationError,
    _dagster_urls,
    launch_dagster_run,
)
from kortravelgeo.settings import Settings


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "_env_file": None,
        "dagster_url": "http://dagster.example:12502",
        "dagster_allowed_hosts": ("dagster.example",),
        "dagster_request_timeout_seconds": 1.0,
    }
    base.update(overrides)
    return Settings(**base)


def test_dagster_urls_validates_and_resolves() -> None:
    urls = _dagster_urls(_settings())
    assert urls.dagster_url == "http://dagster.example:12502"
    assert urls.graphql_url == "http://dagster.example:12502/graphql"


def test_dagster_urls_rejects_host_not_in_allowlist() -> None:
    with pytest.raises(DagsterUrlConfigurationError):
        _dagster_urls(_settings(dagster_url="http://evil.example:12502"))


@pytest.mark.asyncio
async def test_launch_dagster_run_success_returns_run_id_and_posts_to_internal_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "launchRun": {"__typename": "LaunchRunSuccess", "run": {"runId": "run-abc"}}
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        run_id = await launch_dagster_run(
            _settings(),
            job_name="db_backup",
            run_config={"ops": {"run_db_backup": {"config": {"job_id": "j1"}}}},
            tags={"kor_travel_geo.job_id": "j1"},
            http_client=client,
        )

    assert run_id == "run-abc"
    assert str(requests[0].url) == "http://dagster.example:12502/graphql"
    execution_params = json.loads(requests[0].content)["variables"]["executionParams"]
    assert execution_params["selector"]["jobName"] == "db_backup"
    assert execution_params["selector"]["repositoryName"] == "__repository__"
    assert execution_params["runConfigData"]["ops"]["run_db_backup"]["config"]["job_id"] == "j1"
    assert {"key": "kor_travel_geo.job_id", "value": "j1"} in execution_params["executionMetadata"][
        "tags"
    ]


@pytest.mark.asyncio
async def test_launch_dagster_run_config_invalid_raises_launch_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "launchRun": {
                        "__typename": "RunConfigValidationInvalid",
                        "errors": [{"message": "bad config"}],
                    }
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DagsterLaunchError, match="bad config"):
            await launch_dagster_run(
                _settings(), job_name="db_backup", run_config={}, http_client=client
            )


@pytest.mark.asyncio
async def test_launch_dagster_run_rejects_url_config_error_before_posting() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not POST when the backend URL fails the allowlist")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DagsterUrlConfigurationError):
            await launch_dagster_run(
                _settings(dagster_url="ftp://dagster.example:12502"),
                job_name="db_backup",
                run_config={},
                http_client=client,
            )
