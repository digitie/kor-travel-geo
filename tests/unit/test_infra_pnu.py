import pytest

from kraddr.geo.infra.pnu import build_pnu, pnu_land_type_from_mntn_yn


@pytest.mark.parametrize(
    ("raw_mntn_yn", "expected"),
    [
        ("0", "1"),
        ("1", "2"),
        (0, "1"),
        (1, "2"),
        (" 0 ", "1"),
        (" 1 ", "2"),
    ],
)
def test_pnu_land_type_maps_source_mountain_flag_to_standard_code(
    raw_mntn_yn: object, expected: str
) -> None:
    assert pnu_land_type_from_mntn_yn(raw_mntn_yn) == expected


@pytest.mark.parametrize("raw_mntn_yn", ["", "2", "Y", "N", None])
def test_pnu_land_type_rejects_non_source_values(raw_mntn_yn: object) -> None:
    with pytest.raises(ValueError, match="mntn_yn"):
        pnu_land_type_from_mntn_yn(raw_mntn_yn)


def test_build_pnu_for_normal_land_pads_lot_numbers() -> None:
    assert (
        build_pnu(
            bjd_cd="1168010100",
            raw_mntn_yn="0",
            lnbr_mnnm=12,
            lnbr_slno=3,
        )
        == "1168010100100120003"
    )


def test_build_pnu_for_mountain_land_uses_land_type_two() -> None:
    assert (
        build_pnu(
            bjd_cd="4887034021",
            raw_mntn_yn="1",
            lnbr_mnnm="7",
            lnbr_slno="0",
        )
        == "4887034021200070000"
    )


@pytest.mark.parametrize("bjd_cd", ["116801010", "11680101000", "11680101AA"])
def test_build_pnu_rejects_invalid_legal_dong_code(bjd_cd: str) -> None:
    with pytest.raises(ValueError, match="bjd_cd"):
        build_pnu(bjd_cd=bjd_cd, raw_mntn_yn="0", lnbr_mnnm=1)


@pytest.mark.parametrize(
    ("field_name", "lnbr_mnnm", "lnbr_slno"),
    [
        ("lnbr_mnnm", 0, 0),
        ("lnbr_mnnm", 10000, 0),
        ("lnbr_mnnm", "12A", 0),
        ("lnbr_slno", 1, 10000),
        ("lnbr_slno", 1, "A"),
    ],
)
def test_build_pnu_rejects_invalid_lot_numbers(
    field_name: str, lnbr_mnnm: object, lnbr_slno: object
) -> None:
    with pytest.raises(ValueError, match=field_name):
        build_pnu(
            bjd_cd="1168010100",
            raw_mntn_yn="0",
            lnbr_mnnm=lnbr_mnnm,
            lnbr_slno=lnbr_slno,
        )
