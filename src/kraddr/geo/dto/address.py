"""Address structure DTOs compatible with vworld responses."""

from __future__ import annotations

from pydantic import field_validator

from .common import FrozenModel


class AddressStructure(FrozenModel):
    """Structured address fields using vworld-compatible names."""

    level0: str = "대한민국"
    level1: str | None = None
    level2: str | None = None
    level3: str | None = None
    level4L: str | None = None
    level4LC: str | None = None
    level4A: str | None = None
    level4AC: str | None = None
    level5: str | None = None
    detail: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


class RefinedAddress(FrozenModel):
    text: str
    structure: AddressStructure | None = None
