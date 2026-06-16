from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.run_geocoder_golden_corpus import (
    DEFAULT_CORPUS_PATH,
    GoldenCase,
    _check_expected_payload,
    _stable_response_hash,
    get_path,
    load_corpus,
    select_cases,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_t140_default_corpus_has_required_operation_and_category_coverage() -> None:
    cases = load_corpus(DEFAULT_CORPUS_PATH)

    operations = {case.operation for case in cases}
    categories = {case.category for case in cases}

    assert {"geocode", "reverse", "search", "zipcode", "pobox"} <= operations
    assert {
        "road-exact",
        "road-fuzzy",
        "parcel-exact",
        "reverse-nearest",
        "national-point-number",
        "negative-address",
    } <= categories
    assert len({case.case_id for case in cases}) == len(cases)


def test_t140_corpus_live_selection_excludes_optional_and_future_tags_by_default() -> None:
    cases = load_corpus(DEFAULT_CORPUS_PATH)

    selected = select_cases(cases, exclude_tags=("optional-source", "future-followup"))

    assert selected
    assert all("optional-source" not in case.tags for case in selected)
    assert all("future-followup" not in case.tags for case in selected)
    assert any(case.case_id == "T140-GEO-ROAD-EXACT-001" for case in selected)
    assert all(case.case_id != "T140-ZIP-POBOX-001" for case in selected)


def test_t140_corpus_loader_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(
        """
{
  "schema_version": 1,
  "cases": [
    {
      "case_id": "T140-DUP",
      "operation": "geocode",
      "category": "road",
      "description": "a",
      "params": {"query": "a"},
      "expected": {"status": "OK"},
      "tags": [],
      "source": "unit"
    },
    {
      "case_id": "T140-DUP",
      "operation": "geocode",
      "category": "road",
      "description": "b",
      "params": {"query": "b"},
      "expected": {"status": "OK"},
      "tags": [],
      "source": "unit"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    try:
        load_corpus(path)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("duplicate case_id should fail")


def test_t140_expected_payload_checks_paths_contains_and_numeric_budget() -> None:
    case = GoldenCase(
        case_id="T140-UNIT",
        operation="reverse",
        category="unit",
        description="unit",
        params={},
        expected={
            "status": "OK",
            "min_results": 1,
            "fields": {"candidates[0].match_kind": "road"},
            "field_contains": {"candidates[0].address.full": "왕산로"},
            "numeric_lte": {"candidates[0].distance_m": 50},
            "numeric_gte": {"candidates[0].confidence": 0.42},
            "contains_text": ["동대문구"],
        },
        tags=(),
        source="unit",
        performance_budget_ms=1000,
    )
    payload = {
        "status": "OK",
        "query_id": "unstable",
        "candidates": [
            {
                "match_kind": "road",
                "address": {"full": "서울특별시 동대문구 왕산로 189-4"},
                "distance_m": 3.2,
                "confidence": 0.88,
            }
        ],
    }

    assert _check_expected_payload(case, payload, elapsed_ms=10.0) == []
    assert get_path(payload, "candidates[0].address.full") == "서울특별시 동대문구 왕산로 189-4"

    low_confidence = {
        **payload,
        "candidates": [{**payload["candidates"][0], "confidence": 0.3}],
    }
    assert _check_expected_payload(case, low_confidence, elapsed_ms=10.0) == [
        "candidates[0].confidence expected >= 0.42, got 0.3"
    ]


def test_t140_response_hash_ignores_unstable_query_id() -> None:
    first = {
        "status": "OK",
        "query_id": "a",
        "candidates": [{"match_kind": "road", "address": {"full": "x"}}],
    }
    second = {
        "status": "OK",
        "query_id": "b",
        "candidates": [{"match_kind": "road", "address": {"full": "x"}}],
    }

    assert _stable_response_hash(first) == _stable_response_hash(second)
