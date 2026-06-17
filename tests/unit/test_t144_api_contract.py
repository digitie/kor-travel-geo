from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from kortravelgeo.api.routers import v2
from kortravelgeo.dto.v2 import (
    AddressV2,
    CandidateV2,
    GeocodeV2Input,
    GeocodeV2Response,
    PointV2,
    SearchV2Input,
)


def test_t144_v2_default_geocode_contract_omits_geometry_payload() -> None:
    response = GeocodeV2Response(
        status="OK",
        input=GeocodeV2Input(query="서울특별시 동대문구 왕산로 189-4"),
        candidates=(
            CandidateV2(
                confidence=1.0,
                match_kind="road",
                address=AddressV2(
                    type="road",
                    full="서울특별시 동대문구 왕산로 189-4",
                    road_name="왕산로",
                ),
                point=PointV2(lon=127.044, lat=37.58),
                source="local",
            ),
        ),
    )

    payload = response.model_dump(mode="json", exclude_none=True)

    assert payload["input"]["include_geometry"] is False
    assert "geometry" not in payload["candidates"][0]
    assert "bbox" not in payload["candidates"][0]


def test_t144_v2_candidate_limits_are_hard_capped_at_100() -> None:
    with pytest.raises(ValidationError):
        GeocodeV2Input(query="왕산로", limit=101)

    with pytest.raises(ValidationError):
        SearchV2Input(query="왕산로", size=101)

    assert GeocodeV2Input(query="왕산로", limit=100).limit == 100
    assert SearchV2Input(query="왕산로", size=100).size == 100


def test_t144_v2_routes_keep_none_exclusion_for_payload_slimming() -> None:
    source = inspect.getsource(v2)

    assert "response_model_exclude_none=True" in source
    assert '"/geocode"' in source
    assert '"/reverse"' in source
    assert '"/search"' in source


def test_t144_api_contract_evaluator_flags_latency_and_payload_regression() -> None:
    import scripts.evaluate_t144_api_contract as evaluator

    payload = {
        "summaries": [
            {
                "group": "Q1_ROAD_EXACT",
                "sql_name": "geocode_road",
                "concurrency": 64,
                "samples": 20,
                "errors": 0,
                "p99_ms": 650.0,
                "avg_response_bytes": 70_000.0,
            }
        ]
    }

    report = evaluator.evaluate_api_contract_report(
        payload=payload,
        benchmark_report="api-report.json",
        p99_budget_ms=500.0,
        avg_response_budget_bytes=64 * 1024,
    )

    assert report.passed is False
    assert report.summary_checks[0].reason == (
        "p99_budget_exceeded,avg_response_budget_exceeded"
    )
