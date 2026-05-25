from __future__ import annotations

import json

import pytest

from scripts.benchmark_mv_refresh import (
    BenchmarkPhase,
    BenchmarkResult,
    RelationStats,
    _statement_phase_name,
    build_parser,
    result_to_json,
)


def test_mv_refresh_benchmark_parser_requires_strategy() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])

    args = parser.parse_args(["--strategy", "swap", "--output", "out.json"])
    assert args.strategy == "swap"
    assert str(args.output) == "out.json"


def test_mv_refresh_benchmark_json_is_stable() -> None:
    stats = RelationStats(
        row_count=10,
        total_bytes=100,
        heap_bytes=40,
        index_bytes=60,
        database_bytes=1_000,
        temp_files=2,
        temp_bytes=3_000,
        indexes=(("idx_mv_geocode_target_pk", 10),),
    )
    result = BenchmarkResult(
        strategy="concurrent",
        started_at="2026-05-26T00:00:00+00:00",
        finished_at="2026-05-26T00:00:01+00:00",
        total_seconds=1.0,
        before=stats,
        after=stats,
        phases=(BenchmarkPhase(name="refresh_concurrently", seconds=0.9),),
    )

    payload = json.loads(result_to_json(result))

    assert payload["strategy"] == "concurrent"
    assert payload["before"]["row_count"] == 10
    assert payload["phases"] == [{"name": "refresh_concurrently", "seconds": 0.9}]


def test_mv_refresh_benchmark_names_rebuild_phases() -> None:
    assert _statement_phase_name("SET search_path = public, x_extension") == (
        "rebuild.set_search_path"
    )
    assert _statement_phase_name(
        "CREATE MATERIALIZED VIEW mv_geocode_target_next AS SELECT 1"
    ) == "rebuild.create_next"
    assert _statement_phase_name(
        "CREATE UNIQUE INDEX idx_mv_next_geocode_target_next_pk "
        "ON mv_geocode_target_next (bd_mgt_sn)"
    ) == "rebuild.index.idx_mv_next_geocode_target_next_pk"
    assert _statement_phase_name("ANALYZE mv_geocode_target_next") == (
        "rebuild.analyze_next"
    )
