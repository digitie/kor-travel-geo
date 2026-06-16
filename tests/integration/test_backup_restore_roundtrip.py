"""T-244 backup→restore round-trip live integration test (opt-in).

Exercises the whole flow that previously had no integration coverage: ``run_backup_job`` →
``.tar.zst`` + manifest → ``new_database`` restore → pg_restore/analyze/smoke → compare the
original vs. restored ROW_COUNT_OBJECTS (10 objects). Opt-in via ``KTG_TEST_PG_DSN`` + the
backup CLI tools; it skips otherwise so CI stays green. The setup/backup/restore helpers in
``_backup_roundtrip`` are the fixture foundation for the T-245 fault-injection tests.

Run it with, e.g.:
    KTG_TEST_PG_DSN=postgresql+psycopg://addr:addr@localhost:15434/kor_travel_geo_rt \
        pytest tests/integration/test_backup_restore_roundtrip.py -q
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration._backup_roundtrip import (
    missing_requirement,
    run_backup_restore_round_trip,
)

if TYPE_CHECKING:
    from pathlib import Path

_TARGET_DATABASE = "ktg_roundtrip_restore_t244"


@pytest.mark.asyncio
async def test_backup_restore_round_trip_preserves_row_counts(tmp_path: Path) -> None:
    skip_reason = missing_requirement()
    if skip_reason:
        pytest.skip(skip_reason)
    pytest.importorskip("psycopg")

    result = await run_backup_restore_round_trip(tmp_path, _TARGET_DATABASE)

    # The 10 ROW_COUNT_OBJECTS must round-trip identically (same keys, same counts).
    assert result.restored_counts == result.original_counts
    # And actual data (the probe table) survives the round-trip.
    assert result.restored_probe == result.original_probe
    assert result.original_probe > 0
