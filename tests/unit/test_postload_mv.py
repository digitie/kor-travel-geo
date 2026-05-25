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
    refresh_source = inspect.getsource(postload.refresh_mv)
    swap_source = inspect.getsource(postload.shadow_swap_mv)

    assert "normalize_mv_index_names(engine)" in refresh_source
    assert "_rename_mv_next_indexes(conn)" in swap_source
    assert swap_source.index("DROP MATERIALIZED VIEW mv_geocode_target_old") < swap_source.index(
        "_rename_mv_next_indexes(conn)"
    )


def test_stale_mv_next_index_drop_emits_warning() -> None:
    source = inspect.getsource(postload._rename_mv_next_indexes)

    assert "LOGGER.warning" in source
    assert "warnings.warn" in source
    assert "stale MV index" in source


def test_mv_next_index_rename_targets_are_derived_from_live_indexes() -> None:
    source = inspect.getsource(postload._mv_next_index_renames)

    assert "pg_index" in source
    assert "mv_geocode_target_next" in source
    assert postload._mv_target_index_name(
        "idx_mv_next_geocode_target_next_pk"
    ) == "idx_mv_geocode_target_pk"
    assert postload._mv_target_index_name("idx_mv_next_geom5179") == "idx_mv_geom5179"
