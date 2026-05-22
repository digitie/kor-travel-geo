import pytest
from pydantic import ValidationError

from kraddr.geo.dto.address import AddressStructure, RefinedAddress


def test_address_structure_preserves_vworld_field_names() -> None:
    structure = AddressStructure(
        level1="서울특별시",
        level2="강남구",
        level4L="역삼동",
        level4LC="1168010100",
        level5="테헤란로",
        detail="152",
    )

    assert structure.model_dump(exclude_none=True) == {
        "level0": "대한민국",
        "level1": "서울특별시",
        "level2": "강남구",
        "level4L": "역삼동",
        "level4LC": "1168010100",
        "level5": "테헤란로",
        "detail": "152",
    }


def test_address_structure_turns_blank_optional_fields_into_none() -> None:
    structure = AddressStructure(level0="대한민국", level1="", level2="강남구")

    assert structure.level1 is None
    assert structure.level2 == "강남구"


def test_address_structure_rejects_blank_level0() -> None:
    with pytest.raises(ValidationError):
        AddressStructure(level0="")


def test_refined_address_is_frozen() -> None:
    refined = RefinedAddress(
        text="서울특별시 강남구 테헤란로 152",
        structure=AddressStructure(level1="서울특별시", level2="강남구"),
    )

    with pytest.raises(ValidationError):
        refined.text = "changed"


def test_refined_address_requires_structure() -> None:
    with pytest.raises(ValidationError):
        RefinedAddress(text="서울특별시 강남구 테헤란로 152")
