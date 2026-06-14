from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest

from kortravelgeo.loaders.augment_harness import (
    DistanceMeasurement,
    KeyOverlapMeasurement,
)
from kortravelgeo.loaders.building_shape_bundle import ENTRANCE_KEY_FIELDS
from kortravelgeo.loaders.c11_entrance_sources import (
    FULL_ENTRANCE_JOIN_KEYS,
    WEAK_SIG_ENT_JOIN_KEYS,
    C11EntranceComparison,
    C11PairComparison,
    build_c11_entrance_report,
    discover_c11_entrance_source_groups,
    entrance_staging_spec,
)
from kortravelgeo.loaders.shape_dbf import KeyOverlap, KeySetStats

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def test_c11_entrance_staging_spec_reuses_bundle_entrance_key_fields() -> None:
    spec = entrance_staging_spec("_ktg_c11_test")

    assert spec.table_name == "_ktg_c11_test"
    assert spec.geometry_type == "Point"
    assert tuple(column.source_field for column in spec.columns) == ENTRANCE_KEY_FIELDS
    assert tuple(column.name for column in spec.columns) == (
        "sig_cd",
        "bul_man_no",
        "ent_man_no",
        "eqb_man_sn",
    )
    assert tuple(column.sql_type for column in spec.columns) == (
        "text",
        "bigint",
        "bigint",
        "bigint",
    )
    assert tuple((key.left, key.right) for key in FULL_ENTRANCE_JOIN_KEYS) == (
        ("sig_cd", "sig_cd"),
        ("bul_man_no", "bul_man_no"),
        ("ent_man_no", "ent_man_no"),
        ("eqb_man_sn", "eqb_man_sn"),
    )
    assert tuple((key.left, key.right) for key in WEAK_SIG_ENT_JOIN_KEYS) == (
        ("sig_cd", "sig_cd"),
        ("ent_man_no", "ent_man_no"),
    )


def test_c11_entrance_metrics_keep_full_and_weak_key_contracts() -> None:
    comparison = C11EntranceComparison(
        sido_name="세종특별자치시",
        bundle_zip="bundle.zip",
        electronic_map_dir="electronic/세종특별자치시",
        source_yyyymm="202605",
        bundle_rows=3,
        electronic_rows=2,
        dbf_exact_key_overlap=KeyOverlap(
            left=KeySetStats(row_count=3, distinct_count=3, duplicate_count=0),
            right=KeySetStats(row_count=2, distinct_count=2, duplicate_count=0),
            intersection_count=2,
            left_only_count=1,
            right_only_count=0,
        ),
        pairs=(
            C11PairComparison(
                name="bundle_to_electronic_full_key",
                left_source="bundle",
                right_source="electronic",
                key_contract="full_sig_bul_ent_eqb_key",
                join_keys=FULL_ENTRANCE_JOIN_KEYS,
                overlap=KeyOverlapMeasurement(
                    left_rows=3,
                    right_rows=2,
                    left_distinct=3,
                    right_distinct=2,
                    intersection_count=2,
                    left_only_count=1,
                    right_only_count=0,
                ),
                distance=DistanceMeasurement(
                    samples=2,
                    p50_m=0.0,
                    p95_m=1.5,
                    max_m=2.0,
                    sample=({"left_sig_cd": "36110", "distance_m": 2.0},),
                ),
            ),
            C11PairComparison(
                name="bundle_to_locsum_weak_sig_ent_key",
                left_source="bundle",
                right_source="tl_locsum_entrc",
                key_contract="weak_sig_ent_key",
                join_keys=WEAK_SIG_ENT_JOIN_KEYS,
                overlap=KeyOverlapMeasurement(
                    left_rows=3,
                    right_rows=4,
                    left_distinct=3,
                    right_distinct=3,
                    intersection_count=1,
                    left_only_count=2,
                    right_only_count=2,
                ),
                distance=DistanceMeasurement(
                    samples=1,
                    p50_m=5.0,
                    p95_m=5.0,
                    max_m=5.0,
                    sample=(),
                ),
                note="weak key",
            ),
        ),
    )

    metrics = comparison.metrics()
    pair_metrics = metrics["comparisons"]

    assert metrics["serving_promotion"] is False
    assert metrics["staging_rows"] == {
        "bundle_tl_spbd_entrc": 3,
        "electronic_tl_spbd_entrc": 2,
    }
    assert metrics["dbf_exact_key_overlap"] == {
        "left_rows": 3,
        "right_rows": 2,
        "left_distinct": 3,
        "right_distinct": 2,
        "left_duplicate_count": 0,
        "right_duplicate_count": 0,
        "intersection_count": 2,
        "left_only_count": 1,
        "right_only_count": 0,
    }
    assert isinstance(pair_metrics, dict)
    assert pair_metrics["bundle_to_electronic_full_key"]["key_contract"] == (
        "full_sig_bul_ent_eqb_key"
    )
    assert pair_metrics["bundle_to_locsum_weak_sig_ent_key"]["key_contract"] == (
        "weak_sig_ent_key"
    )
    assert comparison.sample()[0]["comparison"] == "bundle_to_electronic_full_key"
    assert comparison.to_payload().source_yyyymm == "202605"


def test_discover_c11_entrance_source_groups_tracks_required_inputs(tmp_path) -> None:
    bundle_root = tmp_path / "도로명주소 건물 도형"
    electronic_root = tmp_path / "도로명주소 전자지도"
    bundle_root.mkdir()
    (bundle_root / "건물도형_전체분_세종특별자치시.zip").write_text("", encoding="utf-8")
    (electronic_root / "세종특별자치시").mkdir(parents=True)

    groups = discover_c11_entrance_source_groups(
        bundle_root=bundle_root,
        electronic_map_root=electronic_root,
        sido_names=("세종특별자치시", "서울특별시"),
    )

    assert groups[0].path("bundle") == bundle_root / "건물도형_전체분_세종특별자치시.zip"
    assert groups[0].path("electronic") == electronic_root / "세종특별자치시"
    assert groups[0].missing_keys == ()
    assert groups[1].missing_keys == ("bundle", "electronic")


@pytest.mark.asyncio
async def test_build_c11_entrance_report_marks_missing_groups_skipped() -> None:
    groups = discover_c11_entrance_source_groups(
        bundle_root="missing-bundle",
        electronic_map_root="missing-electronic",
        sido_names=("세종특별자치시",),
    )

    report = await build_c11_entrance_report(
        cast("AsyncEngine", object()),
        groups,
        source_yyyymm="202605",
        generated_at=datetime(2026, 6, 14, tzinfo=UTC),
    )

    assert report.task_id == "T-111"
    assert report.skipped_count == 1
    assert report.groups[0].error == "missing required source(s): bundle, electronic"
