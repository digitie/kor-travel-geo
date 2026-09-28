from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
