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
    # Sanitized: class name tag only, never the raw exception text.
    assert data["errors"] == ["Dagster 요청 실패 (ConnectError)"]
    assert "connection refused" not in data["errors"][0]


@pytest.mark.asyncio
async def test_dagster_summary_sanitizes_http_status_error_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_status_error(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert variables
        assert query
        request = httpx.Request("POST", graphql_url)
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError(
            f"Server error '500 Internal Server Error' for url '{graphql_url}'",
            request=request,
            response=response,
        )

    monkeypatch.setattr(dagster_mod, "_post_graphql", _raise_status_error)

    transport = httpx.ASGITransport(app=_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "unavailable"
    # The internal Dagster host/URL must never reach the client.
    assert data["errors"] == ["Dagster 요청 실패 (HTTPStatusError)"]
    assert "dagster.example" not in data["errors"][0]
    assert "12502" not in data["errors"][0]


@pytest.mark.asyncio
async def test_dagster_run_detail_sanitizes_http_status_error_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_status_error(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert variables
        assert query
        request = httpx.Request("POST", graphql_url)
        response = httpx.Response(502, request=request)
        raise httpx.HTTPStatusError(
            f"Server error '502 Bad Gateway' for url '{graphql_url}'",
            request=request,
            response=response,
        )

    monkeypatch.setattr(dagster_mod, "_post_graphql", _raise_status_error)

    transport = httpx.ASGITransport(app=_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/runs/run-1", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "unavailable"
    assert data["errors"] == ["Dagster 요청 실패 (HTTPStatusError)"]
    assert "dagster.example" not in data["errors"][0]


def test_graphql_error_message_falls_back_to_generic_without_message() -> None:
    # Structured error lacking ``message`` -> generic, never echo the raw structure.
    assert (
        dagster_mod._graphql_error_message({"locations": [{"line": 1, "column": 2}]})
        == "Dagster GraphQL 오류 응답"
    )
    # Non-dict raw error -> generic, does not echo the raw string.
    assert dagster_mod._graphql_error_message("internal detail") == "Dagster GraphQL 오류 응답"


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
    assert data["dagster_url"] == ""


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


def _empty_summary_payload() -> dict[str, Any]:
    return {
        "data": {
            "repositoriesOrError": {"__typename": "RepositoryConnection", "nodes": []},
            "runsOrError": {"__typename": "Runs", "results": []},
        }
    }


@pytest.mark.asyncio
async def test_dagster_summary_returns_public_url_not_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Browser-facing dagster_url echoes the public domain (T-290) even though its host
    is not in dagster_allowed_hosts; the backend GraphQL target stays the internal host.
    """
    settings = Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        dagster_url="http://dagster.example:12502",
        dagster_public_url="https://geo-dagster.digitie.mywire.org/",
        dagster_allowed_hosts=("dagster.example",),
        dagster_request_timeout_seconds=1.0,
        geoip_gate_mode="off",
    )

    async def _fake_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        # Backend GraphQL still targets the internal, allowlisted host.
        assert graphql_url == "http://dagster.example:12502/graphql"
        return _empty_summary_payload()

    monkeypatch.setattr(dagster_mod, "_post_graphql", _fake_post_graphql)

    transport = httpx.ASGITransport(app=_app(settings), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    # Browser-facing URL = public domain (trailing slash normalized; host not allowlisted).
    assert data["dagster_url"] == "https://geo-dagster.digitie.mywire.org"
    # Backend GraphQL URL stays internal.
    assert data["graphql_url"] == "http://dagster.example:12502/graphql"


@pytest.mark.asyncio
async def test_dagster_summary_unavailable_uses_validated_public_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        dagster_url="http://dagster.example:12502",
        dagster_public_url="https://geo-dagster.digitie.mywire.org/",
        dagster_allowed_hosts=("dagster.example",),
        dagster_request_timeout_seconds=1.0,
        geoip_gate_mode="off",
    )

    async def _raise_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        assert client
        assert graphql_url == "http://dagster.example:12502/graphql"
        assert variables
        assert query
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(dagster_mod, "_post_graphql", _raise_post_graphql)

    transport = httpx.ASGITransport(app=_app(settings), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "unavailable"
    # Outage summaries reuse the validated/normalized browser-facing URL.
    assert data["dagster_url"] == "https://geo-dagster.digitie.mywire.org"
    assert data["errors"] == ["Dagster 요청 실패 (ConnectError)"]


@pytest.mark.asyncio
async def test_dagster_summary_invalid_public_url_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        dagster_url="http://dagster.example:12502",
        dagster_public_url="javascript:alert(1)",
        dagster_allowed_hosts=("dagster.example",),
        dagster_request_timeout_seconds=1.0,
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
        raise AssertionError("invalid public URL must fail before Dagster is requested")

    monkeypatch.setattr(dagster_mod, "_post_graphql", _unexpected_post_graphql)

    transport = httpx.ASGITransport(app=_app(settings), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "error"
    assert data["errors"] == ["dagster_public_url scheme must be http or https"]
    assert data["dagster_url"] == "http://dagster.example:12502"
    assert "javascript:alert(1)" not in str(data)


@pytest.mark.asyncio
async def test_dagster_summary_dagster_url_falls_back_to_internal_when_public_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty dagster_public_url -> dagster_url falls back to the internal dagster_url."""

    async def _fake_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        return _empty_summary_payload()

    monkeypatch.setattr(dagster_mod, "_post_graphql", _fake_post_graphql)

    # Default _app() settings leave dagster_public_url unset (empty).
    transport = httpx.ASGITransport(app=_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    # Falls back to the internal dagster_url.
    assert data["dagster_url"] == "http://dagster.example:12502"
    assert data["graphql_url"] == "http://dagster.example:12502/graphql"


@pytest.mark.asyncio
async def test_dagster_summary_invalid_graphql_url_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A bad dagster_graphql_url makes _dagster_urls raise; the config-error summary must
    # sanitize graphql_url to "" rather than echoing the raw candidate (#443).
    settings = Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        dagster_url="http://dagster.example:12502",
        dagster_graphql_url="javascript:alert(1)",
        dagster_allowed_hosts=("dagster.example",),
        dagster_request_timeout_seconds=1.0,
        geoip_gate_mode="off",
    )

    async def _unexpected_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_SUMMARY_QUERY,
    ) -> dict[str, Any]:
        raise AssertionError("invalid graphql URL must fail before Dagster is requested")

    monkeypatch.setattr(dagster_mod, "_post_graphql", _unexpected_post_graphql)

    transport = httpx.ASGITransport(app=_app(settings), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/summary", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "error"
    assert data["errors"] == ["dagster_graphql_url scheme must be http or https"]
    assert data["graphql_url"] == ""
    # dagster_url still resolves (valid); the raw graphql value must not appear anywhere.
    assert data["dagster_url"] == "http://dagster.example:12502"
    assert "javascript:alert(1)" not in str(data)


@pytest.mark.asyncio
async def test_dagster_run_detail_config_error_sanitizes_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The run-detail config-error path echoed both dagster_url and graphql_url raw (#443).
    # Both must be sanitized — here to "" since the sole (invalid) URL is dagster_url.
    settings = Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        dagster_url="javascript:alert(1)",
        dagster_allowed_hosts=("dagster.example",),
        dagster_request_timeout_seconds=1.0,
        geoip_gate_mode="off",
    )

    async def _unexpected_post_graphql(
        client: httpx.AsyncClient,
        graphql_url: str,
        variables: dict[str, object],
        query: str = dagster_mod._DAGSTER_RUN_DETAIL_QUERY,
    ) -> dict[str, Any]:
        raise AssertionError("invalid dagster_url must fail before Dagster is requested")

    monkeypatch.setattr(dagster_mod, "_post_graphql", _unexpected_post_graphql)

    transport = httpx.ASGITransport(app=_app(settings), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/ops/dagster/runs/run-123", headers=_HEADERS)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "error"
    assert data["dagster_url"] == ""
    assert data["graphql_url"] == ""
    assert "javascript:alert(1)" not in str(data)
