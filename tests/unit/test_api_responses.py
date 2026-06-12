from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError

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
