"""2026년 7월 시도 통합 전후 원천의 업로드·검증 회귀."""

from __future__ import annotations

import pytest

from kortravelgeo.core.source_validation import (
    GroupManifest,
    ManifestMember,
    PartManifest,
    validate_group_coverage,
    validate_group_manifest,
)
from kortravelgeo.infra.source_upload_repo import slot_definitions

LEGACY_KEYS = (
    "11",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "36",
    "41",
    "43",
    "44",
    "46",
    "47",
    "48",
    "50",
    "51",
    "52",
)
MERGED_KEYS = (
    "11",
    "12",
    "26",
    "27",
    "28",
    "30",
    "31",
    "36",
    "41",
    "43",
    "44",
    "47",
    "48",
    "50",
    "51",
    "52",
)


@pytest.mark.parametrize(
    "month,keys", [("202606", LEGACY_KEYS), ("202607", MERGED_KEYS), ("202610", MERGED_KEYS)]
)
def test_upload_slots_follow_source_month(month: str, keys: tuple[str, ...]) -> None:
    slots = slot_definitions("electronic_map_full", user_yyyymm=month)
    assert tuple(slot.part_key for slot in slots) == keys
    if "12" in keys:
        assert (
            next(slot for slot in slots if slot.part_key == "12").part_label == "전남광주통합특별시"
        )


@pytest.mark.parametrize(
    "month,keys", [("202606", LEGACY_KEYS), ("202607", MERGED_KEYS), ("202610", MERGED_KEYS)]
)
def test_complete_sido_coverage_passes(month: str, keys: tuple[str, ...]) -> None:
    result = validate_group_coverage(
        category="electronic_map_full",
        group_kind="multi_part",
        present_part_keys=keys,
        user_yyyymm=month,
    )
    assert result.outcome == "passed"
    assert set(result.coverage) == set(keys)


@pytest.mark.parametrize(
    "keys", [LEGACY_KEYS, tuple(k for k in MERGED_KEYS if k != "12"), (*MERGED_KEYS, "29")]
)
def test_new_month_rejects_missing_or_mixed_sidos(keys: tuple[str, ...]) -> None:
    result = validate_group_coverage(
        category="electronic_map_full",
        group_kind="multi_part",
        present_part_keys=keys,
        user_yyyymm="202609",
    )
    assert result.outcome == "failed"


@pytest.mark.parametrize(
    "category,prefixes",
    [
        ("locsum_full", ("entrc_",)),
        ("roadname_hangul_full", ("rnaddrkor_", "jibun_rnaddrkor_")),
        ("navi_full", ("match_build_", "match_jibun_")),
    ],
)
@pytest.mark.parametrize(
    "month,count,expected",
    [
        ("202606", 17, "passed"),
        ("202609", 16, "passed"),
        ("202609", 15, "failed"),
        ("202606", 16, "failed"),
    ],
)
def test_text_member_count_follows_source_month(
    category: str,
    prefixes: tuple[str, ...],
    month: str,
    count: int,
    expected: str,
) -> None:
    members = tuple(
        ManifestMember(member_path=f"{prefix}{i}.txt") for prefix in prefixes for i in range(count)
    )
    if category == "navi_full":
        members += (ManifestMember(member_path="match_rs_entrc.txt"),)
    result = validate_group_manifest(
        GroupManifest(
            category=category,
            group_kind="single_file",
            user_yyyymm=month,
            parts=(PartManifest(part_key="archive", members=members),),
        )
    )
    assert result.outcome == expected
