import pytest
from pydantic import ValidationError

from kortravelgeo.dto.address import AddressStructure
from kortravelgeo.dto.common import Point, ServiceMeta
from kortravelgeo.dto.reverse import ReverseInput, ReverseResponse, ReverseResultItem


def test_reverse_input_defaults() -> None:
    item = ReverseInput(point=Point(x=127.0286, y=37.5003))

    assert item.type == "both"
    assert item.radius_m == 200
    assert item.crs == "EPSG:4326"


def test_reverse_input_rejects_lat_lon_swap() -> None:
    with pytest.raises(ValidationError):
        ReverseInput(point=Point(x=37.5003, y=127.0286))


def test_reverse_response_item_wire_shape() -> None:
    response = ReverseResponse(
        service=ServiceMeta(name="kor-travel-geo", operation="reverse"),
        status="OK",
        input=ReverseInput(point=Point(x=127.0286, y=37.5003)),
        result=(
            ReverseResultItem(
                type="road",
                text="서울특별시 강남구 테헤란로 152",
                structure=AddressStructure(level1="서울특별시", level2="강남구"),
                zipcode="06236",
                distance_m=3.2,
            ),
        ),
    )

    dumped = response.model_dump(mode="json", exclude_none=True)

    assert dumped["result"][0]["type"] == "road"
    assert dumped["result"][0]["zipcode"] == "06236"
