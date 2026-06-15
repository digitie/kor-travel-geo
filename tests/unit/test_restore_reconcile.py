"""T-233 post-restore row-count reconcile policy (pure).

``diff_restore_row_counts`` compares manifest expected counts to the restored DB's
actual counts per ``ROW_COUNT_OBJECTS``. An unknown ``expected`` (legacy backup or a
restored DB missing the object) is treated as "not a mismatch" so legacy restores
degrade gracefully; a present-but-different count is a mismatch.
"""

from __future__ import annotations

from kortravelgeo.infra.backup import ROW_COUNT_OBJECTS
from kortravelgeo.infra.restore_reconcile import diff_restore_row_counts


def _full(value: int) -> dict[str, int]:
    return dict.fromkeys(ROW_COUNT_OBJECTS, value)


def test_all_matching_counts_pass() -> None:
    expected = _full(100)
    actual = _full(100)
    diffs = diff_restore_row_counts(expected, actual)
    assert len(diffs) == len(ROW_COUNT_OBJECTS)
    assert all(d.match for d in diffs)


def test_single_mismatch_is_flagged() -> None:
    expected = _full(100)
    actual = _full(100)
    target = ROW_COUNT_OBJECTS[0]
    actual[target] = 99  # one row missing → silent partial restore signal
    diffs = {d.object: d for d in diff_restore_row_counts(expected, actual)}
    assert diffs[target].match is False
    assert diffs[target].expected == 100
    assert diffs[target].actual == 99
    assert all(d.match for name, d in diffs.items() if name != target)


def test_missing_actual_counts_as_zero_mismatch() -> None:
    expected = {ROW_COUNT_OBJECTS[0]: 5}
    actual: dict[str, int] = {}  # restored DB missing the object entirely
    diff = diff_restore_row_counts(expected, actual)[0]
    assert diff.actual == 0
    assert diff.match is False


def test_unknown_expected_is_not_a_mismatch() -> None:
    # legacy manifest without row_counts for an object → can't compare, don't flag.
    expected: dict[str, int] = {}
    actual = _full(100)
    diffs = diff_restore_row_counts(expected, actual)
    assert all(d.match for d in diffs)
    assert all(d.expected is None for d in diffs)


def test_none_expected_mapping_is_graceful() -> None:
    diffs = diff_restore_row_counts(None, _full(7))
    assert all(d.match for d in diffs)
