import pytest
from pydantic import ValidationError

from kraddr.geo.dto.address import AddressStructure, RefinedAddress
from kraddr.geo.dto.common import Point, ServiceMeta, ZipSource
from kraddr.geo.dto.geocode import (
    GeocodeExtension,
    GeocodeInput,
    GeocodeResponse,
    GeocodeResult,
)


def test_geocode_input_defaults_and_crs_normalization() -> None:
    item = GeocodeInput(address="서울특별시 강남구 테헤란로 152", crs="epsg-4326")

    assert item.type == "road"
    assert item.crs == "EPSG:4326"
    assert item.fallback == "local_only"


def test_geocode_extension_bounds_confidence() -> None:
    with pytest.raises(ValidationError):
        GeocodeExtension(source="local", confidence=1.1)


def test_geocode_response_wire_shape() -> None:
    response = GeocodeResponse(
        service=ServiceMeta(name="kraddr-geo", operation="geocode"),
        status="OK",
        input=GeocodeInput(address="서울특별시 강남구 테헤란로 152"),
        refined=RefinedAddress(
            text="서울특별시 강남구 테헤란로 152",
            structure=AddressStructure(level1="서울특별시", level2="강남구"),
        ),
        result=GeocodeResult(point=Point(x=127.0286, y=37.5003)),
        x_extension=GeocodeExtension(
            source="local",
            confidence=1.0,
            bd_mgt_sn="1168010100108250000000001",
            zip_source=ZipSource.BUILDING_BSI_ZON_NO,
        ),
    )

    dumped = response.model_dump(mode="json", exclude_none=True)

    assert dumped["status"] == "OK"
    assert dumped["result"]["point"] == {"x": 127.0286, "y": 37.5003}
    assert dumped["x_extension"]["zip_source"] == "building_bsi_zon_no"
