"""T-202 admin role gate: header parsing, RequestContext, require_role."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from kortravelgeo.api.responses import register_exception_handlers
from kortravelgeo.api.security import (
    KNOWN_ADMIN_ROLES,
    ROLE_DESTRUCTIVE_ADMIN,
    ROLE_REBUILD_OPERATOR,
    ROLE_SOURCE_FILE_MANAGER,
    ROLE_SOURCE_FILE_VIEWER,
    SOURCE_AUDIT_EVENT_TYPES,
    RequestContext,
    require_role,
    resolve_request_context,
)
from kortravelgeo.exceptions import ForbiddenError
from kortravelgeo.settings import Settings

_TRUSTED = "10.0.0.1"
_UNTRUSTED = "203.0.113.9"
_SETTINGS = Settings(
    _env_file=None,
    admin_trusted_proxy_cidrs="10.0.0.0/8",
    geoip_gate_mode="off",
)


_REBUILD_DEP = Depends(require_role(ROLE_REBUILD_OPERATOR))


def _build_app() -> FastAPI:
    from kortravelgeo.settings import get_settings

    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: _SETTINGS

    @app.get("/protected")
    def protected(ctx: RequestContext = _REBUILD_DEP) -> dict[str, object]:
        return {"actor": ctx.actor, "roles": sorted(ctx.roles)}

    return app


# --- role / constant fixtures ---------------------------------------------


def test_four_role_names_match_doc() -> None:
    expected = {
        "source_file_viewer",
        "source_file_manager",
        "rebuild_operator",
        "destructive_admin",
    }
    assert set(KNOWN_ADMIN_ROLES) == expected
    assert ROLE_SOURCE_FILE_VIEWER == "source_file_viewer"
    assert ROLE_SOURCE_FILE_MANAGER == "source_file_manager"
    assert ROLE_REBUILD_OPERATOR == "rebuild_operator"
    assert ROLE_DESTRUCTIVE_ADMIN == "destructive_admin"


def test_source_audit_event_types_defined() -> None:
    assert "source_upload.register" in SOURCE_AUDIT_EVENT_TYPES
    assert "source_match_set.activate" in SOURCE_AUDIT_EVENT_TYPES
    assert "source.rebuild_db" in SOURCE_AUDIT_EVENT_TYPES
    assert "source.forced_promotion" in SOURCE_AUDIT_EVENT_TYPES
    assert "source.hard_delete" in SOURCE_AUDIT_EVENT_TYPES
    assert "source.update_hash_after_verify" in SOURCE_AUDIT_EVENT_TYPES
    assert "source.janitor" in SOURCE_AUDIT_EVENT_TYPES


# --- resolve_request_context (header parsing) ------------------------------


class _FakeRequest:
    def __init__(self, host: str | None, headers: dict[str, str]) -> None:
        self.client = None if host is None else type("C", (), {"host": host})()
        self.headers = {k.lower(): v for k, v in headers.items()}


def _resolve(host: str | None, headers: dict[str, str]) -> RequestContext | None:
    return resolve_request_context(_FakeRequest(host, headers), _SETTINGS)  # type: ignore[arg-type]


def test_resolve_parses_actor_and_roles_from_trusted_proxy() -> None:
    ctx = _resolve(
        _TRUSTED,
        {
            "X-KTG-Actor": "alice@example.com",
            "X-KTG-Roles": "source_file_viewer, rebuild_operator",
            "x-request-id": "req-1",
        },
    )
    assert ctx is not None
    assert ctx.actor == "alice@example.com"
    assert ctx.roles == frozenset({"source_file_viewer", "rebuild_operator"})
    assert ctx.request_id == "req-1"
    assert ctx.has_any_role(frozenset({"rebuild_operator"})) is True


def test_resolve_ignores_unrecognized_roles() -> None:
    ctx = _resolve(
        _TRUSTED,
        {"X-KTG-Actor": "bob", "X-KTG-Roles": "rebuild_operator, superuser, system"},
    )
    assert ctx is not None
    assert ctx.roles == frozenset({"rebuild_operator"})


def test_resolve_none_when_no_recognized_role() -> None:
    assert _resolve(_TRUSTED, {"X-KTG-Actor": "bob", "X-KTG-Roles": "superuser"}) is None
    # empty roles must never be treated as admin (doc #6)
    assert _resolve(_TRUSTED, {"X-KTG-Actor": "bob", "X-KTG-Roles": ""}) is None
    assert _resolve(_TRUSTED, {"X-KTG-Actor": "bob"}) is None


def test_resolve_none_when_actor_missing() -> None:
    assert _resolve(_TRUSTED, {"X-KTG-Roles": "rebuild_operator"}) is None
    assert _resolve(_TRUSTED, {"X-KTG-Actor": "  ", "X-KTG-Roles": "rebuild_operator"}) is None


def test_resolve_none_from_untrusted_peer_even_with_headers() -> None:
    headers = {"X-KTG-Actor": "mallory", "X-KTG-Roles": "destructive_admin"}
    assert _resolve(_UNTRUSTED, headers) is None
    assert _resolve(None, headers) is None


# --- require_role via TestClient -------------------------------------------


def test_require_role_passes_with_matching_role() -> None:
    client = TestClient(_build_app(), client=(_TRUSTED, 5000))
    resp = client.get(
        "/protected",
        headers={"X-KTG-Actor": "carol", "X-KTG-Roles": "rebuild_operator"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"actor": "carol", "roles": ["rebuild_operator"]}


def test_require_role_403_when_header_missing() -> None:
    client = TestClient(_build_app(), client=(_TRUSTED, 5000))
    resp = client.get("/protected")
    assert resp.status_code == 403
    assert resp.json()["response"]["errorCode"] == "E0403"


def test_require_role_403_when_role_missing() -> None:
    client = TestClient(_build_app(), client=(_TRUSTED, 5000))
    # valid actor + a recognized but insufficient role
    resp = client.get(
        "/protected",
        headers={"X-KTG-Actor": "dave", "X-KTG-Roles": "source_file_viewer"},
    )
    assert resp.status_code == 403
    assert resp.json()["response"]["errorCode"] == "E0403"


def test_require_role_403_when_role_unrecognized() -> None:
    client = TestClient(_build_app(), client=(_TRUSTED, 5000))
    resp = client.get(
        "/protected",
        headers={"X-KTG-Actor": "erin", "X-KTG-Roles": "root"},
    )
    assert resp.status_code == 403
    assert resp.json()["response"]["errorCode"] == "E0403"


def test_require_role_403_from_untrusted_peer() -> None:
    client = TestClient(_build_app(), client=(_UNTRUSTED, 5000))
    resp = client.get(
        "/protected",
        headers={"X-KTG-Actor": "frank", "X-KTG-Roles": "rebuild_operator"},
    )
    assert resp.status_code == 403


def test_forbidden_error_is_403() -> None:
    err = ForbiddenError("nope")
    assert err.code == "E0403"
    assert err.http_status == 403
