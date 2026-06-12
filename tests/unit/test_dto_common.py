import pytest
from pydantic import BaseModel, ValidationError

from kortravelgeo.dto.common import CRS, Page, Point, ServiceMeta, ZipSource


class _CrsModel(BaseModel):
    crs: CRS


def test_crs_normalizes_common_spellings() -> None:
    assert _CrsModel(crs="epsg-4326").crs == "EPSG:4326"
    assert _CrsModel(crs="EPSG5179").crs == "EPSG:5179"
    assert _CrsModel(crs="3857").crs == "EPSG:3857"


def test_crs_rejects_unknown_format() -> None:
    with pytest.raises(ValidationError):
        _CrsModel(crs="WGS84")


def test_common_models_are_frozen() -> None:
    point = Point(x=127.0286, y=37.5003)

    with pytest.raises(ValidationError):
        point.x = 128.0


def test_page_bounds() -> None:
    assert Page().model_dump() == {"page": 1, "size": 10}

    with pytest.raises(ValidationError):
        Page(size=101)


def test_enum_serializes_to_wire_value() -> None:
    assert ZipSource.BUILDING_BSI_ZON_NO.value == "building_bsi_zon_no"
    assert ServiceMeta(name="kor-travel-geo", operation="geocode").version == "2.0"
