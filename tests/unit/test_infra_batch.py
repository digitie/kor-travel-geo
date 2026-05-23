from __future__ import annotations

from kraddr.geo.infra.batch import BATCH_SOURCE_KINDS, batch_children


def test_default_children_cover_all_source_kinds_in_order() -> None:
    children = batch_children({})
    assert tuple(kind for kind, _ in children) == BATCH_SOURCE_KINDS
    assert all(payload == {} for _, payload in children)


def test_payloads_mapping_is_picked_up_per_kind() -> None:
    children = dict(
        batch_children(
            {
                "payloads": {
                    "juso_text_load": {"path": "/data/juso"},
                    "shp_polygons_load": {"path": "/data/shp", "mode": "full"},
                }
            }
        )
    )
    assert children["juso_text_load"] == {"path": "/data/juso"}
    assert children["shp_polygons_load"] == {"path": "/data/shp", "mode": "full"}
    assert children["locsum_load"] == {}


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


def test_invalid_child_entries_are_dropped() -> None:
    children = batch_children(
        {
            "children": [
                {"kind": "juso_text_load", "payload": {"path": "/data/juso"}},
                "not-a-dict",
                {"payload": {"path": "/missing-kind"}},
                {"kind": "shp_polygons_load"},
            ]
        }
    )
    assert children == (
        ("juso_text_load", {"path": "/data/juso"}),
        ("shp_polygons_load", {}),
    )
