"""T-242 restore-drill pure policy: throwaway DB naming, serving-DB guard, PASS/FAIL.

The live restore-into-throwaway-DB → reconcile → drop path needs a real cluster and is
integration-tested in T-244. These cover the device/DB-independent pieces: the deterministic
throwaway name (63-char safe), the guard that forbids drilling into the serving DB, and the
PASS/FAIL classification (reconcile FAIL → FAIL → non-zero CLI exit).
"""

from __future__ import annotations

import pytest

from kortravelgeo.exceptions import InvalidInputError
from kortravelgeo.infra.restore_drill import (
    classify_drill_outcome,
    guard_drill_target,
    restore_drill_target_name,
)


def test_target_name_has_restoretest_marker() -> None:
    name = restore_drill_target_name("kor_travel_geo", "20260616T120000Z")
    assert name == "kor_travel_geo_restoretest_20260616T120000Z"


def test_target_name_truncated_within_63_chars() -> None:
    name = restore_drill_target_name("a" * 80, "20260616T120000Z")
    assert len(name) == 63
    assert name.endswith("_restoretest_20260616T120000Z")


def test_guard_rejects_current_serving_database() -> None:
    with pytest.raises(InvalidInputError, match="must differ from the current serving"):
        guard_drill_target("kor_travel_geo", "kor_travel_geo")


def test_guard_allows_distinct_throwaway_and_none_current() -> None:
    # different name → ok; unknown current (None) → ok (nothing to collide with)
    guard_drill_target("kor_travel_geo_restoretest_x", "kor_travel_geo")
    guard_drill_target("anything", None)


def test_classify_pass_when_restored_and_no_failures() -> None:
    assert classify_drill_outcome(restored=True, reconcile_ok=True, smoke_ok=True) == "PASS"
    # None = not evaluated (legacy manifest / no manifest) is not itself a failure
    assert classify_drill_outcome(restored=True, reconcile_ok=None, smoke_ok=True) == "PASS"
    assert classify_drill_outcome(restored=True, reconcile_ok=True, smoke_ok=None) == "PASS"


def test_classify_fail_on_reconcile_or_smoke_or_no_restore() -> None:
    assert classify_drill_outcome(restored=True, reconcile_ok=False, smoke_ok=True) == "FAIL"
    assert classify_drill_outcome(restored=True, reconcile_ok=True, smoke_ok=False) == "FAIL"
    assert classify_drill_outcome(restored=False, reconcile_ok=None, smoke_ok=None) == "FAIL"
