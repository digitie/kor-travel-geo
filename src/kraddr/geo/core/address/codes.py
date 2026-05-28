"""Pure helpers for Korean address code composition.

The helpers in this module are an independent implementation based on public
Korean address-code rules. T-056 found that the local base package copy is
GPL-3.0-or-later and is not a Git checkout, so source code was not copied from
it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

SIGUNGU_CODE_LENGTH = 5
LEGAL_DONG_CODE_LENGTH = 10
ROAD_NAME_CODE_LENGTH = 12
ROAD_NAME_NUMBER_LENGTH = 7
ROAD_NAME_ADDRESS_CODE_LENGTH = 26
BUILDING_NUMBER_WIDTH = 5
BUILDING_MANAGEMENT_NUMBER_LENGTHS = frozenset({25, 26})

_CODE_SEPARATOR_RE = re.compile(r"[\s\-_]+")

_SIGUNGU_ALIASES = (
    "sigungu_code",
    "sigunguCode",
    "sigunguCd",
    "sgg_cd",
    "sggCd",
    "sig_cd",
    "sigCd",
    "SIG_CD",
    "SGG_CD",
)
_LEGAL_DONG_ALIASES = (
    "legal_dong_code",
    "legalDongCode",
    "bjd_cd",
    "bjdCd",
    "adm_cd",
    "admCd",
    "ADM_CD",
)
_ROAD_NAME_ALIASES = (
    "road_name_code",
    "roadNameCode",
    "rncode_full",
    "rn_mgt_sn",
    "rnMgtSn",
    "RN_MGT_SN",
)
_ROAD_NAME_ADDRESS_ALIASES = (
    "road_name_address_code",
    "roadNameAddressCode",
    "roadAddrMgtNo",
    "roadAddrMgtSn",
    "road_address_management_number",
)
_BUILDING_MANAGEMENT_ALIASES = (
    "building_management_number",
    "bd_mgt_sn",
    "bdMgtSn",
    "BD_MGT_SN",
)
_UNDERGROUND_ALIASES = ("udrt_yn", "udrtYn", "UDRT_YN", "buld_se_cd", "buldSeCd")
_BUILDING_MAIN_ALIASES = ("buld_mnnm", "buldMnnm", "BULD_MNNM", "mnnm")
_BUILDING_SUB_ALIASES = ("buld_slno", "buldSlno", "BULD_SLNO", "slno")


def _clean_digits(value: object, *, field_name: str) -> str:
    if value is None:
        msg = f"{field_name} is required"
        raise ValueError(msg)
    cleaned = _CODE_SEPARATOR_RE.sub("", str(value).strip())
    if not cleaned or not cleaned.isascii() or not cleaned.isdigit():
        msg = f"{field_name} must contain digits only"
        raise ValueError(msg)
    return cleaned


def _digits_with_length(value: object, *, field_name: str, length: int) -> str:
    cleaned = _clean_digits(value, field_name=field_name)
    if len(cleaned) != length:
        msg = f"{field_name} must be {length} digits"
        raise ValueError(msg)
    return cleaned


def _digits_part(value: object | None, *, field_name: str, width: int) -> str:
    if value is None:
        return "0" * width
    cleaned = _clean_digits(value, field_name=field_name)
    if len(cleaned) > width:
        msg = f"{field_name} must be at most {width} digits"
        raise ValueError(msg)
    return cleaned.zfill(width)


def _first_mapping_value(mapping: Mapping[str, object], aliases: tuple[str, ...]) -> object | None:
    for alias in aliases:
        value = mapping.get(alias)
        if not _is_blank(value):
            return value

    lowered = {key.lower(): value for key, value in mapping.items()}
    for alias in aliases:
        value = lowered.get(alias.lower())
        if not _is_blank(value):
            return value
    return None


def _is_blank(value: object | None) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def normalize_sigungu_code(value: object) -> str:
    """Normalize a 5-digit 시군구 code."""

    return _digits_with_length(value, field_name="sigungu_code", length=SIGUNGU_CODE_LENGTH)


def normalize_legal_dong_code(value: object) -> str:
    """Normalize a 10-digit 법정동 code."""

    return _digits_with_length(
        value,
        field_name="legal_dong_code",
        length=LEGAL_DONG_CODE_LENGTH,
    )


def normalize_road_name_code(value: object) -> str:
    """Normalize a 12-digit 도로명관리번호."""

    return _digits_with_length(
        value,
        field_name="road_name_code",
        length=ROAD_NAME_CODE_LENGTH,
    )


def normalize_road_name_address_code(value: object) -> str:
    """Normalize a 26-digit 도로명주소관리번호."""

    return _digits_with_length(
        value,
        field_name="road_name_address_code",
        length=ROAD_NAME_ADDRESS_CODE_LENGTH,
    )


def normalize_building_management_number(value: object) -> str:
    """Normalize a 건물관리번호 while accepting 25/26 digit provider variants."""

    cleaned = _clean_digits(value, field_name="building_management_number")
    if len(cleaned) not in BUILDING_MANAGEMENT_NUMBER_LENGTHS:
        lengths = "/".join(str(length) for length in sorted(BUILDING_MANAGEMENT_NUMBER_LENGTHS))
        msg = f"building_management_number must be {lengths} digits"
        raise ValueError(msg)
    return cleaned


def normalize_building_number(value: object) -> int:
    """Normalize a road-address building main/sub number into the 0..99999 range."""

    cleaned = _clean_digits(value, field_name="building_number")
    number = int(cleaned)
    if number > 99999:
        msg = "building_number must be between 0 and 99999"
        raise ValueError(msg)
    return number


def normalize_underground_flag(value: object) -> str:
    """Normalize Juso ``udrtYn`` / 건물구분 flag to ``0`` or ``1``."""

    if isinstance(value, bool):
        return "1" if value else "0"
    cleaned = _clean_digits(value, field_name="underground_flag")
    if cleaned not in {"0", "1"}:
        msg = "underground_flag must be 0 or 1"
        raise ValueError(msg)
    return cleaned


@dataclass(frozen=True, slots=True)
class SigunguCode:
    """5-digit 시군구 code."""

    code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_sigungu_code(self.code))

    def __str__(self) -> str:
        return self.code

    @classmethod
    def from_parts(cls, *, sido: object, sigungu: object) -> SigunguCode:
        sido_part = _digits_part(sido, field_name="sido", width=2)
        sigungu_part = _digits_part(sigungu, field_name="sigungu", width=3)
        return cls(code=f"{sido_part}{sigungu_part}")

    @property
    def sido_code(self) -> str:
        return self.code[:2]

    @property
    def sigungu_part(self) -> str:
        return self.code[2:]

    @property
    def legal_dong_code(self) -> LegalDongCode:
        return LegalDongCode(code=f"{self.code}00000")

    def to_orm_dict(self) -> dict[str, str]:
        return {
            "sido_code": self.sido_code,
            "sigungu_code": self.code,
            "legal_dong_code": self.legal_dong_code.code,
        }


@dataclass(frozen=True, slots=True)
class LegalDongCode:
    """10-digit 법정동 code with hierarchy helpers."""

    code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_legal_dong_code(self.code))

    def __str__(self) -> str:
        return self.code

    @classmethod
    def from_parts(
        cls,
        *,
        sido: object,
        sigungu: object | None = None,
        eup_myeon_dong: object | None = None,
        ri: object | None = None,
    ) -> LegalDongCode:
        return cls(
            code=(
                f"{_digits_part(sido, field_name='sido', width=2)}"
                f"{_digits_part(sigungu, field_name='sigungu', width=3)}"
                f"{_digits_part(eup_myeon_dong, field_name='eup_myeon_dong', width=3)}"
                f"{_digits_part(ri, field_name='ri', width=2)}"
            )
        )

    @property
    def sido_code(self) -> str:
        return self.code[:2]

    @property
    def sigungu_part(self) -> str:
        return self.code[2:5]

    @property
    def sigungu_code(self) -> str:
        return self.code[:5]

    @property
    def eup_myeon_dong_part(self) -> str:
        return self.code[5:8]

    @property
    def eup_myeon_dong_code(self) -> str:
        return self.code[:8]

    @property
    def ri_part(self) -> str:
        return self.code[8:]

    @property
    def is_sido_level(self) -> bool:
        return self.code[2:] == "00000000"

    @property
    def is_sigungu_level(self) -> bool:
        return self.sigungu_part != "000" and self.code[5:] == "00000"

    @property
    def is_eup_myeon_dong_level(self) -> bool:
        return self.eup_myeon_dong_part != "000" and self.ri_part == "00"

    @property
    def is_ri_level(self) -> bool:
        return self.ri_part != "00"

    @property
    def parent_code(self) -> LegalDongCode | None:
        if self.is_ri_level:
            return LegalDongCode(code=f"{self.code[:8]}00")
        if self.is_eup_myeon_dong_level:
            return LegalDongCode(code=f"{self.code[:5]}00000")
        if self.is_sigungu_level:
            return LegalDongCode(code=f"{self.code[:2]}00000000")
        return None

    def to_sigungu_code(self) -> SigunguCode:
        return SigunguCode(code=self.sigungu_code)

    def ancestors(self, *, include_self: bool = False) -> tuple[LegalDongCode, ...]:
        ancestors = [LegalDongCode.from_parts(sido=self.sido_code)]
        if self.sigungu_part != "000":
            ancestors.append(
                LegalDongCode.from_parts(sido=self.sido_code, sigungu=self.sigungu_part)
            )
        if self.eup_myeon_dong_part != "000":
            ancestors.append(
                LegalDongCode.from_parts(
                    sido=self.sido_code,
                    sigungu=self.sigungu_part,
                    eup_myeon_dong=self.eup_myeon_dong_part,
                )
            )
        if self.ri_part != "00":
            ancestors.append(self)
        if include_self and ancestors[-1] != self:
            ancestors.append(self)
        if not include_self and ancestors[-1] == self:
            ancestors.pop()
        return tuple(ancestors)

    def is_descendant_of(self, other: LegalDongCode) -> bool:
        return self.code.startswith(other._significant_prefix())

    def to_orm_dict(self) -> dict[str, str]:
        return {
            "sido_code": self.sido_code,
            "sigungu_code": self.sigungu_code,
            "legal_dong_code": self.code,
        }

    def _significant_prefix(self) -> str:
        if self.is_sido_level:
            return self.sido_code
        if self.is_sigungu_level:
            return self.sigungu_code
        if self.is_eup_myeon_dong_level:
            return self.eup_myeon_dong_code
        return self.code


@dataclass(frozen=True, slots=True)
class RoadNameCode:
    """12-digit 도로명관리번호."""

    code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_road_name_code(self.code))

    def __str__(self) -> str:
        return self.code

    @classmethod
    def from_parts(cls, *, sigungu_code: object, road_number: object) -> RoadNameCode:
        sigungu = SigunguCode(code=normalize_sigungu_code(sigungu_code))
        rn = _digits_part(road_number, field_name="road_number", width=ROAD_NAME_NUMBER_LENGTH)
        return cls(code=f"{sigungu.code}{rn}")

    @property
    def sigungu_code(self) -> str:
        return self.code[:SIGUNGU_CODE_LENGTH]

    @property
    def road_number(self) -> str:
        return self.code[SIGUNGU_CODE_LENGTH:]

    def to_orm_dict(self) -> dict[str, str]:
        return {
            "sigungu_code": self.sigungu_code,
            "road_name_code": self.code,
            "road_name_number": self.road_number,
        }


@dataclass(frozen=True, slots=True)
class RoadNameAddressCode:
    """26-digit road-address management code composed from Juso fields."""

    code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalize_road_name_address_code(self.code))

    def __str__(self) -> str:
        return self.code

    @classmethod
    def from_components(
        cls,
        *,
        adm_cd: object,
        rn_mgt_sn: object,
        udrt_yn: object,
        buld_mnnm: object | None = None,
        buld_slno: object | None = None,
    ) -> RoadNameAddressCode:
        if buld_mnnm is None or buld_slno is None:
            msg = "buld_mnnm and buld_slno are required"
            raise ValueError(msg)
        legal = LegalDongCode(code=normalize_legal_dong_code(adm_cd))
        road = RoadNameCode(code=normalize_road_name_code(rn_mgt_sn))
        if road.sigungu_code != legal.sigungu_code:
            msg = "adm_cd and rn_mgt_sn must belong to the same sigungu"
            raise ValueError(msg)
        main = normalize_building_number(buld_mnnm)
        sub = normalize_building_number(buld_slno)
        underground = normalize_underground_flag(udrt_yn)
        return cls(
            code=(
                f"{legal.eup_myeon_dong_code}"
                f"{road.road_number}"
                f"{underground}"
                f"{main:0{BUILDING_NUMBER_WIDTH}d}"
                f"{sub:0{BUILDING_NUMBER_WIDTH}d}"
            )
        )

    @property
    def legal_dong_code(self) -> LegalDongCode:
        return LegalDongCode(code=f"{self.code[:8]}00")

    @property
    def road_name_code(self) -> RoadNameCode:
        return RoadNameCode(
            code=f"{self.legal_dong_code.sigungu_code}"
            f"{self.code[8:8 + ROAD_NAME_NUMBER_LENGTH]}"
        )

    @property
    def underground_flag(self) -> str:
        return self.code[8 + ROAD_NAME_NUMBER_LENGTH]

    @property
    def building_main_number(self) -> int:
        start = 8 + ROAD_NAME_NUMBER_LENGTH + 1
        return int(self.code[start : start + BUILDING_NUMBER_WIDTH])

    @property
    def building_sub_number(self) -> int:
        start = 8 + ROAD_NAME_NUMBER_LENGTH + 1 + BUILDING_NUMBER_WIDTH
        return int(self.code[start : start + BUILDING_NUMBER_WIDTH])

    def to_juso_query_dict(self) -> dict[str, str]:
        return {
            "admCd": self.legal_dong_code.code,
            "rnMgtSn": self.road_name_code.code,
            "udrtYn": self.underground_flag,
            "buldMnnm": str(self.building_main_number),
            "buldSlno": str(self.building_sub_number),
        }

    def to_orm_dict(self) -> dict[str, str]:
        return {
            "legal_dong_code": self.legal_dong_code.code,
            "road_name_code": self.road_name_code.code,
            "road_name_address_code": self.code,
        }


@dataclass(frozen=True, slots=True, init=False)
class AddressCodeSet:
    """Container for related Korean address code identifiers."""

    _sigungu_code: SigunguCode | None
    legal_dong_code: LegalDongCode | None
    road_name_code: RoadNameCode | None
    road_name_address_code: RoadNameAddressCode | None
    building_management_number: str | None

    def __init__(
        self,
        *,
        sigungu_code: SigunguCode | str | None = None,
        legal_dong_code: LegalDongCode | str | None = None,
        road_name_code: RoadNameCode | str | None = None,
        road_name_address_code: RoadNameAddressCode | str | None = None,
        building_management_number: str | None = None,
    ) -> None:
        road_address = _as_road_name_address_code(road_name_address_code)
        legal = _as_legal_dong_code(legal_dong_code) or (
            road_address.legal_dong_code if road_address else None
        )
        road = _as_road_name_code(road_name_code) or (
            road_address.road_name_code if road_address else None
        )
        explicit_sigungu = _as_sigungu_code(sigungu_code)
        building_management = (
            normalize_building_management_number(building_management_number)
            if building_management_number is not None
            else None
        )

        object.__setattr__(self, "_sigungu_code", explicit_sigungu)
        object.__setattr__(self, "legal_dong_code", legal)
        object.__setattr__(self, "road_name_code", road)
        object.__setattr__(self, "road_name_address_code", road_address)
        object.__setattr__(self, "building_management_number", building_management)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> AddressCodeSet:
        return address_code_set_from_mapping(mapping)

    @property
    def sigungu_code(self) -> SigunguCode | None:
        if self._sigungu_code is not None:
            return self._sigungu_code
        if self.legal_dong_code is not None:
            return self.legal_dong_code.to_sigungu_code()
        if self.road_name_code is not None:
            return SigunguCode(code=self.road_name_code.sigungu_code)
        return None

    @property
    def has_any_code(self) -> bool:
        return any(
            value is not None
            for value in (
                self.sigungu_code,
                self.legal_dong_code,
                self.road_name_code,
                self.road_name_address_code,
                self.building_management_number,
            )
        )

    def to_orm_dict(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if self.sigungu_code is not None:
            values["sigungu_code"] = self.sigungu_code.code
        if self.legal_dong_code is not None:
            values["legal_dong_code"] = self.legal_dong_code.code
        if self.road_name_code is not None:
            values["road_name_code"] = self.road_name_code.code
        if self.road_name_address_code is not None:
            values["road_name_address_code"] = self.road_name_address_code.code
        if self.building_management_number is not None:
            values["building_management_number"] = self.building_management_number
        return values


def sigungu_code_from_mapping(mapping: Mapping[str, object]) -> SigunguCode | None:
    value = _first_mapping_value(mapping, _SIGUNGU_ALIASES)
    return SigunguCode(code=normalize_sigungu_code(value)) if value is not None else None


def legal_dong_code_from_mapping(mapping: Mapping[str, object]) -> LegalDongCode | None:
    value = _first_mapping_value(mapping, _LEGAL_DONG_ALIASES)
    return LegalDongCode(code=normalize_legal_dong_code(value)) if value is not None else None


def road_name_code_from_mapping(mapping: Mapping[str, object]) -> RoadNameCode | None:
    value = _first_mapping_value(mapping, _ROAD_NAME_ALIASES)
    return RoadNameCode(code=normalize_road_name_code(value)) if value is not None else None


def road_name_address_code_from_mapping(
    mapping: Mapping[str, object],
) -> RoadNameAddressCode | None:
    explicit = _first_mapping_value(mapping, _ROAD_NAME_ADDRESS_ALIASES)
    if explicit is not None:
        return RoadNameAddressCode(code=normalize_road_name_address_code(explicit))

    adm_cd = _first_mapping_value(mapping, _LEGAL_DONG_ALIASES)
    rn_mgt_sn = _first_mapping_value(mapping, _ROAD_NAME_ALIASES)
    udrt_yn = _first_mapping_value(mapping, _UNDERGROUND_ALIASES)
    buld_mnnm = _first_mapping_value(mapping, _BUILDING_MAIN_ALIASES)
    buld_slno = _first_mapping_value(mapping, _BUILDING_SUB_ALIASES)
    if any(value is None for value in (adm_cd, rn_mgt_sn, udrt_yn, buld_mnnm, buld_slno)):
        return None
    return RoadNameAddressCode.from_components(
        adm_cd=adm_cd,
        rn_mgt_sn=rn_mgt_sn,
        udrt_yn=udrt_yn,
        buld_mnnm=buld_mnnm,
        buld_slno=buld_slno,
    )


def address_code_set_from_mapping(mapping: Mapping[str, object]) -> AddressCodeSet:
    building_management = _first_mapping_value(mapping, _BUILDING_MANAGEMENT_ALIASES)
    return AddressCodeSet(
        sigungu_code=sigungu_code_from_mapping(mapping),
        legal_dong_code=legal_dong_code_from_mapping(mapping),
        road_name_code=road_name_code_from_mapping(mapping),
        road_name_address_code=road_name_address_code_from_mapping(mapping),
        building_management_number=(
            normalize_building_management_number(building_management)
            if building_management is not None
            else None
        ),
    )


def _as_sigungu_code(value: SigunguCode | str | None) -> SigunguCode | None:
    if value is None:
        return None
    return value if isinstance(value, SigunguCode) else SigunguCode(code=value)


def _as_legal_dong_code(value: LegalDongCode | str | None) -> LegalDongCode | None:
    if value is None:
        return None
    return value if isinstance(value, LegalDongCode) else LegalDongCode(code=value)


def _as_road_name_code(value: RoadNameCode | str | None) -> RoadNameCode | None:
    if value is None:
        return None
    return value if isinstance(value, RoadNameCode) else RoadNameCode(code=value)


def _as_road_name_address_code(
    value: RoadNameAddressCode | str | None,
) -> RoadNameAddressCode | None:
    if value is None:
        return None
    return value if isinstance(value, RoadNameAddressCode) else RoadNameAddressCode(code=value)
