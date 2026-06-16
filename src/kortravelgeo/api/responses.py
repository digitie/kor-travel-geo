"""FastAPI exception response wiring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from kortravelgeo.api.vworld import (
    VWorldOperation,
    vworld_error_payload,
    vworld_operation_for_path,
    vworld_validation_error_payload,
)
from kortravelgeo.exceptions import (
    DatabaseError,
    InvalidCoordinateError,
    InvalidInputError,
    KorTravelGeoError,
)
from kortravelgeo.infra.metrics import record_api_db_error, record_db_pool_checkout_timeout

_COORDINATE_BOUNDS_ERROR = "kor_travel_geo.coordinate_bounds"
_COORDINATE_BOUNDS_MESSAGE = "point must be within Korea lon/lat bounds: 123 < x < 132, 32 < y < 39"
_POOL_TIMEOUT_MESSAGE = "database connection pool checkout timed out"
_POOL_TIMEOUT_HINT = (
    "increase KTG_PG_POOL_SIZE/KTG_PG_MAX_OVERFLOW, lower KTG_API_MAX_CONCURRENCY, "
    "or raise KTG_PG_POOL_TIMEOUT_MS after checking DB capacity"
)
_DB_UNAVAILABLE_MESSAGE = "database operation failed"
_DB_UNAVAILABLE_HINT = (
    "check KTG_PG_DSN, PostgreSQL connectivity, and /v1/readyz before retrying"
)
_MAX_VALIDATION_HINT_PARTS = 8
_MAX_VALIDATION_HINT_CHARS = 600


def error_payload(
    exc: KorTravelGeoError,
    *,
    operation: VWorldOperation | None = None,
) -> dict[str, object]:
    if operation is not None:
        return vworld_error_payload(exc, operation=operation)
    body: dict[str, object] = {
        "response": {
            "status": "ERROR",
            "errorCode": exc.code,
            "errorMessage": exc.message,
        }
    }
    if exc.hint:
        body["response"]["hint"] = exc.hint  # type: ignore[index]
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(KorTravelGeoError)
    async def handle_ktg_error(request: Request, exc: KorTravelGeoError) -> ORJSONResponse:
        operation = vworld_operation_for_path(request.url.path)
        return ORJSONResponse(error_payload(exc, operation=operation), status_code=exc.http_status)

    @app.exception_handler(SQLAlchemyTimeoutError)
    async def handle_sqlalchemy_timeout_error(
        request: Request,
        _exc: SQLAlchemyTimeoutError,
    ) -> ORJSONResponse:
        route = _route_template(request)
        record_db_pool_checkout_timeout(method=request.method, route=route)
        domain_error = DatabaseError(_POOL_TIMEOUT_MESSAGE, hint=_POOL_TIMEOUT_HINT)
        operation = vworld_operation_for_path(request.url.path)
        return ORJSONResponse(
            error_payload(domain_error, operation=operation),
            status_code=domain_error.http_status,
        )

    @app.exception_handler(DBAPIError)
    async def handle_sqlalchemy_dbapi_error(
        request: Request,
        exc: DBAPIError,
    ) -> ORJSONResponse:
        route = _route_template(request)
        record_api_db_error(
            method=request.method,
            route=route,
            error_type=exc.__class__.__name__,
        )
        domain_error = DatabaseError(_DB_UNAVAILABLE_MESSAGE, hint=_DB_UNAVAILABLE_HINT)
        operation = vworld_operation_for_path(request.url.path)
        return ORJSONResponse(
            error_payload(domain_error, operation=operation),
            status_code=domain_error.http_status,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> ORJSONResponse:
        operation = vworld_operation_for_path(request.url.path)
        if operation is not None:
            return ORJSONResponse(
                vworld_validation_error_payload(exc.errors(), operation=operation),
                status_code=400,
            )
        domain_error = _validation_errors_to_domain(exc.errors())
        return ORJSONResponse(error_payload(domain_error), status_code=domain_error.http_status)

    @app.exception_handler(ValidationError)
    async def handle_pydantic_error(request: Request, exc: ValidationError) -> ORJSONResponse:
        domain_error = _validation_error_to_domain(exc)
        operation = vworld_operation_for_path(request.url.path)
        return ORJSONResponse(
            error_payload(domain_error, operation=operation),
            status_code=domain_error.http_status,
        )


def _validation_error_to_domain(exc: ValidationError) -> KorTravelGeoError:
    return _validation_errors_to_domain(exc.errors())


def _validation_errors_to_domain(errors: Sequence[Mapping[str, Any]]) -> KorTravelGeoError:
    if any(error.get("type") == _COORDINATE_BOUNDS_ERROR for error in errors):
        return InvalidCoordinateError(_COORDINATE_BOUNDS_MESSAGE)
    return InvalidInputError("invalid request data", hint=_summarize_validation_errors(errors))


def _summarize_validation_errors(errors: Sequence[Mapping[str, Any]]) -> str | None:
    """Build a stable, bounded ``loc: msg`` hint (ADR-061).

    ``str(exc.errors())`` leaked the raw pydantic error reprs — including the user-supplied
    ``input`` value and internal ``url``/``ctx`` — into the response. Keep only the field
    location and the (template) message so the hint is useful without echoing input.

    The DTOs are ``extra='forbid'``, so an ``extra_forbidden`` error's ``loc`` leaf is the
    user-supplied key name; drop that leaf so the key is not reflected back. Deduplicate and
    cap the count/length so a request stuffed with bogus keys can't amplify the response.
    """
    parts: list[str] = []
    for error in errors:
        loc = tuple(error.get("loc", ()))
        msg = str(error.get("msg") or "invalid value")
        if error.get("type") == "extra_forbidden":
            loc = loc[:-1]  # leaf is the user-supplied key name — do not reflect it
            msg = "unexpected field"
        field = ".".join(str(piece) for piece in loc) or "request"
        part = f"{field}: {msg}"
        if part not in parts:
            parts.append(part)
    if not parts:
        return None
    extra = len(parts) - _MAX_VALIDATION_HINT_PARTS
    shown = parts[:_MAX_VALIDATION_HINT_PARTS]
    if extra > 0:
        shown.append(f"(+{extra} more)")
    hint = "; ".join(shown)
    if len(hint) > _MAX_VALIDATION_HINT_CHARS:
        hint = hint[: _MAX_VALIDATION_HINT_CHARS - 3].rstrip() + "..."
    return hint


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else request.url.path
