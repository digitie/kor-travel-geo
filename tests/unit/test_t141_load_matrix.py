from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts.benchmark_query_performance import BenchmarkCase
from scripts.run_t141_load_matrix import (
    build_plan,
    select_rest_cases,
    select_sql_cases,
    write_plan,
)

if TYPE_CHECKING:
    from pathlib import Path


def _case(case_id: str, group: str, sql_name: str) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        group=group,  # type: ignore[arg-type]
        sql_name=sql_name,
        params={
            "si": "서울특별시",
            "sgg": "강남구",
            "road_nrm": "테헤란로",
            "mnnm": 1,
            "slno": 0,
            "buld_se_cd": "0",
            "limit": 10,
            "offset": 0,
            "query": "테헤란로임의불일치",
            "sig_cd_filter": None,
            "sig_cd_prefix": None,
            "bjd_cd_filter": None,
            "bjd_cd_prefix": None,
        },
        label=case_id,
        source="unit",
    )


def test_build_plan_quick_has_sql_and_rest_steady_profiles() -> None:
    plan = build_plan(
        targets=("sql", "rest"),
        workloads=("actual_mix",),
        concurrency_levels=(1, 4),
        quick=True,
        iterations=3,
        warmup=1,
        statement_timeout_ms=5_000,
        pool_size=20,
        max_overflow=64,
        rest_timeout_s=15.0,
        rest_max_cases_per_sql=None,
        admission_limit=64,
        include_soak=True,
        soak_seconds=1_800,
    )

    assert [item.profile_id for item in plan] == [
        "sql-actual_mix-steady-c1",
        "sql-actual_mix-steady-c4",
        "rest-actual_mix-steady-c1",
        "rest-actual_mix-steady-c4",
    ]
    assert all(item.phase == "steady" for item in plan)
    assert all(item.iterations == 1 for item in plan)
    assert all(item.warmup == 0 for item in plan)


def test_select_sql_cases_applies_workload_weights_and_limits() -> None:
    cases = (
        _case("road-1", "Q1_ROAD_EXACT", "road_exact"),
        _case("road-2", "Q1_ROAD_EXACT", "road_exact"),
        _case("search-1", "Q4_SEARCH", "search_fuzzy"),
    )

    selected = select_sql_cases(cases, "actual_mix", max_cases_per_sql=1)

    road = [case for case in selected if case.sql_name == "road_exact"]
    search = [case for case in selected if case.sql_name == "search_fuzzy"]
    assert len(road) == 6
    assert len(search) == 2
    assert all(case.case_id.startswith("actual_mix-w") for case in selected)


def test_select_rest_cases_adds_admin_summary_cases() -> None:
    cases = (
        _case("road-1", "Q1_ROAD_EXACT", "road_exact"),
        _case("search-1", "Q4_SEARCH", "search_fuzzy"),
    )
    selected = select_sql_cases(cases, "actual_mix", max_cases_per_sql=1)

    rest_cases = select_rest_cases(selected, "actual_mix", max_cases_per_sql=1)

    names = {case.sql_name for case in rest_cases}
    assert "geocode_road" in names
    assert "search_fuzzy" in names
    assert "admin_cache_metrics" in names
    assert "admin_tables" in names
    fuzzy = next(case for case in rest_cases if case.sql_name == "search_fuzzy")
    assert fuzzy.expected_status is None


def test_write_plan_serializes_matrix_items(tmp_path: Path) -> None:
    plan = build_plan(
        targets=("sql",),
        workloads=("adversarial_fuzzy",),
        concurrency_levels=(64, 128),
        quick=False,
        iterations=2,
        warmup=1,
        statement_timeout_ms=3_000,
        pool_size=None,
        max_overflow=None,
        rest_timeout_s=20.0,
        rest_max_cases_per_sql=2,
        admission_limit=None,
        include_soak=False,
        soak_seconds=0,
    )
    path = tmp_path / "matrix-plan.json"

    write_plan(plan, path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert {item["phase"] for item in payload} == {"steady", "burst", "recovery"}
    assert payload[0]["workload"] == "adversarial_fuzzy"
