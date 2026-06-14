"""T-208: backup-manifest source block + restored_from_backup + restore verify.

DB-free tests for the pure logic in ``core.source_restore`` (the highest-value
surface the ``infra/source_restore_service`` + ``infra/backup`` glue consumes):

* manifest ``source_match_set`` block assembly from a synthetic active match set;
* ``restored_from_backup`` stub plan: groups/files ``missing``/``unknown``, the
  manifest ``group_sha256`` preserved as UNTRUSTED metadata (not the group's own
  hash column), ``omitted_optional`` restored as ``omitted=true`` items;
* the relink transition decision (present + manifest-hash ok → validating; absent
  → missing; mismatch → quarantined; size mismatch → quarantined) as pure
  functions;
* the restore-entrypoint source-verification matrix (BOTH pg_restore + rename
  hot-swap run ONE quick reconcile when an active match set exists; legacy → none).
"""

from __future__ import annotations

from kortravelgeo.core.source_restore import (
    MANIFEST_GROUP_SHA256_META_KEY,
    RESTORED_FROM_BACKUP_META_KEY,
    ManifestSourceFile,
    ManifestSourceItem,
    ManifestSourceMatchSet,
    RelinkObjectCheck,
    build_manifest_source_match_set_block,
    decide_relink_child,
    plan_restore_source_verification,
    plan_restored_from_backup,
)

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_GROUP_SHA = "c" * 64
_SET_HASH = "d" * 64


def _single_file_item(
    category: str = "roadname_hangul_full",
    *,
    group_sha256: str | None = _GROUP_SHA,
    role: str = "build_required",
) -> ManifestSourceItem:
    return ManifestSourceItem(
        category=category,
        source_file_group_id="grp-1",
        group_kind="single_file",
        group_sha256=group_sha256,
        role=role,
        user_yyyymm="202603",
        effective_yyyymm="202603",
        files=(
            ManifestSourceFile(
                source_file_id="file-1",
                filename="202603_도로명주소 한글_전체분.zip",
                sha256=_SHA_A,
                size_bytes=123,
                storage_uri="rustfs://bucket/roadname/archive",
                object_key="roadname/archive",
                bucket="bucket",
            ),
        ),
    )


def _multi_part_item() -> ManifestSourceItem:
    return ManifestSourceItem(
        category="electronic_map_full",
        source_file_group_id="grp-2",
        group_kind="multi_part",
        group_sha256=_GROUP_SHA,
        role="build_required",
        user_yyyymm="202604",
        effective_yyyymm="202604",
        files=(
            ManifestSourceFile(
                source_file_id="file-11",
                filename="11.zip",
                sha256=_SHA_A,
                size_bytes=10,
                storage_uri="rustfs://bucket/emap/11",
                part_kind="sido",
                part_key="11",
                object_key="emap/11",
                bucket="bucket",
            ),
            ManifestSourceFile(
                source_file_id="file-41",
                filename="41.zip",
                sha256=_SHA_B,
                size_bytes=20,
                storage_uri="rustfs://bucket/emap/41",
                part_kind="sido",
                part_key="41",
                object_key="emap/41",
                bucket="bucket",
            ),
        ),
    )


def _block(**overrides: object) -> ManifestSourceMatchSet:
    defaults: dict[str, object] = {
        "source_match_set_id": "ms-1",
        "name": "202603 도로명주소 + 202604 전자지도 권장 조합",
        "profile": "serving_recommended",
        "source_set_hash": _SET_HASH,
        "yyyymm_by_category": {
            "roadname_hangul_full": "202603",
            "electronic_map_full": "202604",
        },
        "items": (_single_file_item(), _multi_part_item()),
        "omitted_optional": {"national_point_grid_center": "사용자가 미보유로 생략"},
    }
    defaults.update(overrides)
    return ManifestSourceMatchSet(**defaults)  # type: ignore[arg-type]


# --- manifest source_match_set block assembly ------------------------------


def test_manifest_block_has_match_set_metadata_and_per_file_detail() -> None:
    block = build_manifest_source_match_set_block(_block())
    assert block["source_match_set_id"] == "ms-1"
    assert block["profile"] == "serving_recommended"
    assert block["source_set_hash"] == _SET_HASH
    assert block["yyyymm_by_category"]["roadname_hangul_full"] == "202603"
    assert block["omitted_optional"]["national_point_grid_center"]
    # per-category group with group_sha256 + per-file sha256/size/object_key/uri.
    emap = next(it for it in block["items"] if it["category"] == "electronic_map_full")
    assert emap["group_sha256"] == _GROUP_SHA
    assert {f["part_key"] for f in emap["files"]} == {"11", "41"}
    f11 = next(f for f in emap["files"] if f["part_key"] == "11")
    assert f11["sha256"] == _SHA_A
    assert f11["size_bytes"] == 10
    assert f11["object_key"] == "emap/11"
    assert f11["storage_uri"] == "rustfs://bucket/emap/11"


def test_manifest_block_records_archives_without_copying_them() -> None:
    # The block carries metadata + storage_uri pointers only — no archive bytes.
    block = build_manifest_source_match_set_block(_block())
    serialized = repr(block)
    assert "storage_uri" in serialized
    assert "sha256" in serialized
    assert "content" not in block["items"][0]["files"][0]


def test_manifest_block_allows_null_source_set_hash_legacy() -> None:
    block = build_manifest_source_match_set_block(_block(source_set_hash=None))
    assert block["source_set_hash"] is None


# --- restored_from_backup stub plan ----------------------------------------


def test_restored_stub_groups_and_files_are_missing_unknown() -> None:
    plan = plan_restored_from_backup(
        _block(),
        new_match_set_id="ms-new",
        group_id_for={"grp-1": "g-new-1", "grp-2": "g-new-2"},
        file_id_for={"file-1": "f-new-1", "file-11": "f-new-11", "file-41": "f-new-41"},
    )
    assert plan.state == "restored_from_backup"
    assert plan.source_set_hash == _SET_HASH
    for group in plan.groups:
        assert group.state == "missing"
        assert group.validation_state == "unknown"
        for f in group.files:
            assert f.state == "missing"
            assert f.validation_state == "unknown"


def test_restored_stub_preserves_manifest_hash_as_untrusted_metadata() -> None:
    plan = plan_restored_from_backup(
        _block(),
        new_match_set_id="ms-new",
        group_id_for={"grp-1": "g-new-1", "grp-2": "g-new-2"},
        file_id_for={},
    )
    grp = next(g for g in plan.groups if g.category == "electronic_map_full")
    meta = grp.metadata()
    # The manifest group_sha256 is kept ONLY as untrusted metadata; the plan never
    # presents it as the group's recomputed hash (the group hash column stays NULL
    # in the service — recomputed on relink).
    assert meta[MANIFEST_GROUP_SHA256_META_KEY] == _GROUP_SHA
    assert meta[RESTORED_FROM_BACKUP_META_KEY] is True
    assert grp.manifest_group_sha256 == _GROUP_SHA


def test_restored_stub_assigns_fresh_ids_from_maps() -> None:
    plan = plan_restored_from_backup(
        _block(),
        new_match_set_id="ms-new",
        group_id_for={"grp-1": "g-new-1", "grp-2": "g-new-2"},
        file_id_for={"file-1": "f-new-1", "file-11": "f-new-11", "file-41": "f-new-41"},
    )
    gids = {g.source_file_group_id for g in plan.groups}
    assert gids == {"g-new-1", "g-new-2"}
    fids = {f.source_file_id for g in plan.groups for f in g.files}
    assert fids == {"f-new-1", "f-new-11", "f-new-41"}


def test_restored_stub_restores_omitted_optional_as_omitted_items() -> None:
    plan = plan_restored_from_backup(
        _block(),
        new_match_set_id="ms-new",
        group_id_for={"grp-1": "g1", "grp-2": "g2"},
        file_id_for={},
    )
    omitted = [i for i in plan.items if i.omitted]
    assert len(omitted) == 1
    assert omitted[0].category == "national_point_grid_center"
    assert omitted[0].source_file_group_id is None
    assert omitted[0].omitted_reason == "사용자가 미보유로 생략"
    # present items reference their stub group and are not omitted.
    present = [i for i in plan.items if not i.omitted]
    assert {i.category for i in present} == {"roadname_hangul_full", "electronic_map_full"}
    assert all(i.source_file_group_id is not None for i in present)


def test_restored_stub_expected_part_keys_track_files() -> None:
    plan = plan_restored_from_backup(
        _block(),
        new_match_set_id="ms-new",
        group_id_for={"grp-1": "g1", "grp-2": "g2"},
        file_id_for={},
    )
    emap = next(g for g in plan.groups if g.category == "electronic_map_full")
    assert set(emap.expected_part_keys) == {"11", "41"}
    single = next(g for g in plan.groups if g.category == "roadname_hangul_full")
    assert single.expected_part_keys == ("archive",)


def test_restored_stub_allows_legacy_null_hash() -> None:
    plan = plan_restored_from_backup(
        _block(source_set_hash=None),
        new_match_set_id="ms-new",
        group_id_for={"grp-1": "g1", "grp-2": "g2"},
        file_id_for={},
    )
    assert plan.source_set_hash is None


# --- relink transition decision --------------------------------------------


def test_relink_present_and_consistent_goes_validating() -> None:
    decision = decide_relink_child(
        manifest_sha256=_SHA_A,
        manifest_size=123,
        check=RelinkObjectCheck(
            object_present=True, observed_sha256=_SHA_A, observed_size=123
        ),
    )
    assert decision.new_state == "validating"
    assert decision.validation_state == "running"
    assert decision.observed_sha256 == _SHA_A


def test_relink_absent_goes_missing() -> None:
    decision = decide_relink_child(
        manifest_sha256=_SHA_A,
        manifest_size=123,
        check=RelinkObjectCheck(object_present=False),
    )
    assert decision.new_state == "missing"


def test_relink_hash_mismatch_goes_quarantined() -> None:
    decision = decide_relink_child(
        manifest_sha256=_SHA_A,
        manifest_size=123,
        check=RelinkObjectCheck(
            object_present=True, observed_sha256=_SHA_B, observed_size=123
        ),
    )
    assert decision.new_state == "quarantined"
    assert decision.validation_state == "failed"


def test_relink_size_mismatch_goes_quarantined() -> None:
    decision = decide_relink_child(
        manifest_sha256=_SHA_A,
        manifest_size=123,
        check=RelinkObjectCheck(
            object_present=True, observed_sha256=_SHA_A, observed_size=999
        ),
    )
    assert decision.new_state == "quarantined"


def test_relink_present_not_rehashed_still_validating() -> None:
    # Manifest hash is the trust boundary; with no rehash we cannot prove a
    # mismatch, so we send it to validating (the validator runs downstream).
    decision = decide_relink_child(
        manifest_sha256=_SHA_A,
        manifest_size=123,
        check=RelinkObjectCheck(object_present=True),
    )
    assert decision.new_state == "validating"


# --- restore-entrypoint source verification matrix -------------------------


def test_pg_restore_with_active_match_set_runs_quick_reconcile() -> None:
    plan = plan_restore_source_verification(
        entrypoint="pg_restore", active_source_match_set_id="ms-1"
    )
    assert plan.run_quick_reconcile is True
    assert plan.reconcile_mode == "quick"
    assert plan.has_active_match_set is True
    assert plan.legacy_estimate_only is False


def test_rename_hot_swap_with_active_match_set_runs_quick_reconcile() -> None:
    plan = plan_restore_source_verification(
        entrypoint="rename_hot_swap", active_source_match_set_id="ms-1"
    )
    assert plan.run_quick_reconcile is True
    assert plan.reconcile_mode == "quick"


def test_both_entrypoints_run_one_reconcile_when_active_present() -> None:
    for entrypoint in ("pg_restore", "rename_hot_swap"):
        plan = plan_restore_source_verification(
            entrypoint=entrypoint,  # type: ignore[arg-type]
            active_source_match_set_id="ms-1",
        )
        assert plan.run_quick_reconcile is True
        assert plan.entrypoint == entrypoint


def test_legacy_snapshot_skips_reconcile_estimate_only() -> None:
    for entrypoint in ("pg_restore", "rename_hot_swap"):
        plan = plan_restore_source_verification(
            entrypoint=entrypoint,  # type: ignore[arg-type]
            active_source_match_set_id=None,
        )
        assert plan.run_quick_reconcile is False
        assert plan.legacy_estimate_only is True
        assert plan.has_active_match_set is False


# --- manifest parse round-trip (the client reconstruct path, DB-free) ------


def test_manifest_block_round_trips_through_parse() -> None:
    # The pure assembly + the infra parser are inverses (within tolerance): a
    # manifest written at backup time reconstructs an equivalent block at restore.
    from kortravelgeo.infra.source_restore_service import (
        parse_manifest_source_match_set,
    )

    original = _block()
    as_json = build_manifest_source_match_set_block(original)
    parsed = parse_manifest_source_match_set(as_json)
    assert parsed.source_match_set_id == original.source_match_set_id
    assert parsed.profile == original.profile
    assert parsed.source_set_hash == original.source_set_hash
    assert parsed.omitted_optional == original.omitted_optional
    assert {it.category for it in parsed.items} == {
        it.category for it in original.items
    }
    emap = next(it for it in parsed.items if it.category == "electronic_map_full")
    assert {f.part_key for f in emap.files} == {"11", "41"}
    assert emap.group_sha256 == _GROUP_SHA


def test_manifest_parse_tolerates_legacy_missing_hash() -> None:
    from kortravelgeo.infra.source_restore_service import (
        parse_manifest_source_match_set,
    )

    parsed = parse_manifest_source_match_set(
        {
            "source_match_set_id": "ms-legacy",
            "name": "legacy",
            "profile": "custom",
            "items": [
                {
                    "category": "locsum_full",
                    "source_file_group_id": "g",
                    "group_kind": "single_file",
                    "role": "build_required",
                    "files": [
                        {"filename": "a.zip", "sha256": _SHA_A, "size_bytes": 1,
                         "storage_uri": "rustfs://b/a"}
                    ],
                }
            ],
        }
    )
    assert parsed.source_set_hash is None
    assert parsed.items[0].group_sha256 is None
    assert parsed.items[0].files[0].part_key == "archive"


# --- DTO shapes (T-208 response models) ------------------------------------


def test_restored_from_backup_response_dto_shape() -> None:
    from kortravelgeo.dto.source import RestoredFromBackupCreateResponse

    resp = RestoredFromBackupCreateResponse(
        source_match_set_id="ms-new",
        state="restored_from_backup",
        profile="serving_recommended",
        source_set_hash=_SET_HASH,
        created_group_ids=("g1", "g2"),
        created_file_count=3,
        omitted_categories=("national_point_grid_center",),
        rebuild_enabled=False,
    )
    assert resp.state == "restored_from_backup"
    assert resp.rebuild_enabled is False
    assert resp.created_file_count == 3


def test_restore_source_verification_result_dto_shape() -> None:
    from kortravelgeo.dto.source import RestoreSourceVerificationResult

    resp = RestoreSourceVerificationResult(
        entrypoint="rename_hot_swap",
        run_quick_reconcile=True,
        active_source_match_set_id="ms-1",
        reconcile_run_id="run-1",
        mismatch_count=2,
        reconstruct_unavailable=True,
        message="원천 archive 결손",
    )
    assert resp.entrypoint == "rename_hot_swap"
    assert resp.reconstruct_unavailable is True
