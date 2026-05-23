"""DTO response builders shared by core services."""

from __future__ import annotations

from datetime import UTC, datetime

from kraddr.geo.dto.address import AddressStructure, RefinedAddress
from kraddr.geo.dto.common import ServiceMeta

from .protocols import AddressLookup


def service_meta(operation: str) -> ServiceMeta:
    return ServiceMeta(
        name="kraddr-geo",
        operation=operation,
        time=datetime.now(UTC).isoformat(),
    )


def structure_from_lookup(row: AddressLookup) -> AddressStructure:
    return AddressStructure(
        level1=row.si_nm,
        level2=row.sgg_nm,
        level4L=row.li_nm or row.emd_nm,
        level4LC=row.bjd_cd,
        level4A=row.adm_nm,
        level4AC=row.adm_cd,
        level5=row.road_nm,
        detail=row.detail,
    )


def refined_from_lookup(row: AddressLookup) -> RefinedAddress:
    return RefinedAddress(text=row.text, structure=structure_from_lookup(row))

