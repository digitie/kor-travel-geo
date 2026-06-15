from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import run_t125_c11_serving_preflight as t125
from scripts import run_t131_c11_guarded_policy_simulation as t131
from scripts import run_t132_c11_guarded_policy_validation as t132


def default_policy(**overrides: object) -> t132.GuardedPolicyConfig:
    values: dict[str, object] = {
        "policy_name": "guarded_centroid_c4_50_c6_c7_move_500",
        "current_pt_source": "centroid",
        "building_distance_max_m": 50.0,
        "movement_max_m": 500.0,
        "require_c6_c7_ok": True,
        "require_single_candidate": False,
        "require_same_source_month": False,
    }
    values.update(overrides)
    return t132.GuardedPolicyConfig(**values)  # type: ignore[arg-type]


def test_default_policy_predicate_matches_t131_followup_candidate() -> None:
    predicate = t132.policy_predicate(default_policy())

    assert "current_pt_source = 'centroid'" in predicate
    assert "candidate_c4_dist_m <= 50" in predicate
    assert "candidate_c6_ok AND candidate_c7_ok" in predicate
    assert "movement_m <= 500" in predicate
    assert "candidates_per_bd = 1" not in predicate
    assert "text_source_yyyymm = candidate_source_yyyymm" not in predicate


def test_policy_predicate_can_toggle_repeat_validation_gates() -> None:
    predicate = t132.policy_predicate(
        default_policy(
            policy_name="sample",
            current_pt_source="any",
            movement_max_m=100.0,
            require_c6_c7_ok=False,
            require_single_candidate=True,
            require_same_source_month=True,
        )
    )

    assert "current_pt_source" not in predicate
    assert "candidate_c6_ok" not in predicate
    assert "movement_m <= 100" in predicate
    assert "candidates_per_bd = 1" in predicate
    assert "text_source_yyyymm = candidate_source_yyyymm" in predicate


def test_policy_name_encodes_threshold_flags() -> None:
    name = t132.policy_name(
        current_pt_source="centroid",
        building_distance_max_m=12.5,
        movement_max_m=None,
        require_c6_c7_ok=False,
        require_single_candidate=True,
        require_same_source_month=True,
    )

    assert name == "guarded_centroid_c4_12p5_allow_c6_c7_move_any_single_same_month"


def test_policy_sample_sql_exports_source_detail_and_samples() -> None:
    sql = t132.policy_sample_sql(default_policy())

    assert "'c11_bundle_guarded' AS coord_source_detail" in sql
    assert "f.text_source_yyyymm" in sql
    assert "f.candidate_source_yyyymm" in sql
    assert f"FROM {t131.FEATURE_TABLE} AS f" in sql
    assert f"JOIN {t125.CANDIDATE_BEST_TABLE} AS c USING (bd_mgt_sn)" in sql
    assert "f.movement_m >= :sample_movement_min_m" in sql
    assert "LIMIT :sample_limit" in sql
    assert "ST_Covers" not in sql


def test_reproduction_sql_inlines_source_month_and_sample_params() -> None:
    sql = t132.reproduction_sql(
        default_policy(),
        source_yyyymm="202604",
        sample_limit=25,
        sample_movement_min_m=75.5,
    )

    assert "'202604'::text" in sql
    assert ":candidate_source_yyyymm" not in sql
    assert ":sample_limit" not in sql
    assert ":sample_movement_min_m" not in sql
    assert "LIMIT 25" in sql
    assert "f.movement_m >= 75.5" in sql


def test_evaluate_policy_result_blocks_quality_errors_and_keeps_promotion_off() -> None:
    result = t132.evaluate_policy_result(
        {
            "candidate_used_rows": 10,
            "candidate_c4_over500": 0,
            "candidate_c6_error": 1,
            "candidate_c7_error": 0,
            "movement_over_100m": 2,
            "movement_over_500m": 0,
        }
    )

    assert result["status"] == "blocked"
    assert result["serving_promotion_allowed"] is False
    assert "policy still has C6 error rows" in result["hard_blocks"]
    assert "policy still has movement over 100m" in result["warnings"]


def test_evaluate_policy_result_accepts_repeatable_candidate_with_warning() -> None:
    result = t132.evaluate_policy_result(
        {
            "candidate_used_rows": 3_482_270,
            "candidate_c4_over500": 0,
            "candidate_c6_error": 0,
            "candidate_c7_error": 0,
            "movement_over_100m": 10_099,
            "movement_over_500m": 0,
        }
    )

    assert result["status"] == "repeatable_candidate"
    assert result["serving_promotion_allowed"] is False
    assert result["hard_blocks"] == []
    assert result["warnings"] == ["policy still has movement over 100m"]


def test_cleanup_relation_names_cover_t125_and_t131_work_tables() -> None:
    assert t132.cleanup_relation_names() == [
        t125.ADDRESS_TABLE,
        t125.ENTRANCE_TABLE,
        t125.CANDIDATE_RAW_TABLE,
        t125.CANDIDATE_BEST_TABLE,
        t131.FEATURE_TABLE,
    ]


def test_summary_payload_has_deterministic_top_level_schema() -> None:
    payload = t132.build_summary_payload(
        started_at=datetime(2026, 6, 16, tzinfo=UTC),
        source_yyyymm="202604",
        data_root=Path("data/juso"),
        sido_codes=("11", "26"),
        policy=default_policy(),
    )

    assert tuple(payload) == t132.SUMMARY_KEYS
    assert payload["task"] == "T-132"
    assert payload["schema_version"] == 1
    assert payload["policy"]["coord_source_detail"] == "c11_bundle_guarded"


def test_sql_number_rejects_negative_and_non_finite_values() -> None:
    with pytest.raises(ValueError):
        t132.sql_number(-1.0)
    with pytest.raises(ValueError):
        t132.sql_number(float("inf"))
