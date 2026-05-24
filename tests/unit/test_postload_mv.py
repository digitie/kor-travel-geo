from __future__ import annotations

import inspect

from kraddr.geo.loaders import postload


def test_shadow_swap_handles_missing_current_mv() -> None:
    source = inspect.getsource(postload.shadow_swap_mv)

    assert "to_regclass('mv_geocode_target')" in source
    assert "if current_mv is not None" in source
    assert "ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target" in source
    assert "ANALYZE mv_geocode_target" in source
