from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import pytest

from kortravelgeo.core.geocoder import geocode
from kortravelgeo.core.normalize import AddrParts, normalize_spaces, parse_address
from kortravelgeo.core.protocols import AddressLookup, SppnAreaLookup
from kortravelgeo.dto.common import Point
from kortravelgeo.dto.geocode import GeocodeInput
from kortravelgeo.exceptions import InvalidAddressError

if TYPE_CHECKING:
    from kortravelgeo.dto.region import RegionHint


def _lookup() -> AddressLookup:
    return AddressLookup(
        bd_mgt_sn="1123010700106200000000001",
        text="서울특별시 동대문구 왕산로 189-4",
        address_type="road",
        point=Point(x=127.04416880226447, y=37.579995940386155),
        si_nm="서울특별시",
        sgg_nm="동대문구",
        emd_nm="청량리동",
        road_nm="왕산로",
        detail="189-4",
        rncode_full="112303005001",
        bjd_cd="1123010700",
        adm_cd="1123070500",
        adm_nm="청량리동",
        zip_no="02559",
        pt_source="entrance",
        confidence=1.0,
    )


@dataclass(slots=True)
class RecordingGeocodeRepo:
    road_result: AddressLookup | None = None
    jibun_result: AddressLookup | None = None
    fuzzy_result: list[AddressLookup] = field(default_factory=list)
    last_road_parts: AddrParts | None = None
    last_jibun_parts: AddrParts | None = None
    last_fuzzy_parts: AddrParts | None = None
    last_region_hint: RegionHint | None = None

    async def lookup_by_road(
        self,
        parts: AddrParts,
        *,
        region_hint: RegionHint | None = None,
    ) -> AddressLookup | None:
        self.last_road_parts = parts
        self.last_region_hint = region_hint
        return self.road_result

    async def lookup_by_jibun(
        self,
        parts: AddrParts,
        *,
        region_hint: RegionHint | None = None,
    ) -> AddressLookup | None:
        self.last_jibun_parts = parts
        self.last_region_hint = region_hint
        return self.jibun_result

    async def fuzzy_roads(
        self,
        parts: AddrParts,
        *,
        limit: int = 5,
        region_hint: RegionHint | None = None,
    ) -> list[AddressLookup]:
        self.last_fuzzy_parts = parts
        self.last_region_hint = region_hint
        return self.fuzzy_result[:limit]

    async def lookup_sppn_area(self, point_5179: Point) -> SppnAreaLookup | None:
        _ = point_5179
        return None

    async def project_sppn_point_4326(self, point_5179: Point) -> Point | None:
        _ = point_5179
        return None


def test_normalize_spaces_folds_unicode_digits_dashes_and_separators() -> None:
    raw = (
        " \uC11C\uC6B8\uFF0C\uB3D9\uB300\uBB38\uAD6C  "
        "\uC655\uC0B0\uB85C \uFF11\uFF18\uFF19 \u2013 \uFF14 "
    )

    assert normalize_spaces(raw) == "서울 동대문구 왕산로 189-4"


@pytest.mark.parametrize(
    ("raw", "si", "sgg", "road", "mnnm", "slno"),
    [
        (
            "서울시 동대문구 왕산로\uFF11\uFF18\uFF19\uFF0D\uFF14 (청량리동)",
            "서울특별시",
            "동대문구",
            "왕산로",
            189,
            4,
        ),
        ("경기도 용인시 수지구 성복1로35", "경기도", "용인시 수지구", "성복1로", 35, 0),
        ("서울특별시 강남구 테헤란로1길 10", "서울특별시", "강남구", "테헤란로1길", 10, 0),
        ("서울 송파구 올림픽로35길 123-4", "서울특별시", "송파구", "올림픽로35길", 123, 4),
        ("Seoul 서울 동대문구 Wangsan-ro 왕산로 189-4", None, None, "왕산로", 189, 4),
        ("서울특별시 동대문구 왕산로 189번", "서울특별시", "동대문구", "왕산로", 189, 0),
    ],
)
def test_parse_road_variants_keep_exact_lookup_parts(
    raw: str,
    si: str | None,
    sgg: str | None,
    road: str,
    mnnm: int,
    slno: int,
) -> None:
    parts = parse_address(raw)

    assert parts.is_road is True
    assert parts.si == si
    assert parts.sgg == sgg
    assert parts.road == road
    assert parts.road_nrm == road.replace(" ", "")
    assert parts.mnnm == mnnm
    assert parts.slno == slno


@pytest.mark.parametrize("raw", ["올림픽로35길", "서울 송파구 올림픽로35길"])
def test_parse_road_name_only_does_not_consume_branch_road_number(raw: str) -> None:
    with pytest.raises(InvalidAddressError):
        parse_address(raw)


@pytest.mark.parametrize(
    ("raw", "is_road", "mnnm", "slno"),
    [
        # #339 regression: a unit/floor suffix (호/층) glued to the number with no
        # preceding space must not defeat the number match (was -> InvalidAddressError).
        ("왕산로 189호", True, 189, 0),
        ("왕산로 189-4호", True, 189, 4),
        ("역삼동 642-16호", False, 642, 16),
        ("역삼동 642-16층", False, 642, 16),
    ],
)
def test_parse_keeps_number_when_unit_suffix_is_glued(
    raw: str, is_road: bool, mnnm: int, slno: int
) -> None:
    parts = parse_address(raw)

    assert parts.is_road is is_road
    assert parts.mnnm == mnnm
    assert parts.slno == slno


@pytest.mark.parametrize(
    ("raw", "si", "sgg", "emd", "mntn_yn", "mnnm", "slno"),
    [
        ("강원도 춘천시 신북읍 산12 - 3번지", "강원특별자치도", "춘천시", "신북읍", "1", 12, 3),
        (
            "전라북도 전주시 완산구 효자동1가 123-4",
            "전북특별자치도",
            "전주시 완산구",
            "효자동1가",
            "0",
            123,
            4,
        ),
    ],
)
def test_parse_parcel_variants_normalize_old_province_names(
    raw: str,
    si: str,
    sgg: str,
    emd: str,
    mntn_yn: str,
    mnnm: int,
    slno: int,
) -> None:
    parts = parse_address(raw)

    assert parts.is_road is False
    assert parts.si == si
    assert parts.sgg == sgg
    assert parts.emd == emd
    assert parts.mntn_yn == mntn_yn
    assert parts.mnnm == mnnm
    assert parts.slno == slno


@pytest.mark.asyncio
async def test_geocode_sends_canonicalized_road_parts_to_repository() -> None:
    repo = RecordingGeocodeRepo(road_result=_lookup())

    response = await geocode(
        repo,
        GeocodeInput(address="서울시 동대문구 왕산로\uFF11\uFF18\uFF19\uFF0D\uFF14 (청량리동)"),
    )

    assert response.status == "OK"
    assert repo.last_road_parts is not None
    assert repo.last_road_parts.si == "서울특별시"
    assert repo.last_road_parts.road_nrm == "왕산로"
    assert repo.last_road_parts.mnnm == 189
    assert repo.last_road_parts.slno == 4
    assert repo.last_road_parts.detail == "청량리동"


@pytest.mark.asyncio
async def test_geocode_fuzzy_path_receives_number_parts_from_typo_variant() -> None:
    repo = RecordingGeocodeRepo(road_result=None, fuzzy_result=[_lookup()])

    response = await geocode(
        repo,
        GeocodeInput(address="서울시 동대문구 왕산길189 - 4"),
    )

    assert response.status == "OK"
    assert repo.last_fuzzy_parts is not None
    assert repo.last_fuzzy_parts.road_nrm == "왕산길"
    assert repo.last_fuzzy_parts.mnnm == 189
    assert repo.last_fuzzy_parts.slno == 4


# T-317: "태평로1가"처럼 숫자+"가"로 끝나는 법정동 토큰을 도로명("태평로") + 건물번호(1)로
# 읽던 버그. 아래 동 이름은 운영 tl_scco_emd의 "…로N가" 법정동(전국 80여 개)에서 골랐다.
@pytest.mark.parametrize(
    ("raw", "si", "sgg", "emd", "mntn_yn", "mnnm", "slno"),
    [
        ("서울특별시 중구 태평로1가 31", "서울특별시", "중구", "태평로1가", "0", 31, 0),
        ("서울 종로구 종로1가 1", "서울특별시", "종로구", "종로1가", "0", 1, 0),
        ("서울특별시 중구 을지로2가 199-10", "서울특별시", "중구", "을지로2가", "0", 199, 10),
        ("서울특별시 중구 충무로1가 21-1", "서울특별시", "중구", "충무로1가", "0", 21, 1),
        ("서울특별시 중구 남대문로5가 1-1", "서울특별시", "중구", "남대문로5가", "0", 1, 1),
        ("서울특별시 용산구 한강로3가 40-407", "서울특별시", "용산구", "한강로3가", "0", 40, 407),
        ("대구광역시 중구 동성로2가 88-1", "대구광역시", "중구", "동성로2가", "0", 88, 1),
        ("광주광역시 동구 금남로1가 1", "광주광역시", "동구", "금남로1가", "0", 1, 0),
        (
            "경기도 수원시 팔달구 매산로1가 114-2",
            "경기도",
            "수원시 팔달구",
            "매산로1가",
            "0",
            114,
            2,
        ),
        ("강원도 춘천시 중앙로1가 2-5", "강원특별자치도", "춘천시", "중앙로1가", "0", 2, 5),
        ("서울특별시 중구 태평로1가 산 1", "서울특별시", "중구", "태평로1가", "1", 1, 0),
        ("서울특별시 중구 태평로1가 31-2번지", "서울특별시", "중구", "태평로1가", "0", 31, 2),
        ("태평로1가 31", None, None, "태평로1가", "0", 31, 0),
        # "…로"로 끝나지 않는 "N가" 법정동은 원래도 지번으로 읽혔다(회귀 가드).
        ("서울특별시 중구 명동2가 1", "서울특별시", "중구", "명동2가", "0", 1, 0),
        ("서울특별시 중구 회현동1가 1", "서울특별시", "중구", "회현동1가", "0", 1, 0),
        ("경기도 성남시 분당구 삼평동 681", "경기도", "성남시 분당구", "삼평동", "0", 681, 0),
    ],
)
def test_parse_legal_dong_ga_token_is_parcel_address(
    raw: str,
    si: str | None,
    sgg: str | None,
    emd: str,
    mntn_yn: str,
    mnnm: int,
    slno: int,
) -> None:
    parts = parse_address(raw)

    assert parts.is_road is False
    assert parts.road is None
    assert parts.road_nrm is None
    assert parts.si == si
    assert parts.sgg == sgg
    assert parts.emd == emd
    assert parts.mntn_yn == mntn_yn
    assert parts.mnnm == mnnm
    assert parts.slno == slno
    assert parts.detail is None


def test_parse_legal_dong_ga_token_keeps_trailing_detail() -> None:
    parts = parse_address("서울 종로구 종로1가 1 교보빌딩")

    assert parts.is_road is False
    assert parts.emd == "종로1가"
    assert parts.mnnm == 1
    assert parts.detail == "교보빌딩"


@pytest.mark.parametrize(
    ("raw", "road", "mnnm", "slno", "under"),
    [
        ("서울특별시 중구 태평로1가 세종대로 110", "세종대로", 110, 0, False),
        ("서울특별시 용산구 한강로3가 이촌로37길 19-1", "이촌로37길", 19, 1, False),
        ("강원특별자치도 춘천시 중앙로1가 중앙로 지하 35", "중앙로", 35, 0, True),
        ("서울 종로구 종로1가 종로 1", "종로", 1, 0, False),
    ],
)
def test_parse_road_address_after_legal_dong_ga_token(
    raw: str,
    road: str,
    mnnm: int,
    slno: int,
    under: bool,
) -> None:
    parts = parse_address(raw)

    assert parts.is_road is True
    assert parts.road == road
    assert parts.road_nrm == road
    assert parts.mnnm == mnnm
    assert parts.slno == slno
    assert parts.under is under
    assert parts.detail is None


@pytest.mark.parametrize(
    "raw", ["태평로1가", "서울 종로구 종로1가", "서울특별시 중구 을지로2가", "효자동1가"]
)
def test_parse_legal_dong_ga_only_has_no_address_number(raw: str) -> None:
    # 동 이름 속 숫자는 건물번호·지번이 아니다("올림픽로35길"만 입력한 경우와 같은 취급).
    with pytest.raises(InvalidAddressError):
        parse_address(raw)


@pytest.mark.parametrize(
    ("raw", "si", "sgg", "road", "mnnm", "slno", "under", "detail"),
    [
        ("서울특별시 중구 세종대로 110", "서울특별시", "중구", "세종대로", 110, 0, False, None),
        ("테헤란로 152", None, None, "테헤란로", 152, 0, False, None),
        ("강남대로94길 20", None, None, "강남대로94길", 20, 0, False, None),
        ("서울 종로구 종로 1", "서울특별시", "종로구", "종로", 1, 0, False, None),
        ("종로33길 15", None, None, "종로33길", 15, 0, False, None),
        ("서울특별시 중구 세종대로 지하 2", "서울특별시", "중구", "세종대로", 2, 0, True, None),
        ("서울 중구 을지로 지하 1", "서울특별시", "중구", "을지로", 1, 0, True, None),
        ("서울 중구 을지로 100-3", "서울특별시", "중구", "을지로", 100, 3, False, None),
        (
            "서울특별시 중구 세종대로 110 (태평로1가)",
            "서울특별시",
            "중구",
            "세종대로",
            110,
            0,
            False,
            "태평로1가",
        ),
    ],
)
def test_parse_road_addresses_are_unchanged_by_legal_dong_ga_rule(
    raw: str,
    si: str | None,
    sgg: str | None,
    road: str,
    mnnm: int,
    slno: int,
    under: bool,
    detail: str | None,
) -> None:
    parts = parse_address(raw)

    assert parts.is_road is True
    assert parts.si == si
    assert parts.sgg == sgg
    assert parts.road == road
    assert parts.mnnm == mnnm
    assert parts.slno == slno
    assert parts.under is under
    assert parts.detail == detail


def test_parse_spaced_branch_road_number_is_not_consumed_as_building_number() -> None:
    # "종로 33길 15"처럼 가지번호 앞에 공백이 있어도 33을 건물번호로 먹지 않는다(기존 동작 유지).
    parts = parse_address("종로 33길 15")

    assert parts.is_road is True
    assert parts.mnnm == 15
    assert parts.slno == 0


@pytest.mark.asyncio
async def test_geocode_parcel_sends_legal_dong_ga_parts_to_jibun_lookup() -> None:
    repo = RecordingGeocodeRepo(jibun_result=_lookup())

    response = await geocode(
        repo,
        GeocodeInput(address="서울특별시 중구 태평로1가 31", type="parcel"),
    )

    assert response.status == "OK"
    assert repo.last_road_parts is None
    assert repo.last_jibun_parts is not None
    assert repo.last_jibun_parts.si == "서울특별시"
    assert repo.last_jibun_parts.sgg == "중구"
    assert repo.last_jibun_parts.emd == "태평로1가"
    assert repo.last_jibun_parts.mntn_yn == "0"
    assert repo.last_jibun_parts.mnnm == 31
    assert repo.last_jibun_parts.slno == 0


@pytest.mark.asyncio
async def test_geocode_road_type_does_not_fall_back_to_parcel_for_jibun_text() -> None:
    # v1(vworld 호환)은 명시 type을 그대로 따른다. road type에 지번 문자열이 오면 parcel로
    # 바꾸지 않고 NOT_FOUND다(자유 텍스트 dispatch는 v2 client 몫).
    repo = RecordingGeocodeRepo(jibun_result=_lookup())

    response = await geocode(repo, GeocodeInput(address="서울특별시 중구 태평로1가 31"))

    assert response.status == "NOT_FOUND"
    assert repo.last_jibun_parts is None
    assert repo.last_road_parts is not None
    assert repo.last_road_parts.road_nrm is None


# T-320: 지번 번지는 읍면동·리 바로 다음 토큰이다. 마지막 숫자를 번지로 잡던 parser는 뒤따르는
# 호수·층·동 번호를 번지로 읽어 운영에서 "상계동 1234 … 1203호"가 1203번지(노원검문소)로 OK됐다.
@pytest.mark.parametrize(
    ("raw", "region", "mntn_yn", "mnnm", "slno", "detail"),
    [
        (
            "서울특별시 노원구 상계동 1234 주공아파트 101동 1203호",
            "상계동",
            "0",
            1234,
            0,
            "주공아파트 101동 1203호",
        ),
        ("경기도 성남시 분당구 삼평동 681 101호", "삼평동", "0", 681, 0, "101호"),
        ("서울특별시 강남구 역삼동 737 2층", "역삼동", "0", 737, 0, "2층"),
        ("서울특별시 강남구 역삼동 737번지 2층", "역삼동", "0", 737, 0, "2층"),
        ("서울특별시 강남구 역삼동 737-1번지", "역삼동", "0", 737, 1, None),
        ("서울특별시 강남구 역삼동 737 외 2필지", "역삼동", "0", 737, 0, "외 2필지"),
        (
            "서울특별시 송파구 신천동 29 롯데월드타워 123층",
            "신천동",
            "0",
            29,
            0,
            "롯데월드타워 123층",
        ),
        ("서울특별시 강남구 삼성동 159 코엑스", "삼성동", "0", 159, 0, "코엑스"),
        ("강원특별자치도 춘천시 신북읍 산 12-3", "신북읍", "1", 12, 3, None),
        ("강원특별자치도 춘천시 신북읍 산12-3 번지", "신북읍", "1", 12, 3, None),
        # 번지 자리의 12-3이 먼저다(뒤의 "산 12-3"은 detail).
        ("강원특별자치도 춘천시 신북읍 12-3 산 12-3", "신북읍", "0", 12, 3, "산 12-3"),
        (
            "서울특별시 중구 을지로2가 199-40 (을지로2가)",
            "을지로2가",
            "0",
            199,
            40,
            "을지로2가",
        ),
        ("서울특별시 중구 태평로1가 31 서울신문사", "태평로1가", "0", 31, 0, "서울신문사"),
        ("경기도 양평군 양평읍 양근리 123 번지", "양근리", "0", 123, 0, None),
        ("제주특별자치도 제주시 애월읍 하귀1리 123", "하귀1리", "0", 123, 0, None),
        ("세종특별자치시 조치원읍 신흥리 123 101호", "신흥리", "0", 123, 0, "101호"),
        # #339: 번호에 붙은 호/층 접미사(옛 "642번지 16호" 표기)는 번지 토큰으로 인정한다.
        ("서울특별시 강남구 역삼동 642-16호", "역삼동", "0", 642, 16, "호"),
        ("역삼동 642-16층", "역삼동", "0", 642, 16, "층"),
        # 번지 뒤에 붙은 문장부호·글자는 detail이다 — T-317(main)과 같은 결과(T-320 리뷰 회귀).
        ("서울특별시 강남구 역삼동 737.", "역삼동", "0", 737, 0, "."),
        ("서울특별시 강남구 역삼동 737번지.", "역삼동", "0", 737, 0, "."),
        ("서울특별시 강남구 역삼동 737-1.", "역삼동", "0", 737, 1, "."),
        ("서울특별시 강남구 역삼동 737-", "역삼동", "0", 737, 0, "-"),
        ("서울특별시 강남구 역삼동 737:", "역삼동", "0", 737, 0, ":"),
        ("서울특별시 강남구 역삼동 737)", "역삼동", "0", 737, 0, ")"),
        ("서울특별시 강남구 역삼동 '737'", "역삼동", "0", 737, 0, "'"),
        ("서울특별시 강남구 역삼동 \u2018737\u2019", "역삼동", "0", 737, 0, "\u2019"),
        ("서울특별시 강남구 역삼동 737B", "역삼동", "0", 737, 0, "B"),
        ("서울특별시 강남구 역삼동 737앞", "역삼동", "0", 737, 0, "앞"),
        ("서울특별시 강남구 역삼동 737번지일원", "역삼동", "0", 737, 0, "일원"),
        ("경기도 양평군 양평읍 양근리 산1-1번지일원", "양근리", "1", 1, 1, "일원"),
        ("경기도 양평군 양평읍 양근리 123일대", "양근리", "0", 123, 0, "일대"),
        # main은 마지막 번호(738·1)를 번지로 읽었다 — 첫 번지가 읍면동 바로 다음 토큰이다.
        ("서울특별시 강남구 역삼동 737·738", "역삼동", "0", 737, 0, "·738"),
        ("서울특별시 강남구 역삼동 737의1", "역삼동", "0", 737, 0, "의1"),
    ],
)
def test_parse_jibun_lot_is_first_token_after_region(
    raw: str,
    region: str,
    mntn_yn: str,
    mnnm: int,
    slno: int,
    detail: str | None,
) -> None:
    parts = parse_address(raw)

    assert parts.is_road is False
    assert (parts.li or parts.emd) == region
    assert (parts.mntn_yn, parts.mnnm, parts.slno) == (mntn_yn, mnnm, slno)
    assert parts.detail == detail


@pytest.mark.parametrize(
    "raw",
    [
        # 읍면동 바로 다음이 번지가 아니다 — 뒤에 나오는 층·출구·건물 번호는 번지가 아니다.
        "서울특별시 강남구 역삼동 스타벅스 2층",
        "경기도 성남시 분당구 삼평동 판교역 1번출구",
        "서울특별시 송파구 신천동 롯데월드타워 123",
        "서울특별시 노원구 상계동 101동 1203호",
        "경기도 성남시 분당구 삼평동 3번출구",
        "경기도 성남시 분당구 삼평동 3번 출구",
        "서울특별시 강남구 역삼동 737번지2층",
        "서울특별시 강남구 역삼동 737-1동",
        "서울특별시 강남구 역삼동 3통 2반",
        # 본번에 바로 붙은 호/층은 번지를 빠뜨린 호수·층이다(부번까지 적은 "642-16호"만 번지).
        "서울특별시 노원구 상계동 1203호",
        "서울특별시 강남구 역삼동 2층",
        "서울특별시 강남구 역삼동 지하1층",
        # 행정동·리 이름 속 숫자는 번지가 아니다.
        "서울특별시 관악구 신림1동",
        "부산광역시 강서구 대저1동",
        "서울특별시 동작구 상도1동",
        "제주특별자치도 제주시 애월읍 하귀1리",
        "경상남도 남해군 창선면 창선2리",
        "신림1동",
        "세종특별자치시 조치원읍 신흥리",
    ],
)
def test_parse_jibun_without_lot_right_after_region_has_no_address_number(raw: str) -> None:
    # "서울특별시 관악구 신림동"(번호 없음)과 같은 취급 — 엉뚱한 번지로 lookup하지 않는다.
    with pytest.raises(InvalidAddressError):
        parse_address(raw)


@pytest.mark.parametrize(
    ("raw", "mnnm"),
    [
        # 읍면동·리 anchor가 없으면 번지 자리를 정할 수 없어 기존처럼 마지막 번호를 쓴다.
        ("코엑스 123", 123),
        ("롯데월드타워 123층", 123),
        ("강남역 3번 출구", 3),
        ("서울특별시 강남구 123", 123),
        ("삼평동681", 681),
    ],
)
def test_parse_anchorless_jibun_keeps_last_number(raw: str, mnnm: int) -> None:
    parts = parse_address(raw)

    assert parts.is_road is False
    assert parts.emd is None
    assert parts.li is None
    assert parts.mnnm == mnnm


@pytest.mark.parametrize(
    ("raw", "emd", "li"),
    [
        ("세종특별자치시 조치원읍 신흥리 123", "조치원읍", "신흥리"),
        ("세종 조치원읍 신흥리 123", "조치원읍", "신흥리"),
        ("세종시 전의면 신흥리 123", "전의면", "신흥리"),
        ("세종특별자치시 한솔동 123", "한솔동", None),
    ],
)
def test_parse_sejong_jibun_has_no_sgg(raw: str, emd: str, li: str | None) -> None:
    # 세종특별자치시는 시군구가 없다(MV sgg_nm NULL) — 시도 바로 아래가 읍면동이다.
    parts = parse_address(raw)

    assert parts.is_road is False
    assert parts.si == "세종특별자치시"
    assert parts.sgg is None
    assert parts.sido_without_sgg is True
    assert (parts.emd, parts.li, parts.mnnm) == (emd, li, 123)


@pytest.mark.parametrize(
    "raw",
    [
        "서울특별시 태평로1가 31",  # 시군구를 빠뜨린 입력 — 시군구가 없는 시도가 아니다
        "경기도 성남시 분당구 삼평동 681",
        "삼평동 681",
        "세종특별자치시 세종시 조치원읍 신흥리 123",  # 시군구 토큰이 있다
    ],
)
def test_sido_without_sgg_is_only_sejong_without_sgg(raw: str) -> None:
    assert parse_address(raw).sido_without_sgg is False


@pytest.mark.asyncio
async def test_geocode_parcel_uses_lot_right_after_region_not_trailing_unit() -> None:
    # v1 type=parcel도 parse_address를 그대로 쓴다 — 1203호가 아니라 1234번지로 lookup한다.
    repo = RecordingGeocodeRepo(jibun_result=_lookup())

    response = await geocode(
        repo,
        GeocodeInput(
            address="서울특별시 노원구 상계동 1234 주공아파트 101동 1203호", type="parcel"
        ),
    )

    assert response.status == "OK"
    assert repo.last_jibun_parts is not None
    assert repo.last_jibun_parts.emd == "상계동"
    assert (repo.last_jibun_parts.mnnm, repo.last_jibun_parts.slno) == (1234, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("address", "lot"),
    [
        ("서울특별시 강남구 역삼동 737.", ("0", 737, 0)),
        ("서울특별시 강남구 역삼동 737번지.", ("0", 737, 0)),
        ("경기도 양평군 양평읍 양근리 산1-1번지일원", ("1", 1, 1)),
    ],
)
async def test_geocode_parcel_lot_with_glued_suffix_reaches_jibun_lookup(
    address: str, lot: tuple[str, int, int]
) -> None:
    # T-320 리뷰: 번지 뒤 문장부호·글자 때문에 파싱 불가(v1 400)로 떨어지지 않고 main처럼
    # 지번 lookup에 닿는다.
    repo = RecordingGeocodeRepo(jibun_result=_lookup())

    response = await geocode(repo, GeocodeInput(address=address, type="parcel"))

    assert response.status == "OK"
    assert repo.last_jibun_parts is not None
    parts = repo.last_jibun_parts
    assert (parts.mntn_yn, parts.mnnm, parts.slno) == lot


@pytest.mark.asyncio
@pytest.mark.parametrize("address_type", ["road", "parcel"])
async def test_geocode_dong_name_digit_is_not_a_lot(
    address_type: Literal["road", "parcel"],
) -> None:
    # "신림1동"의 1을 번지로 읽어 lookup하지 않는다(번호 없는 주소 — InvalidAddressError).
    repo = RecordingGeocodeRepo(jibun_result=_lookup())

    with pytest.raises(InvalidAddressError):
        await geocode(
            repo,
            GeocodeInput(address="서울특별시 관악구 신림1동", type=address_type),
        )
    assert repo.last_jibun_parts is None
    assert repo.last_road_parts is None


@pytest.mark.asyncio
async def test_zipcode_by_jibun_address_uses_lot_right_after_region() -> None:
    from kortravelgeo.core.protocols import ZipLookup
    from kortravelgeo.core.zipcoder import zipcode
    from kortravelgeo.dto.zipcode import ZipcodeInput

    seen: list[AddrParts] = []

    class RecordingZipRepo:
        async def lookup_zipcode_by_address(
            self, parts: AddrParts, *, include_bulk: bool
        ) -> list[ZipLookup]:
            seen.append(parts)
            return [ZipLookup(zip_no="01234", source="building_bsi_zon_no")]

    response = await zipcode(
        RecordingZipRepo(),  # type: ignore[arg-type]
        ZipcodeInput(address="서울특별시 노원구 상계동 1234 주공아파트 101동 1203호"),
    )

    assert response.status == "OK"
    assert [(parts.emd, parts.road_nrm, parts.mnnm) for parts in seen] == [("상계동", None, 1234)]


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["서울특별시 관악구 신림1동", "서울특별시 관악구 신림동"])
@pytest.mark.parametrize("address_type", ["road", "parcel"])
async def test_v1_geocode_dong_name_digit_answers_like_address_without_number(
    address: str, address_type: str
) -> None:
    # T-320: "신림1동"은 번호 없는 "신림동"과 같은 VWorld 입력 오류다(이전: 1번지로 lookup).
    import httpx

    from kortravelgeo.api.app import create_app
    from kortravelgeo.api.deps import get_client
    from kortravelgeo.api.public_api_key import require_public_api_key
    from kortravelgeo.client import AsyncAddressClient
    from kortravelgeo.settings import Settings

    app = create_app()
    app.dependency_overrides[get_client] = lambda: AsyncAddressClient(
        engine=object(),  # type: ignore[arg-type]  # SQL에 닿으면 AttributeError
        settings=Settings(_env_file=None, cache_enabled=False),
    )
    app.dependency_overrides[require_public_api_key] = lambda: None
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/address/geocode", params={"address": address, "type": address_type}
        )

    assert response.status_code == 400
    error = response.json()["response"]
    assert error["status"] == "ERROR"
    assert error["error"]["code"] == "INVALID_TYPE"
    assert error["error"]["text"] == "address number could not be parsed"
