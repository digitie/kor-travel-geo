"""VWorld-compatible REST v1 response helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, cast

from fastapi.responses import ORJSONResponse
from pydantic import Field

from kortravelgeo.dto.common import AddressType, FrozenModel
from kortravelgeo.dto.geocode import GeocodeInput, GeocodeResponse
from kortravelgeo.dto.reverse import ReverseInput, ReverseResponse, ReverseResultItem
from kortravelgeo.exceptions import (
    InvalidCoordinateError,
    InvalidInputError,
    KorTravelGeoError,
    RateLimitError,
)

VWorldOperation = Literal["getCoord", "getAddress"]

_VWORLD_OPERATIONS: dict[str, VWorldOperation] = {
    "/v1/address/geocode": "getCoord",
    "/v1/address/reverse": "getAddress",
}


class VWorldGeocodeBody(GeocodeResponse):
    """Published v1 ``getCoord`` success body.

    The wire omits ``input`` when ``simple=true`` (see :func:`vworld_success_payload`),
    so it is optional in the published schema even though :class:`GeocodeResponse`
    requires it. ``refined``/``result`` are already optional. This aligns the OpenAPI
    contract with what the endpoint actually emits — wire behaviour is unchanged (T-219 M2).
    """

    input: GeocodeInput | None = None  # type: ignore[assignment]


class VWorldReverseResultItem(ReverseResultItem):
    """Reverse result item whose ``type`` is dropped from the wire in simple mode."""

    type: AddressType | None = None  # type: ignore[assignment]


class VWorldReverseBody(ReverseResponse):
    """Published v1 ``getAddress`` success body.

    The wire omits ``input`` when ``simple=true`` and drops each result item's
    ``type`` in the same mode, so both are optional in the published schema while
    wire behaviour is unchanged (T-219 M2).
    """

    input: ReverseInput | None = None  # type: ignore[assignment]
    result: tuple[VWorldReverseResultItem, ...] = ()


class VWorldGeocodeEnvelope(FrozenModel):
    response: VWorldGeocodeBody


class VWorldReverseEnvelope(FrozenModel):
    response: VWorldReverseBody


class VWorldErrorDetail(FrozenModel):
    level: int = Field(ge=1, le=3)
    code: str
    text: str


class VWorldErrorBody(FrozenModel):
    service: dict[str, object]
    status: Literal["ERROR"] = "ERROR"
    error: VWorldErrorDetail


class VWorldErrorEnvelope(FrozenModel):
    response: VWorldErrorBody


def vworld_operation_for_path(path: str) -> VWorldOperation | None:
    return _VWORLD_OPERATIONS.get(path)


def vworld_success_response(response: GeocodeResponse | ReverseResponse) -> ORJSONResponse:
    return ORJSONResponse(vworld_success_payload(response))


def vworld_success_payload(response: GeocodeResponse | ReverseResponse) -> dict[str, object]:
    body = response.model_dump(mode="json", exclude_none=True)
    if isinstance(response, GeocodeResponse):
        _set_service(body, "getCoord")
        if response.input.simple:
            body.pop("input", None)
            body.pop("refined", None)
        elif not response.input.refine:
            body.pop("refined", None)
    else:
        _set_service(body, "getAddress")
        if response.input.simple:
            body.pop("input", None)
            for item in body.get("result", ()):
                if isinstance(item, dict):
                    item.pop("type", None)
    return {"response": body}


def vworld_error_payload(
    exc: KorTravelGeoError,
    *,
    operation: VWorldOperation,
) -> dict[str, object]:
    return {
        "response": {
            "service": _service(operation),
            "status": "ERROR",
            "error": {
                "level": _vworld_error_level(exc),
                "code": _vworld_error_code(exc),
                "text": exc.message,
            },
        }
    }


def vworld_validation_error_payload(
    errors: Sequence[dict[str, Any]],
    *,
    operation: VWorldOperation,
) -> dict[str, object]:
    code = _vworld_validation_code(errors)
    return {
        "response": {
            "service": _service(operation),
            "status": "ERROR",
            "error": {
                "level": 1,
                "code": code,
                "text": _vworld_validation_text(errors, code),
            },
        }
    }


def _set_service(body: dict[str, Any], operation: VWorldOperation) -> None:
    service = body.get("service")
    if not isinstance(service, dict):
        body["service"] = _service(operation)
        return
    service["name"] = "address"
    service["operation"] = operation
    service.setdefault("version", "2.0")


def _service(operation: VWorldOperation) -> dict[str, object]:
    return {
        "name": "address",
        "version": "2.0",
        "operation": operation,
    }


def _vworld_error_level(exc: KorTravelGeoError) -> int:
    if isinstance(exc, RateLimitError):
        return 2
    if exc.http_status >= 500:
        return 3
    return 1


def _vworld_error_code(exc: KorTravelGeoError) -> str:
    if isinstance(exc, InvalidCoordinateError):
        return "INVALID_RANGE"
    if isinstance(exc, InvalidInputError):
        return "INVALID_TYPE"
    if isinstance(exc, RateLimitError):
        return "OVER_REQUEST_LIMIT"
    if exc.http_status >= 500:
        return "SYSTEM_ERROR"
    return "UNKNOWN_ERROR"


def _vworld_validation_code(errors: Sequence[dict[str, Any]]) -> str:
    error_types = {str(error.get("type", "")) for error in errors}
    if "missing" in error_types:
        return "PARAM_REQUIRED"
    if any("less_than" in error_type or "greater_than" in error_type for error_type in error_types):
        return "INVALID_RANGE"
    if any(
        "string_too_short" in error_type or "string_too_long" in error_type
        for error_type in error_types
    ):
        return "INVALID_RANGE"
    return "INVALID_TYPE"


def _vworld_validation_text(errors: Sequence[dict[str, Any]], code: str) -> str:
    name = _first_query_param(errors) or "request"
    if code == "PARAM_REQUIRED":
        return f"필수 파라미터인 <{name}>가 없어서 요청을 처리할수 없습니다."
    if code == "INVALID_RANGE":
        return f"<{name}> 파라미터의 값이 유효한 범위를 넘었습니다."
    return f"<{name}> 파라미터 타입이 유효하지 않습니다."


def _first_query_param(errors: Sequence[dict[str, Any]]) -> str | None:
    for error in errors:
        loc = error.get("loc")
        if not isinstance(loc, Sequence) or isinstance(loc, str):
            continue
        parts = cast("Sequence[object]", loc)
        if len(parts) >= 2 and parts[0] == "query":
            return str(parts[1])
    return None
