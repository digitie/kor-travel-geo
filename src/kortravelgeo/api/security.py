"""Admin role gate (T-202, ADR-049 #5).

Identity is injected by a trusted reverse proxy / Next.js admin proxy via the
``X-KTG-Actor`` and ``X-KTG-Roles`` headers. The backend only trusts these
headers when the request's peer address is inside the configured admin
trusted-proxy CIDRs (falling back to ``geoip_trusted_proxies``); a direct
external request that forges the same headers is ignored and therefore 403s.

Gate ordering (doc "Admin 권한 모델" #7): the ADR-037 Korea-only GeoIP gate is
installed as HTTP middleware in :func:`kortravelgeo.api.app.create_app` and runs
for the whole request *before* any route is matched. ``require_role`` is a route
*dependency*, which Starlette resolves only after middleware has run, so GeoIP
always precedes the role gate without any extra wiring. Source-management APIs do
not get a GeoIP bypass.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, Request

from kortravelgeo.core.source_events import (
    SOURCE_AUDIT_EVENT_TYPES,
    SOURCE_FORCED_PROMOTION,
    SOURCE_HARD_DELETE,
    SOURCE_JANITOR,
    SOURCE_MATCH_SET_ACTIVATE,
    SOURCE_REBUILD_DB,
    SOURCE_UPDATE_HASH_AFTER_VERIFY,
    SOURCE_UPLOAD_REGISTER,
)
from kortravelgeo.exceptions import ForbiddenError
from kortravelgeo.infra.geoip import _in_networks, _parse_ip
from kortravelgeo.settings import Settings, get_settings

#: Re-exported for backward compatibility: the source-management audit
#: event_type / action constants now live in ``core.source_events`` (so lower
#: layers can use them without importing ``api``), but importing them from
#: ``api.security`` must keep working.
__all__ = [
    "ACTOR_HEADER",
    "ADMIN_PROXY_SECRET_HEADER",
    "KNOWN_ADMIN_ROLES",
    "ROLES_HEADER",
    "ROLE_DESTRUCTIVE_ADMIN",
    "ROLE_REBUILD_OPERATOR",
    "ROLE_SCHEDULER",
    "ROLE_SOURCE_FILE_MANAGER",
    "ROLE_SOURCE_FILE_VIEWER",
    "ROLE_SYSTEM",
    "SOURCE_AUDIT_EVENT_TYPES",
    "SOURCE_FORCED_PROMOTION",
    "SOURCE_HARD_DELETE",
    "SOURCE_JANITOR",
    "SOURCE_MATCH_SET_ACTIVATE",
    "SOURCE_REBUILD_DB",
    "SOURCE_UPDATE_HASH_AFTER_VERIFY",
    "SOURCE_UPLOAD_REGISTER",
    "RequestContext",
    "get_request_context",
    "require_role",
    "resolve_request_context",
]

# --- Roles -----------------------------------------------------------------
# Verbatim from docs/t109-backup-source-upload-management.md "Admin 권한 모델"
# 권장 role table (lines 1180-1185).
ROLE_SOURCE_FILE_VIEWER = "source_file_viewer"
ROLE_SOURCE_FILE_MANAGER = "source_file_manager"
ROLE_REBUILD_OPERATOR = "rebuild_operator"
ROLE_DESTRUCTIVE_ADMIN = "destructive_admin"

#: Least-privilege role for the internal scheduled-backup on-ramp (T-290 / ADR-066).
#: The Dagster ``scheduled_backup`` schedule calls
#: ``POST /v1/admin/backups/scheduled/run-due``, which only due-checks and enqueues a
#: scheduled backup — it needs no destructive scope. The Dagster ``admin_api`` on-ramp
#: presents this role (never ``destructive_admin``) so the shared-secret system actor is
#: confined to the run-due gate (least privilege). Unlike ``system`` it is
#: header-carriable, because the on-ramp authenticates as a trusted proxy and must pass
#: ``_parse_roles`` (which drops any role outside ``KNOWN_ADMIN_ROLES``).
ROLE_SCHEDULER = "scheduler"

#: Role name reserved for internal job / scheduler actors (doc #4). It is never
#: derived from request headers; it exists so audit rows can record role="system"
#: for ``system:<job_kind>`` actors.
ROLE_SYSTEM = "system"

#: Roles that may be carried by a request via X-KTG-Roles. ``system`` is
#: intentionally excluded: external callers must never claim to be the system.
KNOWN_ADMIN_ROLES: frozenset[str] = frozenset(
    {
        ROLE_SOURCE_FILE_VIEWER,
        ROLE_SOURCE_FILE_MANAGER,
        ROLE_REBUILD_OPERATOR,
        ROLE_DESTRUCTIVE_ADMIN,
        ROLE_SCHEDULER,
    }
)

ACTOR_HEADER = "x-ktg-actor"
ROLES_HEADER = "x-ktg-roles"
ADMIN_PROXY_SECRET_HEADER = "x-ktg-admin-proxy-secret"


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Authenticated admin actor resolved from trusted proxy headers.

    ``actor`` is the identity string the proxy injected (mapped to
    ``ops.audit_events.actor_id`` with ``actor_type="ui"``). ``roles`` is the
    set of recognized roles the actor presented.
    """

    actor: str
    roles: frozenset[str]
    request_id: str | None = None
    trace_id: str | None = field(default=None)

    def has_any_role(self, roles: frozenset[str]) -> bool:
        return bool(self.roles & roles)


def _peer_is_trusted(request: Request, settings: Settings) -> bool:
    proxies = settings.admin_trusted_proxy_cidrs or settings.geoip_trusted_proxies
    if not proxies:
        return False
    peer_host = request.client.host if request.client else ""
    peer_ip = _parse_ip(peer_host)
    return peer_ip is not None and _in_networks(peer_ip, proxies)


def _parse_roles(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(
        part.strip() for part in raw.split(",") if part.strip() in KNOWN_ADMIN_ROLES
    )


def _admin_proxy_secret_matches(request: Request, settings: Settings) -> bool:
    expected = settings.admin_proxy_secret
    if expected is None:
        return True
    actual = (request.headers.get(ADMIN_PROXY_SECRET_HEADER) or "").strip()
    if not actual:
        return False
    return hmac.compare_digest(actual, expected.get_secret_value())


def resolve_request_context(request: Request, settings: Settings) -> RequestContext | None:
    """Build a :class:`RequestContext` from trusted proxy headers, or ``None``.

    Returns ``None`` (→ 403 at the gate) when the peer is not a trusted proxy,
    the actor header is missing/blank, or no recognized role is presented. An
    empty / unrecognized role set is never treated as an administrator (doc #6).
    """
    if not _peer_is_trusted(request, settings):
        return None
    if not _admin_proxy_secret_matches(request, settings):
        return None
    actor = (request.headers.get(ACTOR_HEADER) or "").strip()
    if not actor:
        return None
    roles = _parse_roles(request.headers.get(ROLES_HEADER))
    if not roles:
        return None
    return RequestContext(
        actor=actor,
        roles=roles,
        request_id=request.headers.get("x-request-id"),
        trace_id=request.headers.get("traceparent"),
    )


def get_request_context(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RequestContext:
    """FastAPI dependency returning the admin context or raising 403."""
    context = resolve_request_context(request, settings)
    if context is None:
        raise ForbiddenError(
            "admin identity required",
            hint="request must arrive via a trusted proxy with valid "
            "X-KTG-Actor and X-KTG-Roles headers",
        )
    return context


def require_role(
    *roles: str,
) -> Callable[..., Coroutine[Any, Any, RequestContext]]:
    """Return a FastAPI dependency that requires at least one of ``roles``.

    403s when the request has no trusted admin context, the actor header is
    missing, or none of the required roles are present.
    """
    required = frozenset(roles)

    async def dependency(
        context: Annotated[RequestContext, Depends(get_request_context)],
    ) -> RequestContext:
        if not context.has_any_role(required):
            raise ForbiddenError(
                "insufficient role for this action",
                hint=f"requires one of: {', '.join(sorted(required))}",
            )
        return context

    return dependency
