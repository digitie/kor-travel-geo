from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from kortravelgeo.api.responses import register_exception_handlers
from kortravelgeo.dto.common import KOREA_LON_LAT_BOUNDS_MESSAGE


class _CoordinateModel(BaseModel):
    x: float

    @model_validator(mode="after")
    def reject_outside_korea(self) -> _CoordinateModel:
        raise PydanticCustomError(
            "kor_travel_geo.coordinate_bounds",
            KOREA_LON_LAT_BOUNDS_MESSAGE,
        )


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
    assert response.json()["response"]["errorMessage"] == KOREA_LON_LAT_BOUNDS_MESSAGE


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


def test_sqlalchemy_operational_error_maps_to_database_unavailable_response() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/db-down")
    async def db_down() -> dict[str, str]:
        raise OperationalError(
            "SELECT secret_value FROM private_table",
            {"secret": "plain-text"},
            RuntimeError("server closed the connection unexpectedly"),
        )

    response = TestClient(app, raise_server_exceptions=False).get("/db-down")

    payload_text = response.text
    payload = response.json()
    assert response.status_code == 503
    assert payload["response"]["status"] == "ERROR"
    assert payload["response"]["errorCode"] == "E0500"
    assert payload["response"]["errorMessage"] == "database operation failed"
    assert "KTG_PG_DSN" in payload["response"]["hint"]
    assert "secret_value" not in payload_text
    assert "plain-text" not in payload_text


def test_sqlalchemy_non_operational_dbapi_error_maps_to_internal_response() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/db-bug")
    async def db_bug() -> dict[str, str]:
        raise ProgrammingError(
            "SELECT secret_value FROM private_table",
            {"secret": "plain-text"},
            RuntimeError("syntax error at or near private_table"),
        )

    response = TestClient(app, raise_server_exceptions=False).get("/db-bug")

    payload_text = response.text
    payload = response.json()
    assert response.status_code == 500
    assert payload["response"]["status"] == "ERROR"
    assert payload["response"]["errorCode"] == "E0500"
    assert payload["response"]["errorMessage"] == "database statement failed"
    assert "hint" not in payload["response"]
    assert "secret_value" not in payload_text
    assert "plain-text" not in payload_text


def test_sqlalchemy_integrity_error_maps_to_internal_response() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/db-integrity")
    async def db_integrity() -> dict[str, str]:
        raise IntegrityError(
            "INSERT INTO private_table(secret_value) VALUES (:secret)",
            {"secret": "plain-text"},
            RuntimeError("duplicate key value violates unique constraint"),
        )

    response = TestClient(app, raise_server_exceptions=False).get("/db-integrity")

    payload_text = response.text
    payload = response.json()
    assert response.status_code == 500
    assert payload["response"]["errorCode"] == "E0500"
    assert payload["response"]["errorMessage"] == "database statement failed"
    assert "secret_value" not in payload_text
    assert "plain-text" not in payload_text


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


def test_vworld_sqlalchemy_operational_error_keeps_vworld_error_shape() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/v1/address/geocode")
    async def geocode_db_down() -> dict[str, str]:
        raise OperationalError(
            "SELECT private_query",
            {},
            RuntimeError("database is restarting"),
        )

    response = TestClient(app, raise_server_exceptions=False).get("/v1/address/geocode")

    payload = response.json()
    assert response.status_code == 503
    assert payload["response"]["status"] == "ERROR"
    assert payload["response"]["service"]["operation"] == "getCoord"
    assert payload["response"]["error"]["code"] == "SYSTEM_ERROR"
    assert payload["response"]["error"]["text"] == "database operation failed"
    assert "private_query" not in response.text


def test_vworld_sqlalchemy_non_operational_error_keeps_vworld_shape() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/v1/address/geocode")
    async def geocode_db_bug() -> dict[str, str]:
        raise ProgrammingError(
            "SELECT private_query",
            {},
            RuntimeError("undefined column"),
        )

    response = TestClient(app, raise_server_exceptions=False).get("/v1/address/geocode")

    payload = response.json()
    assert response.status_code == 500
    assert payload["response"]["status"] == "ERROR"
    assert payload["response"]["service"]["operation"] == "getCoord"
    assert payload["response"]["error"]["code"] == "SYSTEM_ERROR"
    assert payload["response"]["error"]["text"] == "database statement failed"
    assert "private_query" not in response.text
