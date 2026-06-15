"""T-203b endpoint tests: register + validate role gating and guards.

DB-free: ``AsyncAddressClient`` is faked via ``dependency_overrides[get_client]``
and RustFS is stubbed so no PostgreSQL / object store is touched. Exercises the
real ``require_role`` gate and the ``confirm_user_yyyymm`` guard.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.dto.source import (
    GroupValidationResult,
    RegisterResponse,
    SourceFileRegistered,
    UploadSessionFileSlot,
    UploadSessionPartStatus,
    UploadSessionStatus,
)
from kortravelgeo.settings import Settings, get_settings, reset_settings, set_settings

if TYPE_CHECKING:
    from kortravelgeo.core.source_validation import GroupValidation

_SETTINGS = Settings(
    admin_trusted_proxy_cidrs="127.0.0.0/8",
    geoip_gate_mode="off",
    rustfs_enabled=True,
    rustfs_access_key="access",  # type: ignore[arg-type]
    rustfs_secret_key="secret",  # type: ignore[arg-type]
    rustfs_config_path=Path("does-not-exist-t203b.json"),
)

_MANAGER_HEADERS = {"X-KTG-Actor": "alice", "X-KTG-Roles": "source_file_manager"}


@pytest.fixture(autouse=True)
def _use_test_settings() -> object:
    set_settings(_SETTINGS)
    yield
    reset_settings()


def _session(**overrides: object) -> UploadSessionStatus:
    now = datetime(2026, 6, 14, tzinfo=UTC)
    base: dict[str, object] = {
        "upload_session_id": "source_upload_abc",
        "source_file_group_id": "group-1",
        "category": "roadname_hangul_full",
        "group_kind": "single_file",
        "user_yyyymm": "202605",
        "display_name": "202605 도로명주소 한글 전체분",
        "state": "awaiting_registration",
        "storage_kind": "local",  # avoid live RustFS head in the endpoint
        "expected_file_count": 1,
        "uploaded_file_count": 1,
        "max_bytes": 2 * 1024 * 1024 * 1024,
        "part_size_bytes": 64 * 1024 * 1024,
        "file_slots": (
            UploadSessionFileSlot(slot="archive", uploaded=True, received_bytes=10),
        ),
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return UploadSessionStatus(**base)  # type: ignore[arg-type]


class _FakeClient:
    def __init__(self) -> None:
        self.registered = False
        self.audit_calls: list[str] = []
        self.last_structure: GroupValidation | None = None

    async def get_upload_session(self, _sid: str) -> UploadSessionStatus:
        return _session()

    async def upload_session_slot_parts(self, _sid, *, part_key):  # type: ignore[no-untyped-def]
        return (
            UploadSessionPartStatus(
                part_key=part_key,
                part_number=1,
                part_etag="etag",
                part_sha256="a" * 64,
                received_bytes=10,
                completed_at=datetime(2026, 6, 14, tzinfo=UTC),
            ),
        )

    async def register_source_group(self, **kwargs):  # type: ignore[no-untyped-def]
        self.registered = True
        structure: GroupValidation = kwargs["structure_validation"]
        self.last_structure = structure
        return RegisterResponse(
            source_file_group_id="group-1",
            category="roadname_hangul_full",
            group_kind="single_file",
            state="available",
            validation_state=structure.outcome,  # type: ignore[arg-type]
            user_yyyymm="202605",
            group_sha256="a" * 64,
            files=(
                SourceFileRegistered(
                    source_file_id="f1",
                    original_filename="archive",
                    sha256="a" * 64,
                    size_bytes=10,
                    storage_uri="local://k",
                    object_key="k",
                    state="available",
                ),
            ),
        )

    async def revalidate_source_file_group(self, gid, *, actor):  # type: ignore[no-untyped-def]
        return GroupValidationResult(
            source_file_group_id=gid,
            category="roadname_hangul_full",
            validation_state="passed",
            state="available",
            coverage={"archive": "present"},
            validator_version="t203b.1",
        )

    async def update_upload_session_state(self, *_a, **_k):  # type: ignore[no-untyped-def]
        return _session(state="failed_register")

    async def record_audit_event(self, *, action: str, **_kwargs):  # type: ignore[no-untyped-def]
        self.audit_calls.append(action)
        return None


def _transport(client: _FakeClient) -> httpx.ASGITransport:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _SETTINGS
    app.dependency_overrides[get_client] = lambda: client
    return httpx.ASGITransport(app=app)


@pytest.mark.asyncio
async def test_register_requires_manager_role() -> None:
    transport = _transport(_FakeClient())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/admin/source-files/upload-sessions/source_upload_abc/register",
            headers={"X-KTG-Actor": "bob", "X-KTG-Roles": "source_file_viewer"},
            json={"confirm_user_yyyymm": "202605"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_rejects_confirm_yyyymm_mismatch() -> None:
    transport = _transport(_FakeClient())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/admin/source-files/upload-sessions/source_upload_abc/register",
            headers=_MANAGER_HEADERS,
            json={"confirm_user_yyyymm": "202601"},  # != session 202605
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_happy_path_returns_group() -> None:
    client = _FakeClient()
    transport = _transport(client)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/admin/source-files/upload-sessions/source_upload_abc/register",
            headers=_MANAGER_HEADERS,
            json={"confirm_user_yyyymm": "202605"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_file_group_id"] == "group-1"
    assert body["state"] == "available"
    assert body["files"][0]["sha256"] == "a" * 64
    assert client.registered is True
    assert client.last_structure is not None
    assert client.last_structure.outcome == "passed"


@pytest.mark.asyncio
async def test_validate_group_requires_manager_role() -> None:
    transport = _transport(_FakeClient())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        unauth = await ac.post(
            "/v1/admin/source-file-groups/group-1/validate",
            headers={"X-KTG-Actor": "bob", "X-KTG-Roles": "source_file_viewer"},
        )
    assert unauth.status_code == 403


@pytest.mark.asyncio
async def test_validate_group_happy_path() -> None:
    client = _FakeClient()
    transport = _transport(client)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/admin/source-file-groups/group-1/validate",
            headers=_MANAGER_HEADERS,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["validation_state"] == "passed"
    assert body["coverage"]["archive"] == "present"
    assert "source.group_validate" in client.audit_calls
