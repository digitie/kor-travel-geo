"""T-203a endpoint tests: require_role gating + 409 conflict resume payload.

DB-free: the ``AsyncAddressClient`` is replaced with a fake via
``app.dependency_overrides[get_client]`` so no PostgreSQL is touched. The role
gate is exercised through real ``require_role`` dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.dto.source import (
    UploadSessionFileSlot,
    UploadSessionStatus,
)
from kortravelgeo.infra.source_upload_repo import SessionCreateResult
from kortravelgeo.settings import (
    Settings,
    get_settings,
    reset_settings,
    set_settings,
)

# ASGITransport reports a loopback peer; trust it as the admin proxy and turn the
# GeoIP gate off so the test focuses on the role gate.
_SETTINGS = Settings(
    admin_trusted_proxy_cidrs="127.0.0.0/8",
    geoip_gate_mode="off",
    rustfs_enabled=True,
    rustfs_access_key="access",  # type: ignore[arg-type]
    rustfs_secret_key="secret",  # type: ignore[arg-type]
    # avoid picking up any on-disk rustfs config that could flip enabled off
    rustfs_config_path=Path("does-not-exist-t203a.json"),
)


@pytest.fixture(autouse=True)
def _use_test_settings() -> object:
    # The endpoints call module-level get_settings() directly (not via Depends),
    # so override the singleton too (dependency_overrides only covers Depends).
    set_settings(_SETTINGS)
    yield
    reset_settings()


_MANAGER_HEADERS = {
    "X-KTG-Actor": "alice@example.com",
    "X-KTG-Roles": "source_file_manager",
}


def _session(**overrides: object) -> UploadSessionStatus:
    now = datetime(2026, 6, 14, tzinfo=UTC)
    base: dict[str, object] = {
        "upload_session_id": "source_upload_abc",
        "source_file_group_id": "group-1",
        "category": "roadname_hangul_full",
        "group_kind": "single_file",
        "user_yyyymm": "202605",
        "display_name": "202605 도로명주소 한글 전체분",
        "state": "created",
        "expected_file_count": 1,
        "uploaded_file_count": 0,
        "max_bytes": 2 * 1024 * 1024 * 1024,
        "part_size_bytes": 64 * 1024 * 1024,
        "file_slots": (UploadSessionFileSlot(slot="archive"),),
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return UploadSessionStatus(**base)  # type: ignore[arg-type]


class _FakeClient:
    def __init__(self, *, conflict: bool = False) -> None:
        self._conflict = conflict
        self.audit_calls: list[str] = []

    async def create_upload_session(self, req, **_kwargs):  # type: ignore[no-untyped-def]
        existing = _session(state="awaiting_registration", uploaded_file_count=1)
        if self._conflict:
            return SessionCreateResult(session=existing, parts=(), conflict=True)
        return SessionCreateResult(
            session=_session(category=req.category, user_yyyymm=req.user_yyyymm),
            parts=(),
            conflict=False,
        )

    async def list_upload_sessions(self, **_kwargs):  # type: ignore[no-untyped-def]
        return [_session()]

    async def record_audit_event(self, *, action: str, **_kwargs):  # type: ignore[no-untyped-def]
        self.audit_calls.append(action)
        return None


def _app(client: _FakeClient) -> httpx.ASGITransport:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _SETTINGS
    app.dependency_overrides[get_client] = lambda: client
    return httpx.ASGITransport(app=app)


@pytest.mark.asyncio
async def test_create_session_requires_source_file_manager_role() -> None:
    transport = _app(_FakeClient())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # viewer role is insufficient for a mutating endpoint
        resp = await ac.post(
            "/v1/admin/source-files/upload-sessions",
            headers={"X-KTG-Actor": "bob", "X-KTG-Roles": "source_file_viewer"},
            json={
                "category": "roadname_hangul_full",
                "user_yyyymm": "202605",
                "display_name": "x",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_session_201_style_returns_session() -> None:
    transport = _app(_FakeClient())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/admin/source-files/upload-sessions",
            headers=_MANAGER_HEADERS,
            json={
                "category": "roadname_hangul_full",
                "user_yyyymm": "202605",
                "display_name": "202605 도로명주소 한글 전체분",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["upload_session_id"] == "source_upload_abc"
    assert body["user_yyyymm"] == "202605"
    assert body["file_slots"][0]["slot"] == "archive"


@pytest.mark.asyncio
async def test_create_session_409_returns_conflict_resume_payload() -> None:
    transport = _app(_FakeClient(conflict=True))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/admin/source-files/upload-sessions",
            headers=_MANAGER_HEADERS,
            json={
                "category": "roadname_hangul_full",
                "user_yyyymm": "202605",
                "display_name": "x",
            },
        )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "upload_session_conflict"
    assert body["upload_session_id"] == "source_upload_abc"
    assert body["existing_session"]["state"] == "awaiting_registration"
    assert "resume_upload" in body["resumable_actions"]


@pytest.mark.asyncio
async def test_list_sessions_requires_viewer_and_returns_sessions() -> None:
    transport = _app(_FakeClient())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        unauth = await ac.get("/v1/admin/source-files/upload-sessions")
        assert unauth.status_code == 403

        ok = await ac.get(
            "/v1/admin/source-files/upload-sessions",
            headers={"X-KTG-Actor": "bob", "X-KTG-Roles": "source_file_viewer"},
        )
    assert ok.status_code == 200
    assert ok.json()[0]["upload_session_id"] == "source_upload_abc"
