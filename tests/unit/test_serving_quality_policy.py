from __future__ import annotations

import pytest

from kortravelgeo.loaders.consistency import _severity


@pytest.mark.parametrize("code", ["C2", "C4", "C6", "C7"])
def test_quarantining_some_records_does_not_waive_remaining_serving_errors(code):
    assert (
        _severity(code, count=5, ratio=0.1, metric={"quarantined_count": 4.0, "error_count": 1.0})
        == "ERROR"
    )


@pytest.mark.parametrize("code", ["C2", "C4", "C6", "C7"])
def test_preserved_but_unserved_source_violations_remain_visible_as_warning(code):
    assert (
        _severity(code, count=4, ratio=0.1, metric={"quarantined_count": 4.0, "error_count": 0.0})
        == "WARN"
    )
