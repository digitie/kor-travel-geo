from __future__ import annotations

import inspect

from kraddr.geo.loaders import postload


def test_shadow_swap_handles_missing_current_mv() -> None:
    source = inspect.getsource(postload.shadow_swap_mv)

    assert "to_regclass('mv_geocode_target')" in source
    assert "if current_mv is not None" in source
    assert "ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target" in source
    assert "ANALYZE mv_geocode_target" in source


def test_shadow_swap_normalizes_next_index_names() -> None:
    assert (
        "idx_mv_next_geocode_target_next_pk",
        "idx_mv_geocode_target_pk",
    ) in postload.MV_NEXT_INDEX_RENAMES

    refresh_source = inspect.getsource(postload.refresh_mv)
    swap_source = inspect.getsource(postload.shadow_swap_mv)

    assert "normalize_mv_index_names(engine)" in refresh_source
    assert "_rename_mv_next_indexes(conn)" in swap_source
    assert swap_source.index("DROP MATERIALIZED VIEW mv_geocode_target_old") < swap_source.index(
        "_rename_mv_next_indexes(conn)"
    )
