from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import run_t125_c11_serving_preflight as t125
from scripts import run_t131_c11_guarded_policy_simulation as t131
from scripts import run_t132_c11_guarded_policy_validation as t132
from scripts import run_t133_c11_shadow_serving_rehearsal as t133


def default_policy() -> t132.GuardedPolicyConfig:
    return t132.GuardedPolicyConfig(
        policy_name="guarded_centroid_c4_50_c6_c7_move_500",
        current_pt_source="centroid",
        building_distance_max_m=50.0,
        movement_max_m=500.0,
        require_c6_c7_ok=True,
    )


@dataclass(frozen=True)
class Summary:
    group: str
    sql_name: str
    concurrency: int
    samples: int
    errors: int
    p95_ms: float


def test_shadow_schema_is_restricted_to_t133_prefix() -> None:
    assert t133.validate_shadow_schema(" _ktg_t133_shadow ") == "_ktg_t133_shadow"
    with pytest.raises(ValueError, match="_ktg_t133_"):
        t133.validate_shadow_schema("public")


def test_shadow_target_select_expressions_only_replace_point_columns() -> None:
    expressions = t133.shadow_target_select_expressions(
        ("bd_mgt_sn", "rncode_full", "pt_5179", "pt_4326", "pt_source")
    )

    assert 'mv."bd_mgt_sn" AS "bd_mgt_sn"' in expressions
    assert (
        'CASE WHEN p.bd_mgt_sn IS NOT NULL THEN c.candidate_pt_5179 ELSE mv."pt_5179" '
        'END AS "pt_5179"'
    ) in expressions
    assert "ST_Transform(c.candidate_pt_5179, 4326)" in expressions[3]
    assert 'mv."pt_source" AS "pt_source"' in expressions


def test_shadow_target_select_requires_public_mv_contract_columns() -> None:
    with pytest.raises(ValueError, match="pt_5179"):
        t133.shadow_target_select_expressions(("bd_mgt_sn", "pt_source"))


def test_shadow_target_sql_uses_public_mv_and_c11_policy_tables() -> None:
    sql = t133.create_shadow_target_sql(
        "_ktg_t133_shadow",
        default_policy(),
        ("bd_mgt_sn", "pt_5179", "pt_4326", "pt_source"),
    )

    assert 'CREATE UNLOGGED TABLE "_ktg_t133_shadow"."mv_geocode_target"' in sql
    assert "FROM public.mv_geocode_target AS mv" in sql
    assert f'FROM "{t131.FEATURE_TABLE}" AS f' in sql
    assert f'LEFT JOIN "{t125.CANDIDATE_BEST_TABLE}" AS c' in sql
    assert "current_pt_source = 'centroid'" in sql
    assert "coord_source_detail" not in sql


def test_shadow_text_search_sql_reads_shadow_target() -> None:
    sql = t133.create_shadow_text_search_sql("_ktg_t133_shadow")

    assert 'CREATE UNLOGGED TABLE "_ktg_t133_shadow"."mv_geocode_text_search"' in sql
    assert 'FROM "_ktg_t133_shadow"."mv_geocode_target"' in sql
    assert "FROM public.mv_geocode_target" not in sql


def test_shadow_indexes_mirror_target_and_text_search_hot_paths() -> None:
    sql = "\n".join(t133.shadow_index_sql("_ktg_t133_shadow"))

    assert 'CREATE UNIQUE INDEX "idx_mv_geocode_target_pk"' in sql
    assert 'ON "_ktg_t133_shadow"."mv_geocode_target"' in sql
    assert "USING GIN (rn_nrm gin_trgm_ops)" in sql
    assert "USING GIST (pt_5179)" in sql
    assert 'CREATE UNIQUE INDEX "idx_mv_text_search_pk"' in sql


def test_compare_summary_rows_passes_within_budget() -> None:
    result = t133.compare_summary_rows(
        [Summary("Q1", "road_exact", 4, 10, 0, 100.0)],
        [Summary("Q1", "road_exact", 4, 10, 0, 104.0)],
        regression_budget_pct=5.0,
    )

    assert result["status"] == "passed"
    assert result["max_p95_regression_pct"] == 4.0
    assert result["rows"][0]["status"] == "passed"


def test_compare_summary_rows_blocks_errors_and_p95_regression() -> None:
    result = t133.compare_summary_rows(
        [
            {
                "group": "Q1",
                "sql_name": "road_exact",
                "concurrency": 4,
                "samples": 10,
                "errors": 0,
                "p95_ms": 100.0,
            }
        ],
        [
            {
                "group": "Q1",
                "sql_name": "road_exact",
                "concurrency": 4,
                "samples": 10,
                "errors": 1,
                "p95_ms": 120.0,
            }
        ],
        regression_budget_pct=5.0,
    )

    assert result["status"] == "failed"
    assert any("errors in Q1/road_exact/c4" in item for item in result["hard_blocks"])
    assert any("exceeds budget" in item for item in result["hard_blocks"])


def test_flag_off_identity_blocks_compare_release_and_hash() -> None:
    before = {
        "target_rows": 10,
        "target_point_rows": 9,
        "text_search_rows": 10,
        "sample_hash": "a",
        "active_release": {"serving_release_id": "r1", "dataset_snapshot_id": "s1"},
    }
    after = {
        **before,
        "sample_hash": "b",
        "active_release": {"serving_release_id": "r2", "dataset_snapshot_id": "s1"},
    }

    blocks = t133.flag_off_identity_blocks(before, after)

    assert "flag-off public identity changed: sample_hash" in blocks
    assert "flag-off active release changed: serving_release_id" in blocks


def test_evaluate_gate_passes_shadow_rehearsal_but_keeps_promotion_off() -> None:
    identity = {
        "target_rows": 100,
        "target_point_rows": 90,
        "text_search_rows": 100,
        "sample_hash": "same",
        "active_release": {
            "serving_release_id": "r1",
            "dataset_snapshot_id": "s1",
            "mv_hash": "h1",
            "state": "active",
        },
    }
    summary = {
        "policy_result": {
            "candidate_used_rows": 10,
            "candidate_c4_over500": 0,
            "candidate_c6_error": 0,
            "candidate_c7_error": 0,
            "movement_over_100m": 0,
            "movement_over_500m": 0,
        },
        "flag_off_before": identity,
        "flag_off_after": identity,
        "flag_on": {
            "applied_rows": 10,
            "shadow_identity": {
                "target_rows": 100,
                "target_point_rows": 95,
                "text_search_rows": 100,
                "sample_hash": "shadow",
            },
        },
        "sql_benchmark": {"status": "passed", "hard_blocks": []},
        "rest_benchmark": {"status": "passed", "hard_blocks": []},
        "rollback": {"status": "dropped"},
    }

    result = t133.evaluate_gate(summary)

    assert result["status"] == "passed"
    assert result["active_serving_promotion_allowed"] is False


def test_evaluate_gate_requires_rest_benchmark_and_rollback() -> None:
    payload = t133.build_summary_payload(
        started_at=datetime(2026, 6, 16, tzinfo=UTC),
        source_yyyymm="202604",
        data_root=Path("data/juso"),
        sido_codes=("11",),
        shadow_schema="_ktg_t133_shadow",
        shadow_search_path="_ktg_t133_shadow,public,x_extension",
        policy=default_policy(),
    )
    payload.update(
        {
            "policy_result": {
                "candidate_used_rows": 1,
                "candidate_c4_over500": 0,
                "candidate_c6_error": 0,
                "candidate_c7_error": 0,
                "movement_over_100m": 0,
                "movement_over_500m": 0,
            },
            "flag_off_before": {"target_rows": 1, "text_search_rows": 1, "sample_hash": "a"},
            "flag_off_after": {"target_rows": 1, "text_search_rows": 1, "sample_hash": "a"},
            "flag_on": {
                "applied_rows": 1,
                "shadow_identity": {"target_rows": 1, "text_search_rows": 1},
            },
            "sql_benchmark": {"status": "passed", "hard_blocks": []},
            "rest_benchmark": {"status": "not_run", "hard_blocks": []},
            "rollback": {"status": "skipped_keep_shadow"},
        }
    )

    result = t133.evaluate_gate(payload)

    assert result["status"] == "blocked"
    assert "rest_benchmark status is not_run" in result["hard_blocks"]
    assert "rollback status is skipped_keep_shadow" in result["hard_blocks"]


def test_summary_payload_has_deterministic_schema() -> None:
    payload = t133.build_summary_payload(
        started_at=datetime(2026, 6, 16, tzinfo=UTC),
        source_yyyymm="202604",
        data_root=Path("data/juso"),
        sido_codes=("11", "26"),
        shadow_schema="_ktg_t133_shadow",
        shadow_search_path="_ktg_t133_shadow,public,x_extension",
        policy=default_policy(),
    )

    assert tuple(payload) == t133.SUMMARY_KEYS
    assert payload["task"] == "T-133"
    assert payload["policy"]["coord_source_detail"] == "c11_bundle_guarded"
