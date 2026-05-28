from __future__ import annotations

import json

import pytest

from scripts.benchmark_mv_refresh import (
    BenchmarkMetadata,
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

    args = parser.parse_args(
        [
            "--strategy",
            "swap",
            "--output",
            "out.json",
            "--trial-index",
            "2",
            "--cache-warm-hint",
            "warm",
            "--note",
            "idle docker db",
        ]
    )
    assert args.strategy == "swap"
    assert str(args.output) == "out.json"
    assert args.trial_index == 2
    assert args.cache_warm_hint == "warm"
    assert args.note == ["idle docker db"]


def test_mv_refresh_benchmark_json_is_stable() -> None:
    stats = RelationStats(
        row_count=10,
        total_bytes=100,
        heap_bytes=40,
        index_bytes=60,
        text_search_row_count=10,
        text_search_total_bytes=80,
        text_search_heap_bytes=30,
        text_search_index_bytes=50,
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
        metadata=BenchmarkMetadata(
            trial_index=1,
            cache_warm_hint="warm",
            notes=("idle docker db",),
            concurrent_sessions_before=0,
            concurrent_sessions_after=0,
            wait_events_before=(("IO:BufFileWrite", 1),),
            wait_events_after=(),
        ),
    )

    payload = json.loads(result_to_json(result))

    assert payload["schema_version"] == 3
    assert payload["strategy"] == "concurrent"
    assert payload["before"]["row_count"] == 10
    assert payload["before"]["text_search_total_bytes"] == 80
    assert payload["phases"] == [{"name": "refresh_concurrently", "seconds": 0.9}]
    assert payload["metadata"] == {
        "trial_index": 1,
        "cache_warm_hint": "warm",
        "notes": ["idle docker db"],
        "concurrent_sessions_before": 0,
        "concurrent_sessions_after": 0,
        "wait_events_before": [["IO:BufFileWrite", 1]],
        "wait_events_after": [],
    }


def test_mv_refresh_benchmark_names_rebuild_phases() -> None:
    assert _statement_phase_name("SET search_path = public, x_extension") == (
        "rebuild.set_search_path"
    )
    assert _statement_phase_name("SET LOCAL maintenance_work_mem = '1GB'") == (
        "rebuild.set_maintenance_work_mem"
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
    assert _statement_phase_name(
        "CREATE INDEX idx_mv_next_text_search_rn_trgm "
        "ON mv_geocode_text_search_next USING GIN (rn_nrm gin_trgm_ops)"
    ) == "rebuild.index.idx_mv_next_text_search_rn_trgm"
