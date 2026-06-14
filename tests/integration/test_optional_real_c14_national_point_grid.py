from __future__ import annotations

import os
from pathlib import Path

import pytest

from kortravelgeo.loaders.c14_national_point_grid import compare_c14_national_point_grid

DATA_ROOTS = (
    Path("data/juso"),
    Path("/mnt/f/dev/kor-travel-geo/data/juso"),
    Path("/home/digitie/kor-travel-geo-data/juso"),
)


def test_real_c14_national_point_grid_sample_when_enabled() -> None:
    if os.getenv("KTG_SLOW_REAL_DATA") != "1":
        pytest.skip("set KTG_SLOW_REAL_DATA=1 to run C14 real-data ZIP smoke")

    grid_zip = _require(
        "국가지점번호 도형/202405/국가지점번호도형_5월분.zip",
        "국가지점번호 도형/국가지점번호도형_5월분.zip",
    )
    center_zip = _require(
        "국가지점번호 중심점/202405/국가지점번호중심점_5월분.zip",
        "국가지점번호 중심점/국가지점번호중심점_5월분.zip",
    )

    comparison = compare_c14_national_point_grid(
        grid_zip,
        center_zip,
        source_yyyymm="202405",
        row_limit_per_layer=3,
        center_row_limit=100,
        sample_limit=3,
    )

    assert len(comparison.layer_validations) == 4
    assert comparison.layer_validations[3].row_count > 10_000_000
    assert all(layer.checked_count == 3 for layer in comparison.layer_validations)
    assert comparison.center_validation.checked_count == 100
    assert comparison.center_validation.invalid_row_count == 0
    assert comparison.metrics()["coverage_count_basis"] == "limited_sample"
    assert comparison.metrics()["serving_promotion"] is False


def _require(*relatives: str) -> Path:
    for root in DATA_ROOTS:
        for relative in relatives:
            candidate = root / relative
            if candidate.exists():
                return candidate
    pytest.skip("actual juso data not available for C14 optional smoke")
