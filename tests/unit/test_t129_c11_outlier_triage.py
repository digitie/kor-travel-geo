from scripts import run_t129_c11_outlier_triage as t129


def base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "bd_mgt_sn": "48220310333302300007800078",
        "road_addr": "경상남도 통영시 용남면 용남해안로 78-78",
        "current_pt_source": "centroid",
        "candidate_sig_cd": "48220",
        "bd_sig_cd": "48220",
        "sido_cd": "48",
        "text_source_yyyymm": "202605",
        "candidate_source_yyyymm": "202604",
        "candidates_per_bd": 1,
        "distance_m": 182892.4,
        "current_lon": 128.445,
        "current_lat": 34.852,
        "candidate_lon": 130.445,
        "candidate_lat": 34.852,
        "abs_lon_delta": 2.0,
        "abs_lat_delta": 0.0,
        "natural_key_polygon_count": 1,
        "current_in_building_polygon": True,
        "candidate_in_building_polygon": False,
        "zip_polygon_count": 1,
        "current_in_zip_polygon": True,
        "candidate_in_zip_polygon": False,
        "emd_polygon_count": 1,
        "current_in_emd_polygon": True,
        "candidate_in_emd_polygon": False,
    }
    row.update(overrides)
    return row


def test_lon_shift_prefers_crs_or_source_coordinate_error() -> None:
    tagged = t129.tag_row(base_row(), candidate_source_yyyymm="202604")

    assert tagged["primary_tag"] == "crs_or_source_coordinate_error"
    assert "lon_shift_approx_2deg" in str(tagged["secondary_tags"])


def test_candidate_outside_context_tags_candidate_coordinate_error() -> None:
    tagged = t129.tag_row(
        base_row(abs_lon_delta=0.01, distance_m=150.0),
        candidate_source_yyyymm="202604",
    )

    assert tagged["primary_tag"] == "candidate_coordinate_error"
    assert "candidate_outside_zip_polygon" in str(tagged["secondary_tags"])


def test_current_outside_context_tags_current_representative_error() -> None:
    tagged = t129.tag_row(
        base_row(
            abs_lon_delta=0.01,
            distance_m=150.0,
            current_in_building_polygon=False,
            current_in_zip_polygon=False,
            current_in_emd_polygon=False,
            candidate_in_building_polygon=True,
            candidate_in_zip_polygon=True,
            candidate_in_emd_polygon=True,
        ),
        candidate_source_yyyymm="202604",
    )

    assert tagged["primary_tag"] == "current_representative_error"
    assert "current_outside_emd_polygon" in str(tagged["secondary_tags"])


def test_candidate_sig_mismatch_tags_key_mismatch() -> None:
    tagged = t129.tag_row(
        base_row(abs_lon_delta=0.01, candidate_sig_cd="99999"),
        candidate_source_yyyymm="202604",
    )

    assert tagged["primary_tag"] == "key_mismatch"
    assert "candidate_sig_cd_mismatch" in str(tagged["secondary_tags"])


def test_build_summary_counts_primary_and_secondary_tags() -> None:
    rows = [
        t129.tag_row(base_row(), candidate_source_yyyymm="202604"),
        t129.tag_row(
            base_row(abs_lon_delta=0.01, distance_m=150.0),
            candidate_source_yyyymm="202604",
        ),
    ]

    summary = t129.build_summary(rows, {"outlier_tags_csv": "outlier_tags.csv"})

    assert summary["outlier_count"] == 2
    assert summary["primary_tag_counts"]["crs_or_source_coordinate_error"] == 1
    assert summary["primary_tag_counts"]["candidate_coordinate_error"] == 1
    assert summary["secondary_tag_counts"]["candidate_source_month_differs_from_text"] == 2
    assert summary["distance_distribution_m"]["max"] == 182892.4


def test_triage_sql_uses_5179_predicates_without_transforming_indexed_columns() -> None:
    sql = t129.triage_sql()

    assert "ST_Covers(z.geom, o.candidate_pt_5179)" in sql
    assert "ST_Covers(e.geom, o.current_pt_5179)" in sql
    assert "ST_Transform(z.geom" not in sql
    assert "ST_Transform(e.geom" not in sql


def test_representative_sample_sql_uses_literal_source_month() -> None:
    sql = t129.representative_sample_sql(candidate_source_yyyymm="202604")

    assert "'202604'::text AS candidate_source_yyyymm" in sql
    assert ":candidate_source_yyyymm" not in sql
