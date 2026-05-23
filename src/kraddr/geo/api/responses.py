"""FastAPI exception response wiring."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse

from kraddr.geo.exceptions import KraddrGeoError


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

