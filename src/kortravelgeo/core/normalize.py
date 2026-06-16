"""Pure address normalization helpers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from kortravelgeo.exceptions import InvalidAddressError

_SPACE_RE = re.compile(r"\s+")
_SEPARATOR_RE = re.compile(r"[,\uFF0C\u3001;\uFF1B]")
_NUMBER_HYPHEN_RE = re.compile(r"(?<=\d)\s*-\s*(?=\d)")
_DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\uFF0D": "-",
    }
)
_BRACKET_RE = re.compile(r"[\(\[\{]([^)\]\}]*)[\)\]\}]")
_ROAD_RE = re.compile(
    r"(?P<road>[가-힣0-9A-Za-z·.\-\s]+?(?:대로|로|길))\s*"
    r"(?P<main>\d+)(?:-(?P<sub>\d+))?(?:\s*(?:번지|번))?"
)
_JIBUN_RE = re.compile(
    r"(?P<mt>산\s*)?(?P<main>\d+)(?:-(?P<sub>\d+))?(?:\s*(?:번지|번))?"
)

_SIDO_ALIASES = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
    "서울시": "서울특별시",
    "부산시": "부산광역시",
    "대구시": "대구광역시",
    "인천시": "인천광역시",
    "대전시": "대전광역시",
    "울산시": "울산광역시",
    "세종시": "세종특별자치시",
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
    "전북도": "전북특별자치도",
    "제주도": "제주특별자치도",
    "충북도": "충청북도",
    "충남도": "충청남도",
    "전남도": "전라남도",
    "경북도": "경상북도",
    "경남도": "경상남도",
}

_SIDO_SUFFIXES = ("특별시", "광역시", "특별자치시", "특별자치도", "자치도", "도")
_SGG_SUFFIXES = ("시", "군", "구")
_DONG_SUFFIXES = ("읍", "면", "동", "가", "리")


@dataclass(frozen=True, slots=True)
class AddrParts:
    raw: str
    normalized: str
    si: str | None = None
    sgg: str | None = None
    emd: str | None = None
    li: str | None = None
    road: str | None = None
    road_nrm: str | None = None
    mnnm: int | None = None
    slno: int = 0
    mt: bool = False
    under: bool = False
    detail: str | None = None
    bracket_note: str | None = None
    is_road: bool = False

    @property
    def mntn_yn(self) -> str:
        return "1" if self.mt else "0"

    @property
    def buld_se_cd(self) -> str:
        return "1" if self.under else "0"

    @property
    def sgg_nrm(self) -> str | None:
        return self.sgg.replace(" ", "") if self.sgg else None


def normalize_spaces(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(_DASH_TRANSLATION)
    normalized = _SEPARATOR_RE.sub(" ", normalized)
    normalized = _NUMBER_HYPHEN_RE.sub("-", normalized)
    return _SPACE_RE.sub(" ", normalized.strip())


def normalize_sido(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return _SIDO_ALIASES.get(stripped, stripped)


def compact(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", "", value)


def _pop_region(tokens: list[str]) -> tuple[str | None, str | None, str | None, str | None]:
    si = sgg = emd = li = None
    idx = 0
    if idx < len(tokens) and (
        tokens[idx] in _SIDO_ALIASES or tokens[idx].endswith(_SIDO_SUFFIXES)
    ):
        si = normalize_sido(tokens[idx])
        idx += 1
    if idx < len(tokens) and tokens[idx].endswith(_SGG_SUFFIXES):
        sgg = tokens[idx]
        idx += 1
        if idx < len(tokens) and tokens[idx].endswith("구") and (sgg.endswith("시")):
            sgg = f"{sgg} {tokens[idx]}"
            idx += 1
    if idx < len(tokens) and tokens[idx].endswith(_DONG_SUFFIXES):
        emd = tokens[idx]
        idx += 1
    if idx < len(tokens) and tokens[idx].endswith("리"):
        li = tokens[idx]
    return si, sgg, emd, li


def parse_address(raw: str) -> AddrParts:
    """Parse a Korean road or parcel address into conservative matching parts."""

    normalized = normalize_spaces(raw)
    if not normalized:
        msg = "address must not be empty"
        raise InvalidAddressError(msg)

    bracket_note: str | None = None
    bracket_match = _BRACKET_RE.search(normalized)
    if bracket_match:
        bracket_note = normalize_spaces(bracket_match.group(1))
        normalized = normalize_spaces(_BRACKET_RE.sub(" ", normalized))

    under = "지하" in normalized
    normalized_without_under = normalize_spaces(normalized.replace("지하", " "))
    tokens = normalized_without_under.split()
    si, sgg, emd, li = _pop_region(tokens)

    road_match = _ROAD_RE.search(normalized_without_under)
    if road_match:
        road = normalize_spaces(road_match.group("road").split()[-1])
        main = int(road_match.group("main"))
        sub = int(road_match.group("sub") or 0)
        detail = normalized_without_under[road_match.end() :].strip() or bracket_note
        return AddrParts(
            raw=raw,
            normalized=normalized_without_under,
            si=si,
            sgg=sgg,
            emd=emd,
            li=li,
            road=road,
            road_nrm=compact(road),
            mnnm=main,
            slno=sub,
            under=under,
            detail=detail,
            bracket_note=bracket_note,
            is_road=True,
        )

    jibun_match = None
    for match in _JIBUN_RE.finditer(normalized_without_under):
        jibun_match = match
    if jibun_match is None:
        msg = "address number could not be parsed"
        raise InvalidAddressError(msg)

    main = int(jibun_match.group("main"))
    sub = int(jibun_match.group("sub") or 0)
    detail = normalized_without_under[jibun_match.end() :].strip() or bracket_note
    return AddrParts(
        raw=raw,
        normalized=normalized_without_under,
        si=si,
        sgg=sgg,
        emd=emd,
        li=li,
        mnnm=main,
        slno=sub,
        mt=bool(jibun_match.group("mt")),
        under=under,
        detail=detail,
        bracket_note=bracket_note,
        is_road=False,
    )
