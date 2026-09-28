"""FastAPI exception response wiring."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from kortravelgeo.api.vworld import (
    vworld_error_payload,
    vworld_operation_for_error_path,
    vworld_operation_for_path,
    vworld_validation_error_payload,
)
from kortravelgeo.dto.common import KOREA_LON_LAT_BOUNDS_MESSAGE
from kortravelgeo.exceptions import (
    DatabaseError,
    DatabaseTimeoutError,
    InvalidCoordinateError,
    InvalidInputError,
    KorTravelGeoError,
)
from kortravelgeo.infra.metrics import (
    UNMATCHED_ROUTE,
    record_api_db_error,
    record_db_pool_checkout_timeout,
)

_COORDINATE_BOUNDS_ERROR = "kor_travel_geo.coordinate_bounds"
_COORDINATE_BOUNDS_MESSAGE = KOREA_LON_LAT_BOUNDS_MESSAGE
_HTTP_404_MESSAGE = "요청 경로를 찾을 수 없습니다."
_HTTP_405_MESSAGE = "요청 메서드가 허용되지 않습니다."
_POOL_TIMEOUT_MESSAGE = "database connection pool checkout timed out"
_POOL_TIMEOUT_HINT = (
    "increase KTG_PG_POOL_SIZE/KTG_PG_MAX_OVERFLOW, lower KTG_API_MAX_CONCURRENCY, "
    "or raise KTG_PG_POOL_TIMEOUT_MS after checking DB capacity"
)
_DB_UNAVAILABLE_MESSAGE = "database operation failed"
_DB_UNAVAILABLE_HINT = "check PostgreSQL server status and /v1/readyz before retrying"
_DB_INTERNAL_MESSAGE = "database statement failed"


@dataclass(frozen=True, slots=True)
class _DbErrorClass:
    """One operational DB failure class (T-309).

    ``error_type`` is the ``ktg_api_db_errors_total`` label value. ``timeout`` classes map to
    ``DatabaseTimeoutError`` (E0504, HTTP 504): the connection worked but the query did not
    finish, so a KTG_PG_DSN hint would point the operator the wrong way (2026-09-28 incident).
    """

    error_type: str
    message: str
    hint: str
    timeout: bool = False


_DB_STATEMENT_TIMEOUT = _DbErrorClass(
    "statement_timeout",
    "database query timed out",
    "the query exceeded the DB statement timeout (KTG_PG_STATEMENT_TIMEOUT_MS); the connection "
    "is fine. Serving MVs may be empty or refreshing: check /v1/readyz components.serving",
    timeout=True,
)
_DB_LOCK_TIMEOUT = _DbErrorClass(
    "lock_timeout",
    "database query timed out waiting for a lock",
    "a concurrent operation (e.g. MV refresh or swap) held the lock past lock_timeout; "
    "retry after it finishes",
    timeout=True,
)
_DB_QUERY_CANCELED = _DbErrorClass(
    "query_canceled",
    "database query was cancelled",
    "the server or an operator cancelled the query; retry the request",
    timeout=True,
)
_DB_MV_NOT_POPULATED = _DbErrorClass(
    "mv_not_populated",
    "serving data is not ready",
    "a serving materialized view has not been populated (e.g. restored without MV data); "
    "run the MV refresh and check /v1/readyz components.serving",
)
_DB_TOO_MANY_CONNECTIONS = _DbErrorClass(
    "too_many_connections",
    "database connection limit reached",
    "PostgreSQL max_connections or a role/database connection limit is exhausted; lower "
    "KTG_PG_POOL_SIZE/KTG_PG_MAX_OVERFLOW or raise the limit",
)
_DB_AUTH_FAILED = _DbErrorClass(
    "auth_failed",
    "database authentication or permission check failed",
    "check the user, password and database name in KTG_PG_DSN and that the role has "
    "CONNECT on the database",
)
_DB_CONNECTION_FAILED = _DbErrorClass(
    "connection_failed",
    "database connection failed",
    "check the host/port in KTG_PG_DSN, PostgreSQL availability, and /v1/readyz before retrying",
)
# Connect-time failures carry no SQLSTATE in psycopg (``sqlstate=None``), only the server
# message, so these are matched on the message. The raw message never reaches the response.
_TOO_MANY_CONNECTIONS_MARKERS = (
    "too many clients",
    "too many connections",
    "remaining connection slots are reserved",
)
_AUTH_FAILURE_MARKERS = (
    "authentication failed",
    "no pg_hba.conf entry",
    "pg_hba.conf rejects",
    "permission denied for database",
)
_MISSING_ROLE_OR_DATABASE_RE = re.compile(r'\b(?:role|database) "[^"]*" does not exist')
# admin_shutdown / crash_shutdown / cannot_connect_now: the server is not taking connections.
_SERVER_UNAVAILABLE_SQLSTATES = frozenset({"57P01", "57P02", "57P03"})
_MAX_VALIDATION_HINT_PARTS = 8
_MAX_VALIDATION_HINT_CHARS = 600


def error_payload(
    exc: KorTravelGeoError,
    *,
    path: str,
    field: str | None = None,
) -> dict[str, object]:
    """Build the error body for ``path`` (ADR-038/ADR-060/ADR-061).

    v1 vworld paths get the VWorld error object; v2 API paths get the v2 error envelope
    (``{status, query_id, error:{code, message, hint?, field?}}``, ADR-060 §4); everything
    else keeps the legacy ``{response:{errorCode,...}}`` shape. ``field`` is only used by the
    v2 envelope. Cross-cutting infra gates (GeoIP 403) build their own shared shape directly.
    """
    operation = vworld_operation_for_path(path)
    if operation is not None:
        return vworld_error_payload(exc, operation=operation)
    if _is_v2_path(path):
        return _v2_error_payload(exc, field=field)
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


def _is_v2_path(path: str) -> bool:
    return path.startswith("/v2/")


def _v2_error_payload(exc: KorTravelGeoError, *, field: str | None = None) -> dict[str, object]:
    error: dict[str, object] = {"code": exc.code, "message": exc.message}
    if exc.hint:
        error["hint"] = exc.hint
    if field:
        error["field"] = field
    return {"status": "ERROR", "query_id": uuid4().hex, "error": error}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(KorTravelGeoError)
    async def handle_ktg_error(request: Request, exc: KorTravelGeoError) -> ORJSONResponse:
        return ORJSONResponse(
            error_payload(exc, path=request.url.path), status_code=exc.http_status
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> ORJSONResponse:
        operation = vworld_operation_for_error_path(request.url.path)
        if operation is not None and exc.status_code in (404, 405):
            domain_error = InvalidInputError(
                _http_exception_message(exc),
                http_status=exc.status_code,
            )
            return ORJSONResponse(
                vworld_error_payload(domain_error, operation=operation),
                status_code=exc.status_code,
                headers=exc.headers,
            )
        return ORJSONResponse(
            {"detail": exc.detail},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(SQLAlchemyTimeoutError)
    async def handle_sqlalchemy_timeout_error(
        request: Request,
        _exc: SQLAlchemyTimeoutError,
    ) -> ORJSONResponse:
        route = _route_template(request)
        record_db_pool_checkout_timeout(method=request.method, route=route)
        domain_error = DatabaseError(_POOL_TIMEOUT_MESSAGE, hint=_POOL_TIMEOUT_HINT)
        return ORJSONResponse(
            error_payload(domain_error, path=request.url.path),
            status_code=domain_error.http_status,
        )

    @app.exception_handler(DBAPIError)
    async def handle_sqlalchemy_dbapi_error(
        request: Request,
        exc: DBAPIError,
    ) -> ORJSONResponse:
        route = _route_template(request)
        error_type, domain_error = _dbapi_error_to_domain(exc)
        record_api_db_error(
            method=request.method,
            route=route,
            error_type=error_type,
        )
        return ORJSONResponse(
            error_payload(domain_error, path=request.url.path),
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
        return ORJSONResponse(
            error_payload(
                domain_error, path=request.url.path, field=_validation_field(exc.errors())
            ),
            status_code=domain_error.http_status,
        )

    @app.exception_handler(ValidationError)
    async def handle_pydantic_error(request: Request, exc: ValidationError) -> ORJSONResponse:
        domain_error = _validation_error_to_domain(exc)
        return ORJSONResponse(
            error_payload(
                domain_error, path=request.url.path, field=_validation_field(exc.errors())
            ),
            status_code=domain_error.http_status,
        )


def _dbapi_error_to_domain(exc: DBAPIError) -> tuple[str, DatabaseError]:
    """Map a driver error to ``(error_type metric label, domain error)`` (T-178D/T-309).

    Unclassified errors keep the exception class name as ``error_type`` so the label set stays
    bounded and the pre-T-309 values (``OperationalError`` etc.) keep their meaning.
    """
    if not (isinstance(exc, OperationalError) or exc.connection_invalidated):
        return exc.__class__.__name__, DatabaseError(_DB_INTERNAL_MESSAGE, http_status=500)
    error_class = _classify_operational_error(exc.orig)
    if error_class is None:
        return exc.__class__.__name__, DatabaseError(
            _DB_UNAVAILABLE_MESSAGE, hint=_DB_UNAVAILABLE_HINT
        )
    error_cls = DatabaseTimeoutError if error_class.timeout else DatabaseError
    return error_class.error_type, error_cls(error_class.message, hint=error_class.hint)


def _classify_operational_error(orig: BaseException | None) -> _DbErrorClass | None:
    """Classify by SQLSTATE first, then by the server message for connect-time errors.

    psycopg raises connect-time failures as a plain ``OperationalError`` with
    ``sqlstate=None``, so an error without a SQLSTATE failed outside a statement and counts as
    a connection failure unless its message says auth/permission or connection limit.
    """
    sqlstate = _sqlstate(orig)
    message = str(orig).lower() if orig is not None else ""
    if sqlstate == "57014":  # query_canceled: statement_timeout or pg_cancel_backend
        return _DB_STATEMENT_TIMEOUT if "statement timeout" in message else _DB_QUERY_CANCELED
    if sqlstate == "55P03":  # lock_not_available: lock_timeout
        return _DB_LOCK_TIMEOUT
    if sqlstate == "55000" and "has not been populated" in message:
        return _DB_MV_NOT_POPULATED
    if sqlstate == "53300" or any(marker in message for marker in _TOO_MANY_CONNECTIONS_MARKERS):
        return _DB_TOO_MANY_CONNECTIONS
    if (
        (sqlstate or "").startswith("28")
        or any(marker in message for marker in _AUTH_FAILURE_MARKERS)
        or _MISSING_ROLE_OR_DATABASE_RE.search(message)
    ):
        return _DB_AUTH_FAILED
    if sqlstate is None or sqlstate.startswith("08") or sqlstate in _SERVER_UNAVAILABLE_SQLSTATES:
        return _DB_CONNECTION_FAILED
    return None


def _sqlstate(orig: BaseException | None) -> str | None:
    # psycopg 3 exposes ``sqlstate``; psycopg2-style drivers use ``pgcode``.
    value = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return value if isinstance(value, str) and value else None


def _validation_error_to_domain(exc: ValidationError) -> KorTravelGeoError:
    return _validation_errors_to_domain(exc.errors())


def _http_exception_message(exc: StarletteHTTPException) -> str:
    if exc.status_code == 404:
        return _HTTP_404_MESSAGE
    if exc.status_code == 405:
        return _HTTP_405_MESSAGE
    return str(exc.detail)


def _validation_field(errors: Sequence[Mapping[str, Any]]) -> str | None:
    """First offending field path for the v2 error envelope ``error.field`` (ADR-060 §4).

    Drops the FastAPI container segment (``body``/``query``) and the user-supplied
    ``extra_forbidden`` key leaf so the field path doesn't reflect arbitrary input.
    """
    for error in errors:
        loc = tuple(error.get("loc", ()))
        if error.get("type") == "extra_forbidden":
            loc = loc[:-1]
        parts = [str(piece) for piece in loc if piece not in ("body", "query")]
        if parts:
            return ".".join(parts)
    return None


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
    return str(path) if path else UNMATCHED_ROUTE
