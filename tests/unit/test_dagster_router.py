"""Dagster observability router tests."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.routers import dagster as dagster_mod
from kortravelgeo.settings import Settings, get_settings

_HEADERS = {"X-KTG-Actor": "dagster-test", "X-KTG-Roles": "source_file_viewer"}


def _app(settings: Settings | None = None):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings or Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        dagster_url="http://dagster.example:12502",
        dagster_allowed_hosts=("dagster.example",),
        dagster_request_timeout_seconds=1.0,
        geoip_gate_mode="off",
    )
    return app


@pytest.mark.asyncio
async def test_dagster_summary_parses_graphql_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def _fake_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert graphql_url == "http://dagster.example:12502/graphql"
        calls.append({"query": query, "variables": variables})
        return {
            "data": {
                "version": "1.9.99",
                "repositoriesOrError": {
                    "__typename": "RepositoryConnection",
                    "nodes": [
                        {
                            "name": "__repository__",
                            "location": {"name": "kortravelgeo_dagster.definitions"},
                            "pipelines": [{"name": "mv_refresh", "isJob": True}],
                            "schedules": [
                                {
                                    "name": "scheduled_backup",
                                    "cronSchedule": "0 3 * * *",
                                    "executionTimezone": "Asia/Seoul",
                                    "scheduleState": {
                                        "status": "RUNNING",
                                        "ticks": [
                                            {
                                                "tickId": "tick-1",
                                                "status": "SUCCESS",
                                                "timestamp": 1710000000.0,
                                                "endTimestamp": 1710000010.0,
                                                "runIds": ["run-1"],
                                                "runKeys": ["scheduled"],
                                                "skipReason": None,
                                                "cursor": "cursor-1",
                                                "error": None,
                                            }
                                        ],
                                    },
                                }
                            ],
                            "sensors": [
                                {
                                    "name": "run_failure_sensor",
                                    "sensorState": {
                                        "status": "STOPPED",
                                        "ticks": [
                                            {
                                                "tickId": "sensor-tick-1",
                                                "status": "FAILURE",
                                                "timestamp": 1710000200.0,
                                                "endTimestamp": None,
                                                "runIds": [],
                                                "runKeys": [],
                                                "skipReason": None,
                                                "cursor": None,
                                                "error": {
                                                    "message": "sensor failed",
                                                    "stack": ["frame 1"],
                                                    "className": "SensorFailure",
                                                },
                                            }
                                        ],
                                    },
                                }
                            ],
                            "assetNodes": [
                                {
                                    "id": "asset-1",
                                    "groupName": "ops",
                                    "assetKey": {"path": ["db_backup_artifact"]},
                                }
                            ],
                        }
                    ],
                },
                "runsOrError": {
                    "__typename": "Runs",
                    "results": [
                        {
                            "runId": "run-1",
                            "jobName": "mv_refresh",
                            "status": "SUCCESS",
                            "startTime": 1.0,
                            "endTime": 2.0,
                            "updateTime": 2.0,
                            "tags": [{"key": "dagster/job", "value": "mv_refresh"}],
                        }
                    ],
                },
            }
        }

    monkeypatch.setattr(dagster_mod, "_post_graphql", _fake_post_graphql)

    transport = httpx.ASGITransport(app=_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary?page_size=3", headers=_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert "duration_ms" in body["meta"]
    data = body["data"]
    assert data["status"] == "ok"
    assert data["dagster_url"] == "http://dagster.example:12502"
    assert data["graphql_url"] == "http://dagster.example:12502/graphql"
    assert data["version"] == "1.9.99"
    assert data["repository_count"] == 1
    assert data["job_count"] == 1
    assert data["asset_count"] == 1
    assert data["schedule_count"] == 1
    assert data["sensor_count"] == 1
    assert data["run_counts"] == {"SUCCESS": 1}
    assert data["repositories"][0]["schedules"][0]["recent_ticks"][0]["run_ids"] == ["run-1"]
    assert data["repositories"][0]["sensors"][0]["recent_ticks"][0]["error"] == {
        "message": "sensor failed",
        "stack": ["frame 1"],
        "class_name": "SensorFailure",
    }
    assert data["repositories"][0]["asset_groups"] == [
        {"group_name": "ops", "asset_count": 1, "assets": ["db_backup_artifact"]}
    ]
    assert data["recent_runs"][0]["run_id"] == "run-1"
    assert calls == [
        {"query": dagster_mod._DAGSTER_SUMMARY_QUERY, "variables": {"limit": 3}},
    ]


@pytest.mark.asyncio
async def test_dagster_run_detail_parses_graphql_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def _fake_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert graphql_url == "http://dagster.example:12502/graphql"
        calls.append({"query": query, "variables": variables})
        return {
            "data": {
                "runOrError": {
                    "__typename": "Run",
                    "runId": "run-1",
                    "jobName": "db_backup",
                    "status": "FAILURE",
                    "startTime": 1710000000.0,
                    "endTime": 1710000030.0,
                    "updateTime": 1710000030.0,
                    "tags": [{"key": "dagster/job", "value": "db_backup"}],
                    "eventConnection": {
                        "cursor": "event-cursor-1",
                        "hasMore": True,
                        "events": [
                            {
                                "__typename": "StepStartEvent",
                                "message": "step started",
                                "timestamp": "1710000001.0",
                                "level": "INFO",
                                "stepKey": "backup",
                                "eventType": "STEP_START",
                            },
                            {
                                "__typename": "RunFailureEvent",
                                "message": "run failed",
                                "timestamp": "1710000030.0",
                                "level": "ERROR",
                                "stepKey": None,
                                "eventType": "RUN_FAILURE",
                                "error": {
                                    "message": "boom",
                                    "stack": ["traceback"],
                                    "className": "RuntimeError",
                                },
                            },
                        ],
                    },
                }
            }
        }

    monkeypatch.setattr(dagster_mod, "_post_graphql", _fake_post_graphql)

    transport = httpx.ASGITransport(app=_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/ops/dagster/runs/run-1?page_size=5&after=cursor-0",
            headers=_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["status"] == "ok"
    assert data["run"]["run_id"] == "run-1"
    assert data["run"]["status"] == "FAILURE"
    assert data["event_cursor"] == "event-cursor-1"
    assert data["event_has_more"] is True
    assert data["events"][0]["dagster_event_type"] == "STEP_START"
    assert data["events"][1]["error"] == {
        "message": "boom",
        "stack": ["traceback"],
        "class_name": "RuntimeError",
    }
    assert calls == [
        {
            "query": dagster_mod._DAGSTER_RUN_DETAIL_QUERY,
            "variables": {"runId": "run-1", "eventLimit": 5, "afterCursor": "cursor-0"},
        },
    ]


@pytest.mark.asyncio
async def test_dagster_run_detail_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert graphql_url
        assert variables
        assert query
        return {
            "data": {
                "runOrError": {
                    "__typename": "RunNotFoundError",
                    "message": "Run not found",
                    "runId": "missing-run",
                }
            }
        }

    monkeypatch.setattr(dagster_mod, "_post_graphql", _fake_post_graphql)

    transport = httpx.ASGITransport(app=_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/runs/missing-run", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "not_found"
    assert data["run"] is None
    assert data["events"] == []
    assert data["errors"] == ["Run not found"]


@pytest.mark.asyncio
async def test_dagster_summary_returns_unavailable_when_graphql_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert graphql_url
        assert variables
        assert query
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(dagster_mod, "_post_graphql", _raise_post_graphql)

    transport = httpx.ASGITransport(app=_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "unavailable"
    assert data["repository_count"] == 0
    assert data["recent_runs"] == []
    assert data["errors"]


@pytest.mark.asyncio
async def test_dagster_summary_rejects_disallowed_url_before_http_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        dagster_url="http://169.254.169.254:12502",
        dagster_allowed_hosts=("127.0.0.1",),
        geoip_gate_mode="off",
    )

    async def _unexpected_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert graphql_url
        assert variables
        assert query
        raise AssertionError("disallowed Dagster URL must not be requested")

    monkeypatch.setattr(dagster_mod, "_post_graphql", _unexpected_post_graphql)

    transport = httpx.ASGITransport(app=_app(settings), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "error"
    assert data["repository_count"] == 0
    assert data["errors"] == ["dagster_url host is not in dagster_allowed_hosts"]


@pytest.mark.asyncio
async def test_dagster_run_detail_graphql_error_extracts_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert graphql_url
        assert variables
        assert query
        return {
            "errors": [
                {
                    "message": "Field 'bogus' doesn't exist",
                    "locations": [{"line": 3, "column": 5}],
                    "path": ["runOrError"],
                }
            ]
        }

    monkeypatch.setattr(dagster_mod, "_post_graphql", _fake_post_graphql)

    transport = httpx.ASGITransport(app=_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/runs/run-1", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "error"
    assert data["errors"] == ["Field 'bogus' doesn't exist"]
    assert "locations" not in data["errors"][0]


def test_dagster_summary_openapi_path_is_mounted() -> None:
    paths = set(_app().openapi()["paths"])

    assert "/v1/ops/dagster/runs/{run_id}" in paths
    assert "/v1/ops/dagster/summary" in paths
