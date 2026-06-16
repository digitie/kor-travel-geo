from __future__ import annotations

import pytest

from kortravelgeo.core.confidence import (
    CENTROID_CONFIDENCE_CAP,
    JUSO_FALLBACK_CONFIDENCE,
    LOCAL_EXACT_CONFIDENCE,
    SPPN_GRID_CONFIDENCE,
    VWORLD_FALLBACK_CONFIDENCE,
    clamp_confidence,
    external_geocode_confidence,
    geocode_lookup_confidence,
    geometry_confidence,
    reverse_distance_confidence,
    search_confidence,
    sppn_geocode_confidence,
    sppn_reverse_confidence,
)


def test_confidence_model_clamps_non_finite_and_out_of_range_scores() -> None:
    assert clamp_confidence(1.5) == pytest.approx(1.0)
    assert clamp_confidence(-0.1) == pytest.approx(0.0)
    assert clamp_confidence(float("nan"), default=0.42) == pytest.approx(0.42)
    assert search_confidence(None) == pytest.approx(0.0)
    assert geometry_confidence(None) == pytest.approx(0.90)


def test_geocode_confidence_caps_centroid_but_preserves_lower_scores() -> None:
    assert geocode_lookup_confidence(1.0, pt_source="entrance") == pytest.approx(1.0)
    assert geocode_lookup_confidence(1.0, pt_source="centroid") == pytest.approx(
        CENTROID_CONFIDENCE_CAP
    )
    assert geocode_lookup_confidence(0.51, pt_source="centroid") == pytest.approx(0.51)


def test_reverse_distance_confidence_is_monotonic_by_distance() -> None:
    near = reverse_distance_confidence(10, 200)
    mid = reverse_distance_confidence(100, 200)
    edge = reverse_distance_confidence(200, 200)
    outside = reverse_distance_confidence(300, 200)

    assert LOCAL_EXACT_CONFIDENCE > near > mid > edge
    assert edge == pytest.approx(0.0)
    assert outside == pytest.approx(0.0)
    assert reverse_distance_confidence(None, 200) == pytest.approx(LOCAL_EXACT_CONFIDENCE)


def test_match_family_confidence_baselines_are_ordered() -> None:
    assert LOCAL_EXACT_CONFIDENCE > CENTROID_CONFIDENCE_CAP
    assert CENTROID_CONFIDENCE_CAP > SPPN_GRID_CONFIDENCE
    assert sppn_geocode_confidence() == pytest.approx(SPPN_GRID_CONFIDENCE)
    assert sppn_reverse_confidence() == pytest.approx(SPPN_GRID_CONFIDENCE)
    assert SPPN_GRID_CONFIDENCE > VWORLD_FALLBACK_CONFIDENCE > JUSO_FALLBACK_CONFIDENCE
    assert external_geocode_confidence("api_vworld") == pytest.approx(VWORLD_FALLBACK_CONFIDENCE)
    assert external_geocode_confidence("api_juso") == pytest.approx(JUSO_FALLBACK_CONFIDENCE)
