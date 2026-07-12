"""T-290k §2g/§2h Dagster client recovery calls: terminate_run + fetch_run_state (mock httpx)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from kortravelgeo.api._dagster_client import (
    DagsterTerminateError,
    fetch_run_state,
    terminate_run,
)
from kortravelgeo.core.job_recovery import OrchestratorRunState
from kortravelgeo.settings import Settings


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append({"url": url, "json": json})
        return _FakeResponse(self._payload)


def _settings() -> Settings:
    return Settings(_env_file=None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("SUCCESS", OrchestratorRunState.SUCCESS),
        ("FAILURE", OrchestratorRunState.FAILED),
        ("CANCELED", OrchestratorRunState.CANCELLED),
        ("STARTED", OrchestratorRunState.RUNNING),
        ("QUEUED", OrchestratorRunState.RUNNING),
        ("CANCELING", OrchestratorRunState.RUNNING),
        ("SOME_NEW_STATUS", OrchestratorRunState.RUNNING),
    ],
)
async def test_fetch_run_state_maps_status(
    status: str, expected: OrchestratorRunState
) -> None:
    client = _FakeClient({"data": {"runOrError": {"__typename": "Run", "status": status}}})
    result = await fetch_run_state(_settings(), run_id="r1", http_client=client)  # type: ignore[arg-type]
    assert result is expected
    assert client.calls[0]["json"]["variables"] == {"runId": "r1"}


@pytest.mark.asyncio
async def test_fetch_run_state_missing_run_returns_missing() -> None:
    payload = {"data": {"runOrError": {"__typename": "RunNotFoundError", "message": "gone"}}}
    result = await fetch_run_state(_settings(), run_id="r1", http_client=_FakeClient(payload))  # type: ignore[arg-type]
    assert result is OrchestratorRunState.MISSING


@pytest.mark.asyncio
@pytest.mark.parametrize("typename", ["TerminateRunSuccess", "RunNotFoundError"])
async def test_terminate_run_success_or_gone_does_not_raise(typename: str) -> None:
    payload = {"data": {"terminateRun": {"__typename": typename, "run": {"runId": "r1"}}}}
    client = _FakeClient(payload)
    await terminate_run(_settings(), run_id="r1", http_client=client)  # type: ignore[arg-type]
    assert client.calls[0]["json"]["variables"] == {"runId": "r1"}


@pytest.mark.asyncio
async def test_terminate_run_failure_raises() -> None:
    payload = {"data": {"terminateRun": {"__typename": "TerminateRunFailure", "message": "busy"}}}
    with pytest.raises(DagsterTerminateError, match="busy"):
        await terminate_run(_settings(), run_id="r1", http_client=_FakeClient(payload))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_terminate_run_transport_error_propagates() -> None:
    class _BoomClient:
        async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
            raise httpx.ConnectError("boom")

    with pytest.raises(httpx.HTTPError):
        await terminate_run(_settings(), run_id="r1", http_client=_BoomClient())  # type: ignore[arg-type]
