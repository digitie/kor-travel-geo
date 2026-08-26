"""T-291b: token derivation, reference-month normalizer (4 source_set shapes), history cursor.

Pure-function unit tests for :mod:`kortravelgeo.core.dataset_version` — no DB access. The
async lineage-fallback orchestration lives in ``infra/admin_repo.py`` and is covered by the
live-DB integration test instead (core must not depend on infra).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from kortravelgeo.core.dataset_version import (
    VERSION_TOKEN_RE,
    decode_history_cursor,
    derive_change_type,
    derive_version_token,
    encode_history_cursor,
    normalize_reference_months_from_source_set,
    reference_months_mixed,
)

_FIXED_UUID = "5cbc97a8-122a-47c8-8267-15c027d68f21"
_FIXED_TOKEN = "dv1-f04c0d0f3d1c6b6463f60aaec4ec78e5"


def test_derive_version_token_matches_fixed_vector() -> None:
    """Pinned against ``dv1-`` + sha256("ktg.dataset.version:" + uuid)[:32] computed
    independently — catches any accidental change to the namespace/prefix/truncation."""
    assert derive_version_token(_FIXED_UUID) == _FIXED_TOKEN
    assert VERSION_TOKEN_RE.match(_FIXED_TOKEN)


def test_derive_version_token_is_identical_for_uuid_object_and_text() -> None:
    """The repository projection passes a ``uuid.UUID`` object; a restored backup manifest
    passes its ``::text`` copy. Both must derive the same token (ADR-067 D1)."""
    as_object = UUID(_FIXED_UUID)
    assert derive_version_token(as_object) == derive_version_token(_FIXED_UUID)
    # Case/format variance in the input string must still normalize to the same canonical
    # 36-char lowercase-hyphenated form before hashing.
    assert derive_version_token(_FIXED_UUID.upper()) == derive_version_token(_FIXED_UUID)


def test_derive_version_token_differs_for_different_releases() -> None:
    other = "a414401f-3cb2-4ec7-a702-fffd14d1bf7e"
    assert derive_version_token(other) != derive_version_token(_FIXED_UUID)


@pytest.mark.parametrize(
    ("release_kind", "expected"),
    [
        ("full_load", "full"),
        ("restore", "full"),
        ("manual_rebuild", "full"),
        ("rollback", "full"),
        ("daily_delta", "delta"),
    ],
)
def test_derive_change_type(release_kind: str, expected: str) -> None:
    """Only daily_delta reads as "delta" — rollback deliberately reads as "full", not a 3rd
    "revert" value (ADR-067 D2 rejected that: it would 1:1-disclose hot-swap-rollback
    incidents, contradicting the coarsening the field exists to provide)."""
    assert derive_change_type(release_kind) == expected


def test_normalize_form_a_rebuild_category_keys_with_effective_yyyymm_fallback() -> None:
    """Form A (source_rebuild_service): top-level category codes, nested
    {source_file_group_id, group_sha256, user_yyyymm, effective_yyyymm}. roadname_hangul_full
    maps to BOTH juso and parcel_link (the 한글 전체분 archive is the source of both)."""
    source_set = {
        "roadname_hangul_full": {
            "source_file_group_id": "g1",
            "group_sha256": "abc",
            "user_yyyymm": "202607",
            "effective_yyyymm": "202608",
        },
        "locsum_full": {
            "source_file_group_id": "g2",
            "group_sha256": "def",
            "user_yyyymm": "202606",
            "effective_yyyymm": None,
        },
        "load_batch_id": "batch-1",  # denylist: injected by admin_repo, not a category
    }
    result = normalize_reference_months_from_source_set(source_set)
    assert result == {
        "juso": "202608",
        "parcel_link": "202608",
        "locsum": "202606",  # effective_yyyymm None -> user_yyyymm fallback
    }


def test_normalize_form_a_unmapped_category_is_skipped() -> None:
    """A rebuild category outside `_CATEGORY_TO_LOAD_KINDS` (e.g. a validation-only category
    never bridged into a load) must not be guessed into the external vocabulary."""
    source_set = {
        "detail_address_db_full": {
            "source_file_group_id": "g9",
            "group_sha256": "xyz",
            "user_yyyymm": "202608",
            "effective_yyyymm": "202608",
        },
    }
    assert normalize_reference_months_from_source_set(source_set) is None


def test_normalize_form_b_admin_repo_inference_writer_nested_yyyymm_by_kind() -> None:
    """Form B, writer #1 (admin_repo._infer_current_source_set — 7 kinds + `source` key):
    {yyyymm_by_kind: {...}, mixed_yyyymm, source} — reads the nested map."""
    source_set = {
        "yyyymm_by_kind": {
            "juso": "202608",
            "parcel_link": "202608",
            "locsum": "202607",
            "navi": None,
            "shp": "202607",
            "roadaddr_entrance": "202607",
            "sppn_makarea": "202607",
        },
        "mixed_yyyymm": True,
        "source": "database_manifest_inference",
    }
    result = normalize_reference_months_from_source_set(source_set)
    assert result == {
        "juso": "202608",
        "parcel_link": "202608",
        "locsum": "202607",
        "shp": "202607",
        "roadaddr_entrance": "202607",
        "sppn_makarea": "202607",
    }
    assert "navi" not in result  # None value never matches ^\d{6}$


def test_normalize_form_b_backup_infer_source_set_writer_distinct_shape() -> None:
    """Form B, writer #2 (backup.infer_source_set) — 6 kinds, NO `source` key, and no
    `sppn_makarea` at all (that table isn't part of this writer's fixed table map). A
    normalizer that only fit writer #1's shape could silently miss this writer's output."""
    source_set = {
        "yyyymm_by_kind": {
            "juso": "202608",
            "parcel_link": "202608",
            "locsum": "202607",
            "navi": "202607",
            "shp": "202607",
            "roadaddr_entrance": "202607",
        },
        "mixed_yyyymm": True,
    }
    result = normalize_reference_months_from_source_set(source_set)
    assert result == {
        "juso": "202608",
        "parcel_link": "202608",
        "locsum": "202607",
        "navi": "202607",
        "shp": "202607",
        "roadaddr_entrance": "202607",
    }
    assert "sppn_makarea" not in result


def test_normalize_form_c_hot_swap_metadata_only_normalizes_to_none() -> None:
    """Form C (hot-swap/rollback recording). The *actually persisted* source_set carries
    TWO denylisted top-level keys, not one — record_hot_swap_release passes both
    source_set={"hot_swap": {...}} AND snapshot_metadata={"hot_swap": {...}}, and
    _snapshot_source_set merges the latter in under a *second* key,
    "rebuild_metadata": {"hot_swap": {...}} (admin_repo.py _snapshot_source_set). Neither
    key carries category/kind data — must normalize to None (not an empty dict
    masquerading as "nothing mixed"), signaling the caller to fall back to snapshot
    lineage."""
    hot_swap_set = {
        "hot_swap": {"current_database": "x", "restore_database": "y", "previous_alias": "z"},
        "rebuild_metadata": {
            "hot_swap": {
                "previous_alias": "z",
                "pre_swap_release_id": "rel-1",
                "maintenance_window_id": "win-1",
            }
        },
    }
    assert normalize_reference_months_from_source_set(hot_swap_set) is None

    rollback_set = {
        "hot_swap_rollback": {"current_database": "x", "rollback_target": "y"},
        "rebuild_metadata": {"hot_swap_rollback": {"rollback_target": "y"}},
    }
    assert normalize_reference_months_from_source_set(rollback_set) is None


def test_normalize_form_d_flat_map_accepts_valid_yyyymm() -> None:
    """Form D (batch_dag._source_set / operator-submitted payload): {key: "YYYYMM"}."""
    assert normalize_reference_months_from_source_set({"juso": "202608"}) == {"juso": "202608"}


def test_normalize_form_d_rejects_degraded_repr_string() -> None:
    """batch_dag._source_set's str() flattening can turn a rich value into a Python repr
    string (T-291e's bug to fix, not this normalizer's job to guess around) — must be
    silently skipped, not accepted as a bogus "month"."""
    degraded = "{'source_file_group_id': 'g1', 'effective_yyyymm': '202608'}"
    assert normalize_reference_months_from_source_set({"juso": degraded}) is None


def test_normalize_unknown_keys_are_skipped_not_guessed() -> None:
    assert normalize_reference_months_from_source_set({"some_operator_key": "202608"}) is None


def test_normalize_empty_source_set_returns_none() -> None:
    assert normalize_reference_months_from_source_set({}) is None


@pytest.mark.parametrize(
    ("reference_months", "expected"),
    [
        (None, False),
        ({}, False),
        ({"juso": "202608"}, False),
        ({"juso": "202608", "locsum": "202608"}, False),
        ({"juso": "202608", "locsum": "202607"}, True),
    ],
)
def test_reference_months_mixed(reference_months: dict[str, str] | None, expected: bool) -> None:
    assert reference_months_mixed(reference_months) is expected


def test_history_cursor_round_trips() -> None:
    ordered_at = datetime(2026, 8, 20, 3, 12, 45, 123456, tzinfo=UTC)
    cursor = encode_history_cursor(ordered_at, _FIXED_TOKEN)
    decoded = decode_history_cursor(cursor)
    assert decoded == (ordered_at, _FIXED_TOKEN)


def test_history_cursor_never_carries_an_internal_uuid() -> None:
    """The cursor payload is `{before_at, before_token}` only — never a serving_release_id
    or dataset_snapshot_id (design doc §1.2: "커서가 내부 UUID를 담지 않기 때문")."""
    ordered_at = datetime(2026, 8, 20, 3, 12, 45, tzinfo=UTC)
    cursor = encode_history_cursor(ordered_at, _FIXED_TOKEN)
    import base64
    import json

    padded = cursor + "=" * (-len(cursor) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    assert set(payload) == {"before_at", "before_token"}
    assert payload["before_token"] == _FIXED_TOKEN


@pytest.mark.parametrize(
    "malformed",
    [
        "not-base64!!!",
        "",
        "e30=",  # base64("{}")  -- valid base64, valid JSON, missing required keys
    ],
)
def test_decode_history_cursor_rejects_malformed_input(malformed: str) -> None:
    assert decode_history_cursor(malformed) is None


def test_decode_history_cursor_rejects_a_token_with_bad_format() -> None:
    ordered_at = datetime(2026, 8, 20, tzinfo=UTC)
    cursor = encode_history_cursor(ordered_at, "not-a-real-token")
    assert decode_history_cursor(cursor) is None
