"""FastAPI exception response wiring."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError

from kortravelgeo.exceptions import InvalidCoordinateError, InvalidInputError, KorTravelGeoError

_COORDINATE_BOUNDS_ERROR = "kor_travel_geo.coordinate_bounds"
_COORDINATE_BOUNDS_MESSAGE = "point must be within Korea lon/lat bounds: 123 < x < 132, 32 < y < 39"


def error_payload(exc: KorTravelGeoError) -> dict[str, object]:
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
    async def handle_ktg_error(_request: Request, exc: KorTravelGeoError) -> ORJSONResponse:
        return ORJSONResponse(error_payload(exc), status_code=exc.http_status)

    @app.exception_handler(ValidationError)
    async def handle_pydantic_error(_request: Request, exc: ValidationError) -> ORJSONResponse:
        domain_error = _validation_error_to_domain(exc)
        return ORJSONResponse(error_payload(domain_error), status_code=domain_error.http_status)


def _validation_error_to_domain(exc: ValidationError) -> KorTravelGeoError:
    errors = exc.errors()
    if any(error.get("type") == _COORDINATE_BOUNDS_ERROR for error in errors):
        return InvalidCoordinateError(_COORDINATE_BOUNDS_MESSAGE)
    return InvalidInputError("invalid request data", hint=str(errors))
