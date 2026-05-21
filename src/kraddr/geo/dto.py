"""Pydantic DTOs for address geocoding and reverse geocoding."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CoordinateCrs = Literal["EPSG:4326", "EPSG:5174", "EPSG:5179"]


class AddressGeocodeRequest(BaseModel):
    """Address-to-coordinate request."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    service: str = "address"
    request: str = "getcoord"
    version: str = "2.0"
    format: Literal["json", "xml"] = "json"
    type: Literal["road", "parcel", "both"] = "road"
    crs: CoordinateCrs = "EPSG:4326"
    query: str | None = None
    road_name_code: str | None = Field(default=None, alias="rnMgtSn")
    legal_dong_code: str | None = Field(default=None, alias="admCd")
    underground_yn: str | None = Field(default=None, alias="udrtYn")
    building_main_no: int | str | None = Field(default=None, alias="buldMnnm")
    building_sub_no: int | str | None = Field(default=None, alias="buldSlno")
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator(
        "query",
        "road_name_code",
        "legal_dong_code",
        "underground_yn",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class AddressReverseGeocodeRequest(BaseModel):
    """Coordinate-to-address request."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    service: str = "address"
    request: str = "getaddress"
    version: str = "2.0"
    format: Literal["json", "xml"] = "json"
    type: Literal["road", "parcel", "both"] = "both"
    crs: CoordinateCrs = "EPSG:4326"
    x: float
    y: float
    max_distance_m: float | None = Field(default=50.0, ge=0)


class PostalCodeLookupRequest(BaseModel):
    """Postal-code lookup request."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    zipcode: str = Field(alias="zipNo", min_length=5, max_length=5)
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    @field_validator("zipcode", mode="before")
    @classmethod
    def _normalize_zipcode(cls, value: Any) -> str:
        return str(value or "").strip()


class CoordinateCandidate(BaseModel):
    """Normalized coordinate candidate returned by offline geocoding."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    x: float
    y: float
    crs: CoordinateCrs = "EPSG:5179"
    road_address: str | None = None
    parcel_address: str | None = None
    postal_code: str | None = None
    legal_dong_code: str | None = None
    road_name_code: str | None = None
    underground_yn: str | None = None
    building_main_no: str | None = None
    building_sub_no: str | None = None
    building_management_number: str | None = None
    building_name: str | None = None
    source: str = ""
    coordinate_role: str = ""
    distance_m: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
