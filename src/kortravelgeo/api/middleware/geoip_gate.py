"""FastAPI wiring for the Korea-only GeoIP gate."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse, Response

from kortravelgeo.infra.admin_repo import AdminRepository
from kortravelgeo.infra.geoip import (
    GeoIpCountryReader,
    GeoIpDecision,
    build_geoip_reader,
    classify_ip,
    client_ip_from_forwarded,
    is_open_path,
)
from kortravelgeo.settings import Settings

_LOGGER = logging.getLogger(__name__)


def install_geoip_gate(
    app: FastAPI,
    settings: Settings,
    *,
    reader: GeoIpCountryReader | None = None,
) -> None:
    if settings.geoip_gate_mode == "off":
        return
    resolved_reader = reader if reader is not None else build_geoip_reader(settings)

    @app.middleware("http")
    async def geoip_gate(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if is_open_path(request.url.path, settings.geoip_open_paths):
            return await call_next(request)

        peer_host = request.client.host if request.client else ""
        client_ip = client_ip_from_forwarded(
            peer_host,
            request.headers.get("x-forwarded-for"),
            settings.geoip_trusted_proxies,
        )
        decision = classify_ip(
            client_ip,
            reader=resolved_reader,
            mode=settings.geoip_gate_mode,
            allow_cidrs=settings.geoip_allow_cidrs,
            deny_cidrs=settings.geoip_deny_cidrs,
        )
        if decision.allowed:
            return await call_next(request)

        if settings.geoip_audit_denials:
            await _record_denial_audit(request, decision)
        return _deny_response(decision)


def _deny_response(decision: GeoIpDecision) -> ORJSONResponse:
    return ORJSONResponse(
        {
            "response": {
                "status": "ERROR",
                "errorCode": "E0403",
                "errorMessage": "이 서비스는 대한민국 IP에서만 호출할 수 있습니다.",
                "message_en": "This service is restricted to requests from South Korea.",
                "client_country": decision.country_code,
                "reason": decision.reason,
            }
        },
        status_code=403,
    )


async def _record_denial_audit(request: Request, decision: GeoIpDecision) -> None:
    client = getattr(request.app.state, "client", None)
    engine = getattr(client, "engine", None)
    if engine is None:
        return
    try:
        await AdminRepository(engine).record_audit_event(
            action="geoip.denied",
            actor_type="api",
            outcome="denied",
            client_ip=decision.client_ip,
            user_agent=request.headers.get("user-agent"),
            payload={
                "path": request.url.path,
                "method": request.method,
                "client_country": decision.country_code,
                "reason": decision.reason,
            },
            resource_type="http_request",
            resource_id=request.url.path,
        )
    except Exception:
        _LOGGER.exception("failed to record geoip.denied audit event")
