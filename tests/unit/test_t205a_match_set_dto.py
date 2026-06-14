"""T-205a match set DTO + profile-required-category smoke tests (DB-free).

Validates the OpenAPI-facing match-set DTO shapes (create request, item, detail,
validate/activate/retire responses) and the profile→required-category map the
validate coverage check uses, without touching a DB.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kortravelgeo.dto.source import (
    SourceMatchSet,
    SourceMatchSetActivateResponse,
    SourceMatchSetCreateRequest,
    SourceMatchSetDetail,
    SourceMatchSetItem,
    SourceMatchSetItemRequest,
    SourceMatchSetRetireResponse,
    SourceMatchSetValidateResponse,
)
from kortravelgeo.infra.source_match_set_service import _PROFILE_REQUIRED_CATEGORIES


def test_create_request_defaults_profile_recommended() -> None:
    req = SourceMatchSetCreateRequest(name="2026-04 recommended")
    assert req.profile == "serving_recommended"
    assert req.items == ()


def test_create_request_rejects_unknown_profile() -> None:
    with pytest.raises(ValidationError):
        SourceMatchSetCreateRequest(name="x", profile="turbo")  # type: ignore[arg-type]


def test_item_request_yyyymm_pattern() -> None:
    ok = SourceMatchSetItemRequest(
        category="locsum_full", role="build_required",
        source_file_group_id="g1", effective_yyyymm="202604",
    )
    assert ok.effective_yyyymm == "202604"
    with pytest.raises(ValidationError):
        SourceMatchSetItemRequest(
            category="locsum_full", role="build_required", effective_yyyymm="26-04"
        )


def test_item_request_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        SourceMatchSetItemRequest(category="locsum_full", role="nope")  # type: ignore[arg-type]


def test_validate_response_shape() -> None:
    resp = SourceMatchSetValidateResponse(
        source_match_set_id="ms1",
        action="validate_in_place",
        ok=True,
        state="active",
        source_set_hash="a" * 64,
        integrity_alert=False,
        reasons=(),
    )
    payload = resp.model_dump(mode="json")
    assert payload["action"] == "validate_in_place"
    assert payload["state"] == "active"


def test_activate_response_requires_64_char_hash() -> None:
    with pytest.raises(ValidationError):
        SourceMatchSetActivateResponse(
            source_match_set_id="ms1", state="active", source_set_hash="short"
        )
    ok = SourceMatchSetActivateResponse(
        source_match_set_id="ms1", state="active",
        retired_match_set_id="old", source_set_hash="b" * 64,
    )
    assert ok.retired_match_set_id == "old"


def test_retire_response_shape() -> None:
    resp = SourceMatchSetRetireResponse(
        source_match_set_id="ms1", state="retired", was_active=True
    )
    assert resp.was_active is True


def test_detail_wraps_match_set_and_items() -> None:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    ms = SourceMatchSet(
        source_match_set_id="ms1", name="x", profile="serving_minimal",
        state="draft", created_at=now, updated_at=now,
    )
    item = SourceMatchSetItem(
        source_match_set_item_id="i1", source_match_set_id="ms1",
        category="locsum_full", role="build_required", source_file_group_id="g1",
    )
    detail = SourceMatchSetDetail(match_set=ms, items=(item,))
    assert detail.match_set.state == "draft"
    assert detail.items[0].category == "locsum_full"


def test_profile_required_categories_match_doc() -> None:
    assert _PROFILE_REQUIRED_CATEGORIES["serving_minimal"] == frozenset(
        {"roadname_hangul_full", "locsum_full", "navi_full", "electronic_map_full"}
    )
    assert _PROFILE_REQUIRED_CATEGORIES["serving_recommended"] == frozenset(
        {
            "roadname_hangul_full", "locsum_full", "navi_full",
            "electronic_map_full", "roadaddr_entrance_full", "zone_shape_full",
        }
    )
    assert _PROFILE_REQUIRED_CATEGORIES["custom"] == frozenset()
