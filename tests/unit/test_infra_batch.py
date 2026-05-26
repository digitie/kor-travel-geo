from __future__ import annotations

import pytest

from kraddr.geo.exceptions import InvalidInputError
from kraddr.geo.infra.batch import BATCH_SOURCE_KINDS, batch_children


def _payloads() -> dict[str, dict[str, str]]:
    return {kind: {"path": f"/data/{kind}"} for kind in BATCH_SOURCE_KINDS}


def test_default_children_cover_all_source_kinds_in_order() -> None:
    children = batch_children({"payloads": _payloads()})
    assert tuple(kind for kind, _ in children) == BATCH_SOURCE_KINDS
    assert all(payload == {"path": f"/data/{kind}"} for kind, payload in children)


def test_payloads_mapping_is_picked_up_per_kind() -> None:
    payloads = _payloads()
    payloads["shp_polygons_load"] = {"path": "/data/shp", "mode": "full"}
    children = dict(
        batch_children(
            {
                "payloads": payloads,
            }
        )
    )
    assert children["juso_text_load"] == {"path": "/data/juso_text_load"}
    assert children["juso_parcel_link_load"] == {"path": "/data/juso_parcel_link_load"}
    assert children["shp_polygons_load"] == {"path": "/data/shp", "mode": "full"}
    assert children["locsum_load"] == {"path": "/data/locsum_load"}


def test_explicit_children_override_default_set() -> None:
    children = batch_children(
        {
            "children": [
                {"kind": "juso_text_load", "payload": {"path": "/data/juso"}},
                {"kind": "locsum_load", "payload": {"path": "/data/locsum"}},
            ]
        }
    )
    assert children == (
        ("juso_text_load", {"path": "/data/juso"}),
        ("locsum_load", {"path": "/data/locsum"}),
    )


def test_default_batch_requires_all_source_payload_paths() -> None:
    with pytest.raises(InvalidInputError, match="juso_parcel_link_load"):
        batch_children({"payloads": {"juso_text_load": {"path": "/data/juso"}}})


def test_missing_payloads_mapping_fails_before_creating_empty_children() -> None:
    with pytest.raises(InvalidInputError, match="juso_text_load"):
        batch_children({})


def test_empty_explicit_children_raise_instead_of_falling_back_to_defaults() -> None:
    with pytest.raises(InvalidInputError, match="at least one child job"):
        batch_children({"children": []})


@pytest.mark.parametrize(
    "children, message",
    [
        (["not-a-dict"], r"children\[0\] must be an object"),
        ([{"payload": {"path": "/missing-kind"}}], r"children\[0\]\.kind"),
        ([{"kind": "juso_text_load", "payload": "not-a-dict"}], r"children\[0\]\.payload"),
    ],
)
def test_invalid_child_entries_raise(
    children: list[object],
    message: str,
) -> None:
    with pytest.raises(InvalidInputError, match=message):
        batch_children({"children": children})


def test_explicit_children_require_path_for_known_loaders() -> None:
    with pytest.raises(InvalidInputError, match="shp_polygons_load"):
        batch_children({"children": [{"kind": "shp_polygons_load", "payload": {}}]})


def test_custom_roadaddr_entrance_child_requires_path() -> None:
    with pytest.raises(InvalidInputError, match="roadaddr_entrance_load"):
        batch_children({"children": [{"kind": "roadaddr_entrance_load", "payload": {}}]})


def test_source_path_is_accepted_for_child_payloads() -> None:
    children = batch_children(
        {
            "children": [
                {"kind": "juso_text_load", "payload": {"source_path": "/data/juso"}},
            ]
        }
    )
    assert children == (("juso_text_load", {"source_path": "/data/juso"}),)
