"""Public API key dependency for REST v1/v2 surfaces."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.api.security import resolve_request_context
from kortravelgeo.exceptions import ApiKeyError
from kortravelgeo.infra.public_api_keys import (
    PUBLIC_API_KEY_QUERY_PARAM,
    cached_active_public_api_key_hashes,
    hash_public_api_key,
    public_api_key_matches,
)
from kortravelgeo.settings import Settings, get_settings


async def require_public_api_key(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    key: str | None = Query(
        default=None,
        alias=PUBLIC_API_KEY_QUERY_PARAM,
        description="외부/비신뢰 클라이언트는 필수. trusted admin proxy 요청은 검증을 우회한다.",
    ),
) -> None:
    """Require a valid public API key for public REST endpoints."""

    if _trusted_public_client(request, settings):
        return
    _validate_public_api_key_shape(key)
    assert key is not None
    engine = _engine_from_request(request)
    active_hashes = (
        await cached_active_public_api_key_hashes(
            engine,
            ttl_seconds=settings.public_api_key_cache_ttl_s,
        )
        if engine is not None
        else frozenset()
    )
    effective_hashes = active_hashes or _vworld_default_key_hashes(settings)
    if not effective_hashes or not public_api_key_matches(key, effective_hashes):
        raise ApiKeyError("VWorld 호환 인증키가 유효하지 않습니다.")


def _trusted_public_client(request: Request, settings: Settings) -> bool:
    return resolve_request_context(request, settings) is not None


def _validate_public_api_key_shape(key: str | None) -> None:
    if key is None:
        raise _public_api_key_validation_error("missing", "Field required", None)
    if len(key) < 1:
        raise _public_api_key_validation_error(
            "string_too_short",
            "String should have at least 1 character",
            key,
        )
    if len(key) > 128:
        raise _public_api_key_validation_error(
            "string_too_long",
            "String should have at most 128 characters",
            key,
        )


def _public_api_key_validation_error(
    error_type: str,
    message: str,
    value: str | None,
) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": error_type,
                "loc": ("query", PUBLIC_API_KEY_QUERY_PARAM),
                "msg": message,
                "input": value,
            }
        ]
    )


def _engine_from_request(request: Request) -> AsyncEngine | None:
    client = getattr(request.app.state, "client", None)
    engine = getattr(client, "engine", None)
    return engine if isinstance(engine, AsyncEngine) else None


def _vworld_default_key_hashes(settings: Settings) -> frozenset[str]:
    if settings.vworld_api_key is None:
        return frozenset()
    key = settings.vworld_api_key.get_secret_value().strip()
    if not key:
        return frozenset()
    return frozenset({hash_public_api_key(key)})
