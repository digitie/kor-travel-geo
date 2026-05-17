from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "backend"))

from kraddr_geo_api import database  # noqa: E402
from kraddr_geo_api.main import app  # noqa: E402


@pytest.fixture()
def seeded_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KRADDR_GEO_SPATIALITE_PATH", str(tmp_path / "api.sqlite"))
    database.store.cache_clear()
    current = database.store()
    now = datetime.now(UTC)
    with current.engine.begin() as connection:
        connection.execute(
            current.point_table.insert(),
            [
                {
                    "point_id": "point-donghae",
                    "source": "fixture",
                    "source_dataset": "location_summary",
                    "source_key": "summary:1",
                    "source_priority": 10,
                    "coordinate_role": "summary_entrance",
                    "building_management_number": "5117010100100010000",
                    "legal_dong_code": "5117010100",
                    "sido_name": "강원특별자치도",
                    "sigungu_name": "동해시",
                    "eup_myeon_dong_name": "천곡동",
                    "road_name_code": "511703221001",
                    "road_name": "동해대로",
                    "underground_yn": "0",
                    "building_main_no": "4491",
                    "building_sub_no": "0",
                    "postal_code": "25769",
                    "road_address": "강원특별자치도 동해시 동해대로 4491",
                    "parcel_address": "",
                    "building_name": "fixture",
                    "building_use": "",
                    "x": 1131000.0,
                    "y": 1902000.0,
                    "srid": 5179,
                    "geom_wkt": "POINT (1131000 1902000)",
                    "geom_wkb": b"0",
                    "loaded_at": now,
                    "raw_json": {},
                },
                {
                    "point_id": "point-donghae-road-only",
                    "source": "fixture",
                    "source_dataset": "navigation_building",
                    "source_key": "navigation:1",
                    "source_priority": 20,
                    "coordinate_role": "building_center",
                    "building_management_number": "5117010200100010000",
                    "legal_dong_code": "5117010200",
                    "sido_name": "",
                    "sigungu_name": "",
                    "eup_myeon_dong_name": "",
                    "road_name_code": "511703221002",
                    "road_name": "",
                    "underground_yn": "0",
                    "building_main_no": "1",
                    "building_sub_no": "0",
                    "postal_code": "25700",
                    "road_address": "강원특별자치도 동해시 묵호진동 1",
                    "parcel_address": "",
                    "building_name": "",
                    "building_use": "",
                    "x": 1131100.0,
                    "y": 1902100.0,
                    "srid": 5179,
                    "geom_wkt": "POINT (1131100 1902100)",
                    "geom_wkb": b"0",
                    "loaded_at": now,
                    "raw_json": {},
                }
            ],
        )
        connection.execute(
            current.boundary_table.insert(),
            [
                {
                    "source_system": "fixture",
                    "source_file": "TL_SCCO_SIG.shp",
                    "source_layer": "tl_scco_sig",
                    "source_code": "51000:51170:1",
                    "source_name": "동해시",
                    "legal_dong_code": None,
                    "boundary_level": "sigungu",
                    "mapping_status": "loaded",
                    "srid": 5179,
                    "geom_wkt": (
                        "POLYGON (("
                        "1130000 1901000, "
                        "1132000 1901000, "
                        "1132000 1903000, "
                        "1130000 1903000, "
                        "1130000 1901000"
                        "))"
                    ),
                    "geom_wkb": b"0",
                    "loaded_at": now,
                    "raw_json": {},
                }
            ],
        )
        connection.execute(
            current.metadata_table.insert(),
            [
                {
                    "key": "address_search_index_ready",
                    "value": "fts5_trigram",
                    "updated_at": now,
                }
            ],
        )
    yield
    database.store.cache_clear()


def test_jibun_scope_finds_region_names_when_parcel_address_is_empty(seeded_backend) -> None:
    del seeded_backend
    client = TestClient(app)

    response = client.get("/addresses", params={"query": "동해시", "scope": "jibun"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["roadAddress"] == "강원특별자치도 동해시 동해대로 4491"


def test_jibun_scope_uses_road_address_region_text_when_jibun_is_missing(
    seeded_backend,
) -> None:
    del seeded_backend
    client = TestClient(app)

    response = client.get("/addresses", params={"query": "묵호진동", "scope": "jibun"})

    assert response.status_code == 200
    item_ids = {item["id"] for item in response.json()["items"]}
    assert "point-donghae-road-only" in item_ids


def test_address_response_includes_best_available_boundary(seeded_backend) -> None:
    del seeded_backend
    client = TestClient(app)

    response = client.get("/addresses", params={"query": "동해시", "page_size": 1})

    assert response.status_code == 200
    place = response.json()["items"][0]
    assert place["boundaryName"] == "동해시"
    assert place["boundaryLevel"] == "sigungu"
    assert len(place["boundary"]) >= 4
    assert {"lat", "lng"} <= set(place["boundary"][0])
