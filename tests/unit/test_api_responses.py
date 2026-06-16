from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from kortravelgeo.api.responses import register_exception_handlers


class _CoordinateModel(BaseModel):
    x: float

    @model_validator(mode="after")
    def reject_outside_korea(self) -> _CoordinateModel:
        msg = "point must be within Korea lon/lat bounds: 123 < x < 132, 32 < y < 39"
        raise PydanticCustomError("kor_travel_geo.coordinate_bounds", msg)


def test_pydantic_validation_error_maps_to_invalid_coordinate_response() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/invalid-coordinate")
    async def invalid_coordinate() -> dict[str, str]:
        _CoordinateModel(x=0)
        return {"status": "unreachable"}

    response = TestClient(app, raise_server_exceptions=False).get("/invalid-coordinate")

    assert response.status_code == 400
    assert response.json()["response"]["status"] == "ERROR"
    assert response.json()["response"]["errorCode"] == "E0102"


class _GenericInvalidModel(BaseModel):
    value: int = Field(ge=1)


def test_generic_pydantic_validation_error_maps_to_invalid_input_response() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/invalid-input")
    async def invalid_input() -> dict[str, str]:
        _GenericInvalidModel(value=0)
        return {"status": "unreachable"}

    response = TestClient(app, raise_server_exceptions=False).get("/invalid-input")

    assert response.status_code == 400
    assert response.json()["response"]["status"] == "ERROR"
    assert response.json()["response"]["errorCode"] == "E0100"


def test_sqlalchemy_pool_timeout_maps_to_database_unavailable_response() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/db-timeout")
    async def db_timeout() -> dict[str, str]:
        raise SQLAlchemyTimeoutError("QueuePool checkout timed out")

    response = TestClient(app, raise_server_exceptions=False).get("/db-timeout")

    payload = response.json()
    assert response.status_code == 503
    assert payload["response"]["status"] == "ERROR"
    assert payload["response"]["errorCode"] == "E0500"
    assert payload["response"]["errorMessage"] == "database connection pool checkout timed out"
    assert "KTG_PG_POOL_TIMEOUT_MS" in payload["response"]["hint"]


def test_vworld_sqlalchemy_pool_timeout_keeps_vworld_error_shape() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/v1/address/geocode")
    async def geocode_timeout() -> dict[str, str]:
        raise SQLAlchemyTimeoutError("QueuePool checkout timed out")

    response = TestClient(app, raise_server_exceptions=False).get("/v1/address/geocode")

    payload = response.json()
    assert response.status_code == 503
    assert payload["response"]["status"] == "ERROR"
    assert payload["response"]["service"]["operation"] == "getCoord"
    assert payload["response"]["error"]["code"] == "SYSTEM_ERROR"
