from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from scripts.benchmark_query_performance import (
    BenchmarkCase,
    Measurement,
    _case_group_counts,
    _search_exact_params,
    build_parser,
    corpus_from_json,
    corpus_to_json,
    percentile,
    pg_stat_delta,
    summarize_measurements,
)


def test_query_benchmark_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args([])

    assert args.cases_per_group == 5
    assert args.iterations == 3
    assert args.warmup == 1
    assert args.concurrency is None
    assert args.statement_timeout_ms == 5_000
    assert args.pool_size is None
    assert args.max_overflow is None
    assert args.reset_pg_stat_statements is False
    assert args.pg_stat_limit == 50


def test_query_benchmark_parser_accepts_multiple_concurrency_values() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["--concurrency", "1", "--concurrency", "4", "--pool-size", "64", "--max-overflow", "0"]
    )

    assert args.concurrency == [1, 4]
    assert args.pool_size == 64
    assert args.max_overflow == 0


def test_percentile_uses_linear_interpolation() -> None:
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile(values, 0) == 10.0
    assert percentile(values, 50) == 25.0
    assert percentile(values, 95) == pytest.approx(38.5)
    assert percentile(values, 100) == 40.0


def test_percentile_rejects_invalid_q() -> None:
    with pytest.raises(ValueError):
        percentile([1.0], 101)


def test_summarize_measurements_excludes_warmup_and_counts_errors() -> None:
    rows = [
        Measurement(
            case_id="warm",
            group="Q1_ROAD_EXACT",
            sql_name="road_exact",
            concurrency=1,
            iteration=1,
            warmup=True,
            ok=True,
            elapsed_ms=1_000.0,
            row_count=1,
        ),
        Measurement(
            case_id="ok1",
            group="Q1_ROAD_EXACT",
            sql_name="road_exact",
            concurrency=1,
            iteration=2,
            warmup=False,
            ok=True,
            elapsed_ms=10.0,
            row_count=1,
            checkout_ms=1.0,
            execute_ms=9.0,
        ),
        Measurement(
            case_id="ok2",
            group="Q1_ROAD_EXACT",
            sql_name="road_exact",
            concurrency=1,
            iteration=3,
            warmup=False,
            ok=True,
            elapsed_ms=30.0,
            row_count=3,
            checkout_ms=3.0,
            execute_ms=27.0,
        ),
        Measurement(
            case_id="err",
            group="Q1_ROAD_EXACT",
            sql_name="road_exact",
            concurrency=1,
            iteration=4,
            warmup=False,
            ok=False,
            elapsed_ms=50.0,
            row_count=0,
            error="timeout",
        ),
    ]

    summary = summarize_measurements(rows)

    assert len(summary) == 1
    assert summary[0].samples == 3
    assert summary[0].errors == 1
    assert summary[0].p50_ms == 20.0
    assert summary[0].p95_checkout_ms == 2.9
    assert summary[0].p95_execute_ms == 26.1
    assert summary[0].avg_rows == 2.0


def test_corpus_json_roundtrip(tmp_path: Path) -> None:
    cases = (
        BenchmarkCase(
            case_id="Q1-road-001",
            group="Q1_ROAD_EXACT",
            sql_name="road_exact",
            params={"si": "서울특별시", "mnnm": 1},
            label="서울특별시 테스트로 1",
            source="unit",
        ),
    )
    path = tmp_path / "corpus.json"
    path.write_text(corpus_to_json(cases), encoding="utf-8")

    loaded = corpus_from_json(path)

    assert loaded == cases
    assert json.loads(path.read_text(encoding="utf-8"))[0]["case_id"] == "Q1-road-001"
    assert _case_group_counts(loaded) == {"Q1_ROAD_EXACT": 1}


def test_search_exact_preflight_params_match_repository_normalization() -> None:
    params = {"query": "선릉로 111길", "limit": 10, "offset": 20}

    assert _search_exact_params(params) == {
        "query_nrm": "선릉로111길",
        "limit": 10,
        "offset": 20,
    }


def test_pg_stat_delta_uses_queryid_and_sorts_by_total_exec_time() -> None:
    before = {
        "available": True,
        "rows": [
            {
                "queryid": "10",
                "calls": 2,
                "total_exec_time_ms": 20.0,
                "result_rows": 4,
                "query": "SELECT 1",
            },
            {
                "queryid": "20",
                "calls": 1,
                "total_exec_time_ms": 5.0,
                "result_rows": 1,
                "query": "SELECT 2",
            },
        ],
    }
    after = {
        "available": True,
        "rows": [
            {
                "queryid": "20",
                "calls": 4,
                "total_exec_time_ms": 35.0,
                "result_rows": 7,
                "query": "SELECT 2",
            },
            {
                "queryid": "10",
                "calls": 3,
                "total_exec_time_ms": 25.0,
                "result_rows": 5,
                "query": "SELECT 1",
            },
        ],
    }

    delta = pg_stat_delta(before, after)

    assert delta["available"] is True
    rows = delta["rows"]
    assert rows[0]["queryid"] == "20"
    assert rows[0]["delta_calls"] == 3
    assert rows[0]["delta_total_exec_time_ms"] == 30.0
    assert rows[0]["delta_mean_exec_time_ms"] == 10.0
    assert rows[0]["delta_result_rows"] == 6
