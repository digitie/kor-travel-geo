from __future__ import annotations

from typing import Any, Literal

import httpx
import pytest

from kortravelgeo.api.app import create_app
from kortravelgeo.api.deps import get_client
from kortravelgeo.api.public_api_key import require_public_api_key
from kortravelgeo.dto.address import AddressStructure, RefinedAddress
from kortravelgeo.dto.common import KOREA_LON_LAT_BOUNDS_MESSAGE, Point, ServiceMeta
from kortravelgeo.dto.geocode import GeocodeExtension, GeocodeInput, GeocodeResponse, GeocodeResult
from kortravelgeo.dto.reverse import ReverseInput, ReverseResponse, ReverseResultItem
from kortravelgeo.exceptions import (
    DatabaseError,
    InvalidCoordinateError,
    InvalidInputError,
    KorTravelGeoError,
    RateLimitError,
)


async def _get_v1(path: str, params: dict[str, Any], client_factory: Any) -> httpx.Response:
    """Drive a v1 endpoint with a fake client dependency and return the raw HTTP response."""
    app = create_app()
    app.dependency_overrides[get_client] = client_factory
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, params=params)


class _FakeV1Client:
    async def _geocode_v1(
        self,
        address: str,
        **kwargs: Any,
    ) -> GeocodeResponse:
        kwargs.pop("sig_cd", None)
        kwargs.pop("bjd_cd", None)
        inp = GeocodeInput(address=address, **kwargs)
        return GeocodeResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="geocode"),
            status="OK",
            input=inp,
            refined=RefinedAddress(
                text=address,
                structure=AddressStructure(level1="서울특별시", level2="강남구"),
            ),
            result=GeocodeResult(point=Point(x=127.036, y=37.501)),
            x_extension=GeocodeExtension(
                source="local",
                confidence=0.98,
                bd_mgt_sn="1168010100108250000028924",
            ),
        )

    async def _reverse_geocode_v1(
        self,
        x: float,
        y: float,
        **kwargs: Any,
    ) -> ReverseResponse:
        kwargs.pop("sig_cd", None)
        kwargs.pop("bjd_cd", None)
        radius_m = kwargs.pop("radius_m") or 200
        inp = ReverseInput(point=Point(x=x, y=y), radius_m=radius_m, **kwargs)
        return ReverseResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
            status="OK",
            input=inp,
            result=(
                ReverseResultItem(
                    type="road",
                    text="서울특별시 강남구 테헤란로 152",
                    structure=AddressStructure(level1="서울특별시", level2="강남구"),
                    point=Point(x=x, y=y),
                    zipcode="06236",
                    distance_m=3.2,
                ),
            ),
        )


@pytest.mark.asyncio
async def test_v1_geocode_http_response_uses_vworld_envelope() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = _FakeV1Client
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/address/geocode",
            params={
                "address": "서울특별시 강남구 테헤란로 152",
                "type": "road",
                "fallback": "local_only",
            },
        )

    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"response"}
    assert body["response"]["service"]["name"] == "address"
    assert body["response"]["service"]["operation"] == "getCoord"
    assert body["response"]["input"]["type"] == "ROAD"
    assert body["response"]["result"]["point"] == {"x": 127.036, "y": 37.501}
    assert body["response"]["x_extension"]["bd_mgt_sn"] == "1168010100108250000028924"


@pytest.mark.asyncio
async def test_v1_geocode_simple_omits_input_and_refined() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = _FakeV1Client
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/address/geocode",
            params={
                "address": "서울특별시 강남구 테헤란로 152",
                "simple": "true",
            },
        )

    payload = response.json()["response"]

    assert response.status_code == 200
    assert "input" not in payload
    assert "refined" not in payload
    assert payload["result"]["point"]["x"] == 127.036


@pytest.mark.asyncio
async def test_v1_reverse_http_response_uses_vworld_envelope() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = _FakeV1Client
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/address/reverse",
            params={"x": 127.036, "y": 37.501, "type": "both"},
        )

    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"response"}
    assert body["response"]["service"]["name"] == "address"
    assert body["response"]["service"]["operation"] == "getAddress"
    assert body["response"]["input"]["type"] == "BOTH"
    assert body["response"]["result"][0]["type"] == "ROAD"
    assert body["response"]["result"][0]["zipcode"] == "06236"


@pytest.mark.asyncio
async def test_v1_geocode_request_validation_uses_vworld_error_object() -> None:
    app = create_app()
    app.dependency_overrides[get_client] = _FakeV1Client
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/address/geocode")

    body = response.json()

    assert response.status_code == 400
    assert set(body) == {"response"}
    assert body["response"]["service"]["operation"] == "getCoord"
    assert body["response"]["status"] == "ERROR"
    assert body["response"]["error"] == {
        "level": 1,
        "code": "PARAM_REQUIRED",
        "text": "필수 파라미터인 <address>가 없어서 요청을 처리할수 없습니다.",
    }


class _NotFoundV1Client:
    """A v1 client whose geocode finds nothing → status=NOT_FOUND at HTTP 200 (success envelope)."""

    async def _geocode_v1(self, address: str, **kwargs: Any) -> GeocodeResponse:
        kwargs.pop("sig_cd", None)
        kwargs.pop("bjd_cd", None)
        return GeocodeResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="geocode"),
            status="NOT_FOUND",
            input=GeocodeInput(address=address, **kwargs),
            refined=None,
            result=None,
            x_extension=None,
        )


class _ParcelReverseV1Client(_FakeV1Client):
    """Reverse client returning a parcel-typed result (to pin VWorld PARCEL casing)."""

    async def _reverse_geocode_v1(self, x: float, y: float, **kwargs: Any) -> ReverseResponse:
        kwargs.pop("sig_cd", None)
        kwargs.pop("bjd_cd", None)
        radius_m = kwargs.pop("radius_m") or 200
        inp = ReverseInput(point=Point(x=x, y=y), radius_m=radius_m, **kwargs)
        return ReverseResponse(
            service=ServiceMeta(name="kor-travel-geo", operation="reverse_geocode"),
            status="OK",
            input=inp,
            result=(
                ReverseResultItem(
                    type="parcel",
                    text="서울특별시 강남구 역삼동 737",
                    structure=AddressStructure(level1="서울특별시", level2="강남구"),
                    point=Point(x=x, y=y),
                ),
            ),
        )


def _raising_client(exc: KorTravelGeoError) -> type:
    class _RaisingV1Client:
        async def _geocode_v1(self, address: str, **kwargs: Any) -> GeocodeResponse:
            raise exc

        async def _reverse_geocode_v1(self, x: float, y: float, **kwargs: Any) -> ReverseResponse:
            raise exc

    return _RaisingV1Client


# --- M5: previously-untested live branches -------------------------------------------------


@pytest.mark.asyncio
async def test_v1_reverse_simple_omits_input_and_result_type() -> None:
    response = await _get_v1(
        "/v1/address/reverse",
        {"x": 127.036, "y": 37.501, "simple": "true"},
        _FakeV1Client,
    )
    payload = response.json()["response"]

    assert response.status_code == 200
    assert "input" not in payload
    # simple drops each result item's `type` but keeps the address text/zipcode.
    assert "type" not in payload["result"][0]
    assert payload["result"][0]["text"].startswith("서울특별시")
    assert payload["result"][0]["zipcode"] == "06236"


@pytest.mark.asyncio
async def test_v1_geocode_refine_false_omits_refined_but_keeps_input() -> None:
    response = await _get_v1(
        "/v1/address/geocode",
        {"address": "서울특별시 강남구 테헤란로 152", "refine": "false"},
        _FakeV1Client,
    )
    payload = response.json()["response"]

    assert response.status_code == 200
    # refine=false (not simple) drops only `refined`; `input` stays.
    assert "refined" not in payload
    assert payload["input"]["type"] == "ROAD"
    assert payload["result"]["point"]["x"] == 127.036


@pytest.mark.asyncio
async def test_v1_geocode_parcel_input_casing() -> None:
    response = await _get_v1(
        "/v1/address/geocode",
        {"address": "서울특별시 강남구 역삼동 737", "type": "parcel"},
        _FakeV1Client,
    )
    payload = response.json()["response"]

    assert response.status_code == 200
    assert payload["input"]["type"] == "PARCEL"


@pytest.mark.asyncio
async def test_v1_reverse_parcel_result_casing() -> None:
    response = await _get_v1(
        "/v1/address/reverse",
        {"x": 127.036, "y": 37.501, "type": "parcel"},
        _ParcelReverseV1Client,
    )
    payload = response.json()["response"]

    assert response.status_code == 200
    assert payload["result"][0]["type"] == "PARCEL"


@pytest.mark.asyncio
async def test_v1_geocode_accepts_uppercase_type_param() -> None:
    # The wire serializes input.type upper-case (vworld convention), so echoing the
    # response value back as input (type=PARCEL) must be accepted case-insensitively.
    response = await _get_v1(
        "/v1/address/geocode",
        {"address": "서울특별시 강남구 역삼동 737", "type": "PARCEL"},
        _FakeV1Client,
    )
    payload = response.json()["response"]

    assert response.status_code == 200
    assert payload["input"]["type"] == "PARCEL"


@pytest.mark.asyncio
async def test_v1_reverse_accepts_uppercase_type_param() -> None:
    response = await _get_v1(
        "/v1/address/reverse",
        {"x": 127.036, "y": 37.501, "type": "BOTH"},
        _FakeV1Client,
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_v1_geocode_rejects_unknown_type_param() -> None:
    # Case-insensitivity must not accept genuinely invalid values — still a vworld error.
    response = await _get_v1(
        "/v1/address/geocode",
        {"address": "서울특별시 강남구 역삼동 737", "type": "zipcode"},
        _FakeV1Client,
    )

    assert response.status_code == 400
    assert response.json()["response"]["error"]["code"] == "INVALID_TYPE"


@pytest.mark.asyncio
async def test_v1_geocode_not_found_returns_200_success_envelope() -> None:
    response = await _get_v1(
        "/v1/address/geocode",
        {"address": "존재하지 않는 주소"},
        _NotFoundV1Client,
    )
    body = response.json()

    # NOT_FOUND is a *success* envelope (HTTP 200), not a vworld error object.
    assert response.status_code == 200
    assert set(body) == {"response"}
    assert body["response"]["status"] == "NOT_FOUND"
    assert "error" not in body["response"]
    assert body["response"]["service"]["operation"] == "getCoord"


@pytest.mark.parametrize(
    ("exc", "status_code", "code", "level"),
    [
        (InvalidCoordinateError("좌표가 범위를 벗어났습니다"), 400, "INVALID_RANGE", 1),
        (InvalidInputError("입력 타입이 올바르지 않습니다"), 400, "INVALID_TYPE", 1),
        (RateLimitError("요청 한도를 초과했습니다"), 429, "OVER_REQUEST_LIMIT", 2),
        (DatabaseError("내부 오류"), 503, "SYSTEM_ERROR", 3),
    ],
)
@pytest.mark.asyncio
async def test_v1_geocode_domain_errors_map_to_vworld_error_object(
    exc: KorTravelGeoError,
    status_code: int,
    code: str,
    level: int,
) -> None:
    response = await _get_v1(
        "/v1/address/geocode",
        {"address": "서울특별시 강남구 테헤란로 152"},
        _raising_client(exc),
    )
    body = response.json()

    assert response.status_code == status_code
    assert set(body) == {"response"}
    assert body["response"]["service"]["operation"] == "getCoord"
    assert body["response"]["status"] == "ERROR"
    assert body["response"]["error"] == {"level": level, "code": code, "text": exc.message}


@pytest.mark.asyncio
async def test_v1_geocode_validation_range_template_interpolates_param() -> None:
    # address over max_length → string_too_long → INVALID_RANGE template with the param name.
    response = await _get_v1("/v1/address/geocode", {"address": "a" * 201}, _FakeV1Client)
    body = response.json()

    expected_text = "<address> 파라미터의 값이 유효한 범위를 넘었습니다."
    assert response.status_code == 400
    assert body["response"]["error"]["code"] == "INVALID_RANGE"
    assert body["response"]["error"]["text"] == expected_text


@pytest.mark.asyncio
async def test_v1_reverse_validation_error_uses_invalid_type_template() -> None:
    # x as a non-float → a type validation error → INVALID_TYPE template with the param name.
    response = await _get_v1(
        "/v1/address/reverse",
        {"x": "not-a-number", "y": 37.5},
        _FakeV1Client,
    )
    body = response.json()

    assert response.status_code == 400
    assert body["response"]["service"]["operation"] == "getAddress"
    assert body["response"]["error"]["code"] == "INVALID_TYPE"
    assert body["response"]["error"]["text"] == "<x> 파라미터 타입이 유효하지 않습니다."


@pytest.mark.asyncio
async def test_v1_reverse_coordinate_bounds_error_uses_invalid_range() -> None:
    response = await _get_v1(
        "/v1/address/reverse",
        {"x": 0.0, "y": 0.0},
        _FakeV1Client,
    )
    body = response.json()

    assert response.status_code == 400
    assert body["response"]["service"]["operation"] == "getAddress"
    assert body["response"]["error"]["code"] == "INVALID_RANGE"
    assert body["response"]["error"]["text"] == KOREA_LON_LAT_BOUNDS_MESSAGE


@pytest.mark.asyncio
async def test_v1_geocode_404_subpath_keeps_vworld_error_object() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/address/geocode/not-found")

    body = response.json()

    assert response.status_code == 404
    assert body["response"]["status"] == "ERROR"
    assert body["response"]["service"] == {
        "name": "address",
        "version": "2.0",
        "operation": "getCoord",
    }
    assert body["response"]["error"] == {
        "level": 1,
        "code": "INVALID_TYPE",
        "text": "요청 경로를 찾을 수 없습니다.",
    }


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        ("/v1/address/geocode", "getCoord"),
        ("/v1/address/reverse", "getAddress"),
    ],
)
@pytest.mark.asyncio
async def test_v1_405_keeps_vworld_error_object(path: str, operation: str) -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(path)

    body = response.json()

    assert response.status_code == 405
    assert body["response"]["status"] == "ERROR"
    assert body["response"]["service"]["operation"] == operation
    assert body["response"]["service"]["version"] == "2.0"
    assert body["response"]["error"] == {
        "level": 1,
        "code": "INVALID_TYPE",
        "text": "요청 메서드가 허용되지 않습니다.",
    }


# --- M1: representative success bodies pin the published v1 contract shape ------------------


@pytest.mark.parametrize(
    ("path", "params", "operation", "present", "absent"),
    [
        (
            "/v1/address/geocode",
            {"address": "서울특별시 강남구 테헤란로 152"},
            "getCoord",
            {"service", "status", "input", "refined", "result", "x_extension"},
            set(),
        ),
        (
            "/v1/address/geocode",
            {"address": "서울특별시 강남구 테헤란로 152", "simple": "true"},
            "getCoord",
            {"service", "status", "result"},
            {"input", "refined"},
        ),
        (
            "/v1/address/reverse",
            {"x": 127.036, "y": 37.501},
            "getAddress",
            {"service", "status", "input", "result"},
            set(),
        ),
    ],
)
@pytest.mark.asyncio
async def test_v1_success_envelope_contract_shape(
    path: str,
    params: dict[str, Any],
    operation: Literal["getCoord", "getAddress"],
    present: set[str],
    absent: set[str],
) -> None:
    response = await _get_v1(path, params, _FakeV1Client)
    body = response.json()

    assert response.status_code == 200
    assert set(body) == {"response"}
    payload = body["response"]
    assert payload["service"]["operation"] == operation
    assert present <= set(payload)
    assert absent.isdisjoint(payload)


def test_v1_paths_are_published_in_openapi() -> None:
    schema = create_app().openapi()
    for path in ("/v1/address/geocode", "/v1/address/reverse"):
        assert path in schema["paths"]
        assert "200" in schema["paths"][path]["get"]["responses"]


# --- #304 (T-219 M2/M3/M1): the published OpenAPI matches actual wire behaviour ------------
#
# M2: success-body fields the endpoint drops in simple mode must be optional in the schema.
# M3: validation failures surface as the 400 VWorld error envelope, so the auto-422 is gone.
# M1: representative runtime bodies are cross-validated against the published 200 schema, so
#     future drift (an undeclared field, or a schema-required field omitted) fails in CI.


_SCALAR_TYPE_CHECKS: dict[str, Any] = {
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "null": lambda v: v is None,
}


def _resolve_ref(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if ref is None:
        return schema
    resolved: dict[str, Any] = components[ref.rsplit("/", 1)[-1]]
    return resolved


def _assert_conforms(
    instance: Any,
    schema: dict[str, Any],
    components: dict[str, Any],
    *,
    path: str = "$",
) -> None:
    """Closed-world structural validation of a runtime body against an OpenAPI schema.

    The published v1 DTOs use ``extra='forbid'`` (``additionalProperties: false``), so both
    drift directions are contract violations and fail here: a runtime key absent from the
    schema ``properties``, or a schema-``required`` key absent at runtime.
    """
    schema = _resolve_ref(schema, components)
    branches = schema.get("anyOf") or schema.get("oneOf")
    if branches is not None:
        failures: list[str] = []
        for branch in branches:
            # Probe each branch; nullable optionals render as anyOf[<schema>, null].
            try:
                _assert_conforms(instance, branch, components, path=path)
            except AssertionError as exc:
                failures.append(str(exc))
            else:
                return
        msg = f"{path}: no anyOf/oneOf branch matched ({failures})"
        raise AssertionError(msg)

    schema_type = schema.get("type")
    if schema_type == "null":
        assert instance is None, f"{path}: expected null, got {instance!r}"
        return
    if schema_type == "array" or "items" in schema:
        assert isinstance(instance, list), f"{path}: expected array, got {type(instance).__name__}"
        for index, item in enumerate(instance):
            _assert_conforms(item, schema["items"], components, path=f"{path}[{index}]")
        return
    if schema_type == "object" or "properties" in schema:
        assert isinstance(instance, dict), f"{path}: expected object, got {type(instance).__name__}"
        props: dict[str, Any] = schema.get("properties", {})
        for required in schema.get("required", []):
            assert required in instance, f"{path}: missing schema-required key {required!r}"
        closed = schema.get("additionalProperties", True) is False
        for key, value in instance.items():
            if key in props:
                _assert_conforms(value, props[key], components, path=f"{path}.{key}")
            else:
                assert not closed, f"{path}: runtime key {key!r} is not declared in the schema"
        return
    if "const" in schema:
        assert instance == schema["const"], f"{path}: {instance!r} != const {schema['const']!r}"
        return
    if "enum" in schema:
        assert instance in schema["enum"], f"{path}: {instance!r} not in enum {schema['enum']}"
        return
    declared = schema_type if isinstance(schema_type, list) else [schema_type]
    checks = [_SCALAR_TYPE_CHECKS[name] for name in declared if name in _SCALAR_TYPE_CHECKS]
    if checks:
        assert any(check(instance) for check in checks), (
            f"{path}: {instance!r} does not match declared type {schema_type!r}"
        )


def _v1_200_body_schema(
    schema: dict[str, Any],
    path: str,
    components: dict[str, Any],
) -> dict[str, Any]:
    envelope_ref = schema["paths"][path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    envelope = _resolve_ref(envelope_ref, components)
    return _resolve_ref(envelope["properties"]["response"], components)


def test_v1_openapi_marks_simple_mode_fields_optional() -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    geocode_body = _v1_200_body_schema(schema, "/v1/address/geocode", components)
    reverse_body = _v1_200_body_schema(schema, "/v1/address/reverse", components)

    # `input` is dropped from the wire in simple mode -> optional; service/status stay required.
    assert "input" not in geocode_body["required"]
    assert "input" not in reverse_body["required"]
    assert {"service", "status"} <= set(geocode_body["required"])
    assert {"service", "status"} <= set(reverse_body["required"])

    # reverse result items drop `type` in simple mode -> optional, but keep text/structure.
    result_item = _resolve_ref(reverse_body["properties"]["result"]["items"], components)
    assert "type" not in result_item["required"]
    assert {"text", "structure"} <= set(result_item["required"])


def test_v1_openapi_advertises_vworld_400_and_drops_auto_422() -> None:
    schema = create_app().openapi()
    for path in ("/v1/address/geocode", "/v1/address/reverse"):
        responses = schema["paths"][path]["get"]["responses"]
        # validation failures return the 400 VWorld error envelope, never FastAPI's 422.
        assert "422" not in responses
        ref = responses["400"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/VWorldErrorEnvelope")


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/v1/address/geocode", {"address": "서울특별시 강남구 테헤란로 152"}),
        ("/v1/address/geocode", {"address": "서울특별시 강남구 테헤란로 152", "simple": "true"}),
        ("/v1/address/geocode", {"address": "서울특별시 강남구 테헤란로 152", "refine": "false"}),
        ("/v1/address/reverse", {"x": 127.036, "y": 37.501}),
        ("/v1/address/reverse", {"x": 127.036, "y": 37.501, "simple": "true"}),
    ],
)
@pytest.mark.asyncio
async def test_v1_runtime_success_body_conforms_to_published_openapi(
    path: str,
    params: dict[str, Any],
) -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    body_schema = schema["paths"][path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    response = await _get_v1(path, params, _FakeV1Client)

    assert response.status_code == 200
    _assert_conforms(response.json(), body_schema, components)


def test_contract_validator_detects_required_and_undeclared_drift() -> None:
    # Guards the M1 cross-validator itself: it must catch both drift directions.
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    body_schema = schema["paths"]["/v1/address/geocode"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    service = {"name": "address", "operation": "getCoord", "version": "2.0"}

    baseline = {"response": {"service": service, "status": "OK"}}
    _assert_conforms(baseline, body_schema, components)  # sanity: a valid body passes.

    # top-level drift, both directions.
    with pytest.raises(AssertionError, match="status"):
        _assert_conforms({"response": {"service": service}}, body_schema, components)
    with pytest.raises(AssertionError, match="bogus"):
        _assert_conforms(
            {"response": {"service": service, "status": "OK", "bogus": 1}},
            body_schema,
            components,
        )

    # nested drift (inside the `service` object) is caught just as well, both directions.
    with pytest.raises(AssertionError, match="operation"):
        _assert_conforms(
            {"response": {"service": {"name": "address", "version": "2.0"}, "status": "OK"}},
            body_schema,
            components,
        )
    with pytest.raises(AssertionError, match="nested"):
        _assert_conforms(
            {"response": {"service": {**service, "nested": 1}, "status": "OK"}},
            body_schema,
            components,
        )

    # scalar type drift in a declared key is caught (service.name must be a string).
    with pytest.raises(AssertionError, match="does not match declared type"):
        _assert_conforms(
            {"response": {"service": {**service, "name": 123}, "status": "OK"}},
            body_schema,
            components,
        )
