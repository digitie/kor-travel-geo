from scripts import run_t130_c11_regression_root_cause as t130


def test_classify_c4_candidate_regression_with_multiple_candidates() -> None:
    kind, cause = t130.classify_c4(
        {
            "candidate_dist_m": 750.0,
            "baseline_dist_m": 5.0,
            "candidates_per_bd": 3,
            "candidate_polygon_bjd_cd": "41111111",
            "bjd_cd": "41111111",
        }
    )

    assert kind == "candidate_regression"
    assert cause == "multiple_candidates_candidate_far_from_building"


def test_classify_c4_candidate_improves_baseline() -> None:
    kind, cause = t130.classify_c4(
        {
            "candidate_dist_m": 15.0,
            "baseline_dist_m": 900.0,
            "candidates_per_bd": 1,
        }
    )

    assert kind == "candidate_improves_baseline"
    assert cause == "candidate_closer_than_baseline"


def test_classify_polygon_candidate_regression_without_baseline() -> None:
    kind, cause = t130.classify_polygon_case(
        {
            "candidate_reason": "outside_zip_polygon",
            "baseline_reason": "no_baseline_entrance",
        }
    )

    assert kind == "candidate_regression"
    assert cause == "candidate_error_without_baseline_entrance"


def test_classify_polygon_shared_error() -> None:
    kind, cause = t130.classify_polygon_case(
        {
            "candidate_reason": "outside_emd_polygon",
            "baseline_reason": "outside_emd_polygon",
        }
    )

    assert kind == "shared_error"
    assert cause == "shared_outside_emd_polygon"


def test_summarize_case_counts_candidate_and_baseline_errors() -> None:
    rows = [
        t130.tag_row(
            "C6",
            {"candidate_reason": "outside_zip_polygon", "baseline_reason": "ok"},
        ),
        t130.tag_row(
            "C6",
            {
                "candidate_reason": "ok",
                "baseline_reason": "outside_zip_polygon",
            },
        ),
    ]

    summary = t130.summarize_case(rows)

    assert summary["candidate_error_count"] == 1
    assert summary["baseline_error_count"] == 1
    assert summary["regression_kind_counts"]["candidate_regression"] == 1
    assert summary["regression_kind_counts"]["candidate_improves_baseline"] == 1


def test_c6_c7_sql_uses_5179_predicates_without_transforming_indexed_columns() -> None:
    sql = t130.c6_sql() + t130.c7_sql()

    assert "ST_Covers(p.geom, b.candidate_pt_5179)" in sql
    assert "ST_Covers(p.geom, b.baseline_pt_5179)" in sql
    assert "ST_Transform(p.geom" not in sql
