from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, model_validator

from kraddr.geo.api.responses import register_exception_handlers


class _CoordinateModel(BaseModel):
    x: float

    @model_validator(mode="after")
    def reject_outside_korea(self) -> _CoordinateModel:
        msg = "point must be within Korea lon/lat bounds: 123 < x < 132, 32 < y < 39"
        raise ValueError(msg)


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
