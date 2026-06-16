"""Central confidence scoring helpers for candidate-producing paths."""

from __future__ import annotations

import math
from typing import Literal

from kortravelgeo.dto.common import ResultSource

PointSource = Literal["entrance", "centroid"]

LOCAL_EXACT_CONFIDENCE = 1.0
CENTROID_CONFIDENCE_CAP = 0.82
SPPN_GRID_CONFIDENCE = 0.72
VWORLD_FALLBACK_CONFIDENCE = 0.70
JUSO_FALLBACK_CONFIDENCE = 0.65
GEOMETRY_FALLBACK_CONFIDENCE = 0.90


def clamp_confidence(value: float | int | None, *, default: float = 0.0) -> float:
    """Clamp a score-like value into the public confidence range."""
    raw = default if value is None else float(value)
    if not math.isfinite(raw):
        raw = default
    return max(0.0, min(1.0, raw))


def geocode_lookup_confidence(
    value: float | int | None,
    *,
    pt_source: PointSource | None,
) -> float:
    confidence = clamp_confidence(value, default=LOCAL_EXACT_CONFIDENCE)
    if pt_source == "centroid":
        confidence = min(confidence, CENTROID_CONFIDENCE_CAP)
    return confidence


def sppn_geocode_confidence() -> float:
    return SPPN_GRID_CONFIDENCE


def sppn_reverse_confidence() -> float:
    return SPPN_GRID_CONFIDENCE


def external_geocode_confidence(source: ResultSource) -> float:
    if source == "api_vworld":
        return VWORLD_FALLBACK_CONFIDENCE
    if source == "api_juso":
        return JUSO_FALLBACK_CONFIDENCE
    return LOCAL_EXACT_CONFIDENCE


def reverse_distance_confidence(distance_m: float | int | None, radius_m: float | int) -> float:
    if distance_m is None:
        return LOCAL_EXACT_CONFIDENCE
    radius = float(radius_m)
    if radius <= 0:
        return 0.0
    return clamp_confidence(1.0 - (float(distance_m) / radius))


def search_confidence(score: float | int | None) -> float:
    return clamp_confidence(score)


def geometry_confidence(score: float | int | None) -> float:
    return clamp_confidence(score, default=GEOMETRY_FALLBACK_CONFIDENCE)
