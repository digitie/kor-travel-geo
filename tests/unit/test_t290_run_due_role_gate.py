"""T-290 / #429: least-privilege gate on the scheduled-backup run-due on-ramp.

The Dagster ``scheduled_backup`` on-ramp calls
``POST /v1/admin/backups/scheduled/run-due``. Before #429 the route sat only under the
router-wide ``require_role(*KNOWN_ADMIN_ROLES)``, so any admin role could enqueue a
scheduled backup and the on-ramp sent ``destructive_admin`` (least-privilege violation).
It is now gated to ``scheduler`` (the least-privilege on-ramp role) or
``destructive_admin`` (manual operator trigger); the on-ramp presents only ``scheduler``.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client, get_job_queue
from kortravelgeo.api.responses import register_exception_handlers
from kortravelgeo.api.security import (
    ROLE_DESTRUCTIVE_ADMIN,
    ROLE_REBUILD_OPERATOR,
    ROLE_SCHEDULER,
    ROLE_SOURCE_FILE_MANAGER,
    ROLE_SOURCE_FILE_VIEWER,
    RequestContext,
    require_role,
)
from kortravelgeo.settings import Settings, get_settings

_TRUSTED_PEER = ("127.0.0.1", 12345)
_RUN_DUE = "/v1/admin/backups/scheduled/run-due"


def _trusted_settings() -> Settings:
    # Trusted proxy peer + GeoIP off so a request reaches the role gate on its merits.
    return Settings(
        _env_file=None,
        admin_trusted_proxy_cidrs="127.0.0.0/8",
        geoip_gate_mode="off",
    )


# --- real run-due route: known-but-insufficient admin roles are rejected -----------
# These roles pass the router-wide require_role(*KNOWN_ADMIN_ROLES) but must fail the
# stricter route gate, so a 403 here proves run-due carries the scheduler gate. The DB
# dependencies are stubbed because the body never runs for a gate rejection (and to keep
# the assertion independent of dependency-resolution order).


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [ROLE_SOURCE_FILE_VIEWER, ROLE_SOURCE_FILE_MANAGER, ROLE_REBUILD_OPERATOR],
)
async def test_run_due_rejects_non_scheduler_admin_roles(role: str) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = _trusted_settings
    app.dependency_overrides[get_client] = lambda: object()
    app.dependency_overrides[get_job_queue] = lambda: object()
    transport = httpx.ASGITransport(app=app, client=_TRUSTED_PEER)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            _RUN_DUE,
            headers={"X-KTG-Actor": "ui-admin", "X-KTG-Roles": role},
        )
    assert resp.status_code == 403
    assert resp.json()["response"]["errorCode"] == "E0403"


# --- gate semantics (DB-free minimal app mirroring the run-due gate) ----------------

_GATE = Depends(require_role(ROLE_SCHEDULER, ROLE_DESTRUCTIVE_ADMIN))


def _gate_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_settings] = _trusted_settings

    @app.post("/gated")
    def gated(ctx: RequestContext = _GATE) -> dict[str, object]:
        return {"roles": sorted(ctx.roles)}

    return app


@pytest.mark.parametrize("role", [ROLE_SCHEDULER, ROLE_DESTRUCTIVE_ADMIN])
def test_run_due_gate_admits_scheduler_and_destructive(role: str) -> None:
    client = TestClient(_gate_app(), client=_TRUSTED_PEER)
    resp = client.post("/gated", headers={"X-KTG-Actor": "a", "X-KTG-Roles": role})
    assert resp.status_code == 200
    assert role in resp.json()["roles"]


@pytest.mark.parametrize("role", [ROLE_SOURCE_FILE_VIEWER, ROLE_REBUILD_OPERATOR])
def test_run_due_gate_rejects_other_admin_roles(role: str) -> None:
    client = TestClient(_gate_app(), client=_TRUSTED_PEER)
    resp = client.post("/gated", headers={"X-KTG-Actor": "a", "X-KTG-Roles": role})
    assert resp.status_code == 403
    assert resp.json()["response"]["errorCode"] == "E0403"
