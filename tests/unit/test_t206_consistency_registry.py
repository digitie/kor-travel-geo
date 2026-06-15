"""T-206: consistency case registry + C11~C17 + run-validation (DB-free).

Covers the high-value, DB-free surfaces of T-206:

* **seed coverage / drift** — the registry seed authority spans C1~C17, C1~C10
  match ``CASE_DEFINITIONS`` exactly, and C11's ``roadaddr_entrance_full`` is the
  conditional (``required=false``) input;
* **run-validation decision logic** (pure) — integrity fail → ``failed`` (not
  ``skipped``), absent required → ``skipped``, absent optional → ``skipped``,
  ok → runnable; validator_version change → ``not_started``;
* **prototype == registry metric** — the C11~C17 metric binding computes the
  SAME metric as the phase-① prototype ``.metrics()``. The API run-validation
  endpoint only performs source-archive presence/integrity gating.
"""

from __future__ import annotations

from pathlib import Path

from kortravelgeo.core.consistency_definitions import CASE_DEFINITIONS
from kortravelgeo.core.consistency_registry_seed import (
    REGISTRY_SEED_BY_CODE,
    REGISTRY_SEED_ROWS,
    consistency_registry_seed_rows,
)
from kortravelgeo.core.consistency_run_validation import (
    INTEGRITY_FAILURE_REASON,
    CaseInputFacts,
    ValidatorVersionFacts,
    decide_case_run,
    decide_input_state,
    decide_validator_version_change,
)
from kortravelgeo.loaders.augment_harness import DistanceMeasurement, KeyOverlapMeasurement
from kortravelgeo.loaders.c11_entrance_sources import (
    FULL_ENTRANCE_JOIN_KEYS,
    C11EntranceComparison,
    C11PairComparison,
)
from kortravelgeo.loaders.c17_navi_jibun_coverage import C17NaviJibunCoverageComparison
from kortravelgeo.loaders.consistency_run_validation import (
    AUGMENT_CASE_CODES,
    PROTOTYPE_COMPARISON_BY_CASE,
    is_augment_case,
    prototype_comparison_class,
    prototype_metric,
)
from kortravelgeo.loaders.shape_dbf import KeyOverlap, KeySetStats

# --- seed coverage / drift -------------------------------------------------


def test_seed_covers_c1_through_c17() -> None:
    codes = [row.consistency_case_code for row in REGISTRY_SEED_ROWS]
    assert codes == [f"C{n}" for n in range(1, 18)]
    # display_order is 1..17 in case order.
    assert [row.display_order for row in REGISTRY_SEED_ROWS] == list(range(1, 18))


def test_seed_is_deterministic() -> None:
    assert consistency_registry_seed_rows() == REGISTRY_SEED_ROWS


def test_migration_0017_seeds_the_registry() -> None:
    migration = Path(
        "alembic/versions/0017_t206_consistency_seed.py"
    ).read_text(encoding="utf-8")
    assert 'revision = "0017_t206_consistency_seed"' in migration
    assert 'down_revision = "0016_t200_source_registry"' in migration
    assert "INSERT INTO ops.consistency_case_definitions" in migration
    assert "ON CONFLICT (consistency_case_code) DO UPDATE SET" in migration
    assert "REGISTRY_SEED_ROWS" in migration


def test_c1_to_c10_match_case_definitions_exactly() -> None:
    for case in CASE_DEFINITIONS:
        row = REGISTRY_SEED_BY_CODE[case.code]
        assert row.name == case.name
        assert row.compares == case.compares
        assert row.abnormal_criteria == case.abnormal_criteria
        assert row.evidence == case.evidence
        assert row.likely_causes == case.likely_causes
        assert row.decision_guide == case.decision_guide
        assert row.threshold == case.threshold
        # C1~C10 carry no source-archive validation inputs.
        assert row.inputs == ()
        assert row.metadata.get("family") == "core_serving"


def test_c11_conditional_input_is_encoded() -> None:
    c11 = REGISTRY_SEED_BY_CODE["C11"]
    by_category = {i.category: i.required for i in c11.inputs}
    # The always-on inputs are required; the direct roadaddr entrance pair is
    # conditional (required=false) per the T-118 review note.
    assert by_category["roadaddr_building_shape_bundle"] is True
    assert by_category["electronic_map_full"] is True
    assert by_category["locsum_full"] is True
    assert by_category["roadaddr_entrance_full"] is False
    # The condition is documented in metadata so the UI/run-validation can show it.
    assert "roadaddr_entrance_full" in c11.metadata["conditional_inputs"]


def test_c17_uses_navi_group_with_match_jibun_member_flag() -> None:
    c17 = REGISTRY_SEED_BY_CODE["C17"]
    categories = {i.category for i in c17.inputs}
    assert categories == {"navi_full"}
    assert c17.skip_policy["member_flag"] == "navi_full.match_jibun"
    assert c17.skip_policy["requires_active_table"] == "tl_juso_parcel_link"


def test_c11_to_c17_default_severity_is_warn() -> None:
    for n in range(11, 18):
        assert REGISTRY_SEED_BY_CODE[f"C{n}"].default_severity == "WARN"


def test_augment_cases_are_c11_to_c17() -> None:
    assert AUGMENT_CASE_CODES == ("C11", "C12", "C13", "C14", "C15", "C16", "C17")
    assert all(is_augment_case(c) for c in AUGMENT_CASE_CODES)
    assert not is_augment_case("C1")
    # Every augment case in the seed has a bound prototype comparison class.
    for code in AUGMENT_CASE_CODES:
        assert code in PROTOTYPE_COMPARISON_BY_CASE
        assert REGISTRY_SEED_BY_CODE[code].metadata["family"] == "augment_validation"


# --- run-validation decision logic (pure) ----------------------------------


def test_absent_required_input_is_skipped_not_failed() -> None:
    decision = decide_input_state(
        CaseInputFacts(category="locsum_full", required=True, present=False)
    )
    assert decision.state == "skipped"
    assert decision.failure_reason is None
    assert decision.quarantine_group_id is None


def test_absent_optional_input_is_skipped() -> None:
    decision = decide_input_state(
        CaseInputFacts(category="roadaddr_entrance_full", required=False, present=False)
    )
    assert decision.state == "skipped"


def test_integrity_failure_is_failed_not_skipped() -> None:
    decision = decide_input_state(
        CaseInputFacts(
            category="locsum_full",
            required=True,
            present=True,
            integrity_ok=False,
            source_file_group_id="g-locsum",
        )
    )
    assert decision.state == "failed"
    assert decision.failure_reason == INTEGRITY_FAILURE_REASON
    assert decision.quarantine_group_id == "g-locsum"


def test_present_and_ok_input_is_not_started() -> None:
    decision = decide_input_state(
        CaseInputFacts(
            category="locsum_full",
            required=True,
            present=True,
            integrity_ok=True,
            source_file_group_id="g-locsum",
        )
    )
    assert decision.state == "not_started"
    assert decision.source_file_group_id == "g-locsum"


def test_case_runnable_when_all_required_present_and_ok() -> None:
    decision = decide_case_run(
        "C11",
        (
            CaseInputFacts("roadaddr_building_shape_bundle", True, True, True, "g1"),
            CaseInputFacts("electronic_map_full", True, True, True, "g2"),
            CaseInputFacts("locsum_full", True, True, True, "g3"),
            CaseInputFacts("roadaddr_entrance_full", False, False),  # optional absent
        ),
    )
    assert decision.runnable is True
    assert decision.skipped is False
    assert decision.failed is False
    assert decision.quarantine_group_ids == ()


def test_case_skipped_when_required_input_absent() -> None:
    decision = decide_case_run(
        "C13",
        (
            CaseInputFacts("detail_dong_shape_bundle", True, True, True, "g1"),
            CaseInputFacts("detail_address_db_full", True, False),  # required absent
        ),
    )
    assert decision.skipped is True
    assert decision.runnable is False
    assert decision.failed is False


def test_case_failed_takes_precedence_over_skipped() -> None:
    # A corrupt present input must surface as failed even if another required
    # input is absent (doc ~1562: corrupt is a harder signal than missing).
    decision = decide_case_run(
        "C13",
        (
            CaseInputFacts("detail_dong_shape_bundle", True, True, False, "g-bad"),
            CaseInputFacts("detail_address_db_full", True, False),
        ),
    )
    assert decision.failed is True
    assert decision.skipped is False
    assert decision.runnable is False
    assert decision.quarantine_group_ids == ("g-bad",)


def test_validator_version_change_reverts_passed_to_not_started() -> None:
    decision = decide_validator_version_change(
        ValidatorVersionFacts(
            case_code="C11",
            prior_state="passed",
            prior_validator_version="t203b.1",
            current_validator_version="t206.1",
        )
    )
    assert decision.needs_revalidation is True
    assert decision.revert_state == "not_started"


def test_same_validator_version_does_not_revert() -> None:
    decision = decide_validator_version_change(
        ValidatorVersionFacts(
            case_code="C11",
            prior_state="passed",
            prior_validator_version="t206.1",
            current_validator_version="t206.1",
        )
    )
    assert decision.needs_revalidation is False
    assert decision.revert_state is None


def test_non_trusted_prior_state_not_reverted_on_version_change() -> None:
    decision = decide_validator_version_change(
        ValidatorVersionFacts(
            case_code="C11",
            prior_state="failed",
            prior_validator_version="t203b.1",
            current_validator_version="t206.1",
        )
    )
    assert decision.needs_revalidation is False


# --- prototype == registry metric (regression bridge) ----------------------


def _synthetic_overlap() -> KeyOverlapMeasurement:
    return KeyOverlapMeasurement(
        left_rows=100,
        right_rows=98,
        left_distinct=95,
        right_distinct=93,
        intersection_count=90,
        left_only_count=5,
        right_only_count=3,
    )


def _synthetic_distance() -> DistanceMeasurement:
    return DistanceMeasurement(
        samples=42,
        p50_m=1.5,
        p95_m=8.0,
        max_m=40.0,
        sample=({"comparison": "x", "distance_m": 40.0},),
    )


def _synthetic_dbf_overlap() -> KeyOverlap:
    stats = KeySetStats(row_count=10, distinct_count=9, duplicate_count=1)
    return KeyOverlap(
        left=stats,
        right=stats,
        intersection_count=8,
        left_only_count=1,
        right_only_count=1,
    )


def _synthetic_c11() -> C11EntranceComparison:
    pair = C11PairComparison(
        name="bundle_to_electronic_full_key",
        left_source="roadaddr_building_shape_bundle.TL_SPBD_ENTRC",
        right_source="electronic_map_full.TL_SPBD_ENTRC",
        key_contract="full_sig_bul_ent_eqb_key",
        join_keys=FULL_ENTRANCE_JOIN_KEYS,
        overlap=_synthetic_overlap(),
        distance=_synthetic_distance(),
    )
    return C11EntranceComparison(
        sido_name="서울특별시",
        bundle_zip="/x/bundle.zip",
        electronic_map_dir="/x/electronic",
        source_yyyymm="202605",
        bundle_rows=100,
        electronic_rows=98,
        dbf_exact_key_overlap=_synthetic_dbf_overlap(),
        pairs=(pair,),
    )


def _synthetic_c17() -> C17NaviJibunCoverageComparison:
    from kortravelgeo.loaders.augment_harness import JoinKey

    return C17NaviJibunCoverageComparison(
        name="navi_jibun_to_tl_juso_parcel_link_bd_pnu",
        left_source="navi_full.match_jibun_*.txt",
        right_source="tl_juso_parcel_link",
        key_contract="bd_mgt_sn_pnu",
        join_keys=(JoinKey("bd_mgt_sn", "bd_mgt_sn"), JoinKey("pnu", "pnu")),
        overlap=_synthetic_overlap(),
        sample=({"sample_kind": "left_only", "keys": {"pnu": "1"}},),
    )


def test_c11_registry_metric_equals_prototype_metric() -> None:
    comparison = _synthetic_c11()
    # The registry metric binding for C11 is the C11 prototype comparison class,
    # and computing its metric through the bridge equals the prototype .metrics().
    assert prototype_comparison_class("C11") is C11EntranceComparison
    assert prototype_metric(comparison) == comparison.metrics()
    # Spot-check the metric carries the prototype's distance/key-overlap shape.
    metric = prototype_metric(comparison)
    pair_metric = metric["comparisons"]["bundle_to_electronic_full_key"]
    assert pair_metric["distance_m"]["p95_m"] == 8.0
    assert pair_metric["key_overlap"]["intersection_count"] == 90
    assert metric["serving_promotion"] is False


def test_c17_registry_metric_equals_prototype_metric() -> None:
    comparison = _synthetic_c17()
    assert prototype_comparison_class("C17") is C17NaviJibunCoverageComparison
    assert prototype_metric(comparison) == comparison.metrics()
    metric = prototype_metric(comparison)
    assert metric["key_overlap"]["right_only_count"] == 3
