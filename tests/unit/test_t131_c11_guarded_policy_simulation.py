from pathlib import Path

from scripts import run_t131_c11_guarded_policy_simulation as t131


def test_feature_table_sql_uses_5179_predicates_without_transforming_indexed_columns() -> None:
    sql = t131.feature_table_sql()

    assert "ST_Covers(z.geom, b.candidate_pt_5179)" in sql
    assert "ST_Covers(z.geom, b.baseline_pt_5179)" in sql
    assert "ST_Covers(e.geom, b.candidate_pt_5179)" in sql
    assert "ST_Covers(e.geom, b.baseline_pt_5179)" in sql
    assert "ST_Transform(z.geom" not in sql
    assert "ST_Transform(e.geom" not in sql
    assert "CAST(:candidate_source_yyyymm AS text)" in sql


def test_create_feature_table_sql_is_single_prepared_statement() -> None:
    sql = t131.create_feature_table_sql()

    assert sql.lstrip().startswith("CREATE TABLE")
    assert "DROP TABLE" not in sql
    assert "CREATE UNIQUE INDEX" not in sql
    assert "ANALYZE" not in sql
    assert "CAST(:candidate_source_yyyymm AS text)" in sql


def test_policy_summary_sql_includes_guarded_policy_candidates() -> None:
    sql = t131.policy_summary_sql()

    assert "'blanket_c11' AS policy_name" in sql
    assert "'c4_50_c6_c7_ok' AS policy_name" in sql
    assert "'centroid_c4_50_c6_c7_ok' AS policy_name" in sql
    assert "'centroid_c4_100_c6_c7_ok' AS policy_name" in sql
    assert "'centroid_c4_50_c6_c7_single_candidate' AS policy_name" in sql
    assert "'centroid_c4_50_c6_c7_move_500' AS policy_name" in sql
    assert "'same_text_month_only' AS policy_name" in sql
    assert "candidate_c4_dist_m <= 50 AND candidate_c6_ok AND candidate_c7_ok" in sql
    assert "current_pt_source = 'centroid'" in sql
    assert "candidates_per_bd = 1" in sql
    assert "movement_m <= 500" in sql


def test_policy_select_counts_quality_and_movement_budget() -> None:
    sql = t131.policy_select("sample_policy", "candidate_c6_ok")

    assert "COUNT(*) FILTER (WHERE candidate_c6_ok) AS candidate_used_rows" in sql
    assert "fills_baseline_c3_unresolved" in sql
    assert "replaces_baseline_c4_over500" in sql
    assert "candidate_c6_error" in sql
    assert "percentile_cont(0.95)" in sql
    assert "movement_over_500m" in sql


def test_write_artifacts_uses_requested_source_month(tmp_path: Path) -> None:
    artifacts = t131.write_artifacts(
        tmp_path,
        [
            {
                "policy_name": "blanket_c11",
                "candidate_used_rows": 2,
            }
        ],
        source_yyyymm="202501",
    )

    assert Path(artifacts["policy_summary_csv"]).read_text(encoding="utf-8").startswith(
        "policy_name,candidate_used_rows"
    )
    reproduction_sql = Path(artifacts["reproduction_sql"]).read_text(encoding="utf-8")
    assert "'202501'::text" in reproduction_sql
    assert ":candidate_source_yyyymm" not in reproduction_sql
