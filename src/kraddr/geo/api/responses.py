"""FastAPI exception response wiring."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError

from kraddr.geo.exceptions import InvalidCoordinateError, InvalidInputError, KraddrGeoError


def error_payload(exc: KraddrGeoError) -> dict[str, object]:
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
    @app.exception_handler(KraddrGeoError)
    async def handle_kraddr_error(_request: Request, exc: KraddrGeoError) -> ORJSONResponse:
        return ORJSONResponse(error_payload(exc), status_code=exc.http_status)

    @app.exception_handler(ValidationError)
    async def handle_pydantic_error(_request: Request, exc: ValidationError) -> ORJSONResponse:
        domain_error = _validation_error_to_domain(exc)
        return ORJSONResponse(error_payload(domain_error), status_code=domain_error.http_status)


def _validation_error_to_domain(exc: ValidationError) -> KraddrGeoError:
    message = str(exc)
    if "point must be within Korea lon/lat bounds" in message:
        return InvalidCoordinateError(
            "point must be within Korea lon/lat bounds: 123 < x < 132, 32 < y < 39"
        )
    return InvalidInputError("invalid request data", hint=message)
