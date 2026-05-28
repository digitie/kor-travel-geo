from __future__ import annotations

import pytest
from pydantic import ValidationError

from kraddr.geo.dto.region import RegionHint, region_params


def test_region_hint_accepts_sido_sigungu_and_bjd_prefixes() -> None:
    assert RegionHint(sig_cd="11").sql_params() == {
        "sig_cd_filter": None,
        "sig_cd_prefix": "11%",
        "bjd_cd_filter": None,
        "bjd_cd_prefix": None,
    }
    assert RegionHint(sig_cd="11110").sql_params()["sig_cd_filter"] == "11110"
    assert RegionHint(bjd_cd="11110101").sql_params()["bjd_cd_prefix"] == "11110101%"
    assert RegionHint(bjd_cd="1111010100").sql_params()["bjd_cd_filter"] == "1111010100"


def test_region_hint_rejects_ambiguous_code_lengths() -> None:
    with pytest.raises(ValidationError):
        RegionHint(sig_cd="111")
    with pytest.raises(ValidationError):
        RegionHint(bjd_cd="111101")


def test_empty_region_params_are_complete_for_sql_binds() -> None:
    assert region_params(None) == {
        "sig_cd_filter": None,
        "sig_cd_prefix": None,
        "bjd_cd_filter": None,
        "bjd_cd_prefix": None,
    }
