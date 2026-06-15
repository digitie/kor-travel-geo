"""T-203b: register + recompute_group_aggregates + archive structure validator.

DB-free tests for the pure decision logic (the highest-value surface):

* ``recompute_group_aggregates`` down/up match-set propagation as a function
  table — active vs non-active, validated→invalid, draft/restored pre-hash stay,
  invalid→revalidatable, restored→revalidatable (hash pre-computed), active
  recovery candidate only.
* ``group_sha256`` / ``source_set_hash`` canonical determinism.
* validator profile decisions per category with synthetic member manifests
  (11-layer electronic map pass/fail, missing sido part, DBF-only layer, navi
  optional member warning, single-file text member presence).
* register flow shape via the pure coverage decision + register DTOs.
"""

from __future__ import annotations

from kortravelgeo.core.source_match_propagation import (
    ChildFileFacts,
    MatchSetFacts,
    MatchSetItemFacts,
    compute_group_sha256,
    compute_source_set_hash,
    decide_match_set_transition,
    group_is_available,
    group_is_bad,
    propagate_group_bad,
    propagate_group_recovered,
    recompute_group_derived,
)
from kortravelgeo.core.source_validation import (
    ELECTRONIC_MAP_SERVING_LAYERS,
    ELECTRONIC_MAP_STRUCTURE_LAYERS,
    SIDO_PART_KEYS,
    VALIDATOR_VERSION,
    GroupManifest,
    ManifestMember,
    PartManifest,
    validate_group_coverage,
    validate_group_manifest,
)
from kortravelgeo.dto.source import (
    RegisterRequest,
    RegisterResponse,
    SourceFileRegistered,
)
from kortravelgeo.loaders.juso_map import MASTER_LAYER_NAMES
from kortravelgeo.loaders.shp.polygons_loader import POLYGON_LAYER_NAMES

# --- group_sha256 / source_set_hash canonical determinism ------------------


def _child(
    part_key: str,
    sha: str,
    *,
    part_kind: str = "sido",
    state: str = "available",
) -> ChildFileFacts:
    return ChildFileFacts(
        part_kind=part_kind, part_key=part_key, state=state, sha256=sha, size_bytes=10
    )


def test_group_sha256_is_order_independent() -> None:
    a = _child("11", "a" * 64)
    b = _child("41", "b" * 64)
    assert compute_group_sha256((a, b)) == compute_group_sha256((b, a))


def test_group_sha256_changes_with_child_content() -> None:
    base = (_child("11", "a" * 64), _child("41", "b" * 64))
    changed = (_child("11", "a" * 64), _child("41", "c" * 64))
    assert compute_group_sha256(base) != compute_group_sha256(changed)


def test_group_sha256_none_when_all_deleted() -> None:
    assert compute_group_sha256((_child("11", "a" * 64, state="hard_deleted"),)) is None


def test_group_sha256_single_file_stable() -> None:
    one = (_child("archive", "a" * 64, part_kind="single"),)
    assert compute_group_sha256(one) == compute_group_sha256(one)
    assert len(compute_group_sha256(one) or "") == 64


def test_source_set_hash_order_independent_and_64() -> None:
    items = (
        MatchSetItemFacts("electronic_map_full", "g1", "a" * 64, "202604", False, None),
        MatchSetItemFacts("roadname_hangul_full", "g2", "b" * 64, "202605", False, None),
    )
    reversed_items = tuple(reversed(items))
    assert compute_source_set_hash(items) == compute_source_set_hash(reversed_items)
    assert len(compute_source_set_hash(items)) == 64


# --- recompute group derived ----------------------------------------------


def test_recompute_available_when_all_present_and_validation_ok() -> None:
    derived = recompute_group_derived(
        group_kind="single_file",
        expected_part_keys=("archive",),
        children=(_child("archive", "a" * 64, part_kind="single"),),
        structure_validation_state="passed",
    )
    assert derived.state == "available"
    assert derived.actual_file_count == 1
    assert derived.coverage["archive"] == "present"
    assert derived.group_sha256 is not None


def test_recompute_missing_when_required_part_absent() -> None:
    derived = recompute_group_derived(
        group_kind="multi_part",
        expected_part_keys=("11", "41"),
        children=(_child("11", "a" * 64),),
        structure_validation_state="passed",
    )
    assert derived.state == "missing"
    assert derived.coverage["41"] == "missing"


def test_recompute_quarantined_propagates_worst_child() -> None:
    derived = recompute_group_derived(
        group_kind="multi_part",
        expected_part_keys=("11", "41"),
        children=(_child("11", "a" * 64), _child("41", "b" * 64, state="quarantined")),
        structure_validation_state="passed",
    )
    assert derived.state == "quarantined"


def test_recompute_failed_validation_not_available() -> None:
    derived = recompute_group_derived(
        group_kind="single_file",
        expected_part_keys=("archive",),
        children=(_child("archive", "a" * 64, part_kind="single"),),
        structure_validation_state="failed",
    )
    assert derived.state != "available"


# --- match-set DOWN propagation table -------------------------------------


def _ms(state: str, **kw: object) -> MatchSetFacts:
    return MatchSetFacts(source_match_set_id="ms1", state=state, **kw)  # type: ignore[arg-type]


def test_down_active_keeps_active_sets_integrity_alert() -> None:
    t = propagate_group_bad(_ms("active"), detail={"x": 1})
    assert t is not None
    assert t.new_state is None  # stays active
    assert t.set_integrity_alert is True
    assert t.integrity_alert_detail == {"x": 1}


def test_down_validated_goes_invalid() -> None:
    t = propagate_group_bad(_ms("validated"))
    assert t is not None
    assert t.new_state == "invalid"


def test_down_draft_stays_unchanged() -> None:
    assert propagate_group_bad(_ms("draft")) is None


def test_down_restored_from_backup_pre_hash_stays() -> None:
    assert propagate_group_bad(_ms("restored_from_backup")) is None


def test_down_already_invalid_or_retired_unchanged() -> None:
    assert propagate_group_bad(_ms("invalid")) is None
    assert propagate_group_bad(_ms("retired")) is None
    assert propagate_group_bad(_ms("revalidatable")) is None


# --- match-set UP propagation table ---------------------------------------


def test_up_invalid_goes_revalidatable() -> None:
    t = propagate_group_recovered(_ms("invalid"))
    assert t is not None
    assert t.new_state == "revalidatable"


def test_up_restored_with_all_available_precomputes_hash_then_revalidatable() -> None:
    facts = _ms(
        "restored_from_backup",
        all_groups_available=True,
        recomputed_source_set_hash="d" * 64,
    )
    t = propagate_group_recovered(facts)
    assert t is not None
    assert t.new_state == "revalidatable"
    assert t.set_source_set_hash == "d" * 64  # hash set BEFORE transition (M-A opt 2)


def test_up_restored_without_hash_stays_until_precomputed() -> None:
    facts = _ms("restored_from_backup", all_groups_available=True, recomputed_source_set_hash=None)
    assert propagate_group_recovered(facts) is None


def test_up_restored_without_all_available_stays() -> None:
    facts = _ms(
        "restored_from_backup",
        all_groups_available=False,
        recomputed_source_set_hash="d" * 64,
    )
    assert propagate_group_recovered(facts) is None


def test_up_active_only_marks_recovery_candidate_not_cleared() -> None:
    facts = _ms("active", integrity_alert=True, all_groups_available=True)
    t = propagate_group_recovered(facts)
    assert t is not None
    assert t.new_state is None
    assert t.set_integrity_alert is None  # clearing belongs to POST /validate
    assert t.integrity_alert_detail.get("recovered") is True


# --- decide_match_set_transition (single entry point) ----------------------


def test_decide_routes_bad_state_to_down() -> None:
    t = decide_match_set_transition(_ms("validated"), group_state="missing")
    assert t is not None and t.new_state == "invalid"


def test_decide_routes_available_to_up() -> None:
    t = decide_match_set_transition(_ms("invalid"), group_state="available")
    assert t is not None and t.new_state == "revalidatable"


def test_decide_ignores_intermediate_state() -> None:
    assert decide_match_set_transition(_ms("validated"), group_state="validating") is None


def test_group_state_predicates() -> None:
    assert group_is_bad("missing") and group_is_bad("quarantined") and group_is_bad("delete_failed")
    assert not group_is_bad("available")
    assert group_is_available("available")


# --- validator profiles ----------------------------------------------------


_FULL_SIDECARS = frozenset({".shp", ".shx", ".dbf", ".prj"})


def _layer(name: str, suffixes: frozenset[str] = _FULL_SIDECARS) -> ManifestMember:
    return ManifestMember(
        member_path=f"{name}.shp",
        member_kind="shp_layer",
        layer_name=name,
        suffixes=suffixes,
    )


def _all_master_layers() -> tuple[ManifestMember, ...]:
    return tuple(_layer(name) for name in MASTER_LAYER_NAMES)


def test_electronic_map_requires_all_11_master_layers_pass() -> None:
    assert len(ELECTRONIC_MAP_STRUCTURE_LAYERS) == 11
    assert len(ELECTRONIC_MAP_SERVING_LAYERS) == 9
    parts = tuple(
        PartManifest(part_key=key, members=_all_master_layers())
        for key, _ in _sido_pairs()
    )
    manifest = GroupManifest(category="electronic_map_full", group_kind="multi_part", parts=parts)
    result = validate_group_manifest(manifest)
    assert result.outcome == "passed"
    assert all(v == "present" for v in result.coverage.values())


def test_electronic_map_missing_one_master_layer_fails() -> None:
    layers = tuple(_layer(name) for name in MASTER_LAYER_NAMES if name != "TL_SPBD_EQB")
    parts = tuple(
        PartManifest(part_key=key, members=layers) for key, _ in _sido_pairs()
    )
    manifest = GroupManifest(category="electronic_map_full", group_kind="multi_part", parts=parts)
    result = validate_group_manifest(manifest)
    assert result.outcome == "failed"
    assert any("TL_SPBD_EQB" in r for p in result.parts for r in p.reasons)


def test_electronic_map_missing_sido_part_fails_coverage() -> None:
    parts = tuple(
        PartManifest(part_key=key, members=_all_master_layers())
        for key, _ in _sido_pairs()[:-1]  # drop one sido
    )
    manifest = GroupManifest(category="electronic_map_full", group_kind="multi_part", parts=parts)
    result = validate_group_manifest(manifest)
    assert result.outcome == "failed"
    dropped = _sido_pairs()[-1][0]
    assert result.coverage[dropped] == "missing"


def test_register_coverage_only_does_not_require_archive_members() -> None:
    result = validate_group_coverage(
        category="electronic_map_full",
        group_kind="multi_part",
        present_part_keys=SIDO_PART_KEYS,
    )
    assert result.outcome == "passed"
    assert all(v == "present" for v in result.coverage.values())
    assert not result.reasons


def test_register_coverage_only_fails_missing_required_slot() -> None:
    result = validate_group_coverage(
        category="electronic_map_full",
        group_kind="multi_part",
        present_part_keys=SIDO_PART_KEYS[:-1],
    )
    assert result.outcome == "failed"
    assert result.coverage[SIDO_PART_KEYS[-1]] == "missing"


def test_dbf_only_road_interval_layer_skips_geometry_sidecars() -> None:
    # TL_SPRD_INTRVL needs only .dbf; missing .shp/.shx must not fail it.
    layers = []
    for name in MASTER_LAYER_NAMES:
        if name == "TL_SPRD_INTRVL":
            layers.append(_layer(name, suffixes=frozenset({".dbf"})))
        else:
            layers.append(_layer(name))
    parts = tuple(PartManifest(part_key=key, members=tuple(layers)) for key, _ in _sido_pairs())
    manifest = GroupManifest(category="electronic_map_full", group_kind="multi_part", parts=parts)
    result = validate_group_manifest(manifest)
    assert result.outcome == "passed"


def test_missing_prj_is_warning_not_failure() -> None:
    no_prj = frozenset({".shp", ".shx", ".dbf"})
    layers = tuple(_layer(name, suffixes=no_prj) for name in MASTER_LAYER_NAMES)
    parts = tuple(PartManifest(part_key=key, members=layers) for key, _ in _sido_pairs())
    manifest = GroupManifest(category="electronic_map_full", group_kind="multi_part", parts=parts)
    result = validate_group_manifest(manifest)
    assert result.outcome == "warning"


def test_single_file_text_member_presence_pass() -> None:
    members = (
        *(ManifestMember(member_path=f"rnaddrkor_{i:02d}.txt") for i in range(17)),
        *(ManifestMember(member_path=f"jibun_rnaddrkor_{i:02d}.txt") for i in range(17)),
    )
    manifest = GroupManifest(
        category="roadname_hangul_full",
        group_kind="single_file",
        parts=(PartManifest(part_key="archive", members=members),),
    )
    result = validate_group_manifest(manifest)
    assert result.outcome == "passed"


def test_single_file_text_missing_required_member_fails() -> None:
    members = tuple(ManifestMember(member_path=f"rnaddrkor_{i:02d}.txt") for i in range(17))
    manifest = GroupManifest(
        category="roadname_hangul_full",
        group_kind="single_file",
        parts=(PartManifest(part_key="archive", members=members),),
    )
    result = validate_group_manifest(manifest)
    assert result.outcome == "failed"
    assert any("jibun_rnaddrkor" in r for p in result.parts for r in p.reasons)


def test_navi_optional_match_jibun_absent_is_warning() -> None:
    members = (
        *(ManifestMember(member_path=f"match_build_{i:02d}.txt") for i in range(17)),
        ManifestMember(member_path="match_rs_entrc.txt"),
    )
    manifest = GroupManifest(
        category="navi_full",
        group_kind="single_file",
        parts=(PartManifest(part_key="archive", members=members),),
    )
    result = validate_group_manifest(manifest)
    assert result.outcome == "warning"  # optional match_jibun_* missing
    assert any("match_jibun" in w for p in result.parts for w in p.warnings)


def test_zone_shape_requires_makarea_layer() -> None:
    ok = tuple(
        PartManifest(part_key=key, members=(_layer("TL_SPPN_MAKAREA"),)) for key, _ in _sido_pairs()
    )
    manifest = GroupManifest(category="zone_shape_full", group_kind="multi_part", parts=ok)
    assert validate_group_manifest(manifest).outcome == "passed"

    bad = tuple(
        PartManifest(part_key=key, members=(_layer("TL_SCCO_SIG"),)) for key, _ in _sido_pairs()
    )
    manifest_bad = GroupManifest(category="zone_shape_full", group_kind="multi_part", parts=bad)
    assert validate_group_manifest(manifest_bad).outcome == "failed"


def test_unknown_category_is_warning_not_crash() -> None:
    manifest = GroupManifest(
        category="not_a_real_category",
        group_kind="single_file",
        parts=(PartManifest(part_key="archive"),),
    )
    result = validate_group_manifest(manifest)
    assert result.outcome == "warning"


def test_validator_version_is_set() -> None:
    assert VALIDATOR_VERSION


# --- register DTO / flow shape --------------------------------------------


def test_register_request_confirm_yyyymm_pattern() -> None:
    ok = RegisterRequest(confirm_user_yyyymm="202605", yyyymm_mismatch_ack=True)
    assert ok.confirm_user_yyyymm == "202605"


def test_register_response_shape() -> None:
    resp = RegisterResponse(
        source_file_group_id="g1",
        category="roadname_hangul_full",
        group_kind="single_file",
        state="available",
        validation_state="passed",
        user_yyyymm="202605",
        group_sha256="a" * 64,
        files=(
            SourceFileRegistered(
                source_file_id="f1",
                original_filename="archive",
                sha256="b" * 64,
                size_bytes=10,
                storage_uri="rustfs://b/k",
                object_key="k",
                bucket="b",
                state="available",
            ),
        ),
        duplicate_warning=True,
        duplicate_of_group_id="g0",
    )
    payload = resp.model_dump(mode="json")
    assert payload["duplicate_warning"] is True
    assert payload["files"][0]["sha256"] == "b" * 64


# --- helpers ---------------------------------------------------------------


def _sido_pairs() -> list[tuple[str, str]]:
    from kortravelgeo.core.source_categories import SIDO_PARTS

    return list(SIDO_PARTS)


def test_serving_layers_are_subset_of_master() -> None:
    assert set(POLYGON_LAYER_NAMES) <= set(MASTER_LAYER_NAMES)
    assert set(ELECTRONIC_MAP_SERVING_LAYERS) <= ELECTRONIC_MAP_STRUCTURE_LAYERS
