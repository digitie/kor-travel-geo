from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.dto.admin import AuditEvent
from kortravelgeo.settings import Settings, get_settings

_HEADERS = {"X-KTG-Actor": "ui-auth", "X-KTG-Roles": "source_file_viewer"}


class _FakeClient:
    def __init__(self) -> None:
        self.recorded: dict[str, Any] | None = None

    async def record_audit_event(self, **kwargs: Any) -> AuditEvent:
        self.recorded = kwargs
        return AuditEvent(
            audit_event_id="audit-login",
            occurred_at=datetime(2026, 6, 23, tzinfo=UTC),
            actor_type=kwargs["actor_type"],
            actor_id=kwargs.get("actor_id"),
            client_ip_hash="hash-ip",
            user_agent_hash="hash-ua",
            action=kwargs["action"],
            resource_type=kwargs.get("resource_type"),
            outcome=kwargs["outcome"],
            error_code=kwargs.get("error_code"),
            payload_redacted=kwargs.get("payload", {}),
            payload_hash="0" * 64,
        )


@pytest.mark.asyncio
async def test_admin_auth_event_records_login_attempt_metadata() -> None:
    fake = _FakeClient()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        geoip_gate_mode="off",
    )
    app.dependency_overrides[get_client] = lambda: fake
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/admin/auth-events",
            headers=_HEADERS,
            json={
                "attempted_username": "admin",
                "client_ip": "203.0.113.10",
                "event_type": "login",
                "next_path": "/admin/settings",
                "outcome": "denied",
                "reason": "invalid_credentials",
                "user_agent": "UnitTest",
            },
        )

    assert response.status_code == 200
    assert fake.recorded is not None
    assert fake.recorded["action"] == "admin_auth.login"
    assert fake.recorded["actor_id"] == "admin"
    assert fake.recorded["client_ip"] == "203.0.113.10"
    assert fake.recorded["user_agent"] == "UnitTest"
    assert fake.recorded["error_code"] == "invalid_credentials"
    assert fake.recorded["payload"]["reason"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_admin_auth_event_requires_trusted_proxy_identity() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        geoip_gate_mode="off",
    )
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/admin/auth-events",
            json={"event_type": "login", "outcome": "denied"},
        )

    assert response.status_code == 403
