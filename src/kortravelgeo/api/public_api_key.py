"""Public API key dependency for REST v1/v2 surfaces."""

from __future__ import annotations

import hmac
from collections.abc import Sequence
from typing import Annotated, Literal

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
    _query_key_contract: str | None = Query(
        default=None,
        alias=PUBLIC_API_KEY_QUERY_PARAM,
        min_length=1,
        max_length=128,
        description=(
            "브라우저/VWorld 호환 공개 API 인증키. 서버 간 호출은 X-KTG-API-Key를 사용한다."
        ),
    ),
    _header_key_contract: str | None = Header(
        default=None,
        alias=PUBLIC_API_KEY_HEADER,
        min_length=1,
        max_length=128,
        description="서버 간 공개 API 인증키. 관리자 권한을 부여하지 않는다.",
    ),
) -> None:
    """Require a valid public API key for public REST endpoints."""

    api_key, source = _resolve_public_api_key(
        request.query_params.getlist(PUBLIC_API_KEY_QUERY_PARAM),
        request.headers.getlist(PUBLIC_API_KEY_HEADER),
    )
    if api_key is not None:
        assert source is not None
        _validate_public_api_key_shape(api_key, source=source)
    if _trusted_public_client(request, settings):
        return
    if api_key is None:
        _validate_public_api_key_shape(None, source="query")
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


def _resolve_public_api_key(
    query_keys: Sequence[str],
    header_keys: Sequence[str],
) -> tuple[str | None, Literal["query", "header"] | None]:
    if len(query_keys) > 1 or len(header_keys) > 1:
        raise ApiKeyError("공개 API 인증키를 같은 위치에 여러 번 전달할 수 없습니다.")
    query_key = query_keys[0] if query_keys else None
    header_key = header_keys[0] if header_keys else None
    if query_key is not None and header_key is not None:
        if not hmac.compare_digest(query_key.encode(), header_key.encode()):
            raise ApiKeyError("공개 API 인증키 전달값이 서로 다릅니다.")
        return header_key, "header"
    if header_key is not None:
        return header_key, "header"
    if query_key is not None:
        return query_key, "query"
    return None, None


def _validate_public_api_key_shape(
    key: str | None,
    *,
    source: Literal["query", "header"],
) -> None:
    if key is None:
        raise _public_api_key_validation_error(
            "missing", "Field required", None, source=source
        )
    if len(key) < 1:
        raise _public_api_key_validation_error(
            "string_too_short",
            "String should have at least 1 character",
            key,
            source=source,
        )
    if len(key) > 128:
        raise _public_api_key_validation_error(
            "string_too_long",
            "String should have at most 128 characters",
            key,
            source=source,
        )


def _public_api_key_validation_error(
    error_type: str,
    message: str,
    value: str | None,
    *,
    source: Literal["query", "header"],
) -> RequestValidationError:
    field = PUBLIC_API_KEY_HEADER if source == "header" else PUBLIC_API_KEY_QUERY_PARAM
    return RequestValidationError(
        [
            {
                "type": error_type,
                "loc": (source, field),
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
