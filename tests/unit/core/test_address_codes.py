from __future__ import annotations

import pytest

from kortravelgeo.core.address import (
    AddressCodeSet,
    LegalDongCode,
    RoadNameAddressCode,
    RoadNameCode,
    SigunguCode,
    address_code_set_from_mapping,
    legal_dong_code_from_mapping,
    normalize_building_number,
    normalize_underground_flag,
    road_name_address_code_from_mapping,
)


def test_sigungu_code_exposes_parent_legal_dong_code() -> None:
    code = SigunguCode(code="11-110")

    assert code.code == "11110"
    assert code.sido_code == "11"
    assert code.sigungu_part == "110"
    assert code.legal_dong_code == LegalDongCode(code="1111000000")
    assert code.to_orm_dict() == {
        "sido_code": "11",
        "sigungu_code": "11110",
        "legal_dong_code": "1111000000",
    }


def test_legal_dong_code_hierarchy_helpers() -> None:
    code = LegalDongCode(code="11-110-119-00")

    assert code.code == "1111011900"
    assert code.sigungu_code == "11110"
    assert code.eup_myeon_dong_code == "11110119"
    assert code.ri_part == "00"
    assert code.is_eup_myeon_dong_level
    assert code.parent_code == LegalDongCode(code="1111000000")
    assert code.to_sigungu_code() == SigunguCode(code="11110")


def test_legal_dong_code_builds_from_parts_and_tracks_ancestors() -> None:
    sido = LegalDongCode.from_parts(sido="11")
    sigungu = LegalDongCode.from_parts(sido="11", sigungu="110")
    emd = LegalDongCode.from_parts(sido="11", sigungu="110", eup_myeon_dong="119")
    ri = LegalDongCode.from_parts(
        sido="11",
        sigungu="110",
        eup_myeon_dong="119",
        ri="01",
    )

    assert str(sido) == "1100000000"
    assert sigungu.is_descendant_of(sido)
    assert emd.is_descendant_of(sigungu)
    assert ri.is_descendant_of(emd)
    assert ri.ancestors(include_self=True) == (sido, sigungu, emd, ri)


def test_road_name_code_composes_from_sigungu_and_road_number() -> None:
    code = RoadNameCode.from_parts(sigungu_code="36110", road_number="3258085")

    assert code.code == "361103258085"
    assert code.sigungu_code == "36110"
    assert code.road_number == "3258085"
    assert code.to_orm_dict()["road_name_number"] == "3258085"


def test_road_name_address_code_composes_juso_query_components() -> None:
    code = RoadNameAddressCode.from_components(
        adm_cd="3611011000",
        rn_mgt_sn="361103258085",
        udrt_yn="0",
        buld_mnnm="572",
        buld_slno="0",
    )

    assert code.code == "36110110325808500057200000"
    assert code.legal_dong_code == LegalDongCode(code="3611011000")
    assert code.road_name_code == RoadNameCode(code="361103258085")
    assert code.building_main_number == 572
    assert code.building_sub_number == 0
    assert code.to_juso_query_dict() == {
        "admCd": "3611011000",
        "rnMgtSn": "361103258085",
        "udrtYn": "0",
        "buldMnnm": "572",
        "buldSlno": "0",
    }


def test_address_code_set_derives_related_codes_from_provider_mapping() -> None:
    codes = address_code_set_from_mapping(
        {
            "admCd": "3611011000",
            "rnMgtSn": "361103258085",
            "udrtYn": "0",
            "buldMnnm": "572",
            "buldSlno": "0",
            "bdMgtSn": "3611011000100000000000000",
        }
    )

    assert codes.has_any_code
    assert codes.legal_dong_code == LegalDongCode(code="3611011000")
    assert codes.road_name_code == RoadNameCode(code="361103258085")
    assert codes.road_name_address_code == RoadNameAddressCode(
        code="36110110325808500057200000"
    )
    assert codes.to_orm_dict() == {
        "sigungu_code": "36110",
        "legal_dong_code": "3611011000",
        "road_name_code": "361103258085",
        "road_name_address_code": "36110110325808500057200000",
        "building_management_number": "3611011000100000000000000",
    }


def test_mapping_helpers_return_none_for_absent_optional_codes() -> None:
    assert legal_dong_code_from_mapping({}) is None
    assert road_name_address_code_from_mapping({}) is None
    assert AddressCodeSet.from_mapping({}).has_any_code is False


def test_address_code_set_accepts_partial_inputs() -> None:
    only_legal = AddressCodeSet.from_mapping({"ADM_CD": "1111011900"})
    only_road = AddressCodeSet.from_mapping({"rnMgtSn": "111103005028"})
    only_sigungu = AddressCodeSet.from_mapping({"sigungu_code": "11110"})

    assert only_legal.sigungu_code == SigunguCode(code="11110")
    assert only_legal.legal_dong_code == LegalDongCode(code="1111011900")
    assert only_legal.road_name_address_code is None
    assert only_road.sigungu_code == SigunguCode(code="11110")
    assert only_road.road_name_code == RoadNameCode(code="111103005028")
    assert only_road.road_name_address_code is None
    assert only_sigungu.sigungu_code == SigunguCode(code="11110")
    assert only_sigungu.legal_dong_code is None


def test_address_code_validation_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        LegalDongCode(code="111")
    with pytest.raises(ValueError):
        RoadNameAddressCode.from_components(
            adm_cd="1111011900",
            rn_mgt_sn="361103258085",
            udrt_yn="0",
            buld_mnnm="1",
        )
    with pytest.raises(ValueError):
        normalize_underground_flag("2")
    with pytest.raises(ValueError):
        normalize_building_number("100000")
