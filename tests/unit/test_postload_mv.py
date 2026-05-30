from __future__ import annotations

import inspect

from kraddr.geo.loaders import postload


def test_resolve_text_geometry_links_uses_postload_timeout() -> None:
    source = inspect.getsource(postload.resolve_text_geometry_links)

    assert "statement_timeout_ms: int | None = 1_800_000" in source
    assert "Pass None" in source
    assert "statement_timeout_ms is not None" in source
    assert "set_config('statement_timeout', :timeout_ms, true)" in source
    assert "POSTLOAD_SQL" in source


def test_rebuild_mv_drops_dependent_text_search_helper_first() -> None:
    source = inspect.getsource(postload.rebuild_mv)

    assert "DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search" in source
    assert source.index("DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search") < source.index(
        "MV_SQL"
    )


def test_shadow_swap_handles_missing_current_mv() -> None:
    source = inspect.getsource(postload.shadow_swap_mv)

    assert "to_regclass('mv_geocode_target')" in source
    assert "to_regclass('mv_geocode_text_search')" in source
    assert "if current_mv is not None" in source
    assert "ALTER MATERIALIZED VIEW mv_geocode_target_next RENAME TO mv_geocode_target" in source
    assert "ALTER MATERIALIZED VIEW mv_geocode_text_search_next" in source
    assert "RENAME TO mv_geocode_text_search" in source
    assert "ANALYZE mv_geocode_target" in source
    assert "ANALYZE mv_geocode_text_search" in source
    assert "SET LOCAL lock_timeout = '2s'" in source
    assert "SET LOCAL statement_timeout = 0" in source
    assert source.count("async with engine.begin()") == 2


def test_shadow_swap_normalizes_next_index_names() -> None:
    refresh_source = inspect.getsource(postload.refresh_mv)
    swap_source = inspect.getsource(postload.shadow_swap_mv)

    assert "normalize_mv_index_names(engine)" in refresh_source
    assert "rebuild_text_search_mv_next(engine)" in refresh_source
    assert "rename_mv_next_indexes_for_conn(conn)" in swap_source
    assert swap_source.index("DROP MATERIALIZED VIEW mv_geocode_target_old") < swap_source.index(
        "rename_mv_next_indexes_for_conn(conn)"
    )


def test_stale_mv_next_index_drop_emits_warning() -> None:
    source = inspect.getsource(postload.rename_mv_next_indexes_for_conn)

    assert "LOGGER.warning" in source
    assert "warnings.warn" in source
    assert "stale MV index" in source


def test_mv_next_index_rename_targets_are_derived_from_live_indexes() -> None:
    source = inspect.getsource(postload._mv_next_index_renames)

    assert "pg_index" in source
    assert "mv_geocode_target_next" in source
    assert "mv_geocode_text_search_next" in source
    assert postload._mv_target_index_name(
        "idx_mv_next_geocode_target_next_pk"
    ) == "idx_mv_geocode_target_pk"
    assert postload._mv_target_index_name("idx_mv_next_geom5179") == "idx_mv_geom5179"
    assert (
        postload._mv_target_index_name("idx_mv_next_text_search_rn_trgm")
        == "idx_mv_text_search_rn_trgm"
    )


def test_text_search_shadow_sql_uses_next_target_and_indexes() -> None:
    sql = postload.build_text_search_mv_next_sql()

    assert "DROP MATERIALIZED VIEW IF EXISTS mv_geocode_text_search_next" in sql
    assert "CREATE MATERIALIZED VIEW mv_geocode_text_search_next AS" in sql
    assert "FROM mv_geocode_target_next" in sql
    assert "idx_mv_next_text_search_pk" in sql
