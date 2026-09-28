from __future__ import annotations

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from psycopg import errors as pg_errors
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
    assert payload["response"]["errorMessage"] == "database connection failed"
    assert "KTG_PG_DSN" in payload["response"]["hint"]
    assert "secret_value" not in payload_text
    assert "plain-text" not in payload_text


def _raise_operational(orig: BaseException) -> None:
    raise OperationalError("SELECT secret_value FROM private_table", {"secret": "p"}, orig)


def _db_error_count(error_type: str) -> float:
    value = REGISTRY.get_sample_value(
        "ktg_api_db_errors_total",
        {"method": "POST", "route": "/v2/geocode", "error_type": error_type},
    )
    return value or 0.0


def _db_error_app(orig: BaseException) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/v2/geocode")
    async def v2_geocode() -> dict[str, str]:
        _raise_operational(orig)
        return {"status": "unreachable"}

    @app.get("/v1/address/geocode")
    async def v1_geocode() -> dict[str, str]:
        _raise_operational(orig)
        return {"status": "unreachable"}

    return app


@pytest.mark.parametrize(
    ("orig", "error_type", "message", "hint_marker"),
    [
        (
            pg_errors.QueryCanceled("canceling statement due to statement timeout"),
            "statement_timeout",
            "database query timed out",
            "KTG_PG_STATEMENT_TIMEOUT_MS",
        ),
        (
            pg_errors.LockNotAvailable("canceling statement due to lock timeout"),
            "lock_timeout",
            "database query timed out waiting for a lock",
            "lock_timeout",
        ),
        (
            pg_errors.QueryCanceled("canceling statement due to user request"),
            "query_canceled",
            "database query was cancelled",
            "cancelled",
        ),
    ],
)
def test_query_timeout_maps_to_e0504_gateway_timeout_not_dsn_hint(
    orig: BaseException, error_type: str, message: str, hint_marker: str
) -> None:
    # T-309: statement_timeout(57014)/lock_timeout(55P03) are psycopg OperationalError
    # subclasses, but the connection worked — the response must not blame KTG_PG_DSN.
    before = _db_error_count(error_type)
    response = TestClient(_db_error_app(orig), raise_server_exceptions=False).post("/v2/geocode")

    payload = response.json()
    assert response.status_code == 504
    assert payload["status"] == "ERROR"
    assert payload["error"]["code"] == "E0504"
    assert payload["error"]["message"] == message
    assert hint_marker in payload["error"]["hint"]
    assert "KTG_PG_DSN" not in payload["error"]["hint"]
    assert "secret_value" not in response.text
    assert _db_error_count(error_type) == before + 1


def test_vworld_statement_timeout_keeps_vworld_system_error_shape() -> None:
    orig = pg_errors.QueryCanceled("canceling statement due to statement timeout")
    response = TestClient(_db_error_app(orig), raise_server_exceptions=False).get(
        "/v1/address/geocode"
    )

    payload = response.json()
    assert response.status_code == 504
    assert payload["response"]["status"] == "ERROR"
    assert payload["response"]["service"]["operation"] == "getCoord"
    assert payload["response"]["error"] == {
        "level": 3,
        "code": "SYSTEM_ERROR",
        "text": "database query timed out",
    }


@pytest.mark.parametrize(
    ("orig", "error_type", "message", "hint_marker"),
    [
        (
            psycopg.OperationalError(
                'connection failed: connection to server at "127.0.0.1", port 11000 failed: '
                "Connection refused"
            ),
            "connection_failed",
            "database connection failed",
            "host/port in KTG_PG_DSN",
        ),
        (
            psycopg.OperationalError(
                "failed to resolve host 'db.invalid': [Errno -2] Name or service not known"
            ),
            "connection_failed",
            "database connection failed",
            "host/port in KTG_PG_DSN",
        ),
        (
            psycopg.OperationalError(
                'connection failed: connection to server at "127.0.0.1", port 11000 failed: '
                'FATAL:  password authentication failed for user "secret_user"'
            ),
            "auth_failed",
            "database authentication or permission check failed",
            "password",
        ),
        (
            psycopg.OperationalError(
                'connection failed: connection to server at "127.0.0.1", port 11000 failed: '
                'FATAL:  permission denied for database "secret_db"'
            ),
            "auth_failed",
            "database authentication or permission check failed",
            "CONNECT",
        ),
        (
            psycopg.OperationalError(
                'connection failed: connection to server at "127.0.0.1", port 11000 failed: '
                'FATAL:  role "secret_user" does not exist'
            ),
            "auth_failed",
            "database authentication or permission check failed",
            "CONNECT",
        ),
        (
            psycopg.OperationalError(
                'connection failed: connection to server at "127.0.0.1", port 11000 failed: '
                "FATAL:  sorry, too many clients already"
            ),
            "too_many_connections",
            "database connection limit reached",
            "max_connections",
        ),
        (
            pg_errors.AdminShutdown("terminating connection due to administrator command"),
            "connection_failed",
            "database connection failed",
            "KTG_PG_DSN",
        ),
    ],
)
def test_connection_failures_keep_dsn_hint_and_split_auth_from_unreachable(
    orig: BaseException, error_type: str, message: str, hint_marker: str
) -> None:
    before = _db_error_count(error_type)
    response = TestClient(_db_error_app(orig), raise_server_exceptions=False).post("/v2/geocode")

    payload = response.json()
    assert response.status_code == 503
    assert payload["error"]["code"] == "E0500"
    assert payload["error"]["message"] == message
    assert hint_marker in payload["error"]["hint"]
    # 서버 원문(사용자명·DB명·호스트)은 분류에만 쓰고 응답에 싣지 않는다.
    assert "secret_user" not in response.text
    assert "secret_db" not in response.text
    assert "127.0.0.1" not in response.text
    assert _db_error_count(error_type) == before + 1


def test_unpopulated_serving_mv_maps_to_not_ready_hint() -> None:
    orig = pg_errors.ObjectNotInPrerequisiteState(
        'materialized view "mv_geocode_target" has not been populated'
    )
    before = _db_error_count("mv_not_populated")
    response = TestClient(_db_error_app(orig), raise_server_exceptions=False).post("/v2/geocode")

    payload = response.json()
    assert response.status_code == 503
    assert payload["error"]["code"] == "E0500"
    assert payload["error"]["message"] == "serving data is not ready"
    assert "/v1/readyz" in payload["error"]["hint"]
    assert "KTG_PG_DSN" not in payload["error"]["hint"]
    assert _db_error_count("mv_not_populated") == before + 1


def test_unclassified_operational_error_keeps_generic_message_and_class_label() -> None:
    orig = pg_errors.DiskFull("could not extend file: No space left on device")
    before = _db_error_count("OperationalError")
    response = TestClient(_db_error_app(orig), raise_server_exceptions=False).post("/v2/geocode")

    payload = response.json()
    assert response.status_code == 503
    assert payload["error"]["code"] == "E0500"
    assert payload["error"]["message"] == "database operation failed"
    assert "KTG_PG_DSN" not in payload["error"]["hint"]
    assert _db_error_count("OperationalError") == before + 1


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
    assert payload["response"]["error"]["text"] == "database connection failed"
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
