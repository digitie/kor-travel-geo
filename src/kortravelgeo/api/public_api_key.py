"""Public API key dependency for REST v1/v2 surfaces."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

from kortravelgeo.api.security import resolve_request_context
from kortravelgeo.exceptions import ApiKeyError
from kortravelgeo.infra.public_api_keys import (
    PUBLIC_API_KEY_QUERY_PARAM,
    PublicApiKeyRepository,
    hash_public_api_key,
    public_api_key_matches,
)
from kortravelgeo.settings import Settings, get_settings

PUBLIC_API_KEY_HEADER = "X-KTG-API-Key"


async def require_public_api_key(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    key: str | None = Query(
        default=None,
        alias=PUBLIC_API_KEY_QUERY_PARAM,
        description=(
            "브라우저/VWorld 호환 공개 API 인증키. 서버 간 호출은 X-KTG-API-Key를 사용한다."
        ),
    ),
    header_key: str | None = Header(
        default=None,
        alias=PUBLIC_API_KEY_HEADER,
        description="서버 간 공개 API 인증키. 관리자 권한을 부여하지 않는다.",
    ),
) -> None:
    """Require a valid public API key for public REST endpoints."""

    if _trusted_public_client(request, settings):
        return
    api_key = _resolve_public_api_key(key, header_key)
    _validate_public_api_key_shape(api_key)
    assert api_key is not None
    engine = _engine_from_request(request)
    if engine is not None:
        active_hashes = await PublicApiKeyRepository(engine).active_key_hashes()
    else:
        active_hashes = frozenset()
    effective_hashes = active_hashes or _vworld_default_key_hashes(settings)
    if not effective_hashes or not public_api_key_matches(api_key, effective_hashes):
        raise ApiKeyError("VWorld 호환 인증키가 유효하지 않습니다.")


def _trusted_public_client(request: Request, settings: Settings) -> bool:
    return resolve_request_context(request, settings) is not None


def _resolve_public_api_key(query_key: str | None, header_key: str | None) -> str | None:
    if query_key is not None and header_key is not None:
        if not hmac.compare_digest(query_key, header_key):
            raise ApiKeyError("공개 API 인증키 전달값이 서로 다릅니다.")
        return header_key
    return header_key if header_key is not None else query_key


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
