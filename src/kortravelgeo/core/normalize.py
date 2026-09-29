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
    r"(?P<road>[가-힣0-9A-Za-z·.\-\s]+?(?:대로\d+(?:번)?길|로\d+(?:번)?길|대로|로|길))\s*"
    r"(?P<main>\d+)(?:-(?P<sub>\d+))?(?:\s*(?:번지|번))?(?![길로\d])"
)
_JIBUN_RE = re.compile(
    r"(?P<mt>산\s*)?(?P<main>\d+)(?:-(?P<sub>\d+))?(?:\s*(?:번지|번))?(?![길로\d])"
)
# 읍면동·리 바로 다음에 오는 번지 토큰("681", "199-40", "산 12-3", "31-2번지", "123 번지")
# (T-320). 번호에 바로 붙은 동·통·반·출구 번호("101동", "3번출구", "737번지2층")는 번지가
# 아니다. 호/층은 부번까지 적은 번지에 붙은 접미사("642-16호", #339)만 허용하고, 본번에 바로
# 붙은 "1203호"·"2층"은 호수·층으로 본다. 그 밖의 글자·문장부호("737.", "737번지일원",
# "123일대", "'737'")는 번지 뒤 detail이다(T-317까지의 파싱과 같다).
_LOT_UNIT_AFTER = r"[\d동통반]|\s*번\s*출구|번지?\d"
_LEADING_LOT_RE = re.compile(
    r"[\"'\u2018\u2019\u201c\u201d]?(?P<mt>산\s*)?(?P<main>\d+)"
    rf"(?:-(?P<sub>\d+)(?!{_LOT_UNIT_AFTER})|(?![호층]|-\d|{_LOT_UNIT_AFTER}))"
    r"(?:\s*(?:번지|번))?"
)
# "태평로1가"·"종로1가"·"을지로2가"처럼 숫자+"가"로 끝나는 토큰은 법정동 이름이다(T-317).
# 도로명은 대로/로/길로 끝나므로 이 토큰의 "…로" + 숫자를 도로명 + 건물번호로 읽으면 안 된다.
_LEGAL_DONG_GA_RE = re.compile(r"(?<!\S)[가-힣]+\d+가(?!\S)")

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
# 시군구 없이 시도 바로 아래에 읍면동이 오는 시도. MV ``sgg_nm``이 NULL이다(T-320).
_SIDO_WITHOUT_SGG = frozenset({"세종특별자치시"})
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

    @property
    def sido_without_sgg(self) -> bool:
        """시군구가 없는 시도(세종특별자치시) 주소라 시군구 없이도 행정구역이 온전하다."""
        return self.sgg is None and self.si in _SIDO_WITHOUT_SGG


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


def _pop_region(
    tokens: list[str],
) -> tuple[str | None, str | None, str | None, str | None, int]:
    """앞쪽 행정구역 토큰을 떼어 (시도, 시군구, 읍면동, 리, 소비한 토큰 수)를 돌려준다."""
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
        idx += 1
    return si, sgg, emd, li, idx


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
    si, sgg, emd, li, region_token_count = _pop_region(tokens)
    # 법정동 "N가" 토큰은 같은 길이의 공백으로 가려 번호 탐색에서만 뺀다. 길이를 보존하므로
    # match 위치(detail 잘라내기)는 원문 기준 그대로 쓸 수 있다.
    number_source = _LEGAL_DONG_GA_RE.sub(
        lambda match: " " * len(match.group()), normalized_without_under
    )

    road_match = _ROAD_RE.search(number_source)
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

    jibun_match: re.Match[str] | None = None
    if emd or li:
        # 지번 번지는 읍면동·리 바로 다음 토큰이다(T-320). 마지막 숫자를 번지로 잡으면
        # "상계동 1234 … 1203호"·"역삼동 737 2층"의 호수·층 번호나 "신림1동"·"하귀1리"의
        # 이름 속 숫자를 번지로 읽는다. 그 자리에 번지가 없으면 번호 없는 주소로 본다.
        # tokens는 공백 하나로 정규화한 문자열을 나눈 것이라 join 길이 + 1이 다음 토큰 위치다.
        lot_start = len(" ".join(tokens[:region_token_count])) + 1
        jibun_match = _LEADING_LOT_RE.match(number_source, lot_start)
    else:
        # 읍면동·리 anchor가 없으면 번지 위치를 정할 수 없어 기존처럼 마지막 번호를 쓴다.
        for match in _JIBUN_RE.finditer(number_source):
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
